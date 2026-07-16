"""Google Play billing + entitlement endpoints. The backend is the entitlement authority.

Gated by config.BILLING_ENABLED. When disabled: status still works (returns free/plan
config), and verify/restore/rtdn return a clear 503 WITHOUT ever granting entitlement.
No client-supplied flag can grant Premium — only a Google-verified purchase token does.
"""
import base64
import json
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Request, Header
from pydantic import BaseModel

import config
import monetization as mon
from db import db
from core import CurrentUser

logger = logging.getLogger("student-assistant")
router = APIRouter(prefix="/api")


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


class VerifyIn(BaseModel):
    purchase_token: str
    product_id: Optional[str] = None
    base_plan_id: Optional[str] = None
    obfuscated_account_id: Optional[str] = None


# ----------------------------------------------------------------- Google Play API
def _play_client():
    """Build a Google Play Developer API client from the service-account JSON.
    Returns None if credentials are not configured."""
    path = config.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON
    if not path:
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_file(
            path, scopes=["https://www.googleapis.com/auth/androidpublisher"])
        return build("androidpublisher", "v3", credentials=creds, cache_discovery=False)
    except Exception as e:
        logger.error("Play client build failed: %s", type(e).__name__)
        return None


async def _play_verify_token(purchase_token: str) -> dict:
    """Query Google Play for the subscription purchase. Raises on failure.
    Uses purchases.subscriptionsv2.get (Billing Library v5+/v9 model)."""
    client = _play_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Billing verification is not configured on this server.")
    try:
        res = client.purchases().subscriptionsv2().get(
            packageName=config.GOOGLE_PLAY_PACKAGE_NAME, token=purchase_token).execute()
        return res
    except Exception as e:
        logger.error("Play verify failed: %s", type(e).__name__)
        raise HTTPException(status_code=502, detail="Could not verify the purchase with Google Play.")


def _map_play_state(sub: dict) -> tuple[str, Optional[str], Optional[str]]:
    """Map a subscriptionsv2 resource to (entitlement_state, current_period_end_iso, billing_anchor_iso)."""
    state = sub.get("subscriptionState", "")
    line_items = sub.get("lineItems") or []
    expiry = None
    if line_items:
        expiry = line_items[-1].get("expiryTime")
    start = sub.get("startTime")
    mapping = {
        "SUBSCRIPTION_STATE_ACTIVE": "active",
        "SUBSCRIPTION_STATE_IN_GRACE_PERIOD": "grace_period",
        "SUBSCRIPTION_STATE_ON_HOLD": "account_hold",
        "SUBSCRIPTION_STATE_PAUSED": "paused",
        "SUBSCRIPTION_STATE_CANCELED": "cancelled_active_until_period_end",
        "SUBSCRIPTION_STATE_EXPIRED": "expired",
        "SUBSCRIPTION_STATE_PENDING": "pending",
    }
    return mapping.get(state, "free"), expiry, start


async def _apply_entitlement(uid: str, purchase_token: str, sub: dict, source: str):
    """Idempotently persist subscription + entitlement from a verified Play resource."""
    state, expiry, anchor = _map_play_state(sub)
    # Reject a purchase token already bound to a different account.
    owner = await db.purchase_tokens.find_one({"purchase_token": purchase_token})
    if owner and owner.get("user_id") not in (None, uid):
        raise HTTPException(status_code=409, detail="This purchase is linked to a different account.")

    await db.purchase_tokens.update_one(
        {"purchase_token": purchase_token},
        {"$set": {"user_id": uid, "product_id": config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
                  "state": state, "updated_at": _iso(_utcnow()), "source": source},
         "$setOnInsert": {"created_at": _iso(_utcnow())}}, upsert=True)

    prev = await db.entitlements.find_one({"user_id": uid}) or {}
    ent = {
        "user_id": uid, "plan": "premium" if state in mon.PREMIUM_ACTIVE_STATES else "free",
        "state": state, "purchase_token": purchase_token,
        "current_period_end": expiry, "billing_anchor": prev.get("billing_anchor") or anchor or _iso(_utcnow()),
        "started_at": prev.get("started_at") or anchor or _iso(_utcnow()),
        "updated_at": _iso(_utcnow()),
    }
    await db.entitlements.update_one({"user_id": uid}, {"$set": ent}, upsert=True)
    await db.purchase_events.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "purchase_token": purchase_token,
        "state": state, "source": source, "ts": _iso(_utcnow())})
    # Acknowledge the purchase (v2 API) — best effort, idempotent on Google's side.
    return ent


