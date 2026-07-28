import uuid
import json
import re
import io
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Any, Dict
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form, Header
import config
import ai_service
import auth
import security
from mailer import mailer, send_tracked
import reliability as rel
import vectorstore as vs
from db import db
from core import (now_iso, clean, _parse_dt, normalize, token_overlap, rate_limit, rate_limit_key,
    add_timeline, add_chunks, enforce_ai, maybe_reminder, conf_label, get_prefs,
    is_high_risk, route_item, find_related, commit_item, build_review, route_items,
    CurrentUser, logger, _issue_session, _upsert_user)
from models import (GoogleIn, DevLoginIn, RefreshIn, RegisterIn, LoginIn, VerifyEmailIn,
    ResendVerificationIn, ForgotPasswordIn, ResetPasswordIn, DeleteAccountIn,
    CaptureIn, ImportIn, NotesIn, SearchIn, TaskIn, EventIn, ReviewActionIn, ReminderIn, ReminderStatusIn, CalendarSyncIn)

router = APIRouter(prefix="/api")

# ================= AUTH =================





GENERIC_LOGIN_ERROR = "Invalid email or password."
GENERIC_ACTION_OK = "If an account exists for this address, the email has been queued."


def _norm_email(e: str) -> str:
    return (e or "").strip().lower()


def _utcnow():
    return datetime.now(timezone.utc)


async def _make_email_token(email: str, purpose: str, hours: int) -> str:
    raw = security.new_token()
    await db.auth_tokens.insert_one({
        "email": email, "purpose": purpose, "token_hash": security.token_hash(raw),
        "created_at": _utcnow(), "expires_at": _utcnow() + timedelta(hours=hours),
        "used_at": None,
    })
    return raw


async def _recent_token(email: str, purpose: str, cooldown_s: int) -> bool:
    last = await db.auth_tokens.find_one({"email": email, "purpose": purpose},
                                         sort=[("created_at", -1)])
    if not last:
        return False
    created = last["created_at"]
    if created.tzinfo is None:  # MongoDB returns tz-naive datetimes.
        created = created.replace(tzinfo=timezone.utc)
    return (_utcnow() - created).total_seconds() < cooldown_s


