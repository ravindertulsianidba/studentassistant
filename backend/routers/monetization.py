"""Usage status, plan config, paywall analytics and sanitized admin monetization reports."""
import logging
import uuid
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

import config
import monetization as mon
from db import db
from core import CurrentUser

logger = logging.getLogger("student-assistant")
router = APIRouter(prefix="/api")


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


@router.get("/usage/status")
async def usage_status(uid: str = CurrentUser):
    return await mon.get_usage_status(uid)


@router.get("/plan/config")
async def plan_config(uid: str = CurrentUser):
    """Non-sensitive plan/allowance config for the paywall (no prices — Play provides those)."""
    return {
        "billing_enabled": config.BILLING_ENABLED,
        "product_id": config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID,
        "monthly_base_plan_id": config.GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID,
        "annual_base_plan_id": config.GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID,
        "free_starter": mon.free_allowances(),
        "premium": mon.premium_allowances(),
        "premium_max_recording_minutes": config.PREMIUM_MAX_RECORDING_MINUTES,
        "premium_max_pages_per_import": config.PREMIUM_MAX_PAGES_PER_IMPORT,
    }


class EventIn(BaseModel):
    kind: str  # paywall_impression | purchase_start | purchase_complete | purchase_fail | restore_attempt | starter_completed
    plan: Optional[str] = None       # monthly | annual
    reason: Optional[str] = None     # feature key or trigger (sanitized)


@router.post("/monetization/event")
async def monetization_event(body: EventIn, uid: str = CurrentUser):
    """Record a sanitized paywall/purchase funnel event (no content, no payment data)."""
    allowed = {"paywall_impression", "purchase_start", "purchase_complete", "purchase_fail",
               "restore_attempt", "starter_completed", "upgrade_opened",
               "nudge_shown", "nudge_dismissed"}
    if body.kind not in allowed:
        raise HTTPException(status_code=400, detail="Unknown event kind.")
    await db.monetization_events.insert_one({
        "id": str(uuid.uuid4()), "user_id": uid, "kind": body.kind,
        "plan": body.plan, "reason": (body.reason or "")[:60], "ts": _iso(datetime.now(timezone.utc))})
    return {"ok": True}


async def _require_admin(uid: str):
    u = await db.users.find_one({"id": uid}, {"email": 1})
    email = (u or {}).get("email", "").lower()
    if not email or email not in config.ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Admin only.")
    return email


@router.get("/admin/monetization")
async def admin_monetization(uid: str = CurrentUser):
    """Sanitized business metrics. No student content / tokens / payment details / secrets."""
    await _require_admin(uid)
    now = datetime.now(timezone.utc)
    month_ago = _iso(now - timedelta(days=30))

    active = await db.entitlements.count_documents({"state": {"$in": list(mon.PREMIUM_ACTIVE_STATES)}})
    ent_by_state = await db.entitlements.aggregate([
        {"$group": {"_id": "$state", "n": {"$sum": 1}}}]).to_list(50)
    events = await db.monetization_events.aggregate([
        {"$match": {"ts": {"$gte": month_ago}}},
        {"$group": {"_id": "$kind", "n": {"$sum": 1}}}]).to_list(50)
    ev = {e["_id"]: e["n"] for e in events}
    cost_by_feature = await db.cost_ledger.aggregate([
        {"$match": {"ts": {"$gte": month_ago}}},
        {"$group": {"_id": "$feature", "usd": {"$sum": "$estimated_cost_usd"}, "n": {"$sum": 1}}}]).to_list(50)
    cost_by_model = await db.cost_ledger.aggregate([
        {"$match": {"ts": {"$gte": month_ago}}},
        {"$group": {"_id": "$model", "usd": {"$sum": "$estimated_cost_usd"}}}]).to_list(50)
    total_cost = round(sum(c["usd"] for c in cost_by_feature), 4)
    starter_activated = await db.usage_cycles.count_documents({"cycle_type": "starter", "starter_granted": True})
    rtdn_recent = await db.rtdn_events.count_documents({"ts": {"$gte": month_ago}})
    last_sync = await db.entitlements.find_one({}, sort=[("updated_at", -1)], projection={"updated_at": 1, "_id": 0})

    starts = ev.get("purchase_start", 0)
    completes = ev.get("purchase_complete", 0)
    conversion = round(completes / starts, 3) if starts else None

    # Revenue estimate (sanitized, from active count and configured net price).
    net_monthly = round(config.PRICE_MONTHLY_CAD * 0.85 * config.CAD_USD_RATE, 2)
    est_net_rev = round(active * net_monthly, 2)
    ratio = round(total_cost / est_net_rev, 3) if est_net_rev else None

    return {
        "active_subscriptions": active,
        "entitlements_by_state": {e["_id"]: e["n"] for e in ent_by_state},
        "starter_activated": starter_activated,
        "starter_completed": ev.get("starter_completed", 0),
        "funnel_30d": {
            "paywall_impressions": ev.get("paywall_impression", 0),
            "upgrade_opened": ev.get("upgrade_opened", 0),
            "purchase_starts": starts, "purchase_completes": completes,
            "purchase_failures": ev.get("purchase_fail", 0),
            "restore_attempts": ev.get("restore_attempt", 0),
            "conversion_rate": conversion,
        },
        "cost_30d_usd": total_cost,
        "cost_by_feature_usd": {c["_id"]: round(c["usd"], 4) for c in cost_by_feature},
        "cost_by_model_usd": {c["_id"]: round(c["usd"], 4) for c in cost_by_model},
        "est_net_revenue_usd_30d": est_net_rev,
        "variable_cost_ratio": ratio,
        "cost_ratio_status": ("critical" if ratio and ratio >= config.CRITICAL_VARIABLE_COST_RATIO
                              else "warn" if ratio and ratio >= config.TARGET_VARIABLE_COST_RATIO
                              else "ok"),
        "rtdn_events_30d": rtdn_recent,
        "last_entitlement_sync": (last_sync or {}).get("updated_at"),
        "open_alerts": await db.monetization_alerts.count_documents({}),
        "kill_switches_active": config.KILL_SWITCHES,
    }


@router.get("/admin/cost-projection")
async def admin_cost_projection(uid: str = CurrentUser):
    await _require_admin(uid)
    return mon.project_costs()
