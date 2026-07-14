import uuid
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Header
import config
import ai_service
import auth
import reliability as rel
import vectorstore as vs
from db import db
from core import (now_iso, clean, _parse_dt, normalize, token_overlap, rate_limit,
    add_timeline, add_chunks, enforce_ai, maybe_reminder, conf_label, get_prefs,
    is_high_risk, route_item, find_related, commit_item, build_review, route_items,
    CurrentUser, logger, _issue_session, _upsert_user)
from models import *  # noqa: F401,F403

router = APIRouter(prefix="/api")

# ================= AUTH =================





@router.post("/auth/google")
async def auth_google(body: GoogleIn, request: Request):
    rate_limit(request, "auth", 20)
    if not config.GOOGLE_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google Sign-In is not configured on this server.")
    try:
        info = auth.verify_google(body.id_token)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid Google token")
    user = await _upsert_user(info["sub"], info.get("email"), info.get("name"))
    return await _issue_session(user)

@router.post("/auth/dev-login")
async def dev_login(body: DevLoginIn, request: Request):
    """Test-only. Disabled in production (ALLOW_INSECURE_DEV=false)."""
    if not config.ALLOW_INSECURE_DEV:
        raise HTTPException(status_code=404, detail="Not found")
    rate_limit(request, "auth", 40)
    user = await _upsert_user(f"dev:{body.email}", body.email, body.email.split("@")[0])
    return await _issue_session(user)

@router.post("/auth/refresh")
async def refresh(body: RefreshIn):
    try:
        p = auth.decode(body.refresh_token)
        if p.get("typ") != "refresh":
            raise ValueError()
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    row = await db.refresh_tokens.find_one({"jti_hash": auth.hash_jti(p["jti"]), "revoked_at": None})
    if not row:
        raise HTTPException(status_code=401, detail="Session revoked")
    await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                       {"$set": {"revoked_at": now_iso()}})
    uid = p["sub"]
    access, _, exp = auth.create_token(uid, "access", minutes=config.JWT_ACCESS_MINUTES)
    new_refresh, jti, rexp = auth.create_token(uid, "refresh", days=config.JWT_REFRESH_DAYS)
    await db.refresh_tokens.insert_one({"jti_hash": auth.hash_jti(jti), "user_id": uid,
                                        "revoked_at": None, "expires_at": rexp})
    return {"access_token": access, "refresh_token": new_refresh, "expires_at": exp.isoformat()}

@router.post("/auth/logout")
async def logout(body: RefreshIn):
    try:
        p = auth.decode(body.refresh_token)
        await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                           {"$set": {"revoked_at": now_iso()}})
    except Exception:
        pass
    return {"ok": True}

@router.get("/me")
async def me(uid: str = CurrentUser):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "google_sub": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

@router.delete("/me")
async def delete_account(uid: str = CurrentUser):
    for c in ["tasks", "events", "timeline", "review", "imports", "notes", "chunks",
              "audit", "prefs", "source_docs", "transcripts", "refresh_tokens",
              "commitments", "ledger", "reminders", "idempotency", "ai_usage", "uploads"]:
        await db[c].delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True, "deleted": True}
