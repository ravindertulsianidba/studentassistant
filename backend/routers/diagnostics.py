"""Phase 3C — system health checks & diagnostics.

Aggregates the health of every subsystem the app depends on, plus safe self-test and
recovery actions. Device-owned facts (mic permission, recording, notification delivery)
are reported by the device via /diagnostics/device-state; everything else is derived
server-side. Nothing here fails silently.
"""
import time
from datetime import datetime, timezone

from fastapi import APIRouter

import config
import ai_service
import reliability as rel
from db import db
from core import now_iso, get_prefs, enforce_ai, CurrentUser
from models import DeviceStateIn

router = APIRouter(prefix="/api")


async def _device_state(uid):
    d = await db.device_state.find_one({"user_id": uid}, {"_id": 0}) or {}
    return d


@router.post("/diagnostics/device-state")
async def set_device_state(inp: DeviceStateIn, uid: str = CurrentUser):
    upd = {k: v for k, v in inp.model_dump().items() if v is not None}
    upd["updated_at"] = now_iso()
    await db.device_state.update_one({"user_id": uid}, {"$set": upd}, upsert=True)
    return {"ok": True}


@router.get("/diagnostics")
async def diagnostics(tz: str = "UTC", uid: str = CurrentUser):
    prefs = await get_prefs(uid)
    conn = await db.calendar_connection.find_one({"user_id": uid}, {"_id": 0}) or {}
    dev = await _device_state(uid)

    reminders_scheduled = await db.reminders.count_documents(
        {"user_id": uid, "status": {"$in": ["pending", "scheduled"]}})
    reminders_failed = await db.reminders.count_documents({"user_id": uid, "status": "failed"})
    cal_failures = await db.ledger.count_documents(
        {"user_id": uid, "action": {"$in": ["calendar_sync_failed", "calendar_permission_revoked"]}})
    cal_review = await db.calendar_review.count_documents({"user_id": uid, "status": "pending"})

    pending_uploads = await db.uploads.count_documents(
        {"user_id": uid, "status": {"$in": ["init", "uploading", "processing"]}})
    failed_uploads = await db.uploads.count_documents({"user_id": uid, "status": "failed"})

    last_tx = await db.transcripts.find_one({"user_id": uid}, {"_id": 0}, sort=[("created_at", -1)])
    last_note = await db.notes.find_one({"user_id": uid}, {"_id": 0}, sort=[("created_at", -1)])
    listen = await db.listen_sessions.find_one(
        {"user_id": uid, "status": {"$in": ["listening", "paused", "processing"]}}, {"_id": 0})
    pending_jobs = pending_uploads + await db.listen_sessions.count_documents(
        {"user_id": uid, "status": "processing"})

    ai_ok = bool(config.OPENAI_API_KEY) or config.AI_PROVIDER == "fixture"

    return {
        "generated_at": now_iso(),
        "auth": {"ok": True, "user_id": uid},
        "backend": {"ok": True},
        "ai_provider": {"provider": config.AI_PROVIDER, "configured": ai_ok},
        "notifications": {"scheduled": reminders_scheduled, "failed": reminders_failed,
                          "permission": dev.get("notif_permission")},
        "calendar": {"connected": bool(conn.get("connected")), "access_mode": conn.get("access_mode"),
                     "status": conn.get("status", "disconnected"), "last_sync": conn.get("last_sync"),
                     "failures": cal_failures, "failure_reason": conn.get("failure_reason"),
                     "pending_confirmations": cal_review},
        "microphone": {"permission": dev.get("mic_permission")},
        "active_listening": {"status": (listen or {}).get("status", "idle"),
                             "session_id": (listen or {}).get("id")},
        "recording": {"active": bool(dev.get("recording"))},
        "uploads": {"pending": pending_uploads, "failed": failed_uploads},
        "processing": {"pending_jobs": pending_jobs},
        "last_transcription": (last_tx or {}).get("created_at"),
        "last_study_notes": (last_note or {}).get("created_at"),
        "timezone": tz,
    }


@router.post("/diagnostics/test-backend")
async def test_backend(uid: str = CurrentUser):
    return {"ok": True, "time": now_iso()}


