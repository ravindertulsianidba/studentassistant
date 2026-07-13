from fastapi import FastAPI, APIRouter, HTTPException
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os, logging, uuid, json, re
from pathlib import Path
from pydantic import BaseModel, Field
from typing import List, Optional, Any, Dict
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage, ImageContent, TextDelta, StreamDone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]
EMERGENT_LLM_KEY = os.environ.get('EMERGENT_LLM_KEY', '')
MODEL = ("anthropic", "claude-sonnet-4-6")

app = FastAPI()
api_router = APIRouter(prefix="/api")
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


async def llm_json(system: str, user: str, image_b64: Optional[str] = None) -> Any:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=str(uuid.uuid4()),
                   system_message=system).with_model(*MODEL)
    files = [ImageContent(image_base64=image_b64)] if image_b64 else []
    msg = UserMessage(text=user, file_contents=files)
    out = ""
    async for ev in chat.stream_message(msg):
        if isinstance(ev, TextDelta):
            out += ev.content
        elif isinstance(ev, StreamDone):
            break
    return _parse_json(out)


async def llm_text(system: str, user: str) -> str:
    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=str(uuid.uuid4()),
                   system_message=system).with_model(*MODEL)
    out = ""
    async for ev in chat.stream_message(UserMessage(text=user)):
        if isinstance(ev, TextDelta):
            out += ev.content
        elif isinstance(ev, StreamDone):
            break
    return out.strip()


def _parse_json(raw: str) -> Any:
    raw = raw.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", raw, re.DOTALL)
    if m:
        raw = m.group(1).strip()
    else:
        s = raw.find('{'); a = raw.find('[')
        start = min([x for x in [s, a] if x >= 0], default=0)
        raw = raw[start:]
        end = max(raw.rfind('}'), raw.rfind(']'))
        if end >= 0:
            raw = raw[:end + 1]
    try:
        return json.loads(raw)
    except Exception as e:
        logger.error(f"JSON parse failed: {e} :: {raw[:200]}")
        return {}


def clean(doc: dict) -> dict:
    doc.pop('_id', None)
    return doc


async def add_timeline(kind, title, subtitle=None, course=None, ref_id=None):
    item = {"id": str(uuid.uuid4()), "kind": kind, "title": title,
            "subtitle": subtitle, "course": course, "ref_id": ref_id,
            "ts": now_iso()}
    await db.timeline.insert_one(dict(item))
    return item


# ---------- Models ----------
class CaptureIn(BaseModel):
    text: str

class TaskIn(BaseModel):
    title: str
    course: Optional[str] = None
    due: Optional[str] = None
    priority: Optional[str] = "normal"
    category: Optional[str] = "general"

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

class ImportIn(BaseModel):
    image_base64: str
    kind: str  # schedule | syllabus | email

class NotesIn(BaseModel):
    title: str
    course: Optional[str] = None
    transcript: str

class SearchIn(BaseModel):
    query: str

class ReviewActionIn(BaseModel):
    action: str  # approve | ignore
    edited: Optional[Dict[str, Any]] = None


# ---------- Capture ----------
CAPTURE_SYS = """You are an AI Academic Executive Assistant for a university student.
Parse the student's natural language into structured commitment items.
Return ONLY strict JSON: {"items":[{"kind":"event|task|reminder|followup","title":"short imperative","course":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","confidence":0.0-1.0,"reason":"why"}]}
Rules: classes/labs/exams/meetings/appointments -> kind "event". Assignments/readings/emails/todos -> kind "task". "remind me" -> kind "reminder". Following up with someone -> kind "followup".
Resolve relative dates (today, tomorrow, Friday, next week) against the provided current date. confidence reflects how sure you are of the intent AND details."""

@api_router.post("/capture")
async def capture(inp: CaptureIn):
    now = datetime.now(timezone.utc)
    ctx = f"Current date/time: {now.isoformat()} ({now.strftime('%A')}).\nStudent said: \"{inp.text}\""
    data = await llm_json(CAPTURE_SYS, ctx)
    items = data.get("items", []) if isinstance(data, dict) else []
    committed, review = [], []
    for it in items:
        conf = float(it.get("confidence", 0) or 0)
        if conf >= 0.75:
            rec = await _commit_item(it, source="voice capture")
            committed.append(rec)
        else:
            rev = {"id": str(uuid.uuid4()), "source": "capture", "raw_text": inp.text,
                   "item": it, "confidence": conf, "status": "pending", "created_at": now_iso()}
            await db.review.insert_one(dict(rev))
            review.append(clean(rev))
    await add_timeline("capture", inp.text[:80], f"{len(committed)} added, {len(review)} to review")
    return {"committed": committed, "review": review}


