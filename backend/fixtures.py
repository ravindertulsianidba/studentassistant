"""Deterministic, offline AI provider used for pipeline testing when a live
OpenAI key is unavailable. It is rule-based (NO network, NO randomness) so the
capture → commitment → reminder → calendar pipeline can be exercised and
asserted end-to-end. Output is intentionally simple but well-formed.

IMPORTANT: This is NOT a substitute for the live model. It exists so the
reliability backend can be tested deterministically. Live AI quality
(extraction accuracy, transcription, study notes) must be re-validated against
the real provider once a funded key is supplied.
"""
import hashlib
import re
from datetime import datetime, timedelta, timezone

WEEKDAYS = {"monday": 0, "mon": 0, "tuesday": 1, "tue": 1, "wednesday": 2, "wed": 2,
            "thursday": 3, "thu": 3, "friday": 4, "fri": 4, "saturday": 5, "sat": 5,
            "sunday": 6, "sun": 6}


def _anchor(user: str) -> datetime:
    m = re.search(r"Current date(?:/time)?:\s*([0-9T:\-\.\+]+)", user)
    if m:
        try:
            return datetime.fromisoformat(m.group(1).replace("Z", "+00:00"))
        except Exception:
            pass
    return datetime.now(timezone.utc)


def _resolve_dt(text: str, anchor: datetime):
    t = text.lower()
    base = None
    if "today" in t:
        base = anchor
    elif "tomorrow" in t:
        base = anchor + timedelta(days=1)
    else:
        for name, idx in WEEKDAYS.items():
            if re.search(rf"\b{name}\b", t):
                delta = (idx - anchor.weekday()) % 7
                delta = delta or 7
                base = anchor + timedelta(days=delta)
                break
    if base is None:
        return None
    hour, minute = 9, 0
    tm = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", t)
    if tm:
        hour = int(tm.group(1)) % 12
        if tm.group(3) == "pm":
            hour += 12
        minute = int(tm.group(2) or 0)
    return base.replace(hour=hour, minute=minute, second=0, microsecond=0).isoformat()


def _classify_kind(text: str):
    t = text.lower()
    if re.search(r"\bremind\b", t):
        return "reminder", "personal"
    if re.search(r"\b(lab)\b", t):
        return "event", "lab"
    if re.search(r"\bexam|midterm|final\b", t):
        return "event", "exam"
    if re.search(r"\b(class|lecture|room|meeting|meet)\b", t):
        return "event", "class" if "class" in t or "lecture" in t else "meeting"
    if re.search(r"\b(email|call|follow up|follow-up|reach out)\b", t):
        return "followup", "personal"
    return "task", "assignment" if "assignment" in t or "homework" in t else "personal"


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(i'?ll|i have|i need to|please|remind me to|remember to)\s+", "", text, flags=re.I)
    return text[:80].strip().capitalize() or "Untitled"


def _split(text: str):
    parts = re.split(r"[\n;]+|\band then\b|\balso\b", text)
    return [p.strip() for p in parts if len(p.strip()) > 3] or [text.strip()]


def _parse_commitments(raw: str, anchor: datetime):
    items = []
    for seg in _split(raw):
        kind, ev = _classify_kind(seg)
        dt = _resolve_dt(seg, anchor)
        ambiguous = bool(re.search(r"\b(maybe|sometime|soon|later)\b", seg.lower())) or (dt is None and bool(re.search(r"\b(next|this)\b", seg.lower())))
        conf = 0.6 if ambiguous else 0.92
        items.append({
            "kind": kind, "title": _clean_title(seg),
            "course": None, "entity": _clean_title(seg),
            "datetime": dt, "end_datetime": None, "location": None,
            "event_type": ev, "days": None, "recurring": False,
            "ambiguous": ambiguous, "is_deadline_change": False,
            "confidence": conf, "reason": "fixture rule-based extraction"})
    return items


def extract_json(system: str, user: str, image_b64=None) -> dict:
    anchor = _anchor(user)
    s = system.lower()
    # weekly review
    if "weekly review" in s:
        return {"summary": "Deterministic fixture weekly review.", "busy_days": [],
                "workload": "moderate", "recommendations": ["Start with the nearest deadline."]}
    # study notes
    if "study notes" in s:
        body = user[:400]
        return {"overview": f"Fixture study notes for: {body[:120]}",
                "key_concepts": ["Concept A (fixture)", "Concept B (fixture)"],
                "definitions": [{"term": "Term", "definition": "Fixture definition."}],
                "action_items": ["Review the transcript"], "unclear_flags": []}
    # import / classify-and-extract (has 'classify')
    if "classify" in s or "doc_type" in s:
        m = re.search(r"Document text:\s*(.*)", user, re.S)
        text = (m.group(1) if m else user)[:4000]
        items = _parse_commitments(text, anchor)
        for it in items:
            it["page"] = 1
        return {"doc_type": "document", "extracted_text": text, "items": items}
    # default: capture
    m = re.search(r'Student said:\s*"(.*)"', user, re.S)
    raw = m.group(1) if m else user
    return {"items": _parse_commitments(raw, anchor)}


def complete_text(system: str, user: str) -> str:
    m = re.search(r"Sources:\s*(.*)", user, re.S)
    src = (m.group(1).strip() if m else "")
    first = src.split("\n\n")[0] if src else ""
    q = ""
    qm = re.search(r"Question:\s*(.*)", user)
    if qm:
        q = qm.group(1).strip()
    if not first:
        return "I couldn't find anything in your materials to verify that. (fixture)"
    return f"Based on your materials: {first[:220]} (fixture answer for: {q[:60]})"


def transcribe(file_bytes: bytes, filename: str = "audio.m4a") -> str:
    digest = hashlib.sha256(file_bytes).hexdigest()[:8]
    kb = max(1, len(file_bytes) // 1024)
    return (f"[FIXTURE TRANSCRIPT — no live model] Recording '{filename}' "
            f"({kb} KB, sig {digest}). Replace with real Whisper output once a "
            f"funded OpenAI key is provided.")


def embed(text: str, dim: int = 384):
    """Deterministic pseudo-embedding from token hashes (unit-normalized)."""
    vec = [0.0] * dim
    for tok in re.findall(r"[a-z0-9]+", (text or "").lower()):
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        vec[h % dim] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]
