import logging
import uuid
import re
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form, Header
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

import config
import ai_service
import auth
import reliability as rel
import vectorstore as vs

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("student-assistant")

MISSING = config.validate()
if MISSING:
    logger.warning("Config incomplete (some features disabled until set): %s", ", ".join(MISSING))

from db import db


CurrentUser = Depends(auth.get_current_user)

# ---------------- helpers ----------------
def now_iso():
    return datetime.now(timezone.utc).isoformat()

def clean(doc: dict) -> dict:
    doc.pop("_id", None)
    return doc

def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None

def normalize(s: Optional[str]) -> str:
    if not s:
        return ""
    s = s.lower()
    words = {"one": "1", "two": "2", "three": "3", "four": "4", "five": "5",
             "six": "6", "seven": "7", "eight": "8", "nine": "9", "ten": "10"}
    for w, d in words.items():
        s = re.sub(rf"\b{w}\b", d, s)
    return re.sub(r"[^a-z0-9]+", " ", s).strip()

def token_overlap(a: str, b: str) -> float:
    ta, tb = set(a.split()), set(b.split())
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)

# simple in-memory rate limiter (per-IP, per-bucket)
_hits: Dict[str, list] = defaultdict(list)
def rate_limit(request: Request, bucket: str, limit: int, window: int = 60):
    ip = request.client.host if request.client else "unknown"
    _enforce(f"{bucket}:{ip}", limit, window)

def rate_limit_key(key: str, limit: int, window: int = 60):
    """Rate-limit an arbitrary subject (e.g. an account/email bucket)."""
    _enforce(key, limit, window)

def _enforce(key: str, limit: int, window: int):
    n = time.time()
    _hits[key] = [t for t in _hits[key] if n - t < window]
    if len(_hits[key]) >= limit:
        raise HTTPException(status_code=429, detail="Too many requests. Please slow down.")
    _hits[key].append(n)

async def add_timeline(uid, kind, title, subtitle=None, course=None, ref_id=None, entity=None, node="ai_interpretation"):
    item = {"id": str(uuid.uuid4()), "user_id": uid, "kind": kind, "title": title,
            "subtitle": subtitle, "course": course, "ref_id": ref_id, "entity": entity,
            "node": node, "ts": now_iso()}
    await db.timeline.insert_one(dict(item))
    return item

async def add_chunks(uid, source_type, source_id, label, course, text):
    if not text:
        return
    text = text.strip()
    parts = [text[i:i + 800] for i in range(0, len(text), 800)] or [text]
    for idx, p in enumerate(parts):
        cid = str(uuid.uuid4())
        lbl = f"{label}" + (f" (part {idx+1})" if len(parts) > 1 else "")
        await db.chunks.insert_one({
            "id": cid, "user_id": uid, "source_type": source_type,
            "source_id": source_id, "source_label": lbl,
            "course": course, "text": p, "ts": now_iso()})
        # Best-effort semantic index (only when a vector store is configured).
        if vs.enabled():
            try:
                vec = await ai_service.embed(p)
                await vs.upsert(cid, uid, vec, {"text": p, "source_label": lbl,
                                                "source_type": source_type, "source_id": source_id})
            except Exception as e:
                logger.warning("Vector upsert skipped: %s", type(e).__name__)


async def enforce_ai(uid):
    """Per-user daily AI cap (cost protection). Call before any AI provider use."""
    prefs = await get_prefs(uid)
    await rel.enforce_ai_cap(db, uid, prefs)


async def maybe_reminder(uid, ref_type, ref_id, title, when_iso):
    dt = _parse_dt(when_iso)
    if not dt:
        return None
    prefs = await get_prefs(uid)
    lead = int(prefs.get("default_reminder_min", 60) or 60)
    remind_at = (dt - timedelta(minutes=lead)).isoformat()
    return await rel.create_reminder(db, uid, ref_type=ref_type, ref_id=ref_id,
                                     title=title, remind_at=remind_at, body=f"Upcoming: {title}")

def conf_label(c: float) -> str:
    return "high" if c >= 0.90 else "medium" if c >= 0.80 else "low"

async def get_prefs(uid) -> dict:
    p = await db.prefs.find_one({"user_id": uid}, {"_id": 0})
    if p:
        # Never expose the administrative AI cap through consumer preferences (legacy docs).
        p.pop("daily_ai_limit", None)
        return p
    return {"user_id": uid, "auto_create_tasks": True, "morning_time": "07:30",
            "evening_time": "20:00", "weekly_day": "Sun", "weekly_time": "18:00",
            "default_reminder_min": 60, "quiet_start": "22:00", "quiet_end": "07:00"}

