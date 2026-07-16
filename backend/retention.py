"""Storage cost control: delete backend raw audio + temporary uploaded source files after
their retention window. Transcripts, notes, extracted commitments and structured data are
KEPT; only the raw/temporary binaries are removed.

- Chunked-upload binaries (db.upload_chunks) for assembled lecture audio are deleted after
  RAW_AUDIO_RETENTION_HOURS; the parent db.uploads doc is marked raw_deleted.
- Any db.temp_files entries (temporary uploaded source files) are deleted after
  TEMP_UPLOAD_RETENTION_HOURS.
Runs hourly in the background; cleanup_once() is also directly callable by tests.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta

import config
from db import db

logger = logging.getLogger("student-assistant")


def _parse(dt):
    if not dt:
        return None
    if isinstance(dt, datetime):
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        d = datetime.fromisoformat(str(dt))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except Exception:
        return None


async def cleanup_once() -> dict:
    """Delete expired raw audio + temp files. Returns sanitized counts. Idempotent."""
    now = datetime.now(timezone.utc)
    audio_cutoff = now - timedelta(hours=config.RAW_AUDIO_RETENTION_HOURS)
    temp_cutoff = now - timedelta(hours=config.TEMP_UPLOAD_RETENTION_HOURS)
    chunks_deleted = 0
    uploads_marked = 0
    temp_deleted = 0

    try:
        # Raw assembled audio (chunked uploads) past retention.
        async for up in db.uploads.find({"raw_deleted": {"$ne": True}}):
            created = _parse(up.get("created_at"))
            if created and created < audio_cutoff:
                res = await db.upload_chunks.delete_many({"upload_id": up.get("id") or up.get("upload_id")})
                chunks_deleted += res.deleted_count
                await db.uploads.update_one({"_id": up["_id"]},
                    {"$set": {"raw_deleted": True, "raw_deleted_at": now.isoformat()}})
                uploads_marked += 1
    except Exception as e:
        logger.warning("audio retention pass skipped: %s", type(e).__name__)

    try:
        # Temporary uploaded source files (if that collection is used).
        async for tf in db.temp_files.find({}):
            created = _parse(tf.get("created_at"))
            if created and created < temp_cutoff:
                await db.temp_files.delete_one({"_id": tf["_id"]})
                temp_deleted += 1
    except Exception as e:
        logger.warning("temp-file retention pass skipped: %s", type(e).__name__)

    result = {"raw_audio_chunks_deleted": chunks_deleted, "uploads_marked": uploads_marked,
              "temp_files_deleted": temp_deleted, "ran_at": now.isoformat()}
    if chunks_deleted or uploads_marked or temp_deleted:
        logger.info("Retention cleanup: %s", result)
    return result


async def _loop():
    while True:
        try:
            await cleanup_once()
        except Exception as e:
            logger.warning("retention loop error: %s", type(e).__name__)
        await asyncio.sleep(3600)  # hourly


def start(app):
    """Launch the hourly retention loop as a background task (best effort)."""
    try:
        asyncio.get_event_loop().create_task(_loop())
    except Exception as e:
        logger.warning("retention start skipped: %s", type(e).__name__)
