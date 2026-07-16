"""Monetization: entitlements, usage metering, cost ledger and cost projection.

Design principles
- The backend is the single entitlement authority (never trust a client flag).
- Free users get a ONE-TIME, non-renewing Starter Pack (granted at email verification).
- Premium allowances reset every 30 days anchored on the billing anchor (incl. annual).
- Metering uses reserve -> (settle | refund) so failed operations never consume usage
  and concurrent requests cannot exceed a limit (atomic conditional $inc).
- Every cost-generating op writes a Usage Ledger + Cost Ledger entry (costs sanitized
  out of normal logs). Pricing lives in a configurable registry (no scattered constants).

Nothing here calls Google Play; billing verification lives in routers/billing.py and is
gated by config.BILLING_ENABLED.
"""
import math
import uuid
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException

import config
from db import db

logger = logging.getLogger("student-assistant")


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


# ------------------------------------------------------------------ plans / buckets
FEATURES = ["audio_minutes", "ai_import", "import_pages", "memory_question",
            "briefing", "weekly_review"]

# Human labels for messaging / analytics (no cost data).
FEATURE_LABELS = {
    "audio_minutes": "audio minutes",
    "ai_import": "AI imports",
    "import_pages": "imported pages",
    "memory_question": "AI Memory questions",
    "briefing": "AI Daily Briefings",
    "weekly_review": "AI Weekly Reviews",
    "ai_briefing": "AI Briefings/Reviews",
}


def free_allowances() -> dict:
    # Free lumps briefings + weekly reviews into one shared "ai_briefing" bucket.
    return {
        "audio_minutes": config.FREE_STARTER_AUDIO_MINUTES,
        "ai_import": config.FREE_STARTER_AI_IMPORTS,
        "import_pages": config.FREE_STARTER_IMPORT_PAGES,
        "memory_question": config.FREE_STARTER_MEMORY_QUESTIONS,
        "ai_briefing": config.FREE_STARTER_AI_BRIEFINGS,
    }


def premium_allowances() -> dict:
    return {
        "audio_minutes": config.PREMIUM_AUDIO_MINUTES_PER_CYCLE,
        "ai_import": config.PREMIUM_AI_IMPORTS_PER_CYCLE,
        "import_pages": config.PREMIUM_IMPORT_PAGES_PER_CYCLE,
        "memory_question": config.PREMIUM_MEMORY_QUESTIONS_PER_CYCLE,
        "briefing": config.PREMIUM_DAILY_BRIEFINGS_PER_CYCLE,
        "weekly_review": config.PREMIUM_WEEKLY_REVIEWS_PER_CYCLE,
    }


def _bucket_for(plan: str, feature: str) -> str:
    """Map a requested feature to the plan's actual usage bucket."""
    if plan == "free" and feature in ("briefing", "weekly_review"):
        return "ai_briefing"
    return feature


def max_pages_per_import(plan: str) -> int:
    return config.PREMIUM_MAX_PAGES_PER_IMPORT if plan == "premium" else config.FREE_STARTER_IMPORT_PAGES


def max_recording_minutes(plan: str) -> int:
    return config.PREMIUM_MAX_RECORDING_MINUTES if plan == "premium" else config.FREE_STARTER_AUDIO_MINUTES


# Entitlement states (see spec).
PREMIUM_ACTIVE_STATES = {"active", "grace_period", "cancelled_active_until_period_end", "paused"}
# "paused" keeps data access but pauses billing; treated as retaining access until resume/expire.


# ------------------------------------------------------------------ entitlement
async def _get_entitlement_doc(uid: str) -> Optional[dict]:
    return await db.entitlements.find_one({"user_id": uid}, {"_id": 0})


def _is_premium_active(ent: Optional[dict]) -> bool:
    if not ent:
        return False
    if not config.BILLING_ENABLED:
        # Even with a stored entitlement, do not serve premium if billing is off,
        # UNLESS explicitly marked for testing via test_override.
        if not ent.get("test_override"):
            return False
    state = ent.get("state", "free")
    if state not in PREMIUM_ACTIVE_STATES:
        return False
    exp = ent.get("current_period_end")
    if exp:
        try:
            ed = datetime.fromisoformat(exp)
            if ed.tzinfo is None:
                ed = ed.replace(tzinfo=timezone.utc)
            # grace/cancelled retain until period end.
            if ed < _utcnow() and state not in ("grace_period", "account_hold"):
                return False
        except Exception:
            pass
    return True


