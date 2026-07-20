"""Secret redaction for logs.

A logging filter + `redact()` helper that scrubs credential-like values from any
log record BEFORE it is emitted. This guards against accidental leakage of API
keys, passwords, Authorization headers, purchase tokens, verification/reset
tokens and full verification/reset links in application logs.
"""
import re
import logging

_PLACEHOLDER = "[REDACTED]"

# Ordered patterns → replacement. Each keeps a short, non-sensitive label.
_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9_\-]{8,}"), "sk-[REDACTED]"),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[A-Za-z0-9._\-]+"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)(password\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(smtp_password\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)(jwt_secret\s*[:=]\s*)\S+"), r"\1[REDACTED]"),
    # Full verification / reset links → keep the path, drop the token.
    (re.compile(r"(https?://[^\s?]+/(?:verify-email|reset-password))\?token=[^\s&]+"),
     r"\1?token=[REDACTED]"),
    # Bare token=... query fragments.
    (re.compile(r"(?i)(token=)[A-Za-z0-9._\-]{12,}"), r"\1[REDACTED]"),
    # Google Play purchase tokens are long opaque strings after purchase_token.
    (re.compile(r"(?i)(purchase_token[\"'\s:=]+)[A-Za-z0-9._\-]{12,}"), r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    if not text:
        return text
    out = str(text)
    for pat, repl in _PATTERNS:
        out = pat.sub(repl, out)
    return out


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            if isinstance(record.msg, str):
                record.msg = redact(record.msg)
            if record.args:
                if isinstance(record.args, dict):
                    record.args = {k: redact(v) if isinstance(v, str) else v
                                   for k, v in record.args.items()}
                else:
                    record.args = tuple(redact(a) if isinstance(a, str) else a
                                        for a in record.args)
        except Exception:
            pass
        return True


def install():
    """Attach the redaction filter to the root logger and app logger handlers."""
    f = RedactionFilter()
    for name in ("", "student-assistant", "uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.addFilter(f)
        for h in lg.handlers:
            h.addFilter(f)
