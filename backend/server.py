import logging
import uuid
import re
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Any, Dict

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, UploadFile, File, Form
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel

import config
import ai_service
import auth

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("student-assistant")

MISSING = config.validate()
if MISSING:
    logger.warning("Config incomplete (some features disabled until set): %s", ", ".join(MISSING))

client = AsyncIOMotorClient(config.MONGO_URL)
db = client[config.DB_NAME]

app = FastAPI(title="Student Assistant API")
api = APIRouter(prefix="/api")

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
    key = f"{bucket}:{ip}"
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
        await db.chunks.insert_one({
            "id": str(uuid.uuid4()), "user_id": uid, "source_type": source_type,
            "source_id": source_id, "source_label": f"{label}" + (f" (part {idx+1})" if len(parts) > 1 else ""),
            "course": course, "text": p, "ts": now_iso()})

def conf_label(c: float) -> str:
    return "high" if c >= 0.90 else "medium" if c >= 0.80 else "low"

async def get_prefs(uid) -> dict:
    p = await db.prefs.find_one({"user_id": uid}, {"_id": 0})
    return p or {"user_id": uid, "auto_create_tasks": True, "morning_time": "07:30",
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

async def commit_item(uid, it: dict, source="ai"):
    course = it.get("course")
    existing, coll, certain = await find_related(uid, it)
    entity = it.get("entity")
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
        doc = await db[coll].find_one({"id": existing["id"], "user_id": uid}, {"_id": 0})
        return {"type": coll[:-1], "linked": True, **doc}

    if it.get("kind") == "event":
        ev = {"id": str(uuid.uuid4()), "user_id": uid, "title": it.get("title", "Event"),
              "event_type": it.get("event_type") or "personal", "course": course,
              "start": it.get("datetime"), "end": it.get("end_datetime"),
              "location": it.get("location"), "days": it.get("days"),
              "recurring": bool(it.get("recurring")), "notes": it.get("reason"),
              "entity": entity, "created_at": now_iso()}
        await db.events.insert_one(dict(ev))
        await add_timeline(uid, "event", ev["title"], ev.get("event_type"), course, ev["id"], entity, node="user_action")
        return {"type": "event", **clean(ev)}
    else:
        tk = {"id": str(uuid.uuid4()), "user_id": uid, "title": it.get("title", "Task"),
              "course": course, "due": it.get("datetime"),
              "priority": "high" if it.get("kind") == "reminder" else "normal",
              "category": it.get("kind", "task"), "status": "open", "entity": entity,
              "created_at": now_iso()}
        await db.tasks.insert_one(dict(tk))
        await add_timeline(uid, "task", tk["title"], tk["category"], course, tk["id"], entity, node="user_action")
        return {"type": "task", **clean(tk)}

def build_review(uid, source, raw, it, related_id=None):
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
            "suggestion": reason, "related_id": related_id, "confidence": conf,
            "confidence_label": conf_label(conf), "status": "pending", "created_at": now_iso()}

async def route_items(uid, items, source, raw):
    prefs = await get_prefs(uid)
    committed, review = [], []
    for it in items:
        existing, _, certain = await find_related(uid, it)
        if existing and not certain:
            it["possible_match"] = True
        if it.get("event_type") == "exam" or bool(it.get("recurring")):
            it.setdefault("_", None)
        if route_item(it, prefs) == "commit":
            rec = await commit_item(uid, it, source=source)
            rec["auto"] = True
            committed.append(rec)
            await add_timeline(uid, "capture", f"Auto-created: {it.get('title','')}",
                               "high confidence · undo available", it.get("course"), rec.get("id"))
        else:
            rev = build_review(uid, source, raw, it, related_id=(existing or {}).get("id"))
            await db.review.insert_one(dict(rev))
            review.append(clean(rev))
    return committed, review

# ================= AUTH =================
class GoogleIn(BaseModel):
    id_token: str

class DevLoginIn(BaseModel):
    email: str

class RefreshIn(BaseModel):
    refresh_token: str

