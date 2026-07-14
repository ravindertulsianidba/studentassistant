# Security Audit Report — Student Assistant

Method: automated pytest + manual review of `server.py`, `auth.py`, `config.py`. Result: no critical/high unresolved issues in server-side scope.

| Area | Test | Expected | Actual | Result | Risk |
|---|---|---|---|---|---|
| AuthN bypass | Call protected endpoints w/o/with bad token | 401 | 401 | PASS | — |
| Token type confusion | Use refresh token as access | 401 | 401 (typ check) | PASS | — |
| Refresh replay | Reuse rotated/revoked refresh | 401 | 401 (jti hash + revoked) | PASS | — |
| Cross-user (IDOR) | A access/modify/delete B (tasks/events/notes/sources) | 404 | 404 | PASS | — |
| Authorization scope | All queries filtered by user_id | scoped | scoped | PASS | — |
| Public admin endpoint | DELETE /api/wipe | removed | 404 | PASS | — |
| File upload validation | Oversized import (> MAX_UPLOAD_MB) | 413 | 413 | PASS | — |
| Rate limiting | Burst /auth/dev-login & AI endpoints | 429 | 429 | PASS | per-pod (see note) |
| Error sanitization | Force server error | generic 500, no stack | `{"detail":"Internal server error"}` | PASS | — |
| Secrets management | Grep source for keys | none hardcoded | env-only | PASS | — |
| Token storage (client) | Access/refresh location | secure store (Keystore) | expo-secure-store | PASS | — |
| Transport | Prod TLS | HTTPS via Nginx | configured | PASS (deploy) | needs cert on VPS |
| CORS | Wildcard in prod | restricted list | env CORS_ORIGINS | PASS | set real domains |
| Log privacy | PII/secrets in logs | none | sanitized errors, no token logging | PASS | — |
| Account deletion | Remove all user data + sessions | complete | confirmed | PASS | — |
| Data export | User-scoped export | scoped | scoped | PASS | — |
| Google token verify | iss/aud/exp validated | validated | google-auth verify_oauth2_token + iss check | PASS (needs client id) | — |

## Notes / hardening applied
- `config.validate()` rejects placeholder `JWT_SECRET` and requires `CORS_ORIGINS`, `OPENAI_API_KEY` (openai), and `GOOGLE_CLIENT_ID` unless dev mode.
- `ALLOW_INSECURE_DEV=false` disables `/auth/dev-login` (returns 404) in production.
- DB indexes on `user_id`, unique `google_sub`, unique refresh `jti_hash`, TTL on refresh expiry.

## Recommendations (non-blocking)
- Move rate limiting to Redis for multi-instance deployments (current limiter is per-process).
- Add dependency vulnerability scanning (`pip-audit`) and a secrets scanner to CI.
- Consider payload schema max-length limits on free-text fields.
