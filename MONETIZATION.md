# Monetization, Entitlements & Cost Control

Two plans only: **Free** and **Student Assistant Premium** (`student_assistant_premium`,
base plans `monthly` + `annual`). No trials, no multiple tiers, nothing advertised as unlimited.
The **backend is the entitlement authority** — no local `isPremium` flag ever grants access.

## Architecture (backend)
- `backend/monetization.py` — entitlement resolver, usage cycles, reserve/settle/refund metering
  (atomic + concurrency-safe), Usage + Cost ledgers, model-pricing registry, cost projection,
  Starter Pack grant, kill switches, cost alerts.
- `backend/routers/billing.py` — `GET /api/billing/status`, `POST /api/billing/google/verify`,
  `POST /api/billing/google/restore`, `POST /api/billing/google/rtdn`. Google Play Developer API
  verification (subscriptionsv2), idempotent, rejects reused/mismatched tokens. Gated by `BILLING_ENABLED`.
- `backend/routers/monetization.py` — `GET /api/usage/status`, `GET /api/plan/config`,
  `POST /api/monetization/event` (sanitized funnel), `GET /api/admin/monetization`,
  `GET /api/admin/cost-projection` (admin-only via `ADMIN_EMAILS`).
- `backend/retention.py` — hourly cleanup deleting raw audio chunks + temp files after
  `RAW_AUDIO_RETENTION_HOURS` / `TEMP_UPLOAD_RETENTION_HOURS` (transcripts/notes/structured data kept).

### Collections
`entitlements`, `subscriptions`(via entitlements), `purchase_tokens`, `purchase_events`,
`usage_cycles`, `usage_ledger`, `cost_ledger`, `rtdn_events`, `monetization_events`,
`monetization_alerts`, `pricing_config`.

### Entitlement states
`free · active · grace_period · account_hold · paused · cancelled_active_until_period_end ·
expired · revoked · pending`. Cancelled keeps Premium until period end; expired returns to Free
WITHOUT losing data. Premium allowances reset every 30 days on the billing anchor (incl. annual).

## Metering
Reserve **before** the AI call (atomic conditional `$inc` — cannot exceed the allowance under
concurrency) → on success `record_usage` writes ledgers → on failure `refund` (failed ops never
consume). Metered features: `audio_minutes` (transcribe), `ai_import` + `import_pages` (imports),
`memory_question` (grounded AI answers). Per-import page cap + single-recording minute cap enforced.
Notes/commitment generation from a transcript are covered by the audio minutes already consumed.
Deterministic (non-AI) briefings, manual tasks/notes/courses, viewing/editing existing data, and
basic calendar remain free and are never metered.

## Frontend
- `src/services/billing.ts` — status/plan/event API + lazy native `expo-iap` purchase/restore
  (device-only, guarded; web/Expo Go unaffected). Never grants entitlement locally.
- `app/paywall.tsx` — headline + student-outcome value, Annual/Monthly (both visible, no preselect,
  no countdown), localized Play prices, auto-renew disclosure, Restore + Manage Subscription,
  Privacy/Terms. Shown on premium-only action, allowance exhaustion (backend 402 → auto-routed via
  `src/api.ts` limit handler), or explicit Upgrade — never during onboarding.
- Diagnostics → **Plan & usage**: plan, state, renew/expiry, per-feature usage bars, Restore, Manage.

## Billing library
**`expo-iap@4.5.1`** (Expo-compatible wrapper over Google Play Billing Library v8+). Config plugin
`expo-iap` wired in `app.json`. Purchase → obtain purchaseToken → backend `verify` (Google-side) →
entitlement granted only after verification. Device/installed-build only (not Expo Go / web).

## Cost projection (configured models: transcribe=gpt-4o-transcribe, json/vision=gpt-4o-mini)
| Metric | Value (USD) |
|---|---|
| Full-quota Premium / cycle | ~$2.03 |
| Typical Premium (35% util) | ~$0.71 |
| Starter Pack (full, one-time) | ~$0.19 (under $0.75 alert ✅) |
| Monthly net revenue (after 15% Play fee) | ~$7.44 |
| Annual net monthly revenue | ~$5.69 |
| Full-quota ÷ monthly net | 27% ✅ |
| **Full-quota ÷ annual net monthly** | **35.6% ⚠️ (flagged > 35%)** |
| Typical ÷ annual net monthly | 12.5% ✅ |

**Flag & recommendation:** worst-case full-quota is 35.6% of annual-plan net monthly revenue
(driven by audio: $1.80 of $2.03). Options (server-configurable, no rebuild):
reduce `PREMIUM_AUDIO_MINUTES_PER_CYCLE` 300→240 (→ ~28.6%), or keep 300 given typical use is 12.5%
and few users hit full quota. Guardrails: target ≤20%, alert 20%, critical 30% of net revenue.

## Remaining Google Play / Pub/Sub configuration (do BEFORE enabling billing)
1. Play Console app for `com.decisivlabs.studentassistant` (internal testing track).
2. Subscription `student_assistant_premium` with base plans `monthly` (CAD $11.99) + `annual` (CAD $109.99).
3. Google Cloud **service account** with Android Publisher access → JSON key → set
   `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` (server path/secret; never commit).
4. Link the service account in Play Console (Users & permissions / API access).
5. **Pub/Sub** topic for RTDN + push subscription to `/api/billing/google/rtdn`; set
   `PUBSUB_SERVICE_ACCOUNT_EMAIL` (OIDC) or `PUBSUB_VERIFICATION_TOKEN`; add the RTDN topic name
   in Play Console → Monetization setup.
