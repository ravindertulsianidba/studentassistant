"""Reliability layer: commitment state machine, append-only reliability ledger,
dedicated reminder entity with retry, per-user idempotency, and daily AI usage
caps. All operations are user-scoped. Pure data logic — no HTTP here.
"""
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException

import config


def _now():
    return datetime.now(timezone.utc).isoformat()


def _id():
    return str(uuid.uuid4())


# ---------------- commitment state machine ----------------
# Lifecycle of every captured item.
STATES = ["detected", "confirmed", "scheduled", "completed", "dismissed", "cancelled", "failed"]
TRANSITIONS = {
    "detected": {"confirmed", "dismissed", "failed"},
    "confirmed": {"scheduled", "dismissed", "failed"},
    "scheduled": {"completed", "cancelled", "failed", "scheduled"},
    "completed": set(),
    "dismissed": {"confirmed"},          # allow undo
    "cancelled": {"scheduled"},          # allow re-schedule
    "failed": {"detected", "confirmed", "scheduled"},  # allow recovery/retry
}


class InvalidTransition(Exception):
    pass


async def log(db, uid, action, *, commitment_id=None, entity_type=None, entity_id=None,
              from_state=None, to_state=None, actor="system", detail=None, idem=None):
    """Append an immutable audit entry to the reliability ledger."""
    entry = {"id": _id(), "user_id": uid, "commitment_id": commitment_id,
             "entity_type": entity_type, "entity_id": entity_id, "action": action,
             "from_state": from_state, "to_state": to_state, "actor": actor,
             "detail": detail, "idempotency_key": idem, "ts": _now()}
    await db.ledger.insert_one(dict(entry))
    return entry


async def create_commitment(db, uid, item, source, actor="ai", idem=None):
    doc = {"id": _id(), "user_id": uid, "title": item.get("title", "Untitled"),
           "kind": item.get("kind", "task"), "source": source, "state": "detected",
           "confidence": float(item.get("confidence", 0) or 0), "ref_type": None,
           "ref_id": None, "entity": item.get("entity"), "idempotency_key": idem,
           "item": item, "created_at": _now(), "updated_at": _now()}
    await db.commitments.insert_one(dict(doc))
    await log(db, uid, "commitment_detected", commitment_id=doc["id"],
              entity_type="commitment", entity_id=doc["id"], to_state="detected",
              actor=actor, detail=doc["title"], idem=idem)
    doc.pop("_id", None)
    return doc


async def transition(db, uid, commitment_id, to_state, *, actor="user", detail=None,
                     ref_type=None, ref_id=None):
    c = await db.commitments.find_one({"id": commitment_id, "user_id": uid})
    if not c:
        raise HTTPException(status_code=404, detail="Commitment not found")
    frm = c.get("state", "detected")
    if to_state not in TRANSITIONS.get(frm, set()):
        raise InvalidTransition(f"{frm} -> {to_state} not allowed")
    upd = {"state": to_state, "updated_at": _now()}
    if ref_type:
        upd["ref_type"] = ref_type
    if ref_id:
        upd["ref_id"] = ref_id
    await db.commitments.update_one({"id": commitment_id, "user_id": uid}, {"$set": upd})
    await log(db, uid, f"commitment_{to_state}", commitment_id=commitment_id,
              entity_type="commitment", entity_id=commitment_id, from_state=frm,
              to_state=to_state, actor=actor, detail=detail)
    c.update(upd)
    c.pop("_id", None)
    return c


# ---------------- reminders (dedicated entity) ----------------
async def create_reminder(db, uid, *, ref_type, ref_id, title, remind_at, body=None,
                          routine=None, max_retries=3, actor="system"):
    r = {"id": _id(), "user_id": uid, "ref_type": ref_type, "ref_id": ref_id,
         "title": title, "body": body, "remind_at": remind_at, "status": "pending",
         "retry_count": 0, "max_retries": max_retries, "last_attempt_at": None,
         "delivered_at": None, "external_id": None, "snooze_until": None,
         "routine": routine, "created_at": _now(), "updated_at": _now()}
    await db.reminders.insert_one(dict(r))
    await log(db, uid, "reminder_created", entity_type="reminder", entity_id=r["id"],
              to_state="pending", actor=actor, detail=title)
    r.pop("_id", None)
    return r