# ---------------- risk-based routing ----------------
def is_high_risk(it: dict) -> bool:
    if bool(it.get("recurring")):
        return True
    if it.get("event_type") == "exam":
        return True
    if it.get("ambiguous"):
        return True
    if it.get("is_deadline_change"):
        return True
    if it.get("possible_match"):
        return True
    return False

def route_item(it: dict, prefs: dict) -> str:
    """Return 'commit' or 'inbox' per risk-based rules."""
    conf = float(it.get("confidence", 0) or 0)
    if is_high_risk(it):
        return "inbox"
    if it.get("kind") == "event":
        return "commit" if conf >= 0.90 else "inbox"
    # task-like (task/reminder/followup)
    if conf >= 0.90 and prefs.get("auto_create_tasks", True):
        return "commit"
    return "inbox"

async def find_related(uid, it: dict):
    """Return (existing_doc, coll_name, certain_bool) for relationship detection."""
    course = it.get("course")
    entity = normalize(it.get("entity") or it.get("title"))
    coll = "events" if it.get("kind") == "event" else "tasks"
    if not entity:
        return None, coll, False
    q = {"user_id": uid}
    if course:
        q["course"] = course
    candidates = await db[coll].find(q, {"_id": 0}).to_list(200)
    best, best_ratio = None, 0.0
    for c in candidates:
        ne = normalize(c.get("entity") or c.get("title"))
        if ne and ne == entity:
            return c, coll, True
        r = token_overlap(entity, ne)
        if r > best_ratio:
            best, best_ratio = c, r
    if best and best_ratio >= 0.6:
        return best, coll, False  # possible match, uncertain
    return None, coll, False

async def commit_item(uid, it: dict, source="ai", commitment_id=None):
    course = it.get("course")
    existing, coll, certain = await find_related(uid, it)
    entity = it.get("entity")

    async def _finalize(ref_type, ref_id, title, when, linked=False):
        # advance the commitment state machine and schedule a reminder
        if commitment_id:
            try:
                await rel.transition(db, uid, commitment_id, "confirmed",
                                     actor=("user" if source == "review" else "ai"))
                await rel.transition(db, uid, commitment_id, "scheduled",
                                     actor=("user" if source == "review" else "ai"),
                                     ref_type=ref_type, ref_id=ref_id, detail=title)
            except rel.InvalidTransition:
                pass
        if not linked:
            await maybe_reminder(uid, ref_type, ref_id, title, when)

    if existing and certain:
        # relationship link + deadline-change audit
        new_due = it.get("datetime")
        old_due = existing.get("due") if coll == "tasks" else existing.get("start")
        upd = {}
        if coll == "tasks":
            if new_due and new_due != old_due:
                upd["due"] = new_due
                await db.audit.insert_one({"id": str(uuid.uuid4()), "user_id": uid,
                    "entity": entity, "ref_id": existing["id"], "field": "due",
                    "old": old_due, "new": new_due, "source": source, "ts": now_iso()})
            if it.get("title"):
                upd["title"] = it["title"]
        else:
            if new_due and new_due != old_due:
                upd["start"] = new_due
                await db.audit.insert_one({"id": str(uuid.uuid4()), "user_id": uid,
                    "entity": entity, "ref_id": existing["id"], "field": "start",
                    "old": old_due, "new": new_due, "source": source, "ts": now_iso()})
        if upd:
            await db[coll].update_one({"id": existing["id"], "user_id": uid}, {"$set": upd})
        await add_timeline(uid, coll[:-1], it.get("title", existing.get("title")),
                           "updated · linked", course, existing["id"], entity, node="user_action")
        await _finalize(coll[:-1], existing["id"], existing.get("title", ""), new_due or old_due, linked=True)
        doc = await db[coll].find_one({"id": existing["id"], "user_id": uid}, {"_id": 0})
        return {"type": coll[:-1], "linked": True, **doc}

    if it.get("kind") == "event":
        ev = {"id": str(uuid.uuid4()), "user_id": uid, "title": it.get("title", "Event"),
              "event_type": it.get("event_type") or "personal", "course": course,
              "start": it.get("datetime"), "end": it.get("end_datetime"),
              "location": it.get("location"), "days": it.get("days"),
              "recurring": bool(it.get("recurring")), "notes": it.get("reason"),
              "entity": entity, "external_id": None, "synced_at": None, "created_at": now_iso()}
        await db.events.insert_one(dict(ev))
        await add_timeline(uid, "event", ev["title"], ev.get("event_type"), course, ev["id"], entity, node="user_action")
        await _finalize("event", ev["id"], ev["title"], ev.get("start"))
        return {"type": "event", **clean(ev)}
    else:
        tk = {"id": str(uuid.uuid4()), "user_id": uid, "title": it.get("title", "Task"),
              "course": course, "due": it.get("datetime"),
              "priority": "high" if it.get("kind") == "reminder" else "normal",
              "category": it.get("kind", "task"), "status": "open", "entity": entity,
              "created_at": now_iso()}
        await db.tasks.insert_one(dict(tk))
        await add_timeline(uid, "task", tk["title"], tk["category"], course, tk["id"], entity, node="user_action")
        await _finalize("task", tk["id"], tk["title"], tk.get("due"))
        return {"type": "task", **clean(tk)}