async def _issue_session(user):
    uid = user["id"]
    access, _, exp = auth.create_token(uid, "access", minutes=config.JWT_ACCESS_MINUTES)
    refresh, jti, rexp = auth.create_token(uid, "refresh", days=config.JWT_REFRESH_DAYS)
    await db.refresh_tokens.insert_one({"jti_hash": auth.hash_jti(jti), "user_id": uid,
                                        "revoked_at": None, "expires_at": rexp})
    return {"access_token": access, "refresh_token": refresh, "expires_at": exp.isoformat(),
            "user": {"id": uid, "email": user.get("email"), "name": user.get("name")}}

async def _upsert_user(google_sub, email, name):
    existing = await db.users.find_one({"google_sub": google_sub})
    if existing:
        return {"id": existing["id"], "email": existing.get("email"), "name": existing.get("name")}
    uid = str(uuid.uuid4())
    doc = {"id": uid, "google_sub": google_sub, "email": email, "name": name, "created_at": now_iso()}
    await db.users.insert_one(doc)
    return {"id": uid, "email": email, "name": name}

@api.post("/auth/google")
async def auth_google(body: GoogleIn, request: Request):
    rate_limit(request, "auth", 20)
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured on this server.")
    try:
        info = auth.verify_google(body.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    user = await _upsert_user(info["sub"], info.get("email"), info.get("name"))
    return await _issue_session(user)

@api.post("/auth/dev-login")
async def dev_login(body: DevLoginIn, request: Request):
    """Test-only. Disabled in production (ALLOW_INSECURE_DEV=false)."""
    if not config.ALLOW_INSECURE_DEV:
        raise HTTPException(status_code=404, detail="Not found")
    rate_limit(request, "auth", 40)
    user = await _upsert_user(f"dev:{body.email}", body.email, body.email.split("@")[0])
    return await _issue_session(user)

@api.post("/auth/refresh")
async def refresh(body: RefreshIn):
    try:
        p = auth.decode(body.refresh_token)
        if p.get("typ") != "refresh":
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    row = await db.refresh_tokens.find_one({"jti_hash": auth.hash_jti(p["jti"]), "revoked_at": None})
    if not row:
        raise HTTPException(status_code=401, detail="Session revoked")
    await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                       {"$set": {"revoked_at": now_iso()}})
    uid = p["sub"]
    access, _, exp = auth.create_token(uid, "access", minutes=config.JWT_ACCESS_MINUTES)
    new_refresh, jti, rexp = auth.create_token(uid, "refresh", days=config.JWT_REFRESH_DAYS)
    await db.refresh_tokens.insert_one({"jti_hash": auth.hash_jti(jti), "user_id": uid,
                                        "revoked_at": None, "expires_at": rexp})
    return {"access_token": access, "refresh_token": new_refresh, "expires_at": exp.isoformat()}

@api.post("/auth/logout")
async def logout(body: RefreshIn):
    try:
        p = auth.decode(body.refresh_token)
        await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                           {"$set": {"revoked_at": now_iso()}})
    except Exception:
        pass
    return {"ok": True}

@api.get("/me")
async def me(uid: str = CurrentUser):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "google_sub": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

@api.delete("/me")
async def delete_account(uid: str = CurrentUser):
    for c in ["tasks", "events", "timeline", "review", "imports", "notes", "chunks",
              "audit", "prefs", "source_docs", "transcripts", "refresh_tokens"]:
        await db[c].delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True, "deleted": True}

# ================= CAPTURE =================
CAPTURE_SYS = """You are an AI Academic Executive Assistant. Parse the student's message into structured commitment items.
Return ONLY strict JSON: {"items":[{"kind":"event|task|reminder|followup","title":"short imperative","course":null|string,"entity":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","recurring":bool,"ambiguous":bool,"is_deadline_change":bool,"confidence":0.0-1.0,"reason":"why"}]}
Rules: classes/labs/exams/meetings -> "event"; assignments/readings/emails/todos -> "task"; "remind me" -> "reminder"; following up with a person -> "followup".
Split multiple commitments into separate items. NEVER invent a date that was not stated; if a date is implied but unclear set datetime=null and ambiguous=true. Resolve clear relative dates (today, tomorrow, Friday) against the provided current date. "entity" = canonical name (e.g. "Assignment 2") or null. Set confidence honestly."""

