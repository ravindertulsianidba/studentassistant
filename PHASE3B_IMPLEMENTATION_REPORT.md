# Phase 3B Implementation Report

_Provider-neutral calendar synchronization · June 2026_

## What was built

### Backend (`backend/routers/calendar.py`, new)
Endpoints (all `/api`, user-scoped):
| Method | Path | Purpose |
|---|---|---|
| GET | `/calendar/connection` | Current connection + status |
| PUT | `/calendar/connection` | Select device calendar + access mode (read_write/read_only) |
| POST | `/calendar/disconnect` | Disconnect |
| POST | `/calendar/status` | Device reports syncing/sync_failed/permission_revoked/... |
| GET | `/calendar/pending` | SA events to write out (gated: connected + read_write) |
| POST | `/calendar/sync` | Store external IDs + create `calendar_links` |
| POST | `/calendar/link` | Idempotent single-link upsert |
| POST | `/calendar/unlink/{id}` | Failure recovery (safe re-create) |
| POST | `/calendar/external/ingest` | Mirror external events, reconcile, detect deletions |
| GET | `/calendar/external` | Read-only mirror (awareness/conflict) |
| GET | `/calendar/review` | Pending high-risk confirmations |
| POST | `/calendar/review/{id}` | Approve/dismiss a confirmation |

### Backend integration (`backend/routers/planner.py`)
- `/briefing` merges external timed events into `today_classes` (`external:true`), excludes
  SA-linked mirror rows (no duplication), adds **conflict-detection** risk and a
  `calendar_review` risk, and returns `stats.external_today` + `stats.calendar_review`.
- `/weekly-review` includes external events in the workload context.

### Data model
New collections `calendar_connection`, `calendar_links`, `external_events`,
`calendar_review` (see CALENDAR_SYNC_ARCHITECTURE.md §4). Indexes added in `server.py`.

### Frontend
- `src/services/calendar.ts`: `listCalendars`, `connect`, `disconnect`, `getConnection`,
  `fullSync` (read+ingest+write+status), device-guarded and safe on web.
- `app/calendar-connect.tsx` (modal): status card (Connected/Read only/Syncing/Sync
  failed/Permission revoked), access-mode segment, device-calendar picker (with account +
  provider), "Sync now"/"Disconnect", and inline high-risk confirmations.
- `app/(tabs)/profile.tsx`: "Connect Calendar" entry.
- `app/(tabs)/index.tsx` (Today): external events rendered distinctly ("External" badge);
  open-tasks list de-duplicated against due-today/deadlines/overdue.
- `app/_layout.tsx`: `fullSync()` runs on app open when signed in.

## Phase 3A safeguards locked in (this session)
1. `dev-login` and `dev-outbox` → `404` when `ALLOW_INSECURE_DEV=false`.
2. `MockMailer` is used **only** in dev; in production an unconfigured SMTP fails safely
   (`503`) instead of silently mocking (`backend/mailer.py`).
3. Email verification / password reset remain **blocked** for production until live SMTP is
   tested (see AUTHENTICATION_AND_ACCOUNT_AUDIT.md §6).
4. Google Sign-In classification tracked in KNOWN_LIMITATIONS.md.
5. Account deletion now requires **password confirmation** for password accounts
   (`DELETE /api/me` → 403 without it).
6. Phase 3A checkpoint committed (`git tag phase-3a-checkpoint`) before calendar changes.

## Test results
- Backend: **24/24 pass** (`backend/tests/test_calendar_phase3b.py`,
  report `test_reports/iteration_10.json`). Auth 17/17 (iteration 8), onboarding 8/8
  (iteration 9) remain green.
- See PHASE3B_ACCEPTANCE_TEST_REPORT.md for the case-by-case matrix.

## Requires installed-device verification (NOT passed here)
Real `expo-calendar` reads/writes and actual Google / Microsoft-365-on-Android sync are
device-only and were **not** validated on web. See KNOWN_LIMITATIONS.md.
