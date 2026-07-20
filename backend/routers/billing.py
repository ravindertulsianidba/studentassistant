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

import config
import monetization as mon
import token_crypto
from db import db
from core import CurrentUser, rate_limit
from pydantic import BaseModel

logger = logging.getLogger("student-assistant")
router = APIRouter(prefix="/api")


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _token_hash(token: str) -> str:
    """Non-reversible fingerprint of a purchase token for logging / dedupe (never log the token)."""
    return token_crypto.token_hash(token)


def _short_hash(token: str) -> str:
    return _token_hash(token)[:12]


def _decrypt_stored_token(doc: dict) -> Optional[str]:
    """Recover a purchase token for a stored record: decrypt the ciphertext. Legacy plaintext
    (should not exist in production) is tolerated read-only. Never logs the token."""
    enc = doc.get("encrypted_purchase_token")
    if enc:
        return token_crypto.decrypt_token(enc)
    return doc.get("purchase_token")  # read-only migration fallback; we never WRITE plaintext


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


def _extract_line_item(sub: dict) -> dict:
    """Return {product_id, base_plan_id} from the authoritative Play resource (never the client)."""
    line_items = sub.get("lineItems") or []
    if not line_items:
        return {"product_id": None, "base_plan_id": None}
    li = line_items[-1]
    offer = li.get("offerDetails") or {}
    return {"product_id": li.get("productId"), "base_plan_id": offer.get("basePlanId")}


def _validate_product(sub: dict):
    """Fail closed unless the verified purchase is for OUR configured product. The client-supplied
    product/base plan is never trusted — this reads the Google-side line item."""
    info = _extract_line_item(sub)
    prod = info["product_id"]
    # Some resources omit lineItems for terminal states; only reject on an explicit mismatch.
    if prod and prod != config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID:
        raise HTTPException(status_code=409, detail="This purchase is not for this product.")
    return info


async def _maybe_acknowledge(purchase_token: str, sub: dict):
    """Acknowledge a valid subscription via the Google Play Developer API — ONLY after Premium
    entitlement has been persisted. Idempotent: skips when already acknowledged; never
    acknowledges pending/invalid purchases. Best-effort (failure never revokes entitlement)."""
    ack_state = sub.get("acknowledgementState", "")
    if ack_state == "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED":
        return "already_acknowledged"
    client = _play_client()
    if client is None:
        return "unconfigured"
    try:
        client.purchases().subscriptions().acknowledge(
            packageName=config.GOOGLE_PLAY_PACKAGE_NAME,
            subscriptionId=config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
            token=purchase_token, body={}).execute()
        return "acknowledged"
    except Exception as e:
        logger.warning("Acknowledge skipped (token=%s): %s", _short_hash(purchase_token), type(e).__name__)
        return "ack_failed"


