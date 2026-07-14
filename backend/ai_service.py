"""Provider-independent AI service. Swap providers by changing AI_PROVIDER env.
Currently implements OpenAI (chat JSON, vision OCR, Whisper transcription)."""
import io
import json
import logging
from typing import Optional

import config

logger = logging.getLogger("student-assistant")

try:
    from openai import AsyncOpenAI, OpenAIError
except Exception:  # pragma: no cover
    AsyncOpenAI = None
    OpenAIError = Exception


class AIError(Exception):
    pass


_client = None


def _get_client():
    global _client
    if config.AI_PROVIDER != "openai":
        raise AIError(f"Unsupported AI_PROVIDER: {config.AI_PROVIDER}")
    if not config.OPENAI_API_KEY:
        raise AIError("AI is not configured: OPENAI_API_KEY is missing. Set it in the environment.")
    if AsyncOpenAI is None:
        raise AIError("openai package not installed")
    if _client is None:
        _client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)
    return _client


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


async def extract_json(system: str, user: str, image_b64: Optional[str] = None) -> dict:
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
    try:
        resp = await client.chat.completions.create(
            model=model, messages=messages, temperature=0,
            response_format={"type": "json_object"})
    except OpenAIError as e:
        logger.error("OpenAI error (extract_json): %s", type(e).__name__)
        raise AIError(_friendly(e))
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except Exception:
        return {}


async def complete_text(system: str, user: str) -> str:
    client = _get_client()
    try:
        resp = await client.chat.completions.create(
            model=config.OPENAI_MODEL_JSON,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            temperature=0.2)
    except OpenAIError as e:
        logger.error("OpenAI error (complete_text): %s", type(e).__name__)
        raise AIError(_friendly(e))
    return (resp.choices[0].message.content or "").strip()


async def transcribe(file_bytes: bytes, filename: str = "audio.m4a") -> str:
    client = _get_client()
    f = io.BytesIO(file_bytes)
    f.name = filename
    try:
        resp = await client.audio.transcriptions.create(
            model=config.OPENAI_MODEL_TRANSCRIBE, file=f, response_format="json")
    except OpenAIError as e:
        logger.error("OpenAI error (transcribe): %s", type(e).__name__)
        raise AIError(_friendly(e))
    return getattr(resp, "text", "") or ""