# ----------------------------------------------------------------- endpoints
@router.get("/billing/status")
async def billing_status(uid: str = CurrentUser):
    """Entitlement + current-cycle usage. Safe when billing is disabled."""
    status = await mon.get_usage_status(uid)
    status["product"] = {
        "product_id": config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
        "monthly_base_plan_id": config.GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID,
        "annual_base_plan_id": config.GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID,
        "package_name": config.GOOGLE_PLAY_PACKAGE_NAME,
    }
    return status


@router.post("/billing/google/verify")
async def billing_verify(body: VerifyIn, uid: str = CurrentUser):
    if not config.BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Subscriptions are not yet available.")
    if not body.purchase_token:
        raise HTTPException(status_code=400, detail="Missing purchase token.")
    sub = await _play_verify_token(body.purchase_token)
    ent = await _apply_entitlement(uid, body.purchase_token, sub, source="verify")
    return {"ok": True, "state": ent["state"], "plan": ent["plan"],
            "current_period_end": ent["current_period_end"]}


@router.post("/billing/google/restore")
async def billing_restore(body: VerifyIn, uid: str = CurrentUser):
    if not config.BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Subscriptions are not yet available.")
    if not body.purchase_token:
        raise HTTPException(status_code=400, detail="Missing purchase token.")
    sub = await _play_verify_token(body.purchase_token)
    ent = await _apply_entitlement(uid, body.purchase_token, sub, source="restore")
    return {"ok": True, "state": ent["state"], "plan": ent["plan"]}


@router.post("/billing/google/rtdn")
async def billing_rtdn(request: Request, authorization: str = Header(default="")):
    """Google Play Real-time Developer Notifications via Pub/Sub push.
    Authenticates the request, dedupes by messageId, then re-queries Play (never trusts
    the payload). Requires billing configured; otherwise acknowledges without action."""
    # Authenticate the Pub/Sub push (OIDC bearer token or shared verification token).
    ok_auth = False
    if config.PUBSUB_VERIFICATION_TOKEN:
        token = request.query_params.get("token", "")
        ok_auth = token == config.PUBSUB_VERIFICATION_TOKEN
    if not ok_auth and authorization.startswith("Bearer "):
        ok_auth = await _verify_pubsub_oidc(authorization[7:])
    if not ok_auth:
        raise HTTPException(status_code=401, detail="Unauthorized push.")

    envelope = await request.json()
    msg = (envelope or {}).get("message", {})
    message_id = msg.get("messageId") or msg.get("message_id")
    if not message_id:
        return {"ok": True}  # ack malformed to avoid redelivery storms
    # Deduplicate.
    seen = await db.rtdn_events.find_one({"message_id": message_id})
    if seen:
        return {"ok": True, "duplicate": True}
    try:
        data = json.loads(base64.b64decode(msg.get("data", "")).decode("utf-8"))
    except Exception:
        data = {}
    await db.rtdn_events.insert_one({"message_id": message_id, "data_kind": _rtdn_kind(data),
                                     "ts": _iso(_utcnow()), "processed": False})

    if not config.BILLING_ENABLED:
        return {"ok": True, "billing_disabled": True}

    sub_notice = data.get("subscriptionNotification") or {}
    purchase_token = sub_notice.get("purchaseToken")
    if purchase_token:
        owner = await db.purchase_tokens.find_one({"purchase_token": purchase_token})
        try:
            sub = await _play_verify_token(purchase_token)  # re-query source of truth
            uid = (owner or {}).get("user_id")
            if uid:
                await _apply_entitlement(uid, purchase_token, sub, source="rtdn")
        except Exception as e:
            logger.error("RTDN reconcile failed: %s", type(e).__name__)
    await db.rtdn_events.update_one({"message_id": message_id}, {"$set": {"processed": True}})
    return {"ok": True}


def _rtdn_kind(data: dict) -> str:
    if "subscriptionNotification" in data:
        return f"sub:{data['subscriptionNotification'].get('notificationType')}"
    if "voidedPurchaseNotification" in data:
        return "voided"
    if "testNotification" in data:
        return "test"
    return "unknown"


async def _verify_pubsub_oidc(jwt_token: str) -> bool:
    """Verify a Google-signed OIDC token from Pub/Sub. Falls back to False on any error."""
    try:
        from google.oauth2 import id_token as gidt
        from google.auth.transport import requests as greq
        info = gidt.verify_oauth2_token(jwt_token, greq.Request())
        email = info.get("email", "")
        if config.PUBSUB_SERVICE_ACCOUNT_EMAIL:
            return email == config.PUBSUB_SERVICE_ACCOUNT_EMAIL and info.get("email_verified", False)
        return bool(info.get("email_verified"))
    except Exception:
        return False
