# Calendar Sync Audit — Phase 3B

_Correctness, safety, privacy & isolation review of the calendar subsystem._

## 1. Data isolation
- Every calendar collection (`calendar_connection`, `calendar_links`, `external_events`,
  `calendar_review`) is filtered by `user_id` on every query/update. Verified by a
  two-user isolation test (user B sees none of user A's data). ✅
- Account deletion removes all four collections for the user (`DELETE /api/me`). ✅

## 2. Duplicate prevention (idempotency)
- `calendar_links` unique on `(user_id, internal_id)`; `external_events` unique on
  `(user_id, external_id)`. `/calendar/sync`, `/calendar/link`, and ingest use upserts. ✅
- Once an SA event is linked it drops out of `/calendar/pending`, so retried device writes
  cannot create a second external copy. ✅
- `/calendar/unlink/{id}` provides safe recovery (clears link → controlled re-create). ✅

## 3. High-risk change protection
- Time changes, recurring events, and exams require explicit confirmation
  (`calendar_review`), never auto-applied. Deleted linked events require confirmation.
  Low-risk (e.g. title) changes auto-apply with an audit record. ✅
- Recurring SA events can only be written out after they are committed (not while in the
  AI Inbox), preserving "recurring requires approval before first creation". ✅

## 4. Read-only vs read-write
- `access_mode=read_only` → `/calendar/pending` returns `[]` (no outbound writes); external
  events are still read for awareness. Enforced server-side, not just in the UI. ✅
- If the chosen device calendar disallows modifications, `connect()` downgrades the mode to
  read_only automatically. ✅

## 5. Awareness-only for foreign events
- Non-SA external events (`is_sa=false`) are stored solely for schedule awareness/conflict.
  They never create tasks, commitments, or Memory/timeline entries. ✅

## 6. Failure visibility (no silent failures)
- Device reports `syncing` / `sync_failed` (with `failure_reason`) / `permission_revoked`
  via `/calendar/status`; the Connect screen surfaces each state and offers Open Settings
  on revocation. `fullSync()` always reports a terminal status. ✅

## 7. Privacy
- Only event metadata needed for scheduling (title, times, location, recurrence flag) is
  mirrored. No attendee lists or descriptions are ingested. External calendar access is
  requested just-in-time and is independent of app login.

## 8. Known gaps / follow-ups
- Real device read/write + provider-specific behavior are device-only (see
  KNOWN_LIMITATIONS.md) and unverified here.
- Deletion detection depends on the device sending a bounded window; a linked event
  outside the reported window is not evaluated for deletion in that pass (by design).
- Provider push/delta detection depends on OS/provider support; otherwise sync is
  app-open + interval + post-edit.
- The time-change audit record stores a human-readable summary rather than per-field
  old/new for start/end (cosmetic; noted in code review).