async def _premium_cycle_window(ent: dict, anchor_override: str = "") -> tuple[str, str]:
    """30-day window anchored on the billing anchor; annual plans still reset every 30 days."""
    anchor = anchor_override or ent.get("billing_anchor") or ent.get("started_at") or _iso(_utcnow())
    try:
        a = datetime.fromisoformat(anchor)
        if a.tzinfo is None:
            a = a.replace(tzinfo=timezone.utc)
    except Exception:
        a = _utcnow()
    now = _utcnow()
    days = max(0, (now - a).days)
    cycles = days // 30
    start = a + timedelta(days=30 * cycles)
    end = start + timedelta(days=30)
    return _iso(start), _iso(end)


async def _active_admin_grant(uid: str) -> Optional[dict]:
    """Return an active complimentary/admin entitlement grant for the user, if any.
    Sources: admin_grant | promotional | internal_test. Coexists with google_play."""
    now = _iso(_utcnow())
    grant = await db.entitlement_grants.find_one({
        "user_id": uid, "status": "active", "revoked_at": None,
        "$and": [
            {"$or": [{"starts_at": None}, {"starts_at": {"$lte": now}}]},
            {"$or": [{"expires_at": None}, {"expires_at": {"$gt": now}}]},
        ],
    }, {"_id": 0})
    return grant


async def resolve_entitlement(uid: str) -> dict:
    """Single source of truth. Effective access = max of ALL valid entitlement sources
    (Google Play + admin/complimentary grants). Sources coexist independently."""
    ent = await _get_entitlement_doc(uid)
    play_active = _is_premium_active(ent)
    grant = await _active_admin_grant(uid)

    if play_active:
        start, end = await _premium_cycle_window(ent)
        return {"plan": "premium", "state": ent.get("state", "active"),
                "source": "google_play",
                "cycle_type": "premium", "cycle_start": start, "cycle_end": end,
                "allowances": premium_allowances(),
                "renews": ent.get("state") != "cancelled_active_until_period_end",
                "current_period_end": ent.get("current_period_end")}
    if grant:
        anchor = grant.get("usage_cycle_anchor") or grant.get("starts_at") or grant.get("created_at")
        start, end = await _premium_cycle_window({}, anchor_override=anchor or _iso(_utcnow()))
        return {"plan": "premium", "state": "active",
                "source": grant.get("source", "admin_grant"),
                "cycle_type": "premium", "cycle_start": start, "cycle_end": end,
                "allowances": premium_allowances(), "renews": False,
                "current_period_end": grant.get("expires_at")}
    # Free (default). Starter Pack is a lifetime, non-renewing cycle.
    state = (ent or {}).get("state", "free")
    if state in ("cancelled_active_until_period_end", "grace_period") and ent:
        state = "expired"
    return {"plan": "free", "state": state if ent else "free", "source": "free",
            "cycle_type": "starter", "cycle_start": None, "cycle_end": None,
            "allowances": free_allowances(), "renews": False, "current_period_end": None}


# ------------------------------------------------------------------ usage cycles
async def _ensure_cycle(uid: str, ent: dict) -> dict:
    """Return the usage-cycle doc for the current entitlement window, creating it if needed."""
    ctype = ent["cycle_type"]
    if ctype == "premium":
        key = {"user_id": uid, "cycle_type": "premium", "cycle_start": ent["cycle_start"]}
        defaults = {**key, "cycle_end": ent["cycle_end"], "created_at": _iso(_utcnow()),
                    "used": {}}
    else:
        key = {"user_id": uid, "cycle_type": "starter"}
        defaults = {**key, "cycle_start": None, "cycle_end": None,
                    "created_at": _iso(_utcnow()), "used": {}}
    doc = await db.usage_cycles.find_one(key)
    if not doc:
        await db.usage_cycles.update_one(key, {"$setOnInsert": defaults}, upsert=True)
        doc = await db.usage_cycles.find_one(key)
    return doc


