"""Phase 3B — provider-neutral calendar synchronization.

The device (expo-calendar) works directly with the Android/iOS calendar provider,
which surfaces calendars synced from Google, Microsoft 365, Outlook, Exchange and
other providers. This backend is provider-agnostic: it only stores the connection
choice, the external-ID link mapping, and a read-only mirror of external events for
schedule awareness / conflict detection. All two-way reconciliation decisions live
here; the device performs the actual reads/writes.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

import reliability as rel
from db import db
from core import now_iso, _parse_dt, clean, CurrentUser, add_timeline, logger
from models import (CalendarConnectionIn, CalendarStatusIn, CalendarSyncIn, CalendarLinkIn,
    ExternalIngestIn, CalendarReviewActionIn)

router = APIRouter(prefix="/api")

VALID_STATUS = {"connected", "read_only", "syncing", "sync_failed", "permission_revoked", "disconnected"}


# ---------------- connection ----------------
async def _connection(uid: str) -> dict:
    c = await db.calendar_connection.find_one({"user_id": uid}, {"_id": 0})
    return c or {"user_id": uid, "connected": False, "access_mode": "read_write",
                 "status": "disconnected", "last_sync": None, "failure_reason": None,
                 "calendar_id": None, "calendar_title": None, "account_name": None, "provider": None}


@router.get("/calendar/connection")
async def get_connection(uid: str = CurrentUser):
    return await _connection(uid)


@router.put("/calendar/connection")
async def set_connection(inp: CalendarConnectionIn, uid: str = CurrentUser):
    if inp.access_mode not in ("read_write", "read_only"):
        raise HTTPException(status_code=422, detail="access_mode must be read_write or read_only")
    doc = {"user_id": uid, "connected": True, "calendar_id": inp.calendar_id,
           "calendar_title": inp.calendar_title, "account_name": inp.account_name,
           "provider": inp.provider, "access_mode": inp.access_mode,
           "status": "read_only" if inp.access_mode == "read_only" else "connected",
           "failure_reason": None, "last_sync": now_iso()}
    await db.calendar_connection.update_one({"user_id": uid}, {"$set": doc}, upsert=True)
    await rel.log(db, uid, "calendar_connected", entity_type="calendar", entity_id=inp.calendar_id,
                  actor="user", detail=f"{inp.provider or 'device'} · {inp.access_mode}")
    return await _connection(uid)


@router.post("/calendar/disconnect")
async def disconnect(uid: str = CurrentUser):
    await db.calendar_connection.update_one({"user_id": uid},
        {"$set": {"connected": False, "status": "disconnected", "failure_reason": None}}, upsert=True)
    await rel.log(db, uid, "calendar_disconnected", entity_type="calendar", entity_id="-", actor="user")
    return await _connection(uid)


@router.post("/calendar/status")
async def report_status(inp: CalendarStatusIn, uid: str = CurrentUser):
    if inp.status not in VALID_STATUS:
        raise HTTPException(status_code=422, detail="invalid status")
    upd = {"status": inp.status, "failure_reason": inp.failure_reason}
    if inp.status == "permission_revoked":
        upd["connected"] = False
    if inp.status in ("connected", "read_only"):
        upd["last_sync"] = now_iso()
    await db.calendar_connection.update_one({"user_id": uid}, {"$set": upd}, upsert=True)
    if inp.status in ("sync_failed", "permission_revoked"):
        await rel.log(db, uid, f"calendar_{inp.status}", entity_type="calendar", entity_id="-",
                      actor="device", detail=inp.failure_reason or "")
    return await _connection(uid)


# ---------------- outbound: SA events -> external ----------------
@router.get("/calendar/pending")
async def pending(uid: str = CurrentUser):
    """SA events that should be written externally: not yet linked, and (for safety)
    recurring events must have been approved (not sitting in the AI Inbox).
    Returns [] unless connected with read_write access."""
    conn = await _connection(uid)
    if not conn.get("connected") or conn.get("access_mode") != "read_write":
        return []
    docs = await db.events.find({"user_id": uid, "external_id": None}, {"_id": 0}).to_list(500)
    # Recurring events require prior approval — they are only present here once committed
    # (committed events are not in db.review). Filter out any without a start time.
    return [d for d in docs if d.get("start")]


@router.post("/calendar/sync")
async def sync(inp: CalendarSyncIn, uid: str = CurrentUser):
    """Device reports the external event id it created for each SA event id."""
    conn = await _connection(uid)
    synced = 0
    for internal_id, ext_id in inp.mappings.items():
        r = await db.events.update_one({"id": internal_id, "user_id": uid},
            {"$set": {"external_id": ext_id, "synced_at": now_iso()}})
        if not r.matched_count:
            continue
        synced += 1
        await db.calendar_links.update_one(
            {"user_id": uid, "internal_id": internal_id},
            {"$set": {"user_id": uid, "internal_id": internal_id, "external_id": ext_id,
                      "device_calendar_id": conn.get("calendar_id"),
                      "provider": conn.get("provider"), "account_name": conn.get("account_name"),
                      "sync_direction": "two_way", "status": "synced", "failure_reason": None,
                      "last_sync": now_iso()}}, upsert=True)
        await rel.log(db, uid, "calendar_synced", entity_type="event", entity_id=internal_id,
                      actor="device", detail=f"ext={ext_id}")
    await db.calendar_connection.update_one({"user_id": uid},
        {"$set": {"last_sync": now_iso(), "status": conn.get("status", "connected")}}, upsert=True)
    return {"ok": True, "synced": synced}


@router.post("/calendar/link")
async def link(inp: CalendarLinkIn, uid: str = CurrentUser):
    """Idempotent link upsert (safe on retries — keyed by internal_id)."""
    await db.events.update_one({"id": inp.internal_id, "user_id": uid},
        {"$set": {"external_id": inp.external_id, "synced_at": now_iso()}})
    await db.calendar_links.update_one(
        {"user_id": uid, "internal_id": inp.internal_id},
        {"$set": {"user_id": uid, "internal_id": inp.internal_id, "external_id": inp.external_id,
                  "device_calendar_id": inp.device_calendar_id, "provider": inp.provider,
                  "account_name": inp.account_name, "sync_direction": inp.sync_direction,
                  "status": "synced", "failure_reason": None, "last_sync": now_iso()}}, upsert=True)
    return {"ok": True}


@router.post("/calendar/unlink/{eid}")
async def unlink(eid: str, uid: str = CurrentUser):
    """Failure recovery: the external event vanished/failed — allow a safe re-create."""
    await db.events.update_one({"id": eid, "user_id": uid},
                               {"$set": {"external_id": None, "synced_at": None}})
    await db.calendar_links.delete_one({"user_id": uid, "internal_id": eid})
    await rel.log(db, uid, "calendar_unlinked", entity_type="event", entity_id=eid, actor="device")
    return {"ok": True}


# ---------------- inbound: external -> SA (read-awareness + reconciliation) ----------------
def _is_high_risk_event(ev: dict) -> bool:
    return bool(ev.get("recurring")) or ev.get("event_type") == "exam"


async def _queue_review(uid, kind, internal_id, external_id, detail, proposed=None):
    doc = {"id": str(uuid.uuid4()), "user_id": uid, "kind": kind,
           "internal_id": internal_id, "external_id": external_id,
           "detail": detail, "proposed": proposed or {}, "status": "pending",
           "created_at": now_iso()}
    await db.calendar_review.insert_one(dict(doc))
    return clean(doc)


@router.post("/calendar/external/ingest")
async def ingest(inp: ExternalIngestIn, uid: str = CurrentUser):
    """Mirror external events for schedule awareness, reconcile linked-event edits,
    and detect external deletions. Non-SA events are stored read-only (never become
    tasks or Memory entries). High-risk changes are queued for user confirmation."""
    conn = await _connection(uid)
    seen_ext = set()
    updated_links, awareness, reviews = 0, 0, 0

    # Preload links for this user (external_id -> internal_id).
    links = await db.calendar_links.find({"user_id": uid}, {"_id": 0}).to_list(1000)
    link_by_ext = {l["external_id"]: l for l in links}

    for ev in inp.events:
        seen_ext.add(ev.external_id)
        base = {"user_id": uid, "external_id": ev.external_id,
                "device_calendar_id": ev.device_calendar_id or inp.device_calendar_id,
                "title": ev.title, "start": ev.start, "end": ev.end, "all_day": ev.all_day,
                "location": ev.location, "recurring": ev.recurring, "deleted": False,
                "updated_at": now_iso()}
        lk = link_by_ext.get(ev.external_id)
        base["is_sa"] = bool(lk)
        base["internal_id"] = lk["internal_id"] if lk else None
        await db.external_events.update_one({"user_id": uid, "external_id": ev.external_id},
                                            {"$set": base}, upsert=True)
        awareness += 1

        # Reconcile edits to SA-created (linked) events made directly in the external calendar.
        if lk:
            internal = await db.events.find_one({"id": lk["internal_id"], "user_id": uid}, {"_id": 0})
            if not internal:
                continue
            changed = {}
            if ev.title and ev.title != internal.get("title"):
                changed["title"] = ev.title
            if ev.start and ev.start != internal.get("start"):
                changed["start"] = ev.start
            if ev.end and ev.end != internal.get("end"):
                changed["end"] = ev.end
            if not changed:
                continue
            time_change = "start" in changed or "end" in changed
            if _is_high_risk_event(internal) or time_change:
                # Require confirmation — do NOT auto-apply.
                await _queue_review(uid, "external_edit", lk["internal_id"], ev.external_id,
                    f"'{internal.get('title')}' was changed in your calendar.", proposed=changed)
                reviews += 1
            else:
                await db.events.update_one({"id": lk["internal_id"], "user_id": uid}, {"$set": changed})
                await db.audit.insert_one({"id": str(uuid.uuid4()), "user_id": uid,
                    "entity": internal.get("entity"), "ref_id": lk["internal_id"],
                    "field": ",".join(changed.keys()), "old": internal.get("title"),
                    "new": ev.title, "source": "calendar_external", "ts": now_iso()})
                await db.calendar_links.update_one({"user_id": uid, "internal_id": lk["internal_id"]},
                    {"$set": {"last_sync": now_iso(), "sync_direction": "two_way"}})
                updated_links += 1

    # Deletion detection within the reported window: any previously-seen linked external
    # event NOT in this batch is treated as an external deletion (high-risk confirmation).
    if inp.window_start or inp.window_end:
        q = {"user_id": uid, "is_sa": True, "deleted": {"$ne": True}}
        for l in links:
            if l["external_id"] in seen_ext:
                continue
            ext_row = await db.external_events.find_one({"user_id": uid, "external_id": l["external_id"]})
            if not ext_row:
                continue
            # only if it falls in the reported window
            st = ext_row.get("start")
            if inp.window_start and st and st < inp.window_start:
                continue
            if inp.window_end and st and st > inp.window_end:
                continue
            await db.external_events.update_one({"user_id": uid, "external_id": l["external_id"]},
                                                {"$set": {"deleted": True, "updated_at": now_iso()}})
            internal = await db.events.find_one({"id": l["internal_id"], "user_id": uid}, {"_id": 0})
            await _queue_review(uid, "external_delete", l["internal_id"], l["external_id"],
                f"'{(internal or {}).get('title', 'An event')}' was deleted from your calendar.")
            reviews += 1

    await db.calendar_connection.update_one({"user_id": uid},
        {"$set": {"last_sync": now_iso()}}, upsert=True)
    return {"ok": True, "awareness": awareness, "updated": updated_links, "pending_reviews": reviews}


@router.get("/calendar/external")
async def external_events(uid: str = CurrentUser):
    """Read-only mirror of external calendar events (for awareness/conflict)."""
    docs = await db.external_events.find({"user_id": uid, "deleted": {"$ne": True}},
                                         {"_id": 0}).sort("start", 1).to_list(1000)
    return docs


# ---------------- confirmations for high-risk external changes ----------------
@router.get("/calendar/review")
async def calendar_review(uid: str = CurrentUser):
    docs = await db.calendar_review.find({"user_id": uid, "status": "pending"},
                                         {"_id": 0}).sort("created_at", -1).to_list(200)
    return docs


@router.post("/calendar/review/{rid}")
async def calendar_review_action(rid: str, inp: CalendarReviewActionIn, uid: str = CurrentUser):
    r = await db.calendar_review.find_one({"id": rid, "user_id": uid})
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    if inp.approve:
        if r["kind"] == "external_edit":
            await db.events.update_one({"id": r["internal_id"], "user_id": uid},
                                       {"$set": r.get("proposed", {})})
            await add_timeline(uid, "event", "Calendar change applied",
                               "external edit · confirmed", None, r["internal_id"], node="user_action")
        elif r["kind"] == "external_delete":
            await db.events.delete_one({"id": r["internal_id"], "user_id": uid})
            await db.calendar_links.delete_one({"user_id": uid, "internal_id": r["internal_id"]})
    await db.calendar_review.update_one({"id": rid, "user_id": uid},
        {"$set": {"status": "approved" if inp.approve else "dismissed", "resolved_at": now_iso()}})
    return {"ok": True}
