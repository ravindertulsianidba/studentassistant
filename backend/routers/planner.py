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

# ================= TASKS =================

@router.get("/tasks")
async def get_tasks(status: Optional[str] = None, uid: str = CurrentUser):
    q = {"user_id": uid}
    if status:
        q["status"] = status
    docs = await db.tasks.find(q, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: (d.get("due") or "9999", d.get("created_at", "")))
    return docs

@router.post("/tasks")
async def create_task(inp: TaskIn, uid: str = CurrentUser):
    tk = {"id": str(uuid.uuid4()), "user_id": uid, **inp.dict(), "status": "open",
          "entity": inp.title, "created_at": now_iso()}
    await db.tasks.insert_one(dict(tk))
    await add_timeline(uid, "task", tk["title"], tk.get("category"), tk.get("course"), tk["id"], node="user_action")
    return clean(tk)

@router.patch("/tasks/{tid}")
async def update_task(tid: str, body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("id", None); body.pop("_id", None); body.pop("user_id", None)
    r = await db.tasks.update_one({"id": tid, "user_id": uid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    if body.get("status") == "done":
        c = await db.commitments.find_one({"user_id": uid, "ref_id": tid, "state": "scheduled"})
        if c:
            try:
                await rel.transition(db, uid, c["id"], "completed", actor="user", detail="task done")
            except rel.InvalidTransition:
                pass
        await db.reminders.update_many(
            {"user_id": uid, "ref_id": tid, "status": {"$in": ["pending", "scheduled"]}},
            {"$set": {"status": "cancelled", "updated_at": now_iso()}})
    return await db.tasks.find_one({"id": tid, "user_id": uid}, {"_id": 0})

@router.delete("/tasks/{tid}")
async def delete_task(tid: str, uid: str = CurrentUser):
    r = await db.tasks.delete_one({"id": tid, "user_id": uid})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Task not found")
    await db.reminders.update_many(
        {"user_id": uid, "ref_id": tid, "status": {"$in": ["pending", "scheduled"]}},
        {"$set": {"status": "cancelled", "updated_at": now_iso()}})
    return {"ok": True}

# ================= EVENTS =================

@router.get("/events")
async def get_events(uid: str = CurrentUser):
    docs = await db.events.find({"user_id": uid}, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: d.get("start") or "9999")
    return docs

@router.post("/events")
async def create_event(inp: EventIn, uid: str = CurrentUser):
    ev = {"id": str(uuid.uuid4()), "user_id": uid, **inp.dict(), "entity": inp.title,
          "external_id": None, "synced_at": None, "created_at": now_iso()}
    await db.events.insert_one(dict(ev))
    await add_timeline(uid, "event", ev["title"], ev.get("event_type"), ev.get("course"), ev["id"], node="user_action")
    await maybe_reminder(uid, "event", ev["id"], ev["title"], ev.get("start"))
    return clean(ev)

@router.patch("/events/{eid}")
async def update_event(eid: str, body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("id", None); body.pop("_id", None); body.pop("user_id", None)
    r = await db.events.update_one({"id": eid, "user_id": uid}, {"$set": body})
    if r.matched_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    # if the time changed, refresh the reminder for this event
    if "start" in body:
        ev = await db.events.find_one({"id": eid, "user_id": uid}, {"_id": 0})
        await db.reminders.update_many(
            {"user_id": uid, "ref_id": eid, "status": {"$in": ["pending", "scheduled"]}},
            {"$set": {"status": "cancelled", "updated_at": now_iso()}})
        await maybe_reminder(uid, "event", eid, ev.get("title", "Event"), ev.get("start"))
    return await db.events.find_one({"id": eid, "user_id": uid}, {"_id": 0})

@router.delete("/events/{eid}")
async def delete_event(eid: str, uid: str = CurrentUser):
    r = await db.events.delete_one({"id": eid, "user_id": uid})
    if r.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Event not found")
    await db.reminders.update_many(
        {"user_id": uid, "ref_id": eid, "status": {"$in": ["pending", "scheduled"]}},
        {"$set": {"status": "cancelled", "updated_at": now_iso()}})
    return {"ok": True}

# ================= TIMELINE / MEMORY =================
@router.get("/timeline")
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
@router.get("/courses")
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

@router.get("/courses/{name}")
async def course_detail(name: str, uid: str = CurrentUser):
    return {"name": name,
            "tasks": await db.tasks.find({"user_id": uid, "course": name}, {"_id": 0}).to_list(200),
            "events": await db.events.find({"user_id": uid, "course": name}, {"_id": 0}).to_list(200),
            "notes": await db.notes.find({"user_id": uid, "course": name}, {"_id": 0, "transcript": 0}).sort("created_at", -1).to_list(200),
            "memory": await db.timeline.find({"user_id": uid, "course": name}, {"_id": 0}).sort("ts", -1).to_list(200)}

# ================= REVIEW / AI INBOX =================

@router.get("/review")
async def get_review(uid: str = CurrentUser):
    return await db.review.find({"user_id": uid, "status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)

@router.post("/review/{rid}/action")
async def review_action(rid: str, body: ReviewActionIn, uid: str = CurrentUser):
    rev = await db.review.find_one({"id": rid, "user_id": uid})
    if not rev:
        raise HTTPException(status_code=404, detail="Item not found")
    cid = rev.get("commitment_id")
    result = None
    if body.action == "approve":
        it = rev.get("item", {})
        if body.edited:
            it = {**it, **body.edited}
        it.pop("possible_match", None)
        result = await commit_item(uid, it, source="review", commitment_id=cid)
    elif body.action in ("ignore", "delete") and cid:
        try:
            await rel.transition(db, uid, cid, "dismissed", actor="user", detail=body.action)
        except rel.InvalidTransition:
            pass
    await db.review.update_one({"id": rid, "user_id": uid}, {"$set": {"status": body.action}})
    return {"ok": True, "committed": result}

# ================= BRIEFING / REVIEWS =================
@router.get("/briefing")
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

@router.get("/evening-review")
async def evening_review(uid: str = CurrentUser):
    nowt = datetime.now(timezone.utc)
    today = nowt.date()
    tasks = await db.tasks.find({"user_id": uid, "status": "open"}, {"_id": 0}).to_list(500)
    unfinished = [t for t in tasks if (_parse_dt(t.get("due")) and _parse_dt(t["due"]).date() <= today)]
    return {"date": nowt.strftime("%A, %B %d"), "unfinished": unfinished,
            "actions": ["done", "reschedule", "skip", "delete", "break_down"]}

@router.get("/weekly-review")
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
@router.get("/prefs")
async def read_prefs(uid: str = CurrentUser):
    return await get_prefs(uid)

@router.put("/prefs")
async def write_prefs(body: Dict[str, Any], uid: str = CurrentUser):
    body.pop("_id", None); body["user_id"] = uid
    await db.prefs.update_one({"user_id": uid}, {"$set": body}, upsert=True)
    return await get_prefs(uid)

@router.get("/export")
async def export_data(uid: str = CurrentUser):
    out = {}
    for c in ["tasks", "events", "notes", "timeline", "review", "source_docs", "transcripts",
              "audit", "commitments", "ledger", "reminders"]:
        out[c] = await db[c].find({"user_id": uid}, {"_id": 0}).to_list(5000)
    out["exported_at"] = now_iso()
    return out
