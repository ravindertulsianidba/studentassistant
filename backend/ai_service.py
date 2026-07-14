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


class AIError(Exception):
    pass


_client = None


def provider() -> str:
    return config.AI_PROVIDER


def _get_client():
    global _client
    if not config.OPENAI_API_KEY:
        raise AIError("AI is not configured: OPENAI_API_KEY is missing.")
    if AsyncOpenAI is None:
        raise AIError("openai package not installed")
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


def _fatal(e: Exception) -> bool:
    """Non-retryable: quota exhausted or bad key."""
    msg = str(getattr(e, "message", "") or e)
    status = getattr(e, "status_code", None)
    return ("insufficient_quota" in msg or "invalid_api_key" in msg
            or status in (401, 402))


def _friendly(e: Exception) -> str:
    msg = str(getattr(e, "message", "") or e)
    status = getattr(e, "status_code", None)
    if "insufficient_quota" in msg:
        return "AI provider quota exceeded — add billing/credits to your OpenAI account."
    if status == 401 or "invalid_api_key" in msg:
        return "Invalid OpenAI API key."
    if status == 429:
        return "AI provider rate limit reached — please try again shortly."
    return "AI provider is temporarily unavailable."


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
        logger.error("OpenAI error (extract_json): %s", type(e).__name__)
        raise AIError(_friendly(e))
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
        logger.error("OpenAI error (complete_text): %s", type(e).__name__)
        raise AIError(_friendly(e))
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
        logger.error("OpenAI error (transcribe): %s", type(e).__name__)
        raise AIError(_friendly(e))
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
        logger.error("OpenAI error (embed): %s", type(e).__name__)
        raise AIError(_friendly(e))
    return resp.data[0].embedding
