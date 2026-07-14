# Known Limitations & Status — Student Assistant

Status legend: ✅ implemented & tested here · 🔑 implemented, needs production credentials · 📱 implemented in code, requires a real Android build to verify · 🟡 partial · ⛔ not implemented.

## Backend / server-side (verifiable in this environment)
- ✅ Provider-independent AI layer (OpenAI) — Emergent runtime removed (`emergentintegrations`/`litellm` uninstalled; no `EMERGENT_LLM_KEY` in code).
- ✅ Auth + per-user data isolation across all entities; 2-user isolation enforced; public delete-all removed; account deletion + export.
- ✅ Security: restricted CORS (env), rate limiting, file size/type validation, sanitized errors, hashed refresh tokens, DB indexes, fail-fast config.
- ✅ Risk-based AI Inbox routing, relationship detection + deadline-change audit history, source-grounded chunked search with citations, briefing/evening/weekly reviews, course workspaces.
- 🔑 Live AI (capture/import/notes/search/transcribe) requires `OPENAI_API_KEY`. Returns a clean `503` when unset.
- 🔑 Real Google Sign-In requires `GOOGLE_CLIENT_ID`. Preview uses `/auth/dev-login` (disabled in prod).

## Mobile / native (implemented in code — require a real dev/release build to VERIFY; not testable in Expo Go / web preview)
See **PHASE2_STATUS.md** for the item-by-item verification matrix.
- 📱 Active Listening: `app/record.tsx` records via `expo-audio` with `UIBackgroundModes:["audio"]` (iOS) and `FOREGROUND_SERVICE_MICROPHONE` (Android) for background/locked-screen capture. Needs device verification of the always-on foreground service.
- 📱 Lecture upload ≥90 min: real chunked/resumable upload (`src/services/recordingUpload.ts` → `/api/uploads/init|chunk|complete`) with per-chunk retry+backoff; server refuses incomplete assembly (409) and `/complete` is idempotent. Long-run + interruption recovery to be confirmed on device.
- 📱 Device calendar: `src/services/calendar.ts` creates a dedicated calendar, writes events (with weekly recurrence), verifies each write, and reports external ids to the server for dedupe/recovery (`/api/calendar/*`). Needs device verification.
- 📱 Local notifications: `src/services/notifications.ts` schedules reminders + daily/weekly routines, Done/Snooze actions, and rebuilds the schedule from the server on launch (reboot restoration). Needs device verification.
- 📱 Data export via Android share sheet: `expo-sharing` writes the `/api/export` archive to a file and opens the share sheet. Needs device verification.
- ✅ Reliability backend for all of the above (state machine, ledger, reminders, idempotency, AI cap, chunked upload, calendar mapping) is verified here with automated tests (`backend/tests/test_phase2_reliability.py`).
- 🔴 Live AI (capture/import/notes/transcribe/search quality) is BLOCKED: the supplied OpenAI key has no billing (429 insufficient_quota). Preview runs `AI_PROVIDER=fixture` (deterministic). Flip to `openai` + funded key and run the live-AI checklist in PHASE2_STATUS.md.

## Not implemented (by design / out of scope)
- ⛔ LMS API integration (explicitly excluded).
- ⛔ Grade calculator, flashcards, quizzes, tutor, Pomodoro, wellness — intentionally excluded to preserve focus.

## Recommended before Play release
Wire the native modules (foreground-service recording, expo-calendar, expo-notifications, share intents) in a development build and execute the device test matrix in ANDROID_RELEASE_GUIDE.md; publish Privacy Policy & Terms pages.