async def _commit_item(it: dict, source="ai"):
    kind = it.get("kind", "task")
    course = it.get("course")
    if kind == "event":
        ev = {"id": str(uuid.uuid4()), "title": it.get("title", "Event"),
              "event_type": it.get("event_type") or "personal", "course": course,
              "start": it.get("datetime"), "end": it.get("end_datetime"),
              "location": it.get("location"), "days": it.get("days"),
              "recurring": bool(it.get("recurring")), "notes": it.get("reason"),
              "created_at": now_iso()}
        await db.events.insert_one(dict(ev))
        await add_timeline("event", ev["title"], ev.get("event_type"), course, ev["id"])
        return {"type": "event", **clean(ev)}
    else:
        tk = {"id": str(uuid.uuid4()), "title": it.get("title", "Task"), "course": course,
              "due": it.get("datetime"), "priority": "high" if kind in ("reminder",) else "normal",
              "category": kind, "status": "open", "created_at": now_iso()}
        await db.tasks.insert_one(dict(tk))
        await add_timeline("task", tk["title"], kind, course, tk["id"])
        return {"type": "task", **clean(tk)}


# ---------- Tasks ----------
@api_router.get("/tasks")
async def get_tasks(status: Optional[str] = None):
    q = {"status": status} if status else {}
    docs = await db.tasks.find(q, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: (d.get("due") or "9999", d.get("created_at", "")))
    return docs

@api_router.post("/tasks")
async def create_task(inp: TaskIn):
    tk = {"id": str(uuid.uuid4()), **inp.dict(), "status": "open", "created_at": now_iso()}
    await db.tasks.insert_one(dict(tk))
    await add_timeline("task", tk["title"], tk.get("category"), tk.get("course"), tk["id"])
    return clean(tk)

