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
import monetization as mon
from db import db
from core import (now_iso, clean, _parse_dt, normalize, token_overlap, rate_limit,
    add_timeline, add_chunks, enforce_ai, maybe_reminder, conf_label, get_prefs,
    is_high_risk, route_item, find_related, commit_item, build_review, route_items,
    CurrentUser, logger, _issue_session, _upsert_user)
from models import (GoogleIn, DevLoginIn, RefreshIn, CaptureIn, ImportIn, NotesIn, SearchIn, TaskIn, EventIn, ReviewActionIn, ReminderIn, ReminderStatusIn, CalendarSyncIn)

router = APIRouter(prefix="/api")

# ================= CAPTURE =================
CAPTURE_SYS = """You are an AI Academic Executive Assistant. Parse the student's message into structured commitment items.
Return ONLY strict JSON: {"items":[{"kind":"event|task|reminder|followup","title":"short imperative","course":null|string,"entity":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","recurring":bool,"ambiguous":bool,"is_deadline_change":bool,"confidence":0.0-1.0,"reason":"why"}]}
Rules: classes/labs/exams/meetings -> "event"; assignments/readings/emails/todos -> "task"; "remind me" -> "reminder"; following up with a person -> "followup".
Split multiple commitments into separate items. NEVER invent a date that was not stated; if a date is implied but unclear set datetime=null and ambiguous=true. Resolve clear relative dates (today, tomorrow, Friday) against the provided current date. "entity" = canonical name (e.g. "Assignment 2") or null. Set confidence honestly."""


@router.post("/capture")
async def capture(inp: CaptureIn, request: Request, uid: str = CurrentUser,
                  idempotency_key: Optional[str] = Header(None)):
    rate_limit(request, "ai", 60)
    cached = await rel.idem_lookup(db, uid, idempotency_key)
    if cached is not None:
        return cached
    await enforce_ai(uid)
    nowt = datetime.now(timezone.utc)
    try:
        data = await ai_service.extract_json(
            CAPTURE_SYS,
            f'Current date/time: {nowt.isoformat()} ({nowt.strftime("%A")}).\nStudent said: "{inp.text}"')
    except Exception:
        # Technical failure before a result — never permanently consume AI quota.
        await rel.refund_ai_cap(db, uid)
        raise
    items = data.get("items", []) if isinstance(data, dict) else []
    committed, review = await route_items(uid, items, "voice capture", inp.text, idem=idempotency_key)
    await add_chunks(uid, "capture", str(uuid.uuid4()), f'Capture "{inp.text[:40]}"', None, inp.text)
    result = {"committed": committed, "review": review}
    await rel.idem_store(db, uid, idempotency_key, "capture", result)
    return result

# ================= IMPORT (Capture Anything) =================
IMPORT_SYS = """You are an AI Academic Executive Assistant. The student uploaded a document/image without labeling it.
FIRST classify doc_type: schedule, syllabus, assignment, exam_schedule, email, lecture_slide, whiteboard, document, screenshot, other.
THEN extract every academic item and also return the faithfully extracted plain text.
Return ONLY strict JSON: {"doc_type":string,"extracted_text":string,"items":[{"kind":"event|task","title":string,"course":null|string,"entity":null|string,"datetime":ISO8601|null,"end_datetime":ISO8601|null,"location":null|string,"event_type":"class|lab|exam|assignment|meeting|study|personal","days":["Mon"]|null,"recurring":bool,"ambiguous":bool,"page":null|number,"confidence":0.0-1.0,"reason":string}]}
Schedules -> recurring class/lab events with days & times. Syllabus/assignment sheets -> assignments/exams/readings with due dates and page numbers. Emails -> deadline changes (set is_deadline_change), room changes, cancellations, meetings, announcements. NEVER invent dates; set datetime=null and ambiguous=true if unclear."""


