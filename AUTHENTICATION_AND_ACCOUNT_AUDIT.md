# Authentication & Account Audit — Phase 3A

_Student Assistant · Secure email/password authentication + SMTP · June 2026_

## 1. Summary
Secure email/password authentication was implemented alongside the retained Google
Sign-In. Email verification is **required before account access**. All secrets are
sourced from environment variables (no hardcoding). Automated tests: **17/17 backend
pass** (`backend/tests/test_auth_phase3a.py`, report `test_reports/iteration_8.json`)
and **frontend auth UI flows verified**.

## 2. Endpoints implemented (all prefixed `/api`)
| Method | Path | Purpose |
|---|---|---|
| POST | `/auth/register` | Create account (unverified), send verification email. Generic response — no account-existence leak. |
| POST | `/auth/verify-email` | Consume single-use verification token; marks email verified. |
| POST | `/auth/resend-verification` | Resend verification email (5-min cooldown, generic response). |
| POST | `/auth/login` | Email+password → session. `401` generic on bad creds; `403` only after correct password if unverified. |
| POST | `/auth/forgot-password` | Always generic `200`; emails a reset link if the account exists. |
| POST | `/auth/reset-password` | Consume single-use reset token, rotate password, **revoke all sessions**. |
| POST | `/auth/refresh` | Rotate access+refresh; enforces `token_version`. |
| POST | `/auth/logout` | Revoke the current refresh token. |
| POST | `/auth/logout-all` | Revoke **all** sessions (bumps `token_version`). |
| POST | `/auth/google` | Google ID-token sign-in (retained). Links to a same-email password account. |
| POST | `/auth/dev-login` | Dev-only bypass. `404` in production (`ALLOW_INSECURE_DEV=false`). |
| GET | `/auth/dev-outbox` | Dev-only mock-mail inspection. `404` in production. |
| GET | `/me` | Current profile (never returns `password_hash`). |
| DELETE | `/me` | Delete account and all user-scoped data. |

## 3. Security properties
- **Hashing**: Argon2id via `pwdlib` (`backend/security.py`). Dummy-hash verification on
  unknown accounts to reduce login-timing enumeration.
- **Password policy**: min 10 / max 128 chars, spaces & passphrases allowed, **not**
  truncated, common/compromised passwords rejected (bundled list; full HIBP deferred).
  Strength meter + confirm + show/hide on the client.
- **Tokens (verification & reset)**: cryptographically random (`secrets.token_urlsafe`),
  **stored only as SHA-256 hash** in `db.auth_tokens`, **single-use** (`used_at`),
  **time-limited** (verify 24h, reset 1h), invalidated on success, resend cooldown 5 min.
- **Sessions**: JWT access (30 min) + refresh (30 d) with rotation; `token_version` claim
  checked on every authenticated request → immediate **revoke-all** and
  **password-reset session invalidation**. Refresh tokens stored hashed, revocable.
- **Generic errors**: login/register/forgot/reset never disclose account existence.
- **Rate limiting**: per-IP + per-account buckets (in-memory) on register/login/resend/
  forgot/reset. **Brute-force lockout**: 5 failed logins → 15-min lockout (`429`).
- **Email normalization**: lowercased/trimmed everywhere; `EmailStr` validation.
- **Data isolation**: every entity scoped by `user_id`; verified with a 2-user test.
- **Dev bypass**: `dev-login`/`dev-outbox` gated by `ALLOW_INSECURE_DEV`; `404` in prod.
  The client shows dev quick sign-in only under `__DEV__`.

## 4. Environment variables required
```
# Auth / JWT
JWT_SECRET=<>=16 random chars; placeholder rejected when ALLOW_INSECURE_DEV=false>
JWT_ISSUER=student-assistant
JWT_ACCESS_MINUTES=30
JWT_REFRESH_DAYS=30
GOOGLE_CLIENT_ID=<google oauth client id>        # for Google Sign-In
ALLOW_INSECURE_DEV=false                          # MUST be false in production

# Email token lifetimes (optional; defaults shown)
VERIFICATION_TOKEN_HOURS=24
RESET_TOKEN_HOURS=1
RESEND_COOLDOWN_SECONDS=300
LOGIN_MAX_FAILS=5
LOGIN_LOCKOUT_MINUTES=15
APP_WEB_URL=<base url used in email links>        # defaults to first CORS origin

# SMTP (provider-neutral) — placeholders => MockMailer (no live send)
SMTP_HOST=[ADD_SMTP_HOST]
SMTP_PORT=[ADD_SMTP_PORT]
SMTP_USERNAME=[ADD_SMTP_USERNAME]
SMTP_PASSWORD=[ADD_SMTP_PASSWORD]
SMTP_FROM_EMAIL=[ADD_FROM_EMAIL]
SMTP_FROM_NAME=Student Assistant
SMTP_USE_TLS=true
```

## 5. Tested with mocks (no live credentials)
- **All email delivery** is mocked via in-memory `MockMailer` (`backend/mailer.py`) because
  SMTP env values are placeholders. Captured messages are inspected in tests via
  `GET /api/auth/dev-outbox`. Register/verify/resend/forgot/reset flows are fully exercised.
- Covered cases (17/17): register + exactly one email, pre-verify login `403`, verify
  success, verify reuse `400`, invalid token `400`, login `200`, generic `401`,
  5-fail → `429` lockout, forgot generic `200`, reset revokes access+refresh (`tv` bump) +
  reset-reuse `400`, weak-password `422` (register & reset), duplicate-verified generic
  `200`, `MixedCase@Uni.EDU` normalization, two-user isolation, logout-all revoke,
  Google `401` on bad token, dev-login `200`.

## 6. Requires LIVE SMTP validation (not yet done)
- Real delivery of the **verification email** and **password-reset email** to an inbox.
- Deliverability/formatting (SPF/DKIM, spam placement) with the chosen provider.
- These are **not** marked as passed. Provide `SMTP_*` credentials, set them in
  `backend/.env`, restart backend; `smtp_configured()` then switches to `SmtpMailer`.

## 7. Known-incomplete / deferred
- Expired-token paths (24h/1h) are implemented but not exercised in CI (would require
  waiting); the invalid/reused paths are covered.
- Compromised-password check is a bundled common-list only (no live HIBP API).
- Rate limiting is in-memory (per-process); a multi-instance deployment should move this
  to a shared store (e.g. Redis) — playbook noted, deferred for MVP.