@api_router.patch("/tasks/{tid}")
async def update_task(tid: str, body: Dict[str, Any]):
    body.pop("id", None); body.pop("_id", None)
    await db.tasks.update_one({"id": tid}, {"$set": body})
    doc = await db.tasks.find_one({"id": tid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    return doc

@api_router.delete("/tasks/{tid}")
async def delete_task(tid: str):
    await db.tasks.delete_one({"id": tid})
    return {"ok": True}


# ---------- Events ----------
@api_router.get("/events")
async def get_events():
    docs = await db.events.find({}, {"_id": 0}).to_list(500)
    docs.sort(key=lambda d: d.get("start") or "9999")
    return docs

@api_router.post("/events")
async def create_event(inp: EventIn):
    ev = {"id": str(uuid.uuid4()), **inp.dict(), "created_at": now_iso()}
    await db.events.insert_one(dict(ev))
    await add_timeline("event", ev["title"], ev.get("event_type"), ev.get("course"), ev["id"])
    return clean(ev)

@api_router.delete("/events/{eid}")
async def delete_event(eid: str):
    await db.events.delete_one({"id": eid})
    return {"ok": True}


# ---------- Timeline ----------
@api_router.get("/timeline")
async def get_timeline(kind: Optional[str] = None, course: Optional[str] = None, q: Optional[str] = None):
    query = {}
    if kind and kind != "all":
        query["kind"] = kind
    if course:
        query["course"] = course
    docs = await db.timeline.find(query, {"_id": 0}).sort("ts", -1).to_list(300)
    if q:
        ql = q.lower()
        docs = [d for d in docs if ql in (d.get("title", "") + (d.get("subtitle") or "")).lower()]
    return docs


# ---------- Review Queue ----------
@api_router.get("/review")
async def get_review():
    return await db.review.find({"status": "pending"}, {"_id": 0}).sort("created_at", -1).to_list(200)

@api_router.post("/review/{rid}/action")
async def review_action(rid: str, body: ReviewActionIn):
    rev = await db.review.find_one({"id": rid})
    if not rev:
        raise HTTPException(404, "not found")
    result = None
    if body.action == "approve":
        item = rev.get("item", {})
        if body.edited:
            item = {**item, **body.edited}
        result = await _commit_item(item, source="review")
    await db.review.update_one({"id": rid}, {"$set": {"status": body.action}})
    return {"ok": True, "committed": result}


# ---------- Import (schedule / syllabus / email) ----------
IMPORT_SYS = """You are an AI Academic Executive Assistant. Extract structured academic items from the provided image (a screenshot/photo of a {kind}).
Return ONLY strict JSON: {"items":[{"kind":"event|task","title":string,"course":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","days":["Mon"]|null,"recurring":bool,"confidence":0.0-1.0,"reason":string}]}
For schedules: create recurring class/lab events with days & times. For syllabus: assignments/exams/readings/office hours as tasks or events with due dates. For emails: detect deadline changes, room changes, cancellations, meetings as tasks/events."""

@api_router.post("/import")
async def import_doc(inp: ImportIn):
    now = datetime.now(timezone.utc)
    sys = IMPORT_SYS.replace("{kind}", inp.kind)
    user = f"Current date: {now.isoformat()} ({now.strftime('%A')}). Extract all {inp.kind} items from this image."
    b64 = inp.image_base64.split(",")[-1]
    data = await llm_json(sys, user, image_b64=b64)
    items = data.get("items", []) if isinstance(data, dict) else []
    review = []
    for it in items:
        rev = {"id": str(uuid.uuid4()), "source": f"import:{inp.kind}", "raw_text": f"Imported from {inp.kind}",
               "item": it, "confidence": float(it.get("confidence", 0.6) or 0.6),
               "status": "pending", "created_at": now_iso()}
        await db.review.insert_one(dict(rev))
        review.append(clean(rev))
    await db.imports.insert_one({"id": str(uuid.uuid4()), "kind": inp.kind, "count": len(review), "created_at": now_iso()})
    await add_timeline("import", f"Imported {inp.kind}", f"{len(review)} items detected")
    return {"review": review}


# ---------- Study Notes ----------
NOTES_SYS = """You are an expert academic assistant creating high-quality study notes (not a plain summary). Reorganize the lecture transcript using learning best practices.
Return ONLY strict JSON: {"overview":string,"key_concepts":[string],"definitions":[{"term":string,"definition":string}],"examples":[string],"relationships":[string],"professor_emphasis":[string],"important_dates":[string],"likely_exam_topics":[string],"action_items":[string],"review_recommendations":[string]}"""

@api_router.post("/notes/generate")
async def generate_notes(inp: NotesIn):
    data = await llm_json(NOTES_SYS, f"Course: {inp.course or 'General'}\nTitle: {inp.title}\nTranscript:\n{inp.transcript}")
    note = {"id": str(uuid.uuid4()), "title": inp.title, "course": inp.course,
            "transcript": inp.transcript, "study_notes": data, "created_at": now_iso()}
    await db.notes.insert_one(dict(note))
    await add_timeline("note", inp.title, "AI study notes generated", inp.course, note["id"])
    return clean(note)

@api_router.get("/notes")
async def list_notes():
    return await db.notes.find({}, {"_id": 0, "transcript": 0}).sort("created_at", -1).to_list(200)

@api_router.get("/notes/{nid}")
async def get_note(nid: str):
    doc = await db.notes.find_one({"id": nid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "not found")
    return doc


# ---------- Search ----------
@api_router.post("/search")
async def search(inp: SearchIn):
    tasks = await db.tasks.find({}, {"_id": 0}).to_list(200)
    events = await db.events.find({}, {"_id": 0}).to_list(200)
    notes = await db.notes.find({}, {"_id": 0}).to_list(100)
    tl = await db.timeline.find({}, {"_id": 0}).sort("ts", -1).to_list(200)
    ctx = {
        "tasks": [{"title": t["title"], "due": t.get("due"), "course": t.get("course"), "status": t.get("status")} for t in tasks],
        "events": [{"title": e["title"], "type": e.get("event_type"), "start": e.get("start"), "course": e.get("course")} for e in events],
        "notes": [{"title": n["title"], "course": n.get("course"), "notes": n.get("study_notes")} for n in notes],
        "timeline": [{"title": t["title"], "kind": t.get("kind"), "ts": t.get("ts")} for t in tl],
    }
    sys = "You are the student's academic memory. Answer the question using ONLY the provided data (tasks, events, study notes, timeline). Be concise and specific with dates. If nothing relevant, say so."
    user = f"Question: {inp.query}\n\nData (JSON):\n{json.dumps(ctx)[:12000]}"
    answer = await llm_text(sys, user)
    ql = inp.query.lower()
    matches = [t for t in tl if any(w in (t.get("title", "") + (t.get("subtitle") or "")).lower() for w in ql.split() if len(w) > 3)][:10]
    return {"answer": answer, "matches": matches}


# ---------- Briefing / Weekly Review ----------
def _parse_dt(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

@api_router.get("/briefing")
async def briefing():
    now = datetime.now(timezone.utc)
    today = now.date()
    wk = now.strftime("%a")
    events = await db.events.find({}, {"_id": 0}).to_list(500)
    tasks = await db.tasks.find({"status": "open"}, {"_id": 0}).to_list(500)
    review_count = await db.review.count_documents({"status": "pending"})
    imports_count = await db.imports.count_documents({})

    today_classes = []
    for e in events:
        d = _parse_dt(e.get("start"))
        recurs = e.get("recurring") and e.get("days") and wk in [x[:3] for x in e.get("days")]
        if (d and d.date() == today) or recurs:
            today_classes.append(e)

    deadlines = []
    for t in tasks:
        d = _parse_dt(t.get("due"))
        if d and 0 <= (d.date() - today).days <= 7:
            deadlines.append(t)
    deadlines.sort(key=lambda t: t.get("due") or "9999")

    # risks
    risks = []
    by_day = {}
    for t in deadlines:
        d = _parse_dt(t.get("due"))
        if d:
            by_day.setdefault(d.date().isoformat(), []).append(t)
    for day, items in by_day.items():
        if len(items) >= 2:
            risks.append({"level": "warning", "text": f"{len(items)} deadlines due on {day}"})
    for t in deadlines:
        d = _parse_dt(t.get("due"))
        if d and (d.date() - today).days <= 2:
            risks.append({"level": "error", "text": f"Due soon: {t['title']}"})
    if not any(e.get("event_type") in ("class", "lab") for e in events):
        risks.append({"level": "info", "text": "No class schedule imported yet"})
    if imports_count == 0:
        risks.append({"level": "info", "text": "No syllabus imported — you may be missing deadlines"})
    if review_count:
        risks.append({"level": "warning", "text": f"{review_count} items waiting in your Review Queue"})

    greeting = "Good morning" if now.hour < 12 else "Good afternoon" if now.hour < 18 else "Good evening"
    return {
        "greeting": greeting,
        "date": now.strftime("%A, %B %d"),
        "stats": {"classes": len(today_classes), "deadlines": len(deadlines),
                  "open_tasks": len(tasks), "review": review_count},
        "today_classes": today_classes,
        "deadlines": deadlines[:6],
        "risks": risks[:6],
    }

@api_router.get("/weekly-review")
async def weekly_review():
    now = datetime.now(timezone.utc)
    tasks = await db.tasks.find({}, {"_id": 0}).to_list(500)
    events = await db.events.find({}, {"_id": 0}).to_list(500)
    upcoming = []
    for t in tasks:
        d = _parse_dt(t.get("due"))
        if d and 0 <= (d.date() - now.date()).days <= 7:
            upcoming.append(t)
    ctx = {
        "assignments": [{"title": t["title"], "due": t.get("due"), "course": t.get("course")} for t in upcoming],
        "events": [{"title": e["title"], "type": e.get("event_type"), "start": e.get("start")} for e in events],
    }
    sys = "You are an academic executive assistant. Given the student's next 7 days, produce a short weekly review. Return ONLY JSON: {\"summary\":string,\"busy_days\":[string],\"workload\":\"light|moderate|heavy\",\"recommendations\":[string]}"
    data = await llm_json(sys, f"Today: {now.strftime('%A %B %d')}. Data: {json.dumps(ctx)[:8000]}")
    return {"upcoming": upcoming, "review": data if isinstance(data, dict) else {}}


# ---------- Privacy / data ----------
@api_router.get("/export")
async def export_data():
    return {
        "tasks": await db.tasks.find({}, {"_id": 0}).to_list(1000),
        "events": await db.events.find({}, {"_id": 0}).to_list(1000),
        "notes": await db.notes.find({}, {"_id": 0}).to_list(1000),
        "timeline": await db.timeline.find({}, {"_id": 0}).to_list(1000),
    }

@api_router.delete("/wipe")
async def wipe():
    for c in ["tasks", "events", "notes", "timeline", "review", "imports"]:
        await db[c].delete_many({})
    return {"ok": True}

@api_router.get("/")
async def root():
    return {"message": "Student Assistant API"}


app.include_router(api_router)
app.add_middleware(CORSMiddleware, allow_credentials=True, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()