async def _consume_token(raw: str, purpose: str):
    """Return (email, error). error is one of None|'invalid'|'expired'|'used'."""
    row = await db.auth_tokens.find_one({"token_hash": security.token_hash(raw), "purpose": purpose})
    if not row:
        return None, "invalid"
    if row.get("used_at"):
        return None, "used"
    exp = row["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _utcnow():
        return None, "expired"
    await db.auth_tokens.update_one({"_id": row["_id"]}, {"$set": {"used_at": _utcnow()}})
    return row["email"], None


async def _peek_token(raw: str, purpose: str):
    """Non-consuming validity check. Returns None if valid, else 'invalid'|'used'|'expired'."""
    row = await db.auth_tokens.find_one({"token_hash": security.token_hash(raw), "purpose": purpose})
    if not row:
        return "invalid"
    if row.get("used_at"):
        return "used"
    exp = row["expires_at"]
    if exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    if exp < _utcnow():
        return "expired"
    return None


async def _send_verification(email: str, name: str | None):
    raw = await _make_email_token(email, "verify_email", config.VERIFICATION_TOKEN_HOURS)
    link = f"{config.APP_WEB_URL}/verify-email?token={raw}"
    await send_tracked(
        "verification", email, "Verify your email — GotU",
        f"Welcome to GotU!\n\nPlease verify your email address to activate your "
        f"account. This link expires in {config.VERIFICATION_TOKEN_HOURS} hours:\n\n{link}\n\n"
        f"If you didn't create an account, you can ignore this email.",
        f'<p>Welcome to GotU!</p><p>Please verify your email to activate your account. '
        f'This link expires in {config.VERIFICATION_TOKEN_HOURS} hours.</p>'
        f'<p><a href="{link}">Verify my email</a></p>')


@router.post("/auth/register")
async def register(body: RegisterIn, request: Request):
    rate_limit(request, "register", 10)
    email = _norm_email(body.email)
    rate_limit_key(f"register:acct:{email}", 5, 3600)
    pw_err = security.validate_password(body.password)
    if pw_err:
        raise HTTPException(status_code=422, detail=pw_err)

    existing = await db.users.find_one({"email": email})
    if existing and existing.get("email_verified"):
        return {"message": GENERIC_ACTION_OK, "verification_required": True, "email": email}

    if not existing:
        # NOTE: Do NOT set google_sub=None here. The users.google_sub unique+sparse
        # index still indexes explicit null values, so multiple password-only users
        # (all with google_sub=null) would collide with E11000. Omit the field so
        # the sparse index correctly skips these docs.
        await db.users.insert_one({
            "id": str(uuid.uuid4()), "email": email,
            "password_hash": security.hash_password(body.password),
            "name": (body.full_name or email.split("@")[0]).strip(),
            "email_verified": False, "token_version": 0, "auth_provider": "password",
            "failed_login_count": 0, "lockout_until": None,
            "created_at": now_iso(),
        })
    else:
        await db.users.update_one({"id": existing["id"]},
            {"$set": {"password_hash": security.hash_password(body.password)}})

    if not await _recent_token(email, "verify_email", config.RESEND_COOLDOWN_SECONDS):
        await _send_verification(email, body.full_name)
    return {"message": "Account created. Check your email to verify your address.",
            "verification_required": True, "email": email}


@router.post("/auth/verify-email")
async def verify_email(body: VerifyEmailIn):
    email, err = await _consume_token(body.token, "verify_email")
    if err == "expired":
        raise HTTPException(status_code=400, detail="This verification link has expired. Request a new one.")
    if err == "used":
        raise HTTPException(status_code=400, detail="This link has already been used. Try signing in.")
    if err:
        raise HTTPException(status_code=400, detail="Invalid verification link.")
    await db.users.update_one({"email": email}, {"$set": {"email_verified": True}})
    await db.auth_tokens.update_many(
        {"email": email, "purpose": "verify_email", "used_at": None},
        {"$set": {"used_at": _utcnow()}})
    # Grant the one-time, non-renewing Starter Pack to this verified account (idempotent).
    try:
        import monetization as mon
        u = await db.users.find_one({"email": email}, {"id": 1})
        if u:
            await mon.grant_starter_pack(u["id"])
    except Exception:
        pass
    return {"message": "Email verified. You can now sign in.", "verified": True}


@router.post("/auth/resend-verification")
async def resend_verification(body: ResendVerificationIn, request: Request):
    rate_limit(request, "resend", 10)
    email = _norm_email(body.email)
    rate_limit_key(f"resend:acct:{email}", 5, 3600)
    user = await db.users.find_one({"email": email})
    if user and not user.get("email_verified") and user.get("auth_provider") == "password":
        if not await _recent_token(email, "verify_email", config.RESEND_COOLDOWN_SECONDS):
            await _send_verification(email, user.get("name"))
    return {"message": GENERIC_ACTION_OK}


@router.post("/auth/login")
async def login(body: LoginIn, request: Request):
    email = _norm_email(body.email)
    rate_limit(request, "login", 20)
    rate_limit_key(f"login:acct:{email}", 10, 300)
    user = await db.users.find_one({"email": email})

    if user and user.get("lockout_until"):
        lu = _parse_dt(user["lockout_until"])
        if lu and lu > _utcnow():
            raise HTTPException(status_code=429, detail="Too many attempts. Please try again later.")

    stored = user.get("password_hash") if user else None
    if stored:
        ok = security.verify_password(body.password, stored)
    else:
        security.verify_password(body.password, security.DUMMY_HASH)  # timing safety
        ok = False

    if not user or not stored or not ok:
        if user and stored:
            fails = int(user.get("failed_login_count", 0)) + 1
            upd = {"failed_login_count": fails}
            if fails >= config.LOGIN_MAX_FAILS:
                upd["lockout_until"] = (_utcnow() + timedelta(minutes=config.LOGIN_LOCKOUT_MINUTES)).isoformat()
                upd["failed_login_count"] = 0
            await db.users.update_one({"id": user["id"]}, {"$set": upd})
        raise HTTPException(status_code=401, detail=GENERIC_LOGIN_ERROR)

    if not user.get("email_verified"):
        raise HTTPException(status_code=403,
            detail="Please verify your email before signing in. Check your inbox for the link.")

    await db.users.update_one({"id": user["id"]},
        {"$set": {"failed_login_count": 0, "lockout_until": None}})
    return await _issue_session(user)


@router.post("/auth/forgot-password")
async def forgot_password(body: ForgotPasswordIn, request: Request):
    rate_limit(request, "forgot", 10)
    email = _norm_email(body.email)
    rate_limit_key(f"forgot:acct:{email}", 5, 3600)
    user = await db.users.find_one({"email": email})
    if user and user.get("password_hash"):
        if not await _recent_token(email, "reset_password", config.RESEND_COOLDOWN_SECONDS):
            raw = await _make_email_token(email, "reset_password", config.RESET_TOKEN_HOURS)
            link = f"{config.APP_WEB_URL}/reset-password?token={raw}"
            await send_tracked(
                "reset", email, "Reset your password — GotU",
                f"We received a request to reset your password. This link expires in "
                f"{config.RESET_TOKEN_HOURS} hour(s):\n\n{link}\n\n"
                f"If you didn't request this, you can safely ignore this email.",
                f'<p>We received a request to reset your password. This link expires in '
                f'{config.RESET_TOKEN_HOURS} hour(s).</p><p><a href="{link}">Reset password</a></p>')
    return {"message": GENERIC_ACTION_OK}


@router.post("/auth/check-reset-token")
async def check_reset_token(body: VerifyEmailIn, request: Request):
    """Non-consuming validity check so the reset screen can hide the form for a
    used/expired/invalid link before submission. Does NOT mark the token used."""
    rate_limit(request, "reset", 30)
    reason = await _peek_token(body.token, "reset_password")
    return {"valid": reason is None, "reason": reason}


@router.post("/auth/reset-password")
async def reset_password(body: ResetPasswordIn, request: Request):
    rate_limit(request, "reset", 20)
    pw_err = security.validate_password(body.password)
    if pw_err:
        raise HTTPException(status_code=422, detail=pw_err)
    email, err = await _consume_token(body.token, "reset_password")
    if err == "expired":
        raise HTTPException(status_code=400, detail="This reset link has expired. Request a new one.")
    if err == "used":
        raise HTTPException(status_code=400, detail="This reset link has already been used.")
    if err:
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    user = await db.users.find_one({"email": email})
    if not user:
        raise HTTPException(status_code=400, detail="Invalid reset link.")
    await db.users.update_one({"id": user["id"]}, {
        "$set": {"password_hash": security.hash_password(body.password),
                 "email_verified": True, "failed_login_count": 0, "lockout_until": None},
        "$inc": {"token_version": 1}})
    await db.auth_tokens.update_many(
        {"email": email, "purpose": "reset_password", "used_at": None},
        {"$set": {"used_at": _utcnow()}})
    await db.refresh_tokens.update_many({"user_id": user["id"], "revoked_at": None},
        {"$set": {"revoked_at": now_iso()}})
    return {"message": "Password updated. Please sign in with your new password."}


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

@router.get("/auth/dev-outbox")
async def dev_outbox():
    """Test-only mock-mail inspection. 404 in production; empty when live SMTP is used."""
    if not config.ALLOW_INSECURE_DEV:
        raise HTTPException(status_code=404, detail="Not found")
    if not getattr(mailer, "is_mock", False):
        return {"live_smtp": True, "messages": []}
    return {"live_smtp": False, "messages": mailer.sent[-50:]}

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
    uid = p["sub"]
    u = await db.users.find_one({"id": uid}, {"token_version": 1, "deleted_at": 1})
    if not u or u.get("deleted_at") or int(p.get("tv", 0)) != int(u.get("token_version", 0)):
        await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                           {"$set": {"revoked_at": now_iso()}})
        raise HTTPException(status_code=401, detail="Session expired. Please sign in again.")
    tv = int(u.get("token_version", 0))
    await db.refresh_tokens.update_one({"jti_hash": auth.hash_jti(p["jti"])},
                                       {"$set": {"revoked_at": now_iso()}})
    access, _, exp = auth.create_token(uid, "access", minutes=config.JWT_ACCESS_MINUTES, extra={"tv": tv})
    new_refresh, jti, rexp = auth.create_token(uid, "refresh", days=config.JWT_REFRESH_DAYS, extra={"tv": tv})
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