@router.post("/import")
async def import_doc(inp: ImportIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 30)
    await enforce_ai(uid)
    if inp.image_base64 and len(inp.image_base64) > config.MAX_UPLOAD_MB * 1024 * 1024 * 1.4:
        raise HTTPException(status_code=413, detail=f"File too large (max {config.MAX_UPLOAD_MB} MB)")
    if not inp.image_base64 and not inp.text:
        raise HTTPException(status_code=400, detail="Provide an image or text to import")
    # Meter: 1 AI import + 1 page (single image/text = 1 page). Refund if the AI op fails.
    h_imp, h_pg, _ = await mon.reserve_import(uid, 1)
    nowt = datetime.now(timezone.utc)
    user_msg = f"Current date: {nowt.isoformat()} ({nowt.strftime('%A')}). Classify and extract."
    if inp.text:
        user_msg += f"\n\nDocument text:\n{inp.text[:15000]}"
    try:
        data = await ai_service.extract_json(IMPORT_SYS, user_msg, image_b64=inp.image_base64)
    except Exception:
        await mon.refund(h_imp); await mon.refund(h_pg); await rel.refund_ai_cap(db, uid)
        raise
    await mon.record_usage(h_imp, op="import", model=config.OPENAI_MODEL_VISION, pages=1)
    await mon.record_usage(h_pg, op="import_pages", model=config.OPENAI_MODEL_VISION, pages=1)
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
        commitment = await rel.create_commitment(db, uid, it, f"import:{doc_type}")
        rev = build_review(uid, f"import:{doc_type}", f"Imported from {doc_type}", it,
                           related_id=(existing or {}).get("id"), commitment_id=commitment["id"])
        rev["source_ref"] = {"source_id": src_id, "page": it.get("page")}
        await db.review.insert_one(dict(rev))
        review.append(clean(rev))
    await db.imports.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "kind": doc_type,
                                 "source_id": src_id, "count": len(review), "created_at": now_iso()})
    await add_timeline(uid, "import", f"Imported {doc_type}", f"{len(review)} items detected", ref_id=src_id, node="source_material")
    return {"doc_type": doc_type, "source_id": src_id, "review": review}

