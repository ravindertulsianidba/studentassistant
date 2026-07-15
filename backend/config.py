"""Central configuration with fail-fast validation. No secrets are hardcoded."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai")  # "openai" | "fixture"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_JSON = os.environ.get("OPENAI_MODEL_JSON", "gpt-4o-mini")
OPENAI_MODEL_VISION = os.environ.get("OPENAI_MODEL_VISION", "gpt-4o-mini")
OPENAI_MODEL_TRANSCRIBE = os.environ.get("OPENAI_MODEL_TRANSCRIBE", "gpt-4o-transcribe")
OPENAI_MODEL_EMBED = os.environ.get("OPENAI_MODEL_EMBED", "text-embedding-3-small")
AI_MAX_RETRIES = int(os.environ.get("AI_MAX_RETRIES", "3"))

# Per-user daily AI request cap (cost protection). 0 == unlimited. Admin-tunable.
DEFAULT_DAILY_AI_LIMIT = int(os.environ.get("DEFAULT_DAILY_AI_LIMIT", "150"))

# Vector store (self-hostable Qdrant). Empty URL => keyword-search fallback.
QDRANT_URL = os.environ.get("QDRANT_URL", "")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "student_memory")
# 1536 for OpenAI text-embedding-3-small; 384 for the deterministic fixture provider.
EMBED_DIM = int(os.environ.get("EMBED_DIM", "1536" if AI_PROVIDER == "openai" else "384"))

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "student-assistant")
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "30"))
JWT_REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "30"))

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
ALLOW_INSECURE_DEV = os.environ.get("ALLOW_INSECURE_DEV", "false").lower() == "true"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))

# --- Email/password auth token lifetimes ---
VERIFICATION_TOKEN_HOURS = int(os.environ.get("VERIFICATION_TOKEN_HOURS", "24"))
RESET_TOKEN_HOURS = int(os.environ.get("RESET_TOKEN_HOURS", "1"))
RESEND_COOLDOWN_SECONDS = int(os.environ.get("RESEND_COOLDOWN_SECONDS", "300"))
LOGIN_MAX_FAILS = int(os.environ.get("LOGIN_MAX_FAILS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
# Base URL used to build verification / reset deep links in emails.
APP_WEB_URL = os.environ.get("APP_WEB_URL", (CORS_ORIGINS[0] if CORS_ORIGINS else "http://localhost:8081"))

# --- SMTP (provider-neutral). Placeholders => MockMailer (no live delivery). ---
SMTP_HOST = os.environ.get("SMTP_HOST", "")
_raw_port = os.environ.get("SMTP_PORT", "587")
SMTP_PORT = int(_raw_port) if _raw_port.strip().isdigit() else 587
SMTP_USERNAME = os.environ.get("SMTP_USERNAME", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.environ.get("SMTP_FROM_EMAIL", "")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Student Assistant")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"


def validate() -> list[str]:
    """Return a list of missing/invalid required config. Empty list == OK."""
    missing = []
    if not JWT_SECRET or len(JWT_SECRET) < 16:
        missing.append("JWT_SECRET (>=16 chars)")
    if not ALLOW_INSECURE_DEV and ("CHANGE_ME" in JWT_SECRET or JWT_SECRET.startswith("dev-only")):
        missing.append("JWT_SECRET (placeholder not allowed when ALLOW_INSECURE_DEV=false)")
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not GOOGLE_CLIENT_ID and not ALLOW_INSECURE_DEV:
        missing.append("GOOGLE_CLIENT_ID (or set ALLOW_INSECURE_DEV=true for dev)")
    if not CORS_ORIGINS:
        missing.append("CORS_ORIGINS")
    # In production, email delivery must be really configured (no silent mock).
    def _ph(v: str) -> bool:
        return (not v) or v.strip().startswith("[ADD_")
    if not ALLOW_INSECURE_DEV and (_ph(SMTP_HOST) or _ph(SMTP_FROM_EMAIL)):
        missing.append("SMTP_HOST/SMTP_FROM_EMAIL (email delivery required in production)")
    return missing