6. License testers + test payment methods for renewal/cancel/grace/hold/recovery/refund/revoke/restore.
7. Set `EXPO_PUBLIC_BILLING_ENABLED=true`, `EXPO_PUBLIC_MONETIZATION_EXPECTED=true`, `BILLING_ENABLED=true`,
   `ADMIN_EMAILS`. Then re-run preflight.

## Privacy/Terms requirements (must be live before store review)
- Disclose: auto-renewing subscription, price/period (shown by Play), how to cancel/manage,
  that backend verifies purchases, and the 24-hour raw-audio / temp-file deletion policy.
- Paywall links `PRIVACY_URL` / `TERMS_URL` in `app/paywall.tsx` — replace with the live URLs.

## Tests
`backend/tests/test_monetization.py`, `test_retention.py`, `test_reset_token_check.py`,
`test_admin_ai_cap.py` (admin cost-control authorization), `test_billing_verify.py`
(Play verification / entitlement / acknowledgement / lifecycle / reconciliation, mocked Play).

## Administrative cost control (AI request cap)
The daily AI request cap is an INTERNAL cost-protection control — never a consumer preference.
- Read/change requires a verified administrator (server-side `ADMIN_EMAILS` check against the
  account's real stored email): `GET /api/admin/ai-cap`, `PATCH /api/admin/ai-cap`.
- A normal authenticated user receives **HTTP 403** from those endpoints.
- `PUT /api/prefs` silently ignores `daily_ai_limit` (consumers can't change or discover the cap).
- The effective cap = admin override (`db.app_config._id="ai_cap"`) → env `DEFAULT_DAILY_AI_LIMIT`.
- Server-side enforcement (`reliability.enforce_ai_cap`, 429 when exceeded; 0 = unlimited) is
  unchanged and always active.
- The consumer "Advanced · cost protection" Settings section is REMOVED. A hidden, admin-only
  screen (`app/admin-cost-controls.tsx`, deep link `/admin-cost-controls`, not in consumer nav)
  exposes the control to authorized admins and shows "not authorized" (backend 403) otherwise.

## Premium entitlement policy (documented, backend-authoritative)
| Play state (subscriptionsv2) | Internal state | Premium access? |
|---|---|---|
| ACTIVE | active | YES (renews) |
| CANCELED (before expiry) | cancelled_active_until_period_end | YES until period end (auto-renew off) |
| IN_GRACE_PERIOD | grace_period | YES (retain; prompt to fix payment) |
| PAUSED | paused | YES until resume/expire |
| ON_HOLD | account_hold | **NO** (entitlement removed until recovered) |
| PENDING | pending | **NO** (never grant a pending purchase) |
| EXPIRED | expired | NO → Free (data retained) |
| Voided / revoked (RTDN voidedPurchaseNotification) | revoked | NO (entitlement removed, idempotent) |

Acknowledgement is performed via the Play Developer API ONLY after a Premium entitlement is
persisted, is idempotent (skips already-acknowledged), and never runs for pending/invalid
purchases. All verification/lifecycle processing is idempotent and fails closed (no local grant).
Purchase tokens are stored bound to one user (replay/reassignment → HTTP 409); logs use a token
hash, never the raw token or service-account credentials.

## Billing endpoints (authenticated, rate-limited)
`GET /api/billing/status` (entitlement + usage), `POST /api/billing/google/verify`,
`POST /api/billing/google/refresh` (re-query Play for the stored token),
`POST /api/billing/google/restore`, `POST /api/billing/google/rtdn` (authenticated Pub/Sub push;
re-queries Play, never trusts the payload; handles purchased/renewed/recovered/restarted/canceled/
paused/grace/on-hold/expired/revoked/pending-canceled/plan-replacement + linked/replacement tokens).
A 6-hourly reconciliation loop (`routers/billing.reconcile_once`) re-verifies active subscriptions
in case an RTDN is missed. Preflight: `python -m billing_preflight` (fails closed when billing is
enabled but credentials are missing; passes with mocked credentials — no real secrets needed).

## Play Console handoff checklist (external — NOT verified from code)
1. Create subscription `student_assistant_premium`.
2. Create monthly base plan `monthly`; set CAD 11.99.
3. Create annual base plan `annual`; set CAD 109.99.
4. Activate BOTH base plans; set regional availability (incl. Canada).
5. Add accurate subscription benefits (match this doc; audio = 240 min / 30 days).
6. Configure grace period; configure account hold; enable resubscribe where appropriate.
7. Configure Google Play Developer API access; create/connect the service account; grant only the
   minimum required permissions; set `GOOGLE_PLAY_SERVICE_ACCOUNT_JSON` on the server.
8. Create the Pub/Sub topic + push subscription to `/api/billing/google/rtdn`; enable RTDN in Play
   Console (Monetization setup); set `PUBSUB_SERVICE_ACCOUNT_EMAIL` (OIDC) or `PUBSUB_VERIFICATION_TOKEN`.
9. Add license testers; test on the internal-testing track: monthly purchase, annual purchase,
   pending payment, cancellation, renewal, restore, reinstall, device change, account hold, grace
   period, expiration, revocation, plan replacement.
10. Set `BILLING_ENABLED=true`, `EXPO_PUBLIC_BILLING_ENABLED=true`,
    `EXPO_PUBLIC_MONETIZATION_EXPECTED=true`, `ADMIN_EMAILS`; re-run both preflights.

