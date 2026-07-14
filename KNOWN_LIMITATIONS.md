# Known Limitations & Status — Student Assistant

Status legend: ✅ implemented & tested here · 🔑 implemented, needs production credentials · 📱 implemented in code, requires a real Android build to verify · 🟡 partial · ⛔ not implemented.

## Backend / server-side (verifiable in this environment)
- ✅ Provider-independent AI layer (OpenAI) — Emergent runtime removed (`emergentintegrations`/`litellm` uninstalled; no `EMERGENT_LLM_KEY` in code).
- ✅ Auth + per-user data isolation across all entities; 2-user isolation enforced; public delete-all removed; account deletion + export.
- ✅ Security: restricted CORS (env), rate limiting, file size/type validation, sanitized errors, hashed refresh tokens, DB indexes, fail-fast config.
- ✅ Risk-based AI Inbox routing, relationship detection + deadline-change audit history, source-grounded chunked search with citations, briefing/evening/weekly reviews, course workspaces.
- 🔑 Live AI (capture/import/notes/search/transcribe) requires `OPENAI_API_KEY`. Returns a clean `503` when unset.
- 🔑 Real Google Sign-In requires `GOOGLE_CLIENT_ID`. Preview uses `/auth/dev-login` (disabled in prod).

## Mobile / native (require a real dev/release build — NOT verifiable in Expo Go web preview)
- 📱 Active Listening foreground service while screen-locked + persistent notification. Recording UI/controls and the `/transcribe` pipeline exist; the always-on Android foreground service must be validated on a device build.
- 📱 Lecture recording ≥90 min with chunked/resumable upload and interruption recovery — client capture + server transcription implemented; long-run resumable upload hardening pending device testing.
- 📱 Device calendar read/write (recurring events to the student's selected calendar) — permissions declared; native calendar writes (`expo-calendar`) to be wired + verified on device.
- 📱 Android local notifications (class/deadline/briefing/evening/weekly), actions, after-reboot scheduling — preferences model + times implemented; native scheduling to be wired on build.
- 📱 Share-sheet intake (share email/text/PDF/DOCX into the app) & document picker for PDF/DOCX — `/import` accepts text/image now; PDF/DOCX text extraction (pypdf/python-docx) runs server-side; Android share intents + document picker wired at build.
- 🟡 Transcript speaker labels & tap-to-timestamp, TXT/PDF/DOCX export of transcript — transcription returns text; timestamped/speaker-labeled output and export formats are partial.
- 🟡 Google Tasks sync — internal tasks are source of truth; external Google Tasks sync not implemented (optional per spec).

## Not implemented (by design / out of scope)
- ⛔ LMS API integration (explicitly excluded).
- ⛔ Grade calculator, flashcards, quizzes, tutor, Pomodoro, wellness — intentionally excluded to preserve focus.

## Recommended before Play release
Wire the native modules (foreground-service recording, expo-calendar, expo-notifications, share intents) in a development build and execute the device test matrix in ANDROID_RELEASE_GUIDE.md; publish Privacy Policy & Terms pages.
