# Phase 3C Implementation Report

_Reliability, Active Listening, Diagnostics, background sync · June 2026_

## 0. Background-sync clarification (answering the open question)
- **Previously**, sync ran only "on app open" — that is a **foreground** trigger, **not**
  background sync. This has been corrected.
- **Now implemented (`src/services/background.ts`)** using **`expo-background-task`** +
  `expo-task-manager`: an OS-scheduled task (`minimumInterval` 15 min) runs
  `calendar.fullSync()` + `notifications.syncAndSchedule()` **while the app is closed**, and
  the OS **re-runs it after device restart**.
- **Foreground triggers** (in `app/_layout.tsx`): on app open, on sign-in, and on
  `AppState` returning to `active` (covers "after permission restored" and "after external
  change" once reopened). After a failed sync, status is set `sync_failed`; the next
  foreground/background pass retries (idempotent upserts).
- ⚠️ **Background execution is DEVICE-ONLY** — it cannot be validated in Expo Go or web.
  Marked accordingly in KNOWN_LIMITATIONS.md.

## 1. What already existed (Phase 2, verified still working)
Reliability Ledger, commitment state machine, dedicated Reminder entity + retry,
notification scheduling & reboot restoration, chunked uploads + retry (`recordingUpload`),
transcript generation (`/transcribe`), study-note generation (`/notes/generate`), and real
data export. Lecture Recording (`app/record.tsx`) already supports course, start/stop,
background/locked-screen capture, 90-min+, local-first audio, chunked resumable upload with
retry, timestamped transcript, study notes, and clear processing states.

## 2. New in Phase 3C

### Active Listening (`backend/routers/listen.py`, `app/listen.tsx`) — 7/7 tests
- Explicitly started by the student; single active session enforced.
- Visible "Listening now" state, elapsed timer, audio-activity meter, pause/resume/stop.
- Device audio captured locally (device-only); on stop, transcribed and run through the
  capture extraction pipeline → commitments routed to the **AI Inbox** (`route_items`).
- Session summary (detected / to-inbox / auto-created) + **Undo** (removes created review +
  committed items + commitments). Every transition written to the **reliability ledger**.
- Best-effort persistent Android notification while listening (stop-from-notification
  round-trip is device-only, pending validation).
- Web fallback: type the transcript to exercise the pipeline without a device.

### Diagnostics (`backend/routers/diagnostics.py`, `app/diagnostics.tsx`) — 7/7 tests
- `GET /api/diagnostics` aggregates: auth, backend, AI provider, notification permission +
  scheduled/failed counts, calendar connection/last-sync/failures/pending-confirmations,
  microphone permission, Active Listening status, recording status, pending/failed uploads,
  pending processing jobs, last transcription, last study-note generation, timezone.
- Safe actions: **Test notification, Test backend, Test AI provider, Test calendar read,
  Create & delete test event, Test microphone, Retry failed jobs, Export diagnostic report.**
- `POST /api/diagnostics/device-state` lets the device report mic/notif permission +
  recording; `GET /api/diagnostics/report` adds the recent ledger for export.

### Offline queue & failure recovery
Failed uploads and reminders are re-queued via `/api/diagnostics/retry-jobs`; uploads keep
local audio until confirmed; sync/ingest are idempotent so retries never duplicate.

## 3. Deliverables reference
1. This report.
2. **Reliability Ledger schema** — `db.ledger`: `{id, user_id, commitment_id, entity_type,
   entity_id, action, from_state, to_state, actor, detail, idempotency_key, ts}` (append-only).
3. **Commitment state machine** — states `detected→confirmed→scheduled→completed` (+
   `dismissed`/`cancelled`/`failed` with undo/retry edges); see `backend/reliability.py`.
4. **Reminder schema & delivery** — `db.reminders`: `{id, user_id, ref_type, ref_id, title,
   body, remind_at, status(pending/scheduled/delivered/snoozed/failed), retry_count,
   max_retries, last_attempt_at, delivered_at, external_id, snooze_until, routine}`; device
   schedules from `/reminders/sync`, reports status back, retries up to `max_retries`,
   rebuilt on cold start / background task (reboot restoration).
5. **Notification implementation** — `src/services/notifications.ts` (permissions,
   `syncAndSchedule`, routines, reboot rebuild, `sendTestNotification`).
6. **Active Listening** — see §2.
7. **Lecture Recording** — `app/record.tsx` + `src/services/recordingUpload.ts` (§1).
8. **Calendar background-sync clarification** — see §0.
9. **Diagnostics** — see §2.
10. **Automated test results** — Phase 3C 20/20 (`test_reports/iteration_11.json`); 3B 24/24
    (10); auth 17/17 (8); onboarding 8/8 (9).
11. **Requires installed-device validation** — on-device audio capture, background &
    locked-screen recording, persistent-notification stop action, **true background sync**,
    and all real device-calendar sync. See KNOWN_LIMITATIONS.md.
12. **Updated APK** — produce via Publish or `eas build … --profile preview`
    (see PHASE3B_APK_PACKAGE.md).
13. **Independent APK/AAB build instructions** — BUILD_AND_SIGNING.md (`eas.json` has
    `preview` APK, `production` AAB, `production-apk` APK profiles + local gradle path).
14. **Honest limitations** — KNOWN_LIMITATIONS.md.

## 4. Not production-ready (unchanged)
- Live SMTP email delivery (Phase 3A) — awaiting real credentials + inbox test.
- Provider-neutral calendar sync — awaiting physical device validation (PHASE3B_APK_PACKAGE.md).
- True background sync & Active Listening audio — awaiting native-build validation.