@router.post("/auth/logout-all")
async def logout_all(uid: str = CurrentUser):
    await db.users.update_one({"id": uid}, {"$inc": {"token_version": 1}})
    await db.refresh_tokens.update_many({"user_id": uid, "revoked_at": None},
                                        {"$set": {"revoked_at": now_iso()}})
    return {"ok": True, "revoked": True}

@router.get("/me")
async def me(uid: str = CurrentUser):
    u = await db.users.find_one({"id": uid}, {"_id": 0, "google_sub": 0, "password_hash": 0,
                                              "failed_login_count": 0, "lockout_until": 0})
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    return u

@router.delete("/me")
async def delete_account(body: DeleteAccountIn | None = None, uid: str = CurrentUser):
    # Re-authentication safeguard: password accounts must confirm their password.
    u = await db.users.find_one({"id": uid})
    if u and u.get("password_hash"):
        pw = (body.password if body else None) or ""
        if not pw or not security.verify_password(pw, u["password_hash"]):
            raise HTTPException(status_code=403, detail="Please confirm your password to delete your account.")
    for c in ["tasks", "events", "timeline", "review", "imports", "notes", "chunks",
              "audit", "prefs", "source_docs", "transcripts", "refresh_tokens",
              "commitments", "ledger", "reminders", "idempotency", "ai_usage", "uploads",
              "calendar_connection", "calendar_links", "external_events",
              "listen_sessions", "device_state"]:
        await db[c].delete_many({"user_id": uid})
    await db.users.delete_one({"id": uid})
    return {"ok": True, "deleted": True}