def build_review(uid, source, raw, it, related_id=None, commitment_id=None):
    conf = float(it.get("confidence", 0.6) or 0.6)
    kind = it.get("kind", "task")
    label = {"event": "calendar event", "task": "task", "reminder": "reminder", "followup": "follow-up"}.get(kind, "item")
    if it.get("event_type") == "exam":
        label = "exam"
    elif it.get("event_type") in ("class", "lab"):
        label = f"recurring {it.get('event_type')}"
    reason = "possible duplicate — review" if it.get("possible_match") else \
             "recurring/high-risk — needs approval" if is_high_risk(it) else f"Add as {label}"
    return {"id": str(uuid.uuid4()), "user_id": uid, "source": source, "raw_text": raw,
            "item": it, "detected": f"I found a {label}: {it.get('title', '')}",
            "suggestion": reason, "related_id": related_id, "commitment_id": commitment_id,
            "confidence": conf, "confidence_label": conf_label(conf),
            "status": "pending", "created_at": now_iso()}

async def route_items(uid, items, source, raw, idem=None):
    prefs = await get_prefs(uid)
    committed, review = [], []
    for it in items:
        existing, _, certain = await find_related(uid, it)
        if existing and not certain:
            it["possible_match"] = True
        commitment = await rel.create_commitment(db, uid, it, source, idem=idem)
        cid = commitment["id"]
        if route_item(it, prefs) == "commit":
            rec = await commit_item(uid, it, source=source, commitment_id=cid)
            rec["auto"] = True
            committed.append(rec)
            await add_timeline(uid, "capture", f"Auto-created: {it.get('title','')}",
                               "high confidence · undo available", it.get("course"), rec.get("id"))
        else:
            rev = build_review(uid, source, raw, it, related_id=(existing or {}).get("id"), commitment_id=cid)
            await db.review.insert_one(dict(rev))
            review.append(clean(rev))
    return committed, review

async def _issue_session(user):
    uid = user["id"]
    tv = int(user.get("token_version", 0))
    access, _, exp = auth.create_token(uid, "access", minutes=config.JWT_ACCESS_MINUTES, extra={"tv": tv})
    refresh, jti, rexp = auth.create_token(uid, "refresh", days=config.JWT_REFRESH_DAYS, extra={"tv": tv})
    await db.refresh_tokens.insert_one({"jti_hash": auth.hash_jti(jti), "user_id": uid,
                                        "revoked_at": None, "expires_at": rexp})
    return {"access_token": access, "refresh_token": refresh, "expires_at": exp.isoformat(),
            "user": {"id": uid, "email": user.get("email"), "name": user.get("name"),
                     "email_verified": bool(user.get("email_verified", True))}}

async def _upsert_user(google_sub, email, name):
    existing = await db.users.find_one({"google_sub": google_sub})
    if existing:
        return {"id": existing["id"], "email": existing.get("email"), "name": existing.get("name"),
                "token_version": existing.get("token_version", 0), "email_verified": True}
    # Link to a pre-existing email/password account with the same address.
    norm = (email or "").strip().lower()
    if norm:
        by_email = await db.users.find_one({"email": norm})
        if by_email:
            await db.users.update_one({"id": by_email["id"]},
                {"$set": {"google_sub": google_sub, "email_verified": True}})
            return {"id": by_email["id"], "email": norm, "name": by_email.get("name") or name,
                    "token_version": by_email.get("token_version", 0), "email_verified": True}
    uid = str(uuid.uuid4())
    doc = {"id": uid, "google_sub": google_sub, "email": norm or email, "name": name,
           "email_verified": True, "token_version": 0, "auth_provider": "google",
           "created_at": now_iso()}
    await db.users.insert_one(doc)
    return {"id": uid, "email": norm or email, "name": name, "token_version": 0, "email_verified": True}