async def get_usage_status(uid: str) -> dict:
    """Sanitized usage snapshot for the current cycle (no cost data)."""
    ent = await resolve_entitlement(uid)
    cycle = await _ensure_cycle(uid, ent)
    used = cycle.get("used", {})
    allow = ent["allowances"]
    features = {}
    for bucket, total in allow.items():
        u = float(used.get(bucket, 0))
        features[bucket] = {
            "label": FEATURE_LABELS.get(bucket, bucket),
            "used": round(u, 2), "allowance": total,
            "remaining": round(max(0, total - u), 2),
            "pct": (round(min(100, (u / total) * 100)) if total else 100),
        }
    return {
        "plan": ent["plan"], "state": ent["state"], "source": ent.get("source", "free"),
        "source_label": {"google_play": "Google Play", "admin_grant": "Complimentary Premium",
                          "promotional": "Complimentary Premium", "internal_test": "Complimentary Premium",
                          "free": "Free"}.get(ent.get("source", "free"), "Free"),
        "cycle_type": ent["cycle_type"], "cycle_start": ent["cycle_start"],
        "cycle_end": ent["cycle_end"], "renews": ent["renews"],
        "current_period_end": ent["current_period_end"],
        "billing_enabled": config.BILLING_ENABLED,
        "features": features,
    }


# ------------------------------------------------------------------ kill switches
def _kill_switched(feature: str) -> bool:
    return feature in config.KILL_SWITCHES


# ------------------------------------------------------------------ reserve / settle / refund
class UsageBlocked(HTTPException):
    def __init__(self, detail: dict):
        super().__init__(status_code=402, detail=detail)


async def reserve(uid: str, feature: str, amount: float = 1) -> dict:
    """Atomically reserve `amount` of `feature`. Raises 402 with structured detail if the
    allowance is exhausted (or 503 if the feature is kill-switched). Returns a handle."""
    if _kill_switched(feature):
        raise HTTPException(status_code=503, detail={
            "error": "feature_unavailable",
            "message": "This AI feature is temporarily paused for maintenance. Your saved data is unaffected.",
            "feature": feature})

    ent = await resolve_entitlement(uid)
    bucket = _bucket_for(ent["plan"], feature)
    allowance = ent["allowances"].get(bucket)
    if allowance is None:
        # Feature not part of this plan's buckets -> treat as blocked (upgrade needed).
        allowance = 0
    await _ensure_cycle(uid, ent)

    if ctype_filter := (ent["cycle_type"] == "premium"):
        key = {"user_id": uid, "cycle_type": "premium", "cycle_start": ent["cycle_start"]}
    else:
        key = {"user_id": uid, "cycle_type": "starter"}

    field = f"used.{bucket}"
    # Atomic conditional increment: only succeeds if it won't exceed the allowance.
    res = await db.usage_cycles.update_one(
        {**key, "$or": [{field: {"$lte": allowance - amount}}, {field: {"$exists": False}}]},
        {"$inc": {field: amount}},
    )
    if res.modified_count == 0:
        # Could be exists-with-no-room OR the $exists branch when amount>allowance.
        doc = await db.usage_cycles.find_one(key) or {"used": {}}
        used = float(doc.get("used", {}).get(bucket, 0))
        if used + amount > allowance:
            status = await get_usage_status(uid)
            raise UsageBlocked({
                "error": "limit_reached",
                "feature": bucket,
                "label": FEATURE_LABELS.get(bucket, bucket),
                "consumed": round(used, 2),
                "allowance": allowance,
                "remaining": round(max(0, allowance - used), 2),
                "reset_date": ent["cycle_end"],
                "plan": ent["plan"],
                "message": ("You've used your one-time Starter Pack allowance for "
                            f"{FEATURE_LABELS.get(bucket, bucket)}. Upgrade for higher monthly allowances — "
                            "your saved data stays available."
                            if ent["plan"] == "free" else
                            f"You've reached this cycle's {FEATURE_LABELS.get(bucket, bucket)} allowance. "
                            "This allowance protects service reliability and resets on the date shown. "
                            "Your saved data stays available."),
            })
        # Rare race: retry once with the found value.
        res2 = await db.usage_cycles.update_one(
            {**key, field: {"$lte": allowance - amount}}, {"$inc": {field: amount}})
        if res2.modified_count == 0:
            raise UsageBlocked({"error": "limit_reached", "feature": bucket,
                                "allowance": allowance, "plan": ent["plan"],
                                "reset_date": ent["cycle_end"]})
    return {"uid": uid, "plan": ent["plan"], "bucket": bucket, "amount": amount, "key": key,
            "cycle_type": ent["cycle_type"]}


