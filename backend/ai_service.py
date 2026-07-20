"""Provider-independent AI service.

Providers (set AI_PROVIDER):
  - "openai"  : real OpenAI (chat JSON, vision OCR, Whisper, embeddings). Retries
                transient errors; surfaces friendly errors for quota/auth.
  - "fixture" : deterministic offline provider (see fixtures.py) for pipeline
                testing when no funded key is available.

Swapping providers requires ZERO code changes elsewhere — only the env var.
"""
import io
import json
import logging
from typing import Optional, List

import config
import fixtures

logger = logging.getLogger("student-assistant")

try:
    from openai import AsyncOpenAI, OpenAIError, APIStatusError
except Exception:  # pragma: no cover
    AsyncOpenAI = None
    OpenAIError = Exception
    APIStatusError = Exception

try:
    from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception
except Exception:  # pragma: no cover
    retry = None


# Single generic, provider-agnostic message shown to end users. NEVER leak the
# provider name, credential state, model, quota-account details or raw exception.
USER_MESSAGE = ("AI processing is temporarily unavailable. "
                "Try again or add the information manually.")

# Structured internal categories (safe to expose as an opaque code; carry no secret).
CATEGORIES = ("ai_unavailable", "authentication_failure", "quota_exceeded",
              "rate_limited", "timeout", "network_failure", "processing_failure")


class AIError(Exception):
    """Sanitized AI failure. `str(exc)` is ALWAYS the generic user message.
    The internal category is available via `.category` (opaque code, no secrets)."""
    def __init__(self, category: str = "ai_unavailable"):
        self.category = category if category in CATEGORIES else "processing_failure"
        super().__init__(USER_MESSAGE)


_client = None


def provider() -> str:
    return config.AI_PROVIDER


def _get_client():
    global _client
    if not config.OPENAI_API_KEY:
        # Missing configuration — treated as unavailable, never surfaced as a key error.
        raise AIError("ai_unavailable")
    if AsyncOpenAI is None:
        raise AIError("ai_unavailable")
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _classify(e: Exception) -> str:
    """Map a raw provider/transport exception to an internal category.
    Only the category (an opaque code) is ever kept; raw text is discarded."""
    msg = str(getattr(e, "message", "") or e).lower()
    status = getattr(e, "status_code", None)
    name = type(e).__name__.lower()
    if "insufficient_quota" in msg or status == 402 or "quota" in msg:
        return "quota_exceeded"
    if status == 401 or "invalid_api_key" in msg or "authentication" in msg or "api key" in msg:
        return "authentication_failure"
    if status == 429 or "rate limit" in msg or "ratelimit" in name:
        return "rate_limited"
    if "timeout" in msg or "timed out" in msg or "timeout" in name:
        return "timeout"
    if ("connection" in msg or "network" in msg or "connect" in name
            or "apiconnection" in name):
        return "network_failure"
    if status in (500, 502, 503, 504) or "server" in msg or "unavailable" in msg:
        return "ai_unavailable"
    return "processing_failure"


def _fatal(e: Exception) -> bool:
    """Non-retryable: quota exhausted or bad key/auth."""
    return _classify(e) in ("quota_exceeded", "authentication_failure")


def _ai_error(e: Exception, op: str) -> "AIError":
    """Log the internal category ONLY (never the raw provider message) and return
    a sanitized AIError."""
    cat = _classify(e)
    logger.error("AI error (%s): category=%s exc=%s", op, cat, type(e).__name__)
    return AIError(cat)


def _with_retry(coro_fn):
    """Wrap an async OpenAI call with bounded retries on transient errors."""
    if retry is None:
        return coro_fn
    return retry(
        reraise=True,
        stop=stop_after_attempt(max(1, config.AI_MAX_RETRIES)),
        wait=wait_exponential(multiplier=0.5, max=4),
        retry=retry_if_exception(lambda e: isinstance(e, OpenAIError) and not _fatal(e)),
    )(coro_fn)


# ---------------- public API ----------------
async def extract_json(system: str, user: str, image_b64: Optional[str] = None) -> dict:
    if provider() == "fixture":
        return fixtures.extract_json(system, user, image_b64)
    client = _get_client()
    model = config.OPENAI_MODEL_VISION if image_b64 else config.OPENAI_MODEL_JSON
    if image_b64:
        b = image_b64.split(",")[-1]
        content = [
            {"type": "text", "text": user},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b}", "detail": "high"}},
        ]
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
    else:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

    async def _call():
        return await client.chat.completions.create(
            model=model, messages=messages, temperature=0,
            response_format={"type": "json_object"})
    try:
        resp = await _with_retry(_call)()
    except OpenAIError as e:
        raise _ai_error(e, "extract_json")
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return {}


