"""Provider-neutral transactional email.

- When real SMTP credentials are configured, `SmtpMailer` delivers via aiosmtplib.
- Otherwise (placeholders / empty), `MockMailer` captures messages in memory so
  the full auth pipeline is testable WITHOUT live credentials. Captured messages
  are exposed for automated tests via the ALLOW_INSECURE_DEV-gated dev outbox
  endpoint — keeping mock tests clearly separate from live-delivery tests.
"""
import logging
from email.message import EmailMessage

import aiosmtplib

import config

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
        await aiosmtplib.send(
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


mailer: SmtpMailer | MockMailer = SmtpMailer() if smtp_configured() else MockMailer()
