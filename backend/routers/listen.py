"""Phase 3C — Active Listening sessions.

The student explicitly starts a listening session; the device captures audio locally
and streams transcript text up. On stop, the transcript is run through the same
extraction pipeline as capture, routing detected commitments into the AI Inbox, and a
session summary + undo handle are produced. Every state change is written to the
reliability ledger.
"""
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

import config
import ai_service
import reliability as rel
from db import db
from core import now_iso, clean, enforce_ai, route_items, add_timeline, rate_limit, CurrentUser, logger
from models import ListenStartIn, ListenAppendIn, ListenStopIn

router = APIRouter(prefix="/api")

LISTEN_SYS = """You are transcribing a student's live lecture/meeting. From the transcript,
extract every actionable academic item (assignments, deadlines, exams, tasks, meetings,
commitments the student made). Return ONLY strict JSON:
{"items":[{"kind":"event|task","title":string,"course":null|string,"entity":null|string,
"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,
"event_type":"class|lab|exam|assignment|meeting|study|personal","days":["Mon"]|null,
"recurring":bool,"ambiguous":bool,"confidence":0.0-1.0,"reason":string}]}"""


def _uid():
    return str(uuid.uuid4())


async def _get(uid, sid):
    s = await db.listen_sessions.find_one({"id": sid, "user_id": uid}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    return s


@router.post("/listen/start")
async def start(inp: ListenStartIn, uid: str = CurrentUser):
    # Only one active session at a time.
    active = await db.listen_sessions.find_one({"user_id": uid, "status": {"$in": ["listening", "paused"]}})
    if active:
        return clean(active)
    doc = {"id": _uid(), "user_id": uid, "course": inp.course, "status": "listening",
           "started_at": now_iso(), "ended_at": None, "transcript": "", "summary": None,
           "created": {"review_ids": [], "committed": []}, "audio_uri": None}
    await db.listen_sessions.insert_one(dict(doc))
    await rel.log(db, uid, "listen_started", entity_type="listen_session", entity_id=doc["id"],
                  to_state="listening", actor="user", detail=inp.course or "")
    return clean(doc)


@router.get("/listen/active")
async def active(uid: str = CurrentUser):
    s = await db.listen_sessions.find_one({"user_id": uid, "status": {"$in": ["listening", "paused"]}}, {"_id": 0})
    return s or {}


@router.get("/listen/{sid}")
async def get_session(sid: str, uid: str = CurrentUser):
    return await _get(uid, sid)


@router.post("/listen/{sid}/pause")
async def pause(sid: str, uid: str = CurrentUser):
    await _get(uid, sid)
    await db.listen_sessions.update_one({"id": sid, "user_id": uid}, {"$set": {"status": "paused"}})
    await rel.log(db, uid, "listen_paused", entity_type="listen_session", entity_id=sid, to_state="paused", actor="user")
    return await _get(uid, sid)


@router.post("/listen/{sid}/resume")
async def resume(sid: str, uid: str = CurrentUser):
    await _get(uid, sid)
    await db.listen_sessions.update_one({"id": sid, "user_id": uid}, {"$set": {"status": "listening"}})
    await rel.log(db, uid, "listen_resumed", entity_type="listen_session", entity_id=sid, to_state="listening", actor="user")
    return await _get(uid, sid)


@router.post("/listen/{sid}/append")
async def append_text(sid: str, inp: ListenAppendIn, uid: str = CurrentUser):
    """Device streams incremental transcript text as it is captured."""
    s = await _get(uid, sid)
    upd = {}
    if inp.audio_uri:
        upd["audio_uri"] = inp.audio_uri
    if inp.text:
        upd["transcript"] = ((s.get("transcript") or "") + " " + inp.text).strip()
    if upd:
        await db.listen_sessions.update_one({"id": sid, "user_id": uid}, {"$set": upd})
    return {"ok": True}


@router.post("/listen/{sid}/stop")
async def stop(sid: str, inp: ListenStopIn, request: Request, uid: str = CurrentUser):
    s = await _get(uid, sid)
    if s["status"] == "done":
        return s
    transcript = (inp.transcript or s.get("transcript") or "").strip()
    await db.listen_sessions.update_one({"id": sid, "user_id": uid},
        {"$set": {"status": "processing", "ended_at": now_iso(),
                  "transcript": transcript, "audio_uri": inp.audio_uri or s.get("audio_uri")}})
    await rel.log(db, uid, "listen_stopped", entity_type="listen_session", entity_id=sid,
                  to_state="processing", actor="user")

    committed, review = [], []
    ai_error = None
    if transcript:
        try:
            await enforce_ai(uid)
            data = await ai_service.extract_json(
                LISTEN_SYS, f"Current time: {datetime.now(timezone.utc).isoformat()}.\nTranscript:\n{transcript[:16000]}")
            items = (data.get("items") if isinstance(data, dict) else []) or []
            committed, review = await route_items(uid, items, "active listening", transcript, idem=f"listen:{sid}")
        except HTTPException as e:
            ai_error = e.detail
        except Exception as e:
            ai_error = str(e)

    summary = {"items_detected": len(committed) + len(review), "to_inbox": len(review),
               "auto_created": len(committed), "chars": len(transcript), "ai_error": ai_error}
    created = {"review_ids": [r["id"] for r in review],
               "committed": [{"id": c.get("id"), "kind": c.get("kind") or c.get("entity"),
                              "commitment_id": c.get("commitment_id")} for c in committed]}
    await db.listen_sessions.update_one({"id": sid, "user_id": uid},
        {"$set": {"status": "done", "summary": summary, "created": created}})
    await rel.log(db, uid, "listen_processed", entity_type="listen_session", entity_id=sid,
                  to_state="done", actor="ai", detail=f"{summary['items_detected']} items")
    await add_timeline(uid, "capture", "Active Listening session processed",
                       f"{summary['items_detected']} items · {len(transcript)} chars",
                       s.get("course"), sid, node="ai_action")
    return await _get(uid, sid)


@router.post("/listen/{sid}/undo")
async def undo(sid: str, uid: str = CurrentUser):
    s = await _get(uid, sid)
    created = s.get("created") or {}
    removed = 0
    for rid in created.get("review_ids", []):
        r = await db.review.delete_one({"id": rid, "user_id": uid})
        removed += r.deleted_count
    for c in created.get("committed", []):
        for coll in ("tasks", "events"):
            r = await db[coll].delete_one({"id": c.get("id"), "user_id": uid})
            removed += r.deleted_count
        if c.get("commitment_id"):
            await db.commitments.delete_one({"id": c["commitment_id"], "user_id": uid})
    await db.listen_sessions.update_one({"id": sid, "user_id": uid},
        {"$set": {"status": "undone", "created": {"review_ids": [], "committed": []}}})
    await rel.log(db, uid, "listen_undone", entity_type="listen_session", entity_id=sid,
                  to_state="undone", actor="user", detail=f"removed {removed}")
    return {"ok": True, "removed": removed}


@router.get("/listen")
async def recent(uid: str = CurrentUser):
    docs = await db.listen_sessions.find({"user_id": uid}, {"_id": 0}).sort("started_at", -1).to_list(30)
    return docs
