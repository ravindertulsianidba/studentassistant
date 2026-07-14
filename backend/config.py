"""Central configuration with fail-fast validation. No secrets are hardcoded."""
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

AI_PROVIDER = os.environ.get("AI_PROVIDER", "openai")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL_JSON = os.environ.get("OPENAI_MODEL_JSON", "gpt-4o-mini")
OPENAI_MODEL_VISION = os.environ.get("OPENAI_MODEL_VISION", "gpt-4o-mini")
OPENAI_MODEL_TRANSCRIBE = os.environ.get("OPENAI_MODEL_TRANSCRIBE", "gpt-4o-transcribe")

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ISSUER = os.environ.get("JWT_ISSUER", "student-assistant")
JWT_ACCESS_MINUTES = int(os.environ.get("JWT_ACCESS_MINUTES", "30"))
JWT_REFRESH_DAYS = int(os.environ.get("JWT_REFRESH_DAYS", "30"))

CORS_ORIGINS = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
ALLOW_INSECURE_DEV = os.environ.get("ALLOW_INSECURE_DEV", "false").lower() == "true"
MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))


def validate() -> list[str]:
    """Return a list of missing/invalid required config. Empty list == OK."""
    missing = []
    if not JWT_SECRET or len(JWT_SECRET) < 16:
        missing.append("JWT_SECRET (>=16 chars)")
    if AI_PROVIDER == "openai" and not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if not GOOGLE_CLIENT_ID and not ALLOW_INSECURE_DEV:
        missing.append("GOOGLE_CLIENT_ID (or set ALLOW_INSECURE_DEV=true for dev)")
    if not CORS_ORIGINS:
        missing.append("CORS_ORIGINS")
    return missing
