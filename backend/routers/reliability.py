import uuid
import json
import re
import io
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Header
import config
import ai_service
import auth
import reliability as rel
import vectorstore as vs
from db import db
from core import (now_iso, clean, _parse_dt, normalize, token_overlap, rate_limit,
    add_timeline, add_chunks, enforce_ai, maybe_reminder, conf_label, get_prefs,
    is_high_risk, route_item, find_related, commit_item, build_review, route_items,
    CurrentUser, logger, _issue_session, _upsert_user)
from models import (GoogleIn, DevLoginIn, RefreshIn, CaptureIn, ImportIn, NotesIn, SearchIn, TaskIn, EventIn, ReviewActionIn, ReminderIn, ReminderStatusIn, CalendarSyncIn)

router = APIRouter(prefix="/api")

# ================= RELIABILITY: commitments + ledger =================
@router.get("/commitments")
async def list_commitments(state: Optional[str] = None, uid: str = CurrentUser):
    q = {"user_id": uid}
    if state:
        q["state"] = state
    return await db.commitments.find(q, {"_id": 0}).sort("updated_at", -1).to_list(500)

@router.get("/ledger")
async def get_ledger(limit: int = 200, uid: str = CurrentUser):
    limit = max(1, min(limit, 1000))
    return await db.ledger.find({"user_id": uid}, {"_id": 0}).sort("ts", -1).to_list(limit)

# ================= REMINDERS (dedicated entity) =================


@router.get("/reminders")
async def list_reminders(status: Optional[str] = None, uid: str = CurrentUser):
    q = {"user_id": uid}
    if status:
        q["status"] = status
    return await db.reminders.find(q, {"_id": 0}).sort("remind_at", 1).to_list(1000)

@router.post("/reminders")
async def create_reminder_ep(inp: ReminderIn, uid: str = CurrentUser):
    return await rel.create_reminder(db, uid, ref_type=inp.ref_type or "manual",
                                     ref_id=inp.ref_id, title=inp.title, remind_at=inp.remind_at,
                                     body=inp.body, actor="user")

@router.post("/reminders/{rid}/status")
async def reminder_status(rid: str, inp: ReminderStatusIn, uid: str = CurrentUser):
    return await rel.set_reminder_status(db, uid, rid, inp.status, external_id=inp.external_id,
                                         snooze_until=inp.snooze_until, detail=inp.detail)

@router.patch("/reminders/{rid}")
async def patch_reminder(rid: str, body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("id", None); body.pop("_id", None); body.pop("user_id", None)
    body["updated_at"] = now_iso()
    r = await db.reminders.update_one({"id": rid, "user_id": uid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Reminder not found")
    return await db.reminders.find_one({"id": rid, "user_id": uid}, {"_id": 0})

@router.get("/reminders/sync")
async def reminders_sync(uid: str = CurrentUser):
    """The device calls this on launch/foreground (and after reboot) to (re)build
    its local schedule: all reminders that should still fire, plus repeating routines."""
    pending = await db.reminders.find(
        {"user_id": uid, "status": {"$in": ["pending", "scheduled", "snoozed"]}},
        {"_id": 0}).sort("remind_at", 1).to_list(1000)
    prefs = await get_prefs(uid)
    return {"reminders": pending, "routines": rel.routine_specs(prefs),
            "quiet_hours": {"start": prefs.get("quiet_start"), "end": prefs.get("quiet_end")},
            "server_time": now_iso()}

@router.get("/reminders/health")
async def reminders_health(uid: str = CurrentUser):
    counts = {}
    for st in ["pending", "scheduled", "delivered", "snoozed", "failed", "cancelled", "done"]:
        counts[st] = await db.reminders.count_documents({"user_id": uid, "status": st})
    return {"counts": counts, "server_time": now_iso()}

# ================= NATIVE CALENDAR SYNC =================
# Moved to routers/calendar.py (Phase 3B: provider-neutral two-way sync).

# ================= CHUNKED / RESUMABLE AUDIO UPLOAD =================
@router.post("/uploads/init")
async def upload_init(uid: str = CurrentUser, body: Optional[Dict[str, Any]] = None):
    body = body or {}
    up = {"id": str(uuid.uuid4()), "user_id": uid, "filename": body.get("filename", "lecture.m4a"),
          "title": body.get("title", "Lecture"), "course": body.get("course"),
          "total_chunks": int(body.get("total_chunks", 0) or 0), "received": [],
          "status": "open", "created_at": now_iso()}
    await db.uploads.insert_one(dict(up))
    return {"upload_id": up["id"]}

@router.post("/uploads/{upload_id}/chunk")
async def upload_chunk(upload_id: str, request: Request, uid: str = CurrentUser,
                       index: int = Form(...), file: UploadFile = File(...)):
    up = await db.uploads.find_one({"id": upload_id, "user_id": uid})
    if not up or up.get("status") != "open":
        raise HTTPException(status_code=404, detail="Upload session not found")
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Chunk too large (max {config.MAX_UPLOAD_MB} MB)")
    await db.upload_chunks.update_one(
        {"upload_id": upload_id, "index": index},
        {"$set": {"upload_id": upload_id, "user_id": uid, "index": index, "data": raw}}, upsert=True)
    if index not in up.get("received", []):
        await db.uploads.update_one({"id": upload_id}, {"$addToSet": {"received": index}})
    got = await db.upload_chunks.count_documents({"upload_id": upload_id})
    return {"ok": True, "received_count": got}  # idempotent: re-uploading a chunk is safe

@router.post("/uploads/{upload_id}/complete")
async def upload_complete(upload_id: str, request: Request, uid: str = CurrentUser):
    up = await db.uploads.find_one({"id": upload_id, "user_id": uid})
    if not up:
        raise HTTPException(status_code=404, detail="Upload session not found")
    # Idempotent: if already assembled+transcribed, return the stored result.
    if up.get("status") == "done" and up.get("transcript_id"):
        return {"transcript_id": up["transcript_id"], "text": up.get("transcript_text", ""),
                "bytes": up.get("bytes", 0)}
    chunks = await db.upload_chunks.find({"upload_id": upload_id}).sort("index", 1).to_list(100000)
    if not chunks:
        raise HTTPException(status_code=422, detail="No chunks received")
    total = up.get("total_chunks") or len(chunks)
    if len(chunks) < total:
        raise HTTPException(status_code=409, detail=f"Missing chunks: have {len(chunks)}/{total}. Re-send missing indices.")
    blob = b"".join(c["data"] for c in chunks)
    await enforce_ai(uid)
    text = await ai_service.transcribe(blob, filename=up.get("filename", "lecture.m4a"))
    tid = str(uuid.uuid4())
    await db.transcripts.insert_one({"id": tid, "user_id": uid, "title": up.get("title"),
                                     "course": up.get("course"), "text": text, "created_at": now_iso()})
    await add_chunks(uid, "transcript", tid, f"{up.get('title')} transcript", up.get("course"), text)
    await db.uploads.update_one({"id": upload_id}, {"$set": {"status": "done", "transcript_id": tid,
                                                             "transcript_text": text, "bytes": len(blob)}})
    await db.upload_chunks.delete_many({"upload_id": upload_id})
    return {"transcript_id": tid, "text": text, "bytes": len(blob)}

# ================= AI USAGE (per-user daily cap) =================
@router.get("/ai-usage")
async def ai_usage(uid: str = CurrentUser):
    prefs = await get_prefs(uid)
    return await rel.ai_usage_status(db, uid, prefs)