@router.post("/diagnostics/test-ai")
async def test_ai(uid: str = CurrentUser):
    t0 = time.time()
    try:
        await enforce_ai(uid)
        data = await ai_service.extract_json(
            "Reply ONLY with strict JSON {\"pong\":true}.", "ping")
        ok = isinstance(data, dict)
        return {"ok": ok, "latency_ms": int((time.time() - t0) * 1000), "provider": config.AI_PROVIDER}
    except Exception as e:
        return {"ok": False, "error": str(getattr(e, "detail", e))[:200]}


@router.post("/diagnostics/test-calendar-read")
async def test_calendar_read(uid: str = CurrentUser):
    """Server-side proxy: real device read is device-only. Reports mirrored count."""
    conn = await db.calendar_connection.find_one({"user_id": uid}) or {}
    n = await db.external_events.count_documents({"user_id": uid, "deleted": {"$ne": True}})
    return {"ok": bool(conn.get("connected")), "connected": bool(conn.get("connected")),
            "external_events_mirrored": n, "note": "Live device read runs in the installed app."}


@router.post("/diagnostics/retry-jobs")
async def retry_jobs(uid: str = CurrentUser):
    up = await db.uploads.update_many({"user_id": uid, "status": "failed"},
                                      {"$set": {"status": "init", "retry_at": now_iso()}})
    rm = await db.reminders.update_many({"user_id": uid, "status": "failed"},
        {"$set": {"status": "pending", "retry_count": 0, "updated_at": now_iso()}})
    await rel.log(db, uid, "diagnostics_retry_jobs", entity_type="diagnostics", entity_id="-",
                  actor="user", detail=f"uploads={up.modified_count} reminders={rm.modified_count}")
    return {"ok": True, "uploads_requeued": up.modified_count, "reminders_requeued": rm.modified_count}


@router.get("/diagnostics/report")
async def report(tz: str = "UTC", uid: str = CurrentUser):
    diag = await diagnostics(tz=tz, uid=uid)
    ledger = await db.ledger.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).to_list(50)
    diag["recent_ledger"] = ledger
    return diag


# Fields safe to expose in a shareable support bundle. Anything that could carry private
# academic content (titles, notes, transcripts, emails, tokens) is intentionally excluded.
_LEDGER_SAFE = ("ts", "action", "entity_type", "entity_id", "from_state", "to_state", "actor")


@router.get("/diagnostics/support-bundle")
async def support_bundle(tz: str = "UTC", uid: str = CurrentUser):
    """Sanitized diagnostics for QA/pilot support. Contains only IDs, status codes and
    timestamps — never passwords, tokens, API keys, SMTP creds, audio, transcripts,
    documents, email content, or other users' data."""
    diag = await diagnostics(tz=tz, uid=uid)
    raw = await db.ledger.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).to_list(40)
    recent_ledger = [{k: e.get(k) for k in _LEDGER_SAFE} for e in raw]
    recent_errors = [
        {"ts": e.get("ts"), "action": e.get("action"), "entity_type": e.get("entity_type")}
        for e in raw if str(e.get("action", "")).endswith(("_failed", "_revoked"))
    ]
    return {
        "generated_at": diag["generated_at"],
        "note": "Sanitized support bundle — IDs/status/timestamps only. No private content.",
        "auth": {"ok": diag["auth"]["ok"], "user_id": uid},
        "backend": diag["backend"],
        "ai_provider": diag["ai_provider"],
        "notifications": {"scheduled": diag["notifications"]["scheduled"],
                          "failed": diag["notifications"]["failed"],
                          "permission": diag["notifications"]["permission"]},
        "calendar": diag["calendar"],
        "microphone": diag["microphone"],
        "active_listening": {"status": diag["active_listening"]["status"]},
        "recording": diag["recording"],
        "uploads": diag["uploads"],
        "processing": diag["processing"],
        "last_transcription": diag["last_transcription"],
        "last_study_notes": diag["last_study_notes"],
        "timezone": diag["timezone"],
        "recent_ledger": recent_ledger,
        "recent_errors": recent_errors,
    }