async def refund(handle: dict, amount: Optional[float] = None):
    """Return reserved units (e.g., when the AI op failed)."""
    amt = handle["amount"] if amount is None else amount
    if amt <= 0:
        return
    await db.usage_cycles.update_one(handle["key"], {"$inc": {f"used.{handle['bucket']}": -amt}})


async def reserve_import(uid: str, pages: int):
    """Reserve 1 AI import + `pages` imported pages (page count capped per-import).
    Returns (import_handle, pages_handle, effective_pages). Rolls back on partial failure."""
    ent = await resolve_entitlement(uid)
    cap = max_pages_per_import(ent["plan"])
    pages = max(1, min(int(pages or 1), cap))
    h_imp = await reserve(uid, "ai_import", 1)
    try:
        h_pg = await reserve(uid, "import_pages", pages)
    except HTTPException:
        await refund(h_imp)
        raise
    return h_imp, h_pg, pages


# ------------------------------------------------------------------ pricing / cost
def _pricing() -> dict:
    """Model pricing registry (USD). Overridable at runtime via db.pricing_config
    (loaded by refresh_pricing) so prices change without an app rebuild."""
    return _PRICING


# USD pricing. per_1k tokens for text; per_minute for audio.
_PRICING = {
    "gpt-4o-mini": {"in_per_1k": 0.00015, "out_per_1k": 0.00060},
    "gpt-4o": {"in_per_1k": 0.0025, "out_per_1k": 0.010},
    "gpt-4o-transcribe": {"audio_per_min": 0.006},
    "whisper-1": {"audio_per_min": 0.006},
    "text-embedding-3-small": {"in_per_1k": 0.00002, "out_per_1k": 0.0},
}


async def refresh_pricing():
    """Load pricing overrides from db.pricing_config (doc _id='current')."""
    try:
        doc = await db.pricing_config.find_one({"_id": "current"})
        if doc and isinstance(doc.get("models"), dict):
            _PRICING.update(doc["models"])
            logger.info("Pricing registry updated from db.pricing_config")
    except Exception as e:
        logger.warning("refresh_pricing skipped: %s", type(e).__name__)


def estimate_cost(model: str, input_tokens: int = 0, output_tokens: int = 0,
                  audio_minutes: float = 0) -> float:
    p = _pricing().get(model, {})
    cost = 0.0
    cost += (input_tokens / 1000.0) * p.get("in_per_1k", 0.0)
    cost += (output_tokens / 1000.0) * p.get("out_per_1k", 0.0)
    cost += audio_minutes * p.get("audio_per_min", 0.0)
    return round(cost, 6)


async def record_usage(handle: dict, *, op: str, provider: str = "openai", model: str = "",
                       input_tokens: int = 0, output_tokens: int = 0, audio_minutes: float = 0,
                       pages: int = 0, file_size: int = 0, request_id: str = "",
                       actual_cost: Optional[float] = None, success: bool = True,
                       idempotency_key: str = "", settle_amount: Optional[float] = None):
    """Write Usage + Cost ledger entries after a successful op. If settle_amount differs
    from the reserved amount, adjust the reserved bucket (e.g., real audio minutes)."""
    uid = handle["uid"]
    # Adjust reservation to the actual consumed amount if provided.
    if settle_amount is not None and settle_amount != handle["amount"]:
        delta = settle_amount - handle["amount"]
        await db.usage_cycles.update_one(handle["key"], {"$inc": {f"used.{handle['bucket']}": delta}})
    est = estimate_cost(model, input_tokens, output_tokens, audio_minutes)
    now = _iso(_utcnow())
    entry = {
        "id": str(uuid.uuid4()), "user_id": uid, "entitlement": handle["plan"],
        "cycle_type": handle["cycle_type"], "operation": op, "feature": handle["bucket"],
        "provider": provider, "model": model,
        "input_tokens": int(input_tokens), "output_tokens": int(output_tokens),
        "audio_minutes": round(float(audio_minutes), 3), "pages": int(pages),
        "file_size": int(file_size), "provider_request_id": request_id,
        "estimated_cost_usd": est, "actual_cost_usd": actual_cost,
        "success": bool(success), "idempotency_key": idempotency_key, "ts": now,
    }
    try:
        await db.cost_ledger.insert_one(dict(entry))
        await db.usage_ledger.insert_one({
            "id": entry["id"], "user_id": uid, "entitlement": handle["plan"],
            "operation": op, "feature": handle["bucket"],
            "amount": settle_amount if settle_amount is not None else handle["amount"],
            "success": bool(success), "ts": now})
        await _check_cost_alerts(uid, handle["plan"])
    except Exception as e:
        logger.warning("record_usage ledger write failed: %s", type(e).__name__)
    return entry