async def complete_text(system: str, user: str) -> str:
    if provider() == "fixture":
        return fixtures.complete_text(system, user)
    client = _get_client()

    async def _call():
        return await client.chat.completions.create(
            model=config.OPENAI_MODEL_JSON,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2)
    try:
        resp = await _with_retry(_call)()
    except OpenAIError as e:
        raise _ai_error(e, "complete_text")
    return (resp.choices[0].message.content or "").strip()


async def transcribe(file_bytes: bytes, filename: str = "audio.m4a") -> str:
    if provider() == "fixture":
        return fixtures.transcribe(file_bytes, filename)
    client = _get_client()
    f = io.BytesIO(file_bytes)
    f.name = filename

    async def _call():
        return await client.audio.transcriptions.create(
            model=config.OPENAI_MODEL_TRANSCRIBE, file=f, response_format="json")
    try:
        resp = await _with_retry(_call)()
    except OpenAIError as e:
        raise _ai_error(e, "transcribe")
    return getattr(resp, "text", "") or ""


async def embed(text: str) -> List[float]:
    if provider() == "fixture":
        return fixtures.embed(text, dim=config.EMBED_DIM)
    client = _get_client()

    async def _call():
        return await client.embeddings.create(model=config.OPENAI_MODEL_EMBED, input=text[:8000])
    try:
        resp = await _with_retry(_call)()
    except OpenAIError as e:
        raise _ai_error(e, "embed")
    return resp.data[0].embedding


# ---------------- health probe (cached; never called on every /health) ----------------
import time as _time
import asyncio as _asyncio

# Cached AI liveness. `ok` is None until the first probe completes.
_live_cache = {"ok": None, "category": None, "last_checked": None, "_ts": 0.0}
# Test/injection hook: set to an async callable returning True to force a live result
# without touching the network. Left None in production.
_probe_override = None


def set_live_status(ok: bool, category: str | None = None):
    """Record a controlled probe result (used by integration probes / tests)."""
    _live_cache.update({"ok": bool(ok), "category": category,
                        "last_checked": _iso_now(), "_ts": _time.time()})


def _iso_now() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


async def _run_probe(timeout: float = 6.0) -> dict:
    """A lightweight authenticated call to confirm the credential actually works.
    Returns {'ok': bool, 'category': str|None}. Never raises; never leaks details."""
    if provider() == "fixture":
        return {"ok": True, "category": None}
    if _probe_override is not None:
        try:
            ok = await _probe_override()
            return {"ok": bool(ok), "category": None if ok else "authentication_failure"}
        except Exception as e:  # pragma: no cover
            return {"ok": False, "category": _classify(e)}
    if not config.OPENAI_API_KEY or AsyncOpenAI is None:
        return {"ok": False, "category": "ai_unavailable"}
    try:
        client = _get_client()
        await _asyncio.wait_for(client.models.list(), timeout=timeout)
        return {"ok": True, "category": None}
    except AIError as e:
        return {"ok": False, "category": e.category}
    except _asyncio.TimeoutError:
        logger.error("AI probe: category=timeout")
        return {"ok": False, "category": "timeout"}
    except Exception as e:
        cat = _classify(e)
        logger.error("AI probe: category=%s exc=%s", cat, type(e).__name__)
        return {"ok": False, "category": cat}


async def get_live_status(ttl: float = 300.0, force: bool = False) -> dict:
    """Return cached AI liveness, refreshing at most once per `ttl` seconds.
    Shape: {ok: bool, category: str|None, last_checked: iso|None}."""
    fresh = (_live_cache["_ts"] > 0) and ((_time.time() - _live_cache["_ts"]) < ttl)
    if force or not fresh:
        res = await _run_probe()
        _live_cache.update({"ok": res["ok"], "category": res["category"],
                            "last_checked": _iso_now(), "_ts": _time.time()})
    return {"ok": _live_cache["ok"], "category": _live_cache["category"],
            "last_checked": _live_cache["last_checked"]}