class CaptureIn(BaseModel):
    text: str

@api.post("/capture")
async def capture(inp: CaptureIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 60)
    nowt = datetime.now(timezone.utc)
    data = await ai_service.extract_json(
        CAPTURE_SYS,
        f'Current date/time: {nowt.isoformat()} ({nowt.strftime("%A")}).\nStudent said: "{inp.text}"')
    items = data.get("items", []) if isinstance(data, dict) else []
    committed, review = await route_items(uid, items, "voice capture", inp.text)
    await add_chunks(uid, "capture", str(uuid.uuid4()), f'Capture "{inp.text[:40]}"', None, inp.text)
    return {"committed": committed, "review": review}

# ================= TASKS =================
class TaskIn(BaseModel):
    title: str
    course: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = "normal"
    category: Optional[str] = "general"

@api.get("/tasks")
async def get_tasks(status: Optional[str] = None, uid: str = CurrentUser):
    q = {"user_id": uid}
    if status:
        q["status"] = status
    docs = await db.tasks.find(q, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: (d.get("due") or "9999", d.get("created_at", "")))
    return docs

@api.post("/tasks")
async def create_task(inp: TaskIn, uid: str = CurrentUser):
    tk = {"id": str(uuid.uuid4()), "user_id": uid, **inp.dict(), "status": "open",
          "entity": inp.title, "created_at": now_iso()}
    await db.tasks.insert_one(dict(tk))
    await add_timeline(uid, "task", tk["title"], tk.get("category"), tk.get("course"), tk["id"], node="user_action")
    return clean(tk)