# ------------------------------------------------------------------ cost alerts
async def _check_cost_alerts(uid: str, plan: str):
    """Lightweight guardrail: alert (log) when a Free account's lifetime Starter Pack cost
    exceeds the configured threshold. Revenue-ratio alerts are computed in admin reports."""
    if plan != "free":
        return
    try:
        agg = await db.cost_ledger.aggregate([
            {"$match": {"user_id": uid}},
            {"$group": {"_id": None, "c": {"$sum": "$estimated_cost_usd"}}},
        ]).to_list(1)
        total = agg[0]["c"] if agg else 0
        if total >= config.FREE_STARTER_COST_ALERT_USD:
            existing = await db.monetization_alerts.find_one({"user_id": uid, "kind": "starter_cost"})
            if not existing:
                await db.monetization_alerts.insert_one({
                    "user_id": uid, "kind": "starter_cost", "ts": _iso(_utcnow()),
                    "threshold_usd": config.FREE_STARTER_COST_ALERT_USD})
                logger.warning("COST ALERT: Free account exceeded Starter Pack cost threshold "
                               "(user hashed elsewhere).")
    except Exception:
        pass


# ------------------------------------------------------------------ starter pack grant
async def grant_starter_pack(uid: str, install_hash: str = "") -> bool:
    """Grant the one-time Starter Pack to a verified account. Idempotent (once per account).
    Logs a duplicate-account anomaly if the same install hash grants many accounts."""
    existing = await db.usage_cycles.find_one({"user_id": uid, "cycle_type": "starter"})
    if existing and existing.get("starter_granted"):
        return False
    await db.usage_cycles.update_one(
        {"user_id": uid, "cycle_type": "starter"},
        {"$set": {"starter_granted": True, "granted_at": _iso(_utcnow()),
                  "install_hash": install_hash or None},
         "$setOnInsert": {"used": {}, "cycle_start": None, "cycle_end": None,
                          "created_at": _iso(_utcnow())}},
        upsert=True)
    if install_hash:
        try:
            n = await db.usage_cycles.count_documents(
                {"cycle_type": "starter", "install_hash": install_hash, "starter_granted": True})
            if n > config.STARTER_INSTALL_ANOMALY_THRESHOLD:
                await db.monetization_alerts.insert_one({
                    "kind": "duplicate_account_anomaly", "install_hash": install_hash,
                    "count": n, "ts": _iso(_utcnow())})
                logger.warning("ANOMALY: install hash linked to %d Starter Pack grants", n)
        except Exception:
            pass
    return True


