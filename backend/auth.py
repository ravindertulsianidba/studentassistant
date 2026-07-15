"""Authentication: Google ID-token verification + our own JWT access/refresh."""
import time
import secrets
import hashlib
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import HTTPException, Request

import config

ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def now():
    return datetime.now(timezone.utc)


def create_token(user_id: str, typ: str, minutes: int | None = None, days: int | None = None,
                 extra: dict | None = None):
    jti = secrets.token_urlsafe(24)
    exp = now() + (timedelta(minutes=minutes) if minutes else timedelta(days=days))
    payload = {"sub": str(user_id), "typ": typ, "jti": jti, "iss": config.JWT_ISSUER,
               "iat": int(time.time()), "exp": exp}
    if extra:
        payload.update(extra)
    return jwt.encode(payload, config.JWT_SECRET, algorithm="HS256"), jti, exp


def decode(token: str) -> dict:
    return jwt.decode(token, config.JWT_SECRET, algorithms=["HS256"], issuer=config.JWT_ISSUER)


def hash_jti(j: str) -> str:
    return hashlib.sha256(j.encode()).hexdigest()


async def get_current_user(request: Request) -> str:
    h = request.headers.get("Authorization", "")
    if not h.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        p = decode(h[7:])
        if p.get("typ") != "access":
            raise HTTPException(status_code=401, detail="Wrong token type")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    uid = p["sub"]
    # Enforce global session revocation (logout-all / password reset / delete).
    from db import db
    u = await db.users.find_one({"id": uid}, {"token_version": 1, "deleted_at": 1})
    if not u or u.get("deleted_at"):
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    if int(p.get("tv", 0)) != int(u.get("token_version", 0)):
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    return uid


def verify_google(id_token_str: str) -> dict:
    from google.oauth2 import id_token as gidt
    from google.auth.transport import requests as greq
    info = gidt.verify_oauth2_token(id_token_str, greq.Request(), config.GOOGLE_CLIENT_ID)
    if info.get("iss") not in ISSUERS:
        raise ValueError("Invalid token issuer")
    return info
