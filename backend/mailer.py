"""Provider-neutral transactional email.

- When real SMTP credentials are configured, `SmtpMailer` delivers via aiosmtplib.
- Otherwise (placeholders / empty), `MockMailer` captures messages in memory so
  the full auth pipeline is testable WITHOUT live credentials. Captured messages
  are exposed for automated tests via the ALLOW_INSECURE_DEV-gated dev outbox
  endpoint — keeping mock tests clearly separate from live-delivery tests.
"""
import logging
import asyncio
from datetime import datetime, timezone
from email.message import EmailMessage

import aiosmtplib
from fastapi import HTTPException

import config
from db import db

logger = logging.getLogger("student-assistant")


def _placeholder(v: str) -> bool:
    return (not v) or v.strip().startswith("[ADD_")


def smtp_configured() -> bool:
    return not (_placeholder(config.SMTP_HOST) or _placeholder(config.SMTP_FROM_EMAIL))


class SmtpMailer:
    is_mock = False

    async def send(self, to: str, subject: str, text: str, html: str | None = None):
        msg = EmailMessage()
        msg["From"] = f"{config.SMTP_FROM_NAME} <{config.SMTP_FROM_EMAIL}>"
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")
        # aiosmtplib returns (errors_by_recipient, response_message).
        return await aiosmtplib.send(
            msg,
            hostname=config.SMTP_HOST,
            port=config.SMTP_PORT,
            username=config.SMTP_USERNAME or None,
            password=config.SMTP_PASSWORD or None,
            start_tls=config.SMTP_USE_TLS,
        )


class MockMailer:
    is_mock = True

    def __init__(self):
        self.sent: list[dict] = []

    async def send(self, to: str, subject: str, text: str, html: str | None = None):
        # Never log token contents; only metadata.
        logger.info("MockMailer captured email to=%s subject=%s", to, subject)
        self.sent.append({"to": to, "subject": subject, "text": text, "html": html})
        # Keep memory bounded.
        if len(self.sent) > 200:
            self.sent = self.sent[-200:]


class UnconfiguredMailer:
    """Used in production when SMTP is not configured. Fails safely instead of
    silently pretending to send (never falls back to MockMailer in production)."""
    is_mock = False

    async def send(self, to: str, subject: str, text: str, html: str | None = None):
        logger.error("SMTP is not configured; refusing to send email to %s", to)
        raise HTTPException(status_code=503,
                            detail="Email delivery is temporarily unavailable. Please try again later.")


# Selection: real SMTP if configured; else MockMailer ONLY in dev (ALLOW_INSECURE_DEV);
# otherwise UnconfiguredMailer which fails safely in production.
if smtp_configured():
    mailer: SmtpMailer | MockMailer | UnconfiguredMailer = SmtpMailer()
elif config.ALLOW_INSECURE_DEV:
    mailer = MockMailer()
else:
    mailer = UnconfiguredMailer()


# ---------------- sanitized delivery observability ----------------
# We record ONLY non-sensitive delivery metadata. We NEVER store the full email
# address, SMTP password, email body, verification/reset token, or full links.

def _domain_of(addr: str) -> str:
    return (addr.rsplit("@", 1)[-1] or "unknown").strip().lower() if addr else "unknown"


def _classify_smtp_exc(e: Exception) -> str:
    name = type(e).__name__.lower()
    msg = str(e).lower()
    if "timeout" in name or "timeout" in msg or "timed out" in msg:
        return "timeout"
    code = getattr(e, "code", None)
    if isinstance(code, int):
        if 400 <= code < 500:
            return "temporary_failure"
        if code >= 500:
            return "permanent_failure"
    if "recipientsrefused" in name or "senderrefused" in name or "550" in msg:
        return "permanent_failure"
    if "connect" in name or "connection" in msg or "network" in msg:
        return "temporary_failure"
    return "error"


async def _record_delivery(message_type: str, to: str, category: str,
                           accepted: int, rejected: int, retry_count: int):
    try:
        await db.email_delivery_log.insert_one({
            "message_type": message_type,
            "recipient_domain": _domain_of(to),
            "accepted_count": int(accepted),
            "rejected_count": int(rejected),
            "smtp_category": category,          # accepted|rejected|timeout|temporary_failure|permanent_failure|error|mock|unconfigured
            "retry_count": int(retry_count),
            "ts": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:  # observability must never break the auth flow
        logger.warning("email_delivery_log insert failed (type=%s domain=%s)",
                       message_type, _domain_of(to))


_TRANSIENT = {"timeout", "temporary_failure"}


async def send_tracked(message_type: str, to: str, subject: str, text: str,
                       html: str | None = None, max_retries: int = 1):
    """Send an email and record sanitized delivery metadata. Retries transient
    SMTP failures up to `max_retries` times. Raises the same HTTPException as the
    underlying mailer on hard failure so callers behave as before."""
    if getattr(mailer, "is_mock", False):
        await mailer.send(to, subject, text, html)
        await _record_delivery(message_type, to, "mock", 1, 0, 0)
        return
    attempt = 0
    while True:
        try:
            result = await mailer.send(to, subject, text, html)
            errors = {}
            if isinstance(result, tuple) and result and isinstance(result[0], dict):
                errors = result[0]
            rejected = len(errors)
            category = "rejected" if rejected else "accepted"
            await _record_delivery(message_type, to, category,
                                   accepted=0 if rejected else 1, rejected=rejected,
                                   retry_count=attempt)
            return
        except HTTPException:
            # UnconfiguredMailer path (production without SMTP): fails safely.
            await _record_delivery(message_type, to, "unconfigured", 0, 0, attempt)
            raise
        except Exception as e:
            category = _classify_smtp_exc(e)
            if category in _TRANSIENT and attempt < max_retries:
                attempt += 1
                await asyncio.sleep(min(2 ** attempt, 4))
                continue
            await _record_delivery(message_type, to, category, 0, 1, attempt)
            logger.error("email send failed type=%s domain=%s category=%s",
                         message_type, _domain_of(to), category)
            raise HTTPException(status_code=503,
                                detail="Email delivery is temporarily unavailable. Please try again later.")