async def set_reminder_status(db, uid, rid, status, *, external_id=None, snooze_until=None,
                              actor="device", detail=None):
    r = await db.reminders.find_one({"id": rid, "user_id": uid})
    if not r:
        raise HTTPException(status_code=404, detail="Reminder not found")
    upd = {"status": status, "updated_at": _now(), "last_attempt_at": _now()}
    if external_id is not None:
        upd["external_id"] = external_id
    if status == "delivered":
        upd["delivered_at"] = _now()
    if status == "snoozed" and snooze_until:
        upd["snooze_until"] = snooze_until
        upd["remind_at"] = snooze_until
        upd["status"] = "scheduled"
    if status == "failed":
        upd["retry_count"] = int(r.get("retry_count", 0)) + 1
        # give up after max retries
        if upd["retry_count"] >= int(r.get("max_retries", 3)):
            upd["status"] = "failed"
        else:
            upd["status"] = "pending"  # eligible for re-schedule on next sync
    await db.reminders.update_one({"id": rid, "user_id": uid}, {"$set": upd})
    await log(db, uid, f"reminder_{status}", entity_type="reminder", entity_id=rid,
              to_state=upd["status"], actor=actor, detail=detail)
    r.update(upd)
    r.pop("_id", None)
    return r


def routine_specs(prefs: dict, evening_review_eligible: bool = True) -> list:
    """Repeating device-scheduled routines derived from user prefs.

    `evening_review_eligible` gates the Evening Review: when the account has
    nothing to review today it is omitted, so empty accounts get no Evening
    Review notification (the single scheduling authority is the device, which
    consumes this list)."""
    specs = [
        {"key": "daily_briefing", "title": "Your daily briefing",
         "body": "Here's what's on your plate today.", "time": prefs.get("morning_time", "07:30"),
         "repeat": "daily"},
    ]
    if evening_review_eligible:
        specs.append(
            {"key": "evening_review", "title": "Evening review",
             "body": "Wrap up today — what got done?", "time": prefs.get("evening_time", "20:00"),
             "repeat": "daily"})
    specs.append(
        {"key": "weekly_review", "title": "Weekly review",
         "body": "Plan the week ahead.", "time": prefs.get("weekly_time", "18:00"),
         "weekday": prefs.get("weekly_day", "Sun"), "repeat": "weekly"})
    return specs


# ---------------- idempotency ----------------
async def idem_lookup(db, uid, key):
    if not key:
        return None
    row = await db.idempotency.find_one({"user_id": uid, "key": key}, {"_id": 0})
    return row.get("response") if row else None


async def idem_store(db, uid, key, endpoint, response):
    if not key:
        return
    try:
        await db.idempotency.insert_one({"id": _id(), "user_id": uid, "key": key,
                                         "endpoint": endpoint, "response": response, "ts": _now()})
    except Exception:
        pass  # unique index race → another request stored it first


# ---------------- daily AI usage cap ----------------
async def enforce_ai_cap(db, uid, prefs):
    """Increment today's AI usage; raise 429 if over the per-user daily cap.
    Cap is prefs['daily_ai_limit'] or the admin default (env). Never hardcoded low."""
    limit = int(prefs.get("daily_ai_limit") or config.DEFAULT_DAILY_AI_LIMIT)
    if limit <= 0:  # 0 == unlimited
        return
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.ai_usage.find_one_and_update(
        {"user_id": uid, "date": day}, {"$inc": {"count": 1}},
        upsert=True, return_document=True)
    used = (doc or {}).get("count", 1)
    if used > limit:
        # roll back the increment we just made so status reads truthfully
        await db.ai_usage.update_one({"user_id": uid, "date": day}, {"$inc": {"count": -1}})
        raise HTTPException(status_code=429, detail=(
            f"Daily AI limit reached ({limit} requests). This protects your API costs. "
            f"It resets at midnight UTC. An administrator can raise the default limit."))


async def refund_ai_cap(db, uid):
    """Reverse a daily-cap increment when the AI operation failed BEFORE producing
    a result, so technical failures never permanently consume the user's quota."""
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.ai_usage.find_one({"user_id": uid, "date": day}, {"_id": 0})
    if doc and (doc.get("count", 0) > 0):
        await db.ai_usage.update_one({"user_id": uid, "date": day}, {"$inc": {"count": -1}})


async def ai_usage_status(db, uid, prefs):
    limit = int(prefs.get("daily_ai_limit") or config.DEFAULT_DAILY_AI_LIMIT)
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    doc = await db.ai_usage.find_one({"user_id": uid, "date": day}, {"_id": 0})
    used = (doc or {}).get("count", 0)
    return {"date": day, "used": used, "limit": limit,
            "remaining": (max(0, limit - used) if limit > 0 else None),
            "unlimited": limit <= 0}