@router.get("/source/{sid}")
async def get_source(sid: str, uid: str = CurrentUser):
    doc = await db.source_docs.find_one({"id": sid, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Source not found")
    return doc

def extract_text_from_file(filename: str, data: bytes):
    """Returns (text, page_count). Raises 415 for unsupported types."""
    name = (filename or "").lower()
    if name.endswith(".txt"):
        return data.decode("utf-8", "ignore"), None
    if name.endswith(".pdf"):
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        pages = [(i + 1, (pg.extract_text() or "")) for i, pg in enumerate(reader.pages)]
        return "\n".join(f"[page {n}]\n{t}" for n, t in pages), len(pages)
    if name.endswith(".docx"):
        import io
        from docx import Document
        doc = Document(io.BytesIO(data))
        return "\n".join(p.text for p in doc.paragraphs if p.text), None
    raise HTTPException(status_code=415, detail="Unsupported file type. Use PDF, DOCX, TXT, or an image.")


@router.post("/import/file")
async def import_file(request: Request, uid: str = CurrentUser, file: UploadFile = File(...)):
    """Capture Anything for real documents (PDF/DOCX/TXT). Extracts text locally,
    stores the source + searchable chunks, then (if AI configured) auto-classifies
    and routes detected items to the AI Inbox. Never silently fails."""
    rate_limit(request, "ai", 30)
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"File too large (max {config.MAX_UPLOAD_MB} MB)")
    text, pages = extract_text_from_file(file.filename, raw)
    if not text.strip():
        raise HTTPException(status_code=422, detail="No readable text found in this file.")
    src_id = str(uuid.uuid4())
    await db.source_docs.insert_one({"id": src_id, "user_id": uid, "doc_type": "document",
        "filename": file.filename, "pages": pages, "text": text, "has_image": False,
        "created_at": now_iso()})
    await add_chunks(uid, "source_doc", src_id, f"{file.filename}", None, text)
    review, ai_extracted, ai_error = [], False, None
    nowt = datetime.now(timezone.utc)
    h_imp = h_pg = None
    try:
        await enforce_ai(uid)
        h_imp, h_pg, _ = await mon.reserve_import(uid, pages or 1)
        data = await ai_service.extract_json(
            IMPORT_SYS,
            f"Current date: {nowt.isoformat()} ({nowt.strftime('%A')}). Classify and extract.\n\nDocument text:\n{text[:15000]}")
        doc_type = (data.get("doc_type") if isinstance(data, dict) else None) or "document"
        for it in (data.get("items", []) if isinstance(data, dict) else []):
            existing, _, certain = await find_related(uid, it)
            if existing and not certain:
                it["possible_match"] = True
            commitment = await rel.create_commitment(db, uid, it, f"import:{doc_type}")
            rev = build_review(uid, f"import:{doc_type}", f"Imported from {file.filename}", it,
                               related_id=(existing or {}).get("id"), commitment_id=commitment["id"])
            rev["source_ref"] = {"source_id": src_id, "page": it.get("page")}
            await db.review.insert_one(dict(rev))
            review.append(clean(rev))
        await db.source_docs.update_one({"id": src_id}, {"$set": {"doc_type": doc_type}})
        await mon.record_usage(h_imp, op="import_file", model=config.OPENAI_MODEL_JSON, pages=h_pg["amount"])
        await mon.record_usage(h_pg, op="import_file_pages", model=config.OPENAI_MODEL_JSON, pages=h_pg["amount"])
        ai_extracted = True
    except ai_service.AIError as e:
        if h_imp:
            await mon.refund(h_imp)
        if h_pg:
            await mon.refund(h_pg)
        await rel.refund_ai_cap(db, uid)
        ai_error = e.category
    await db.imports.insert_one({"id": str(uuid.uuid4()), "user_id": uid, "kind": "file",
        "source_id": src_id, "count": len(review), "created_at": now_iso()})
    await add_timeline(uid, "import", f"Imported file: {file.filename}",
                       (f"{len(review)} items detected" if ai_extracted else "text saved · AI extraction pending"),
                       ref_id=src_id, node="source_material")
    return {"source_id": src_id, "filename": file.filename, "pages": pages,
            "chars": len(text), "ai_extracted": ai_extracted, "ai_error": ai_error, "review": review}


# ================= TRANSCRIBE + STUDY NOTES =================
@router.post("/transcribe")
async def transcribe_audio(request: Request, uid: str = CurrentUser, file: UploadFile = File(...),
                           course: Optional[str] = Form(None), title: Optional[str] = Form("Lecture"),
                           duration_seconds: Optional[float] = Form(None)):
    rate_limit(request, "ai", 30)
    await enforce_ai(uid)
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(status_code=413, detail=f"Audio too large (max {config.MAX_UPLOAD_MB} MB)")
    # Enforce single-recording cap and meter shared audio minutes.
    minutes = mon.minutes_ceil(duration_seconds) if duration_seconds else 1
    cap = mon.max_recording_minutes((await mon.resolve_entitlement(uid))["plan"])
    if minutes > cap:
        raise HTTPException(status_code=413, detail={
            "error": "recording_too_long", "max_minutes": cap,
            "message": f"Single recordings are limited to {cap} minutes."})
    handle = await mon.reserve(uid, "audio_minutes", minutes)
    try:
        text = await ai_service.transcribe(raw, filename=file.filename or "audio.m4a")
    except Exception:
        await mon.refund(handle)
        await rel.refund_ai_cap(db, uid)
        raise
    await mon.record_usage(handle, op="transcribe", model=config.OPENAI_MODEL_TRANSCRIBE,
                           audio_minutes=minutes, file_size=len(raw), settle_amount=minutes)
    tid = str(uuid.uuid4())
    await db.transcripts.insert_one({"id": tid, "user_id": uid, "title": title, "course": course,
                                     "text": text, "created_at": now_iso(),
                                     "raw_audio_pending_delete_at": (datetime.now(timezone.utc) + timedelta(hours=config.RAW_AUDIO_RETENTION_HOURS)).isoformat()})
    await add_chunks(uid, "transcript", tid, f"{title} transcript", course, text)
    return {"transcript_id": tid, "text": text}

NOTES_SYS = """You are an expert academic assistant creating high-quality study notes (NOT a plain summary). Reorganize the transcript using strong study-note practices. Remove filler/false-starts/repetition. NEVER invent concepts, professor statements, dates, or exam topics — flag unclear material instead.
Return ONLY strict JSON with only sections supported by the content: {"overview":string,"learning_objectives":[string],"key_concepts":[string],"definitions":[{"term":string,"definition":string}],"examples":[string],"relationships":[string],"processes":[string],"important_dates":[string],"professor_emphasis":[string],"likely_exam_topics":[string],"questions_raised":[string],"action_items":[string],"review_recommendations":[string],"unclear_flags":[string]}"""


@router.post("/notes/generate")
async def generate_notes(inp: NotesIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 30)
    await enforce_ai(uid)
    try:
        data = await ai_service.extract_json(NOTES_SYS, f"Course: {inp.course or 'General'}\nTitle: {inp.title}\nTranscript:\n{inp.transcript[:20000]}")
    except Exception:
        await rel.refund_ai_cap(db, uid)
        raise
    note = {"id": str(uuid.uuid4()), "user_id": uid, "title": inp.title, "course": inp.course,
            "transcript": inp.transcript, "study_notes": data, "created_at": now_iso()}
    await db.notes.insert_one(dict(note))
    await add_chunks(uid, "note", note["id"], f"{inp.title} study notes", inp.course,
                     inp.transcript + " " + " ".join(str(v) for v in (data.values() if isinstance(data, dict) else [])))
    await add_timeline(uid, "note", inp.title, "AI study notes generated", inp.course, note["id"], node="ai_interpretation")
    return clean(note)

@router.get("/notes")
async def list_notes(uid: str = CurrentUser):
    return await db.notes.find({"user_id": uid}, {"_id": 0, "transcript": 0}).sort("created_at", -1).to_list(200)

@router.get("/notes/{nid}")
async def get_note(nid: str, uid: str = CurrentUser):
    doc = await db.notes.find_one({"id": nid, "user_id": uid}, {"_id": 0})
    if not doc:
        raise HTTPException(status_code=404, detail="Note not found")
    return doc

# ================= SEARCH (source-grounded, chunked retrieval) =================

@router.post("/search")
async def search(inp: SearchIn, request: Request, uid: str = CurrentUser):
    rate_limit(request, "ai", 60)
    top, mode = [], "keyword"
    # 1) Semantic retrieval via the vector store when configured.
    if vs.enabled():
        try:
            await enforce_ai(uid)
            vec = await ai_service.embed(inp.query)
            hits = await vs.search(uid, vec, limit=6)
            if hits:
                top = [{"source_label": h.get("source_label", "source"), "text": h.get("text", "")} for h in hits]
                mode = "semantic"
        except HTTPException:
            raise
        except Exception as e:
            logger.warning("Semantic search fell back to keyword: %s", type(e).__name__)
    # 2) Keyword fallback (always available, guarantees a grounded answer).
    if not top:
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
        # Nothing to ground on — no AI call made, so no usage is consumed.
        return {"answer": "I couldn't find anything in your own materials to verify that. Try capturing or importing the relevant document.", "citations": [], "mode": mode}
    if mode == "keyword":
        await enforce_ai(uid)  # count the answer-generation call once
    # Meter the AI Memory answer against the entitlement (refund if generation fails).
    handle = await mon.reserve(uid, "memory_question", 1)
    context = "\n\n".join(f"[Source: {c['source_label']}]\n{c['text']}" for c in top)
    sys = "You answer ONLY from the provided sources (the student's own data). Cite the exact [Source: ...] label after each fact. If the sources don't contain the answer, say you cannot verify it. Never invent facts. Respond in plain text (this is JSON-free)."
    try:
        answer = await ai_service.complete_text(sys, f"Question: {inp.query}\n\nSources:\n{context}")
    except Exception:
        await mon.refund(handle)
        await rel.refund_ai_cap(db, uid)
        raise
    await mon.record_usage(handle, op="memory_question", model=config.OPENAI_MODEL_JSON)
    citations = [{"label": c["source_label"], "snippet": c["text"][:160]} for c in top]
    return {"answer": answer, "citations": citations, "mode": mode}
