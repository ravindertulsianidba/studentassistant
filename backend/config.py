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
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "GotU")
SMTP_USE_TLS = os.environ.get("SMTP_USE_TLS", "true").lower() == "true"

# --- App environment ---
APP_ENV = os.environ.get("APP_ENV", "development")

# ================= Monetization / entitlements / cost control =================
def _int(name, default):
    try:
        return int(os.environ.get(name, str(default)))
    except Exception:
        return default

def _float(name, default):
    try:
        return float(os.environ.get(name, str(default)))
    except Exception:
        return default

# Free one-time Starter Pack (lifetime, non-renewing).
FREE_STARTER_AUDIO_MINUTES = _int("FREE_STARTER_AUDIO_MINUTES", 30)
FREE_STARTER_AI_IMPORTS = _int("FREE_STARTER_AI_IMPORTS", 2)
FREE_STARTER_IMPORT_PAGES = _int("FREE_STARTER_IMPORT_PAGES", 10)
FREE_STARTER_MEMORY_QUESTIONS = _int("FREE_STARTER_MEMORY_QUESTIONS", 5)
FREE_STARTER_AI_BRIEFINGS = _int("FREE_STARTER_AI_BRIEFINGS", 2)

# Premium per 30-day cycle.
PREMIUM_AUDIO_MINUTES_PER_CYCLE = _int("PREMIUM_AUDIO_MINUTES_PER_CYCLE", 240)
PREMIUM_MAX_RECORDING_MINUTES = _int("PREMIUM_MAX_RECORDING_MINUTES", 120)
PREMIUM_AI_IMPORTS_PER_CYCLE = _int("PREMIUM_AI_IMPORTS_PER_CYCLE", 25)
PREMIUM_IMPORT_PAGES_PER_CYCLE = _int("PREMIUM_IMPORT_PAGES_PER_CYCLE", 150)
PREMIUM_MAX_PAGES_PER_IMPORT = _int("PREMIUM_MAX_PAGES_PER_IMPORT", 20)
PREMIUM_MEMORY_QUESTIONS_PER_CYCLE = _int("PREMIUM_MEMORY_QUESTIONS_PER_CYCLE", 100)
PREMIUM_DAILY_BRIEFINGS_PER_CYCLE = _int("PREMIUM_DAILY_BRIEFINGS_PER_CYCLE", 31)
PREMIUM_WEEKLY_REVIEWS_PER_CYCLE = _int("PREMIUM_WEEKLY_REVIEWS_PER_CYCLE", 5)

# Business guardrails.
TARGET_VARIABLE_COST_RATIO = _float("TARGET_VARIABLE_COST_RATIO", 0.20)
CRITICAL_VARIABLE_COST_RATIO = _float("CRITICAL_VARIABLE_COST_RATIO", 0.30)
FREE_STARTER_COST_ALERT_USD = _float("FREE_STARTER_COST_ALERT_USD", 0.75)
GLOBAL_DAILY_SPEND_ALERT_USD = _float("GLOBAL_DAILY_SPEND_ALERT_USD", 25.0)
GLOBAL_MONTHLY_SPEND_ALERT_USD = _float("GLOBAL_MONTHLY_SPEND_ALERT_USD", 400.0)
STARTER_INSTALL_ANOMALY_THRESHOLD = _int("STARTER_INSTALL_ANOMALY_THRESHOLD", 5)

# Pricing display reference (NOT shown in app; Play provides localized prices).
PRICE_MONTHLY_CAD = _float("PRICE_MONTHLY_CAD", 11.99)
PRICE_ANNUAL_CAD = _float("PRICE_ANNUAL_CAD", 109.99)
CAD_USD_RATE = _float("CAD_USD_RATE", 0.73)

# Emergency per-feature kill switches (comma-separated feature keys).
KILL_SWITCHES = [s.strip() for s in os.environ.get("KILL_SWITCHES", "").split(",") if s.strip()]

# Raw-media / temp-file retention (hours) for storage cost control.
RAW_AUDIO_RETENTION_HOURS = _int("RAW_AUDIO_RETENTION_HOURS", 24)
TEMP_UPLOAD_RETENTION_HOURS = _int("TEMP_UPLOAD_RETENTION_HOURS", 24)

# --- Google Play billing (backend entitlement authority) ---
BILLING_ENABLED = os.environ.get("BILLING_ENABLED", "false").lower() == "true"
GOOGLE_PLAY_PACKAGE_NAME = os.environ.get("GOOGLE_PLAY_PACKAGE_NAME", "com.decisivlabs.studentassistant")
GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID = os.environ.get("GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID", "student_assistant_premium")
GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID = os.environ.get("GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID", "monthly")
GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID = os.environ.get("GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID", "annual")
# Path to the Google service-account JSON (never commit the file itself).
GOOGLE_PLAY_SERVICE_ACCOUNT_JSON = os.environ.get("GOOGLE_PLAY_SERVICE_ACCOUNT_JSON", "")
# Server-side secret for authenticated encryption of purchase tokens at rest (never in frontend).
GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY = os.environ.get("GOOGLE_PLAY_TOKEN_ENCRYPTION_KEY", "")
# Pub/Sub OIDC audience / service account email used to authenticate RTDN pushes.
PUBSUB_VERIFICATION_TOKEN = os.environ.get("PUBSUB_VERIFICATION_TOKEN", "")
PUBSUB_SERVICE_ACCOUNT_EMAIL = os.environ.get("PUBSUB_SERVICE_ACCOUNT_EMAIL", "")
PUBSUB_AUDIENCE = os.environ.get("PUBSUB_AUDIENCE", "")
# Simple admin guard for sanitized monetization reports.
ADMIN_EMAILS = [e.strip().lower() for e in os.environ.get("ADMIN_EMAILS", "").split(",") if e.strip()]


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