@api.patch("/tasks/{tid}")
async def update_task(tid: str, body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("id", None); body.pop("_id", None); body.pop("user_id", None)
    r = await db.tasks.update_one({"id": tid, "user_id": uid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return await db.tasks.find_one({"id": tid, "user_id": uid}, {"_id": 0})

@api.delete("/tasks/{tid}")
async def delete_task(tid: str, uid: str = CurrentUser):
    r = await db.tasks.delete_one({"id": tid, "user_id": uid})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    return {"ok": True}

# ================= EVENTS =================
class EventIn(BaseModel):
    title: str
    event_type: str = "personal"
    course: Optional[str] = None
    start: Optional[str] = None
    end: Optional[str] = None
    location: Optional[str] = None
    days: Optional[List[str]] = None
    recurring: bool = False
    notes: Optional[str] = None

@api.get("/events")
async def get_events(uid: str = CurrentUser):
    docs = await db.events.find({"user_id": uid}, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: d.get("start") or "9999")
    return docs

@api.post("/events")
async def create_event(inp: EventIn, uid: str = CurrentUser):
    ev = {"id": str(uuid.uuid4()), "user_id": uid, **inp.dict(), "entity": inp.title, "created_at": now_iso()}
    await db.events.insert_one(dict(ev))
    await add_timeline(uid, "event", ev["title"], ev.get("event_type"), ev.get("course"), ev["id"], node="user_action")
    return clean(ev)

@api.delete("/events/{eid}")
async def delete_event(eid: str, uid: str = CurrentUser):
    r = await db.events.delete_one({"id": eid, "user_id": uid})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    return {"ok": True}

# ================= TIMELINE / MEMORY =================
@api.get("/timeline")
async def get_timeline(kind: Optional[str] = None, course: Optional[str] = None,
                       q: Optional[str] = None, uid: str = CurrentUser):
    query = {"user_id": uid}
    if kind and kind != "all":
        query["kind"] = kind
    if course:
        query["course"] = course
    docs = await db.timeline.find(query, {"_id": 0}).sort("ts", -1).to_list(300)
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("title", "") + (d.get("subtitle") or "")).lower()]
    return docs

# ================= COURSES =================
@api.get("/courses")
async def get_courses(uid: str = CurrentUser):
    names = set()
    for coll in ["tasks", "events", "notes", "timeline"]:
        for c in await db[coll].distinct("course", {"user_id": uid}):
            if c:
                names.add(c)
    out = []
    for n in sorted(names):
        out.append({"name": n,
                    "open_tasks": await db.tasks.count_documents({"user_id": uid, "course": n, "status": "open"}),
                    "events": await db.events.count_documents({"user_id": uid, "course": n}),
                    "notes": await db.notes.count_documents({"user_id": uid, "course": n})})
    return out

@api.get("/courses/{name}")
async def course_detail(name: str, uid: str = CurrentUser):
    return {"name": name,
            "tasks": await db.tasks.find({"user_id": uid, "course": name}, {"_id": 0}).to_list(200),
            "events": await db.events.find({"user_id": uid, "course": name}, {"_id": 0}).to_list(200),
            "notes": await db.notes.find({"user_id": uid, "course": name}, {"_id": 0, "transcript": 0}).sort("created_at", -1).to_list(200),
            "memory": await db.timeline.find({"user_id": uid, "course": name}, {"_id": 0}).sort("ts", -1).to_list(200)}

# ================= REVIEW / AI INBOX =================
class ReviewActionIn(BaseModel):
    action: str
    edited: Optional[Dict[str, Any]] = None

@api.get("/review")
async def get_review(uid: str = CurrentUser):
    return await db.review.find({"user_id": uid, "status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api.post("/review/{rid}/action")
async def review_action(rid: str, body: ReviewActionIn, uid: str = CurrentUser):
    rev = await db.review.find_one({"id": rid, "user_id": uid})
    if not rev:
        raise HTTPException(status_code=404, detail="Item not found")
    result = None
    if body.action == "approve":
        it = rev.get("item", {})
        if body.edited:
            it = {**it, **body.edited}
        it.pop("possible_match", None)
        result = await commit_item(uid, it, source="review")
    await db.review.update_one({"id": rid, "user_id": uid}, {"$set": {"status": body.action}})
    return {"ok": True, "committed": result}

# ================= IMPORT (Capture Anything) =================
IMPORT_SYS = """You are an AI Academic Executive Assistant. The student uploaded a document/image without labeling it.
FIRST classify doc_type: schedule, syllabus, assignment, exam_schedule, email, lecture_slide, whiteboard, document, screenshot, other.
THEN extract every academic item and also return the faithfully extracted plain text.
Return ONLY strict JSON: {"doc_type":string,"extracted_text":string,"items":[{"kind":"event|task","title":string,"course":null|string,"entity":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","days":["Mon"]|null,"recurring":bool,"ambiguous":bool,"page":null|number,"confidence":0.0-1.0,"reason":string}]}
Schedules -> recurring class/lab events with days & times. Syllabus/assignment sheets -> assignments/exams/readings with due dates and page numbers. Emails -> deadline changes (set is_deadline_change), room changes, cancellations, meetings, announcements. NEVER invent dates; set datetime=null and ambiguous=true if unclear."""

class ImportIn(BaseModel):
    image_base64: Optional[str] = None
    text: Optional[str] = None
    kind: Optional[str] = "auto"
    filename: Optional[str] = None

@api.post("/import")
async def import_doc(inp: ImportIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 30)
    nowt = datetime.now(timezone.utc)
    if inp.image_base64 and len(inp.image_base64) > config.MAX_UPLOAD_MB * 1024 * 1024 * 1.4:
        raise HTTPException(status_code=413, detail=f"File too large (max {config.MAX_UPLOAD_MB} MB)")
    if not inp.image_base64 and not inp.text:
        raise HTTPException(status_code=400, detail="Provide an image or text to import")
    user_msg = f"Current date: {nowt.isoformat()} ({nowt.strftime('%A')}). Classify and extract."
    if inp.text:
        user_msg += f"\n\nDocument text:\n{inp.text[:15000]}"
    data = await ai_service.extract_json(IMPORT_SYS, user_msg, image_b64=inp.image_base64)
    doc_type = (data.get("doc_type") if isinstance(data, dict) else None) or (inp.kind or "document")
    extracted = (data.get("extracted_text") if isinstance(data, dict) else "") or inp.text or ""
    items = data.get("items", []) if isinstance(data, dict) else []
    src_id = str(uuid.uuid4())
    await db.source_docs.insert_one({"id": src_id, "user_id": uid, "doc_type": doc_type,
        "filename": inp.filename, "text": extracted, "has_image": bool(inp.image_base64),
        "created_at": now_iso()})
    await add_chunks(uid, "source_doc", src_id, f"{doc_type} {inp.filename or ''}".strip(), None, extracted)
    # imports are source material -> everything goes to AI Inbox (approval required)
    review = []
    for it in items:
        existing, _, certain = await find_related(uid, it)
        if existing and not certain:
            it["possible_match"] = True
        rev = build_review(uid, f"import:{doc_type}", f"Imported from {doc_type}", it,
                           related_id=(existing or {}).get("id"))
        rev["source_ref"] = {"source_id": src_id, "page": it.get("page")}
        await db.review.insert_one(dict(rev))
        review.append(clean(rev))
    await db.imports.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "kind": doc_type,
                                 "source_id": src_id, "count": len(review), "created_at": now_iso()})
    await add_timeline(uid, "import", f"Imported {doc_type}", f"{len(review)} items detected", ref_id=src_id, node="source_material")
    return {"doc_type": doc_type, "source_id": src_id, "review": review}

@api.get("/source/{sid}")
async def get_source(sid: str, uid: str = CurrentUser):
    doc = await db.source_docs.find_one({"id": sid, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")
    return doc

# ================= TRANSCRIBE + STUDY NOTES =================
@api.post("/transcribe")
async def transcribe_audio(uid: str = CurrentUser, file: UploadFile = File(...),
                           course: Optional[str] = Form(None), title: Optional[str] = Form("Lecture")):
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Audio too large (max {config.MAX_UPLOAD_MB} MB)")
    text = await ai_service.transcribe(raw, filename=file.filename or "audio.m4a")
    tid = str(uuid.uuid4())
    await db.transcripts.insert_one({"id": tid, "user_id": uid, "title": title, "course": course,
                                     "text": text, "created_at": now_iso()})
    await add_chunks(uid, "transcript", tid, f"{title} transcript", course, text)
    return {"transcript_id": tid, "text": text}

NOTES_SYS = """You are an expert academic assistant creating high-quality study notes (NOT a plain summary). Reorganize the transcript using strong study-note practices. Remove filler/false-starts/repetition. NEVER invent concepts, professor statements, dates, or exam topics — flag unclear material instead.
Return ONLY strict JSON with only sections supported by the content: {"overview":string,"learning_objectives":[string],"key_concepts":[string],"definitions":[{"term":string,"definition":string}],"examples":[string],"relationships":[string],"processes":[string],"important_dates":[string],"professor_emphasis":[string],"likely_exam_topics":[string],"questions_raised":[string],"action_items":[string],"review_recommendations":[string],"unclear_flags":[string]}"""

class NotesIn(BaseModel):
    title: str
    course: Optional[str] = None
    transcript: str

@api.post("/notes/generate")
async def generate_notes(inp: NotesIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 30)
    data = await ai_service.extract_json(NOTES_SYS, f"Course: {inp.course or 'General'}\nTitle: {inp.title}\nTranscript:\n{inp.transcript[:20000]}")
    note = {"id": str(uuid.uuid4()), "user_id": uid, "title": inp.title, "course": inp.course,
            "transcript": inp.transcript, "study_notes": data, "created_at": now_iso()}
    await db.notes.insert_one(dict(note))
    await add_chunks(uid, "note", note["id"], f"{inp.title} study notes", inp.course,
                     inp.transcript + " " + " ".join(str(v) for v in (data.values() if isinstance(data, dict) else [])))
    await add_timeline(uid, "note", inp.title, "AI study notes generated", inp.course, note["id"], node="ai_interpretation")
    return clean(note)

@api.get("/notes")
async def list_notes(uid: str = CurrentUser):
    return await db.notes.find({"user_id": uid}, {"_id": 0, "transcript": 0}).sort("created_at", -1).to_list(200)

@api.get("/notes/{nid}")
async def get_note(nid: str, uid: str = CurrentUser):
    doc = await db.notes.find_one({"id": nid, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")
    return doc

# ================= SEARCH (source-grounded, chunked retrieval) =================
class SearchIn(BaseModel):
    query: str

@api.post("/search")
async def search(inp: SearchIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 60)
    terms = [w for w in normalize(inp.query).split() if len(w) > 2]
    chunks = await db.chunks.find({"user_id": uid}, {"_id": 0}).to_list(2000)
    scored = []
    for c in chunks:
        t = c.get("text", "").lower()
        s = sum(t.count(w) for w in terms)
        if s > 0:
            scored.append((s, c))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = [c for _, c in scored[:6]]
    if not top:
        return {"answer": "I couldn't find anything in your own materials to verify that. Try capturing or importing the relevant document.", "citations": []}
    context = "\n\n".join(f"[Source: {c['source_label']}]\n{c['text']}" for c in top)
    sys = "You answer ONLY from the provided sources (the student's own data). Cite the exact [Source: ...] label after each fact. If the sources don't contain the answer, say you cannot verify it. Never invent facts. Respond in plain text (this is JSON-free)."
    answer = await ai_service.complete_text(sys, f"Question: {inp.query}\n\nSources:\n{context}")
    citations = [{"label": c["source_label"], "snippet": c["text"][:160]} for c in top]
    return {"answer": answer, "citations": citations}

# ================= BRIEFING / REVIEWS =================
@api.get("/briefing")
async def briefing(uid: str = CurrentUser):
    nowt = datetime.now(timezone.utc)
    today = nowt.date()
    wk = nowt.strftime("%a")
    events = await db.events.find({"user_id": uid}, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find({"user_id": uid, "status": "open"}, {"_id": 0}).to_list(500)
    review_count = await db.review.count_documents({"user_id": uid, "status": "pending"})
    imports_count = await db.imports.count_documents({"user_id": uid})

    today_classes = []
    for e in events:
        d = _parse_dt(e.get("start"))
        recurs = e.get("recurring") and e.get("days") and wk in [x[:3] for x in e.get("days")]
        if (d and d.date() == today) or recurs:
            today_classes.append(e)

    deadlines = [t for t in tasks if (_parse_dt(t.get("due")) and 0 <= (_parse_dt(t["due"]).date() - today).days <= 7)]
    deadlines.sort(key=lambda t: t.get("due") or "9999")

    risks = []
    for t in tasks:
        d = _parse_dt(t.get("due"))
        if d and d.date() < today:
            verb = "You promised to" if t.get("category") in ("followup", "reminder") else "Overdue —"
            risks.append({"level": "error", "text": f"{verb} {t['title']}"})
    by_day = defaultdict(list)
    for t in deadlines:
        d = _parse_dt(t.get("due"))
        if d:
            by_day[d.date().isoformat()].append(t)
    for day, its in by_day.items():
        if len(its) >= 2:
            risks.append({"level": "warning", "text": f"{len(its)} deadlines due on {day}"})
    for t in deadlines:
        d = _parse_dt(t.get("due"))
        if d and (d.date() - today).days <= 2:
            risks.append({"level": "error", "text": f"Due soon: {t['title']}"})
    if not any(e.get("event_type") in ("class", "lab") for e in events):
        risks.append({"level": "info", "text": "No class schedule imported yet"})
    if imports_count == 0:
        risks.append({"level": "info", "text": "No syllabus imported — you may be missing deadlines"})
    if review_count:
        risks.append({"level": "warning", "text": f"{review_count} items in your AI Inbox"})

    rec = None
    if deadlines:
        rec = f"Start with '{deadlines[0]['title']}' — it's your nearest deadline."
    elif review_count:
        rec = "Clear your AI Inbox so nothing slips through."

    greeting = "Good morning" if nowt.hour < 12 else "Good afternoon" if nowt.hour < 18 else "Good evening"
    return {"greeting": greeting, "date": nowt.strftime("%A, %B %d"),
            "stats": {"classes": len(today_classes), "deadlines": len(deadlines),
                      "open_tasks": len(tasks), "review": review_count},
            "today_classes": today_classes, "deadlines": deadlines[:6],
            "risks": risks[:6], "recommendation": rec}

@api.get("/evening-review")
async def evening_review(uid: str = CurrentUser):
    nowt = datetime.now(timezone.utc)
    today = nowt.date()
    tasks = await db.tasks.find({"user_id": uid, "status": "open"}, {"_id": 0}).to_list(500)
    unfinished = [t for t in tasks if (_parse_dt(t.get("due")) and _parse_dt(t["due"]).date() <= today)]
    return {"date": nowt.strftime("%A, %B %d"), "unfinished": unfinished,
            "actions": ["done", "reschedule", "skip", "delete", "break_down"]}

@api.get("/weekly-review")
async def weekly_review(uid: str = CurrentUser):
    nowt = datetime.now(timezone.utc)
    tasks = await db.tasks.find({"user_id": uid}, {"_id": 0}).to_list(500)
    events = await db.events.find({"user_id": uid}, {"_id": 0}).to_list(500)
    upcoming = [t for t in tasks if (_parse_dt(t.get("due")) and 0 <= (_parse_dt(t["due"]).date() - nowt.date()).days <= 7)]
    ctx = {"assignments": [{"title": t["title"], "due": t.get("due"), "course": t.get("course")} for t in upcoming],
           "events": [{"title": e["title"], "type": e.get("event_type"), "start": e.get("start")} for e in events]}
    import json as _json
    sys = "You are an academic executive assistant. Produce a short weekly review. Return ONLY JSON: {\"summary\":string,\"busy_days\":[string],\"workload\":\"light|moderate|heavy\",\"recommendations\":[string]}"
    try:
        data = await ai_service.extract_json(sys, f"Today: {nowt.strftime('%A %B %d')}. Data: {_json.dumps(ctx)[:8000]}")
    except Exception:
        data = {"summary": f"You have {len(upcoming)} items due this week.", "busy_days": [], "workload": "moderate", "recommendations": []}
    return {"upcoming": upcoming, "review": data if isinstance(data, dict) else {}}

# ================= PREFS / EXPORT =================
@api.get("/prefs")
async def read_prefs(uid: str = CurrentUser):
    return await get_prefs(uid)

@api.put("/prefs")
async def write_prefs(body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("_id", None); body["user_id"] = uid
    await db.prefs.update_one({"user_id": uid}, {"$set": body}, upsert=True)
    return await get_prefs(uid)

@api.get("/export")
async def export_data(uid: str = CurrentUser):
    out = {}
    for c in ["tasks", "events", "notes", "timeline", "review", "source_docs", "transcripts", "audit"]:
        out[c] = await db[c].find({"user_id": uid}, {"_id": 0}).to_list(2000)
    return out

# ================= HEALTH =================
@app.get("/api/health")
async def health():
    ok = True
    try:
        await db.command("ping")
    except Exception:
        ok = False
    return {"status": "ok" if ok else "degraded", "db": ok,
            "ai_configured": bool(config.OPENAI_API_KEY),
            "google_configured": bool(config.GOOGLE_CLIENT_ID),
            "time": now_iso()}


@app.exception_handler(ai_service.AIError)
async def ai_error(request: Request, exc: ai_service.AIError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url.path, type(exc).__name__)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


app.include_router(api)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS or ["http://localhost"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.on_event("startup")
async def startup():
    try:
        await db.users.create_index("google_sub", unique=True)
        await db.refresh_tokens.create_index("jti_hash", unique=True)
        for coll in ["tasks", "events", "timeline", "review", "notes", "chunks",
                     "imports", "source_docs", "transcripts", "audit"]:
            await db[coll].create_index("user_id")
        await db.chunks.create_index([("user_id", 1), ("source_type", 1)])
        logger.info("Indexes ready. AI=%s Google=%s", bool(config.OPENAI_API_KEY), bool(config.GOOGLE_CLIENT_ID))
    except Exception as e:
        logger.warning("Index setup issue: %s", e)


@app.on_event("shutdown")
async def shutdown():
    client.close()