async def _apply_entitlement(uid: str, purchase_token: str, sub: dict, source: str):
    """Idempotently persist a normalized subscription + entitlement from a VERIFIED Play resource.
    The backend is the entitlement authority: state, product, expiry and acknowledgement all come
    from Google, never from the client. Grants Premium ONLY for entitled states."""
    line = _validate_product(sub)
    state, expiry, anchor = _map_play_state(sub)

    thash = _token_hash(purchase_token)
    # Encrypt the token for storage BEFORE any write. Fail closed if the encryption key is
    # missing/invalid so we never persist a plaintext token or grant Premium without it.
    try:
        enc_token = token_crypto.encrypt_token(purchase_token)
    except token_crypto.TokenCryptoError:
        logger.error("Billing token encryption unavailable (token=%s); failing closed.", _short_hash(purchase_token))
        raise HTTPException(status_code=503, detail="Subscriptions are temporarily unavailable.")

    # Reject a purchase token already bound to a different account (no reassignment / replay).
    # Ownership is checked by the non-reversible hash, never the raw token.
    owner = await db.purchase_tokens.find_one({"purchase_token_hash": thash})
    if owner and owner.get("user_id") not in (None, uid):
        raise HTTPException(status_code=409, detail="This purchase is linked to a different account.")

    is_premium = state in mon.PREMIUM_ACTIVE_STATES
    auto_renewing = state in ("active", "grace_period")
    ack_state = sub.get("acknowledgementState", "")
    now_iso = _iso(_utcnow())
    linked_token = sub.get("linkedPurchaseToken")
    linked_hash = _token_hash(linked_token) if linked_token else None

    await db.purchase_tokens.update_one(
        {"purchase_token_hash": thash},
        {"$set": {"user_id": uid, "product_id": line["product_id"] or config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
                  "base_plan_id": line["base_plan_id"], "state": state,
                  "encrypted_purchase_token": enc_token,
                  "acknowledgement_state": ack_state, "auto_renewing": auto_renewing,
                  "linked_purchase_token_hash": linked_hash,
                  "updated_at": now_iso, "last_verified_at": now_iso, "source": source},
         "$setOnInsert": {"created_at": now_iso},
         "$unset": {"purchase_token": ""}}, upsert=True)

    prev = await db.entitlements.find_one({"user_id": uid}) or {}
    ent = {
        "user_id": uid,
        "platform": "android",
        "package_name": config.GOOGLE_PLAY_PACKAGE_NAME,
        "product_id": line["product_id"] or config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
        "base_plan": line["base_plan_id"],
        "plan": "premium" if is_premium else "free",
        "state": state,
        "encrypted_purchase_token": enc_token,
        "purchase_token_hash": thash,
        "linked_purchase_token_hash": linked_hash,
        "acknowledgement_state": ack_state,
        "auto_renewing": auto_renewing,
        "current_period_end": expiry,
        "billing_anchor": prev.get("billing_anchor") or anchor or now_iso,
        "started_at": prev.get("started_at") or anchor or now_iso,
        "last_verified_at": now_iso,
        "last_event": source,
        "updated_at": now_iso,
    }
    await db.entitlements.update_one({"user_id": uid}, {"$set": ent, "$unset": {"purchase_token": ""}}, upsert=True)
    await db.purchase_events.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "purchase_token_hash": thash,
        "state": state, "source": source, "ts": now_iso})

    # Acknowledge ONLY after a granting entitlement has been persisted (idempotent, best-effort).
    if is_premium:
        ack = await _maybe_acknowledge(purchase_token, sub)
        if ack == "acknowledged":
            await db.entitlements.update_one(
                {"user_id": uid}, {"$set": {"acknowledgement_state": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"}})
            await db.purchase_tokens.update_one(
                {"purchase_token_hash": thash},
                {"$set": {"acknowledgement_state": "ACKNOWLEDGEMENT_STATE_ACKNOWLEDGED"}})
    return ent


# ----------------------------------------------------------------- endpoints
def _require_billing_ready():
    """Fail closed unless billing is enabled AND the token encryption key is available, so we
    never verify/store a purchase without being able to protect the token at rest."""
    if not config.BILLING_ENABLED:
        raise HTTPException(status_code=503, detail="Subscriptions are not yet available.")
    if not token_crypto.encryption_ready():
        logger.error("Billing enabled but token encryption key missing; failing closed.")
        raise HTTPException(status_code=503, detail="Subscriptions are temporarily unavailable.")


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
async def billing_verify(body: VerifyIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "billing_verify", limit=20, window=60)
    _require_billing_ready()
    if not body.purchase_token:
        raise HTTPException(status_code=400, detail="Missing purchase token.")
    sub = await _play_verify_token(body.purchase_token)
    ent = await _apply_entitlement(uid, body.purchase_token, sub, source="verify")
    return {"ok": True, "state": ent["state"], "plan": ent["plan"],
            "current_period_end": ent["current_period_end"]}


@router.post("/billing/google/restore")
async def billing_restore(body: VerifyIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "billing_restore", limit=20, window=60)
    _require_billing_ready()
    if not body.purchase_token:
        raise HTTPException(status_code=400, detail="Missing purchase token.")
    sub = await _play_verify_token(body.purchase_token)
    ent = await _apply_entitlement(uid, body.purchase_token, sub, source="restore")
    return {"ok": True, "state": ent["state"], "plan": ent["plan"]}


@router.post("/billing/google/refresh")
async def billing_refresh(request: Request, uid: str = CurrentUser):
    """Re-query Google Play for the user's stored purchase token and reconcile entitlement.
    Fails closed if billing/credentials are unavailable; never grants Premium locally."""
    rate_limit(request, "billing_refresh", limit=30, window=60)
    if not config.BILLING_ENABLED:
        # Status still works (returns Free/plan config); no local grant ever.
        return await billing_status(uid)
    ent_doc = await db.entitlements.find_one({"user_id": uid}) or {}
    try:
        token = _decrypt_stored_token(ent_doc)
    except token_crypto.TokenCryptoError:
        token = None  # fail closed: cannot decrypt -> keep last known state, never guess
    if token:
        try:
            sub = await _play_verify_token(token)
            await _apply_entitlement(uid, token, sub, source="refresh")
        except HTTPException:
            pass  # fail closed: keep last known state; never fabricate a grant
    return await billing_status(uid)


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
    voided_notice = data.get("voidedPurchaseNotification") or {}
    purchase_token = sub_notice.get("purchaseToken") or voided_notice.get("purchaseToken")
    if purchase_token:
        # Ownership lookup uses the token HASH, never the raw token.
        owner = await db.purchase_tokens.find_one({"purchase_token_hash": _token_hash(purchase_token)})
        uid = (owner or {}).get("user_id")
        # A voided/refunded/charged-back purchase revokes entitlement immediately.
        if voided_notice and uid:
            await _revoke_entitlement(uid, purchase_token, source="rtdn_voided")
            await _audit_lifecycle(uid, purchase_token, "revoked", "voided")
        else:
            try:
                sub = await _play_verify_token(purchase_token)  # re-query source of truth
                if uid:
                    ent = await _apply_entitlement(uid, purchase_token, sub, source="rtdn")
                    await _audit_lifecycle(uid, purchase_token, ent["state"],
                                           str(sub_notice.get("notificationType")))
            except Exception as e:
                logger.error("RTDN reconcile failed (token=%s): %s",
                             _short_hash(purchase_token), type(e).__name__)
    await db.rtdn_events.update_one({"message_id": message_id}, {"$set": {"processed": True}})
    return {"ok": True}


async def _revoke_entitlement(uid: str, purchase_token: str, source: str):
    """Remove Premium entitlement for a voided/revoked purchase. Idempotent. Matches by hash."""
    now_iso = _iso(_utcnow())
    thash = _token_hash(purchase_token)
    await db.entitlements.update_one(
        {"user_id": uid, "purchase_token_hash": thash},
        {"$set": {"plan": "free", "state": "revoked", "auto_renewing": False,
                  "last_event": source, "last_verified_at": now_iso, "updated_at": now_iso}})
    await db.purchase_tokens.update_one(
        {"purchase_token_hash": thash},
        {"$set": {"state": "revoked", "updated_at": now_iso, "source": source}})


async def _audit_lifecycle(uid: str, purchase_token: str, state: str, event: str):
    """Store a sanitized lifecycle audit event (never the raw purchase token)."""
    try:
        await db.subscription_audit.insert_one({
            "audit_id": str(uuid.uuid4()), "user_id": uid,
            "purchase_token_hash": _token_hash(purchase_token),
            "state": state, "event": event, "ts": _iso(_utcnow())})
    except Exception:
        pass


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



# ----------------------------------------------------------------- reconciliation
async def reconcile_once(max_batch: int = 200) -> dict:
    """Safety net for missed RTDNs: re-query Google Play for subscriptions whose entitlement
    was verified longest ago and reconcile. Idempotent; fails closed on verification errors.
    Directly callable by tests. No-op (never grants) when billing/credentials are unavailable."""
    if not config.BILLING_ENABLED:
        return {"reconciled": 0, "billing_disabled": True}
    checked = reconciled = 0
    try:
        cursor = db.entitlements.find(
            {"state": {"$in": list(mon.PREMIUM_ACTIVE_STATES) + ["account_hold", "pending"]},
             "encrypted_purchase_token": {"$exists": True, "$ne": None}}).sort("last_verified_at", 1).limit(max_batch)
        async for ent in cursor:
            uid = ent.get("user_id")
            checked += 1
            try:
                # Decrypt ONLY here, immediately before calling Google Play. Never logged.
                token = _decrypt_stored_token(ent)
                if not uid or not token:
                    continue
                sub = await _play_verify_token(token)
                await _apply_entitlement(uid, token, sub, source="reconcile")
                reconciled += 1
            except Exception as e:
                logger.warning("Reconcile skipped (hash=%s): %s",
                               (ent.get("purchase_token_hash") or "")[:12], type(e).__name__)
    except Exception as e:
        logger.warning("Reconcile pass error: %s", type(e).__name__)
    return {"checked": checked, "reconciled": reconciled, "ran_at": _iso(_utcnow())}


async def _reconcile_loop():
    import asyncio
    while True:
        try:
            await reconcile_once()
        except Exception as e:
            logger.warning("reconcile loop error: %s", type(e).__name__)
        await asyncio.sleep(6 * 3600)  # every 6 hours


def start_reconciliation(app):
    """Launch the periodic reconciliation loop (best effort). Only meaningful when billing on."""
    if not config.BILLING_ENABLED:
        return
    try:
        import asyncio
        asyncio.get_event_loop().create_task(_reconcile_loop())
    except Exception as e:
        logger.warning("reconciliation start skipped: %s", type(e).__name__)