# ------------------------------------------------------------------ cost projection
def project_costs() -> dict:
    """Sanitized worst-case + typical cost projection using the CONFIGURED models.
    Assumptions are explicit so allowances can be tuned without a rebuild."""
    tmodel = config.OPENAI_MODEL_TRANSCRIBE
    jmodel = config.OPENAI_MODEL_JSON
    vmodel = config.OPENAI_MODEL_VISION
    # Per-unit token assumptions (documented; tune in one place).
    A = {
        "note_tokens_per_audio_min": (200, 120),   # (in, out) for extraction/notes per audio min
        "import_tokens_per_page": (1500, 800),
        "memory_tokens": (2200, 550),
        "briefing_tokens": (1600, 650),
        "weekly_tokens": (2600, 900),
    }

    def full_premium():
        c = 0.0
        am = config.PREMIUM_AUDIO_MINUTES_PER_CYCLE
        c += estimate_cost(tmodel, audio_minutes=am)
        c += estimate_cost(jmodel, A["note_tokens_per_audio_min"][0] * am,
                           A["note_tokens_per_audio_min"][1] * am)
        pg = config.PREMIUM_IMPORT_PAGES_PER_CYCLE
        c += estimate_cost(vmodel, A["import_tokens_per_page"][0] * pg,
                           A["import_tokens_per_page"][1] * pg)
        mq = config.PREMIUM_MEMORY_QUESTIONS_PER_CYCLE
        c += estimate_cost(jmodel, A["memory_tokens"][0] * mq, A["memory_tokens"][1] * mq)
        bf = config.PREMIUM_DAILY_BRIEFINGS_PER_CYCLE
        c += estimate_cost(jmodel, A["briefing_tokens"][0] * bf, A["briefing_tokens"][1] * bf)
        wr = config.PREMIUM_WEEKLY_REVIEWS_PER_CYCLE
        c += estimate_cost(jmodel, A["weekly_tokens"][0] * wr, A["weekly_tokens"][1] * wr)
        return round(c, 4)

    def typical_premium():
        # Assume ~35% quota utilization for a typical active subscriber.
        return round(full_premium() * 0.35, 4)

    def starter_full():
        c = 0.0
        c += estimate_cost(tmodel, audio_minutes=config.FREE_STARTER_AUDIO_MINUTES)
        c += estimate_cost(jmodel, A["note_tokens_per_audio_min"][0] * config.FREE_STARTER_AUDIO_MINUTES,
                           A["note_tokens_per_audio_min"][1] * config.FREE_STARTER_AUDIO_MINUTES)
        c += estimate_cost(vmodel, A["import_tokens_per_page"][0] * config.FREE_STARTER_IMPORT_PAGES,
                           A["import_tokens_per_page"][1] * config.FREE_STARTER_IMPORT_PAGES)
        c += estimate_cost(jmodel, A["memory_tokens"][0] * config.FREE_STARTER_MEMORY_QUESTIONS,
                           A["memory_tokens"][1] * config.FREE_STARTER_MEMORY_QUESTIONS)
        c += estimate_cost(jmodel, A["briefing_tokens"][0] * config.FREE_STARTER_AI_BRIEFINGS,
                           A["briefing_tokens"][1] * config.FREE_STARTER_AI_BRIEFINGS)
        return round(c, 4)

    # Revenue (CAD -> USD) after Google Play 15% fee.
    fee = 0.15
    cad_usd = config.CAD_USD_RATE
    monthly_net_usd = round(config.PRICE_MONTHLY_CAD * (1 - fee) * cad_usd, 2)
    annual_net_month_usd = round((config.PRICE_ANNUAL_CAD * (1 - fee) * cad_usd) / 12.0, 2)

    fp = full_premium()
    tp = typical_premium()
    sp = starter_full()
    return {
        "assumptions": {"models": {"transcribe": tmodel, "json": jmodel, "vision": vmodel},
                        "google_fee": fee, "cad_usd_rate": cad_usd,
                        "typical_utilization": 0.35, **{k: list(v) for k, v in A.items()}},
        "full_quota_premium_usd": fp,
        "typical_premium_usd": tp,
        "starter_pack_full_usd": sp,
        "monthly_net_revenue_usd": monthly_net_usd,
        "annual_net_monthly_revenue_usd": annual_net_month_usd,
        "full_quota_ratio_monthly": round(fp / monthly_net_usd, 3) if monthly_net_usd else None,
        "full_quota_ratio_annual": round(fp / annual_net_month_usd, 3) if annual_net_month_usd else None,
        "typical_ratio_annual": round(tp / annual_net_month_usd, 3) if annual_net_month_usd else None,
        "starter_alert_usd": config.FREE_STARTER_COST_ALERT_USD,
        "starter_within_alert": sp <= config.FREE_STARTER_COST_ALERT_USD,
        "flag_full_quota_over_35pct_annual": (fp / annual_net_month_usd) > 0.35 if annual_net_month_usd else False,
    }


def minutes_ceil(seconds: float) -> int:
    return max(1, math.ceil((seconds or 0) / 60.0))
