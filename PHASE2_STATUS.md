# Phase 2 Status — Honest Verification Matrix

## ✅ LIVE AI VALIDATION — PASSED (funded OpenAI key, provider=openai)
Direct provider check: `POST /v1/chat/completions` → **HTTP 200** (quota active).
End-to-end through the backend, all HTTP 200 with correct output:
1. **Capture** — "sociology midterm Friday 10am … email Professor Lee tomorrow" → exam correctly routed to review (high-risk), reminder→task auto-committed; relative dates resolved (Fri=2026-07-17, tomorrow=07-15).
2. **Import (text)** — syllabus snippet → classified `syllabus`, 3 items with correct due dates (Sep 15 / Oct 3 / Dec 12 09:00).
3. **Study notes** — full structured sections generated (overview, key_concepts, definitions, exam topics, …).
4. **Transcription** — TTS-synthesized speech → Whisper returned the exact sentence.
5. **Chunked upload → transcribe** — 2-chunk reassembly (75,840 bytes) → exact transcript.
6. **Search** — source-grounded answer with citation ("final exam is on December 12 at 9am [Source: syllabus …]").
7. **Embeddings** — live `text-embedding-3-small`, dim 1536.
8. **Semantic retrieval** — in-memory Qdrant + live embeddings: query "when is the final exam scheduled" → correct nearest doc (score 0.769).

Backend was also refactored (server.py 1118→90 LOC; `core`/`models`/`db`/`routers/*`) with **no functional change** — Phase-2 reliability suite **13/13 pass**.

---

This project distinguishes four levels of "done". Per the user's requirement,
**permissions, packages, endpoints, mocks and documentation do NOT count as
completed functionality.**

Legend:
- ✅ **Verified here** — exercised end-to-end in this environment with automated tests.
- 🧪 **Code complete, deterministic-tested** — real code, tested against the
  `fixture` AI provider (deterministic). Live-model quality NOT yet validated.
- 📱 **Code complete, awaiting DEVICE verification** — real native code that
  cannot run in Expo Go / web preview; must be checked on an APK build.
- 🔴 **Blocked** — cannot proceed without an external dependency.

---

## a. Reliability core (backend)
| Item | Status | Evidence |
|---|---|---|
| Commitment state machine (detected→confirmed→scheduled→completed/dismissed) | ✅ | `test_phase2_reliability.py`, ledger transitions asserted |
| Append-only reliability ledger (user-scoped audit) | ✅ | `GET /api/ledger` |
| Dedicated Reminder entity + retry (max_retries, retry_count) | ✅ | status delivered/failed→retry/snoozed→reschedule |
| Idempotency (`Idempotency-Key` on capture) | ✅ | replay cached, no dup, single ai-usage |
| Per-user daily AI cap (cost protection, admin default env) | ✅ | over-limit → 429; `GET /api/ai-usage` |

## b. Native notifications
| Item | Status | Evidence |
|---|---|---|
| Server reminder model + `/reminders/sync` (routines + pending) | ✅ | tested |
| Local scheduling, Android channel, Done/Snooze actions | 📱 | `src/services/notifications.ts` — needs build |
| Reboot restoration (reschedule from server on launch) | 📱 | `syncAndSchedule()` on app open — needs build |
| Daily briefing / evening / weekly routines | 📱 | DAILY/WEEKLY triggers — needs build |
| Notification health check | ✅ (server) / 📱 (device count) | `/reminders/health` + `notifications.health()` |

## c. Native device calendar
| Item | Status | Evidence |
|---|---|---|
| Sync mapping + dedupe + failure recovery (server) | ✅ | `/calendar/pending`, `/calendar/sync`, `/calendar/unlink` |
| Device calendar create + recurring rules + write verify | 📱 | `src/services/calendar.ts` — needs build |
| External event id mapping (no duplicates on re-sync) | 📱→✅ | server dedupe verified; device write needs build |

## d. Active listening / lecture recording
| Item | Status | Evidence |
|---|---|---|
| Chunked/resumable upload + assemble + transcribe (server) | ✅ | init/chunk/complete, 409-when-incomplete, idempotent complete |
| Mic capture, background + locked-screen recording | 📱 | `app/record.tsx` (`expo-audio`, `UIBackgroundModes`, FG service) — needs build |
| Local audio preserved until server confirms | 📱 | `recordingUpload.ts` deletes only after `/complete` — needs build |
| Chunk retry with backoff | 🧪 | code paths present; long-run verified on device |

## e. Provider-independent AI
| Item | Status | Evidence |
|---|---|---|
| `AI_PROVIDER` dispatch (openai/fixture), zero-code swap | ✅ | `ai_service.py` |
| Deterministic fixtures for pipeline testing | 🧪 | `fixtures.py` |
| Transient-error retry (tenacity, non-fatal only) | 🧪 | quota/auth not retried |
| **Live OpenAI extraction / transcription / notes / search quality** | ✅ | VALIDATED with funded key — see "Live AI Validation" at top (capture/import/notes/transcribe/search/embeddings/semantic all HTTP 200 with correct output) |

## f. Semantic search (Qdrant)
| Item | Status | Evidence |
|---|---|---|
| Keyword fallback (always available) | ✅ | `mode:"keyword"` + citations |
| Qdrant integration + graceful degrade | ✅ | `vectorstore.py`; semantic retrieval verified with live embeddings (in-memory Qdrant round-trip); preview server has no Qdrant so live app uses keyword fallback |
| Production Qdrant service | 📦 | `docker-compose.production.yml` ships `qdrant` |

## g. Data export
| Item | Status | Evidence |
|---|---|---|
| Full user export (server) | ✅ | `GET /api/export` (incl. commitments/ledger/reminders) |
| Android share-sheet export of the archive | 📱 | `profile.tsx` + `expo-sharing` — needs build |

## h. Independent build & deploy
| Item | Status | Evidence |
|---|---|---|
| `eas.json` (dev/preview APK/production AAB) | 📦 | `frontend/eas.json` |
| Local Gradle build path (no cloud) | 📦 | ANDROID_RELEASE_GUIDE.md Option B |
| Hostinger docker-compose (+ Qdrant) | 📦 | `docker-compose.production.yml` |

---

## 🔴 LIVE-AI RE-TEST CHECKLIST (run once a FUNDED OpenAI key is set)
1. In `backend/.env`: set `AI_PROVIDER=openai` and a funded `OPENAI_API_KEY`; restart backend.
2. `GET /api/health` → `ai_live:true`.
3. `POST /api/capture` with real sentences → assert correct kind/date extraction quality.
4. `POST /api/import` (image) and `/api/import/file` (PDF/DOCX) → classification + item extraction quality.
5. `POST /api/notes/generate` → study-note structure fidelity (no invented facts).
6. `POST /api/transcribe` and chunked `/uploads/*` with a REAL audio file → Whisper transcript accuracy.
7. `POST /api/search` → grounded answer + correct citations (and `mode:"semantic"` once `QDRANT_URL` set).
8. Confirm daily AI cap counts live calls; confirm retry behavior on transient 5xx.

## 🔴 DEVICE RE-TEST CHECKLIST (run on an APK build)
Execute the device test matrix in ANDROID_RELEASE_GUIDE.md. Nothing marked 📱
above may be called "working" until it passes on a physical device.

---

## Remaining blockers
- **None for the backend / AI pipeline.** Live AI validated end-to-end.
- To get `mode:"semantic"` in production, run Qdrant (shipped in `docker-compose.production.yml`, `QDRANT_URL=http://qdrant:6333`). Preview has no Qdrant → keyword mode (still grounded + cited).

## Native Android items still requiring PHYSICAL DEVICE testing (📱)
These are implemented in real native code but cannot be verified in Expo Go / web preview:
1. Background / locked-screen lecture recording + persistent foreground-service notification.
2. Long (90-min) chunked upload with interruption/retry on a real network.
3. Scheduled local notifications actually firing; Done/Snooze actions; reminders surviving a device reboot (re-scheduled from `/reminders/sync` on launch).
4. Device-calendar writes (recurring events) + dedupe on re-sync.
5. Data export opening the Android share sheet.

## Readiness for the FIRST APK build
READY. Prerequisites in place:
- `frontend/app.json` — name/package/versionCode, all permissions, iOS `UIBackgroundModes:["audio"]`, config plugins (`expo-audio`/`expo-notifications`/`expo-calendar`).
- `frontend/eas.json` — `preview` (APK) and `production` (AAB) profiles.
- Independent build paths documented in `ANDROID_RELEASE_GUIDE.md` (EAS cloud **or** local `expo prebuild` + Gradle).
- Set build-time env before building: `EXPO_PUBLIC_BACKEND_URL` (+ Google client IDs).
- After install, run the device checklist above; nothing marked 📱 is "working" until it passes on hardware.

---

# Release-Readiness Checklist (pre-APK)

Classification: **Verified** | **Code complete, device testing required** | **Build testing required** | **Production setup required** | **Blocked**

| # | Area | Status | Evidence / Note |
|---|------|--------|-----------------|
| 1 | OpenAI live validation | **Verified** | provider=openai, HTTP 200 for capture/import/notes/transcribe(exact)/embeddings(1536)/search(grounded+cited) |
| 2 | Authentication & user isolation | **Verified** | test_v3_hardening TestAuth + TestIsolation pass (task/event/source/export/courses scoped; B cannot patch/delete A) |
| 3 | MongoDB | **Verified** | health db:true; startup indexes created; full CRUD green |
| 4 | Qdrant (vector store) | **Production setup required** | code + graceful fallback verified; embeddings live (1536-d); semantic retrieval proven via in-memory Qdrant; prod must run the shipped `qdrant` service (`QDRANT_URL`) |
| 5 | Capture & import extraction | **Verified** | live: dates resolved, exam→review, syllabus classified w/ dated items |
| 6 | Transcription | **Verified** | live Whisper returned exact text (TTS round-trip) + chunked reassembly exact |
| 7 | Search | **Verified** (keyword) / semantic **Production setup required** | keyword grounded answer + citations live; semantic needs prod Qdrant |
| 8 | Reliability ledger + commitment state machine | **Verified** | test_phase2_reliability 13/13 (transitions + append-only ledger) |
| 9 | Reminders (server model, retry, sync, health) | **Verified** | lifecycle/retry/snooze/sync/health tested |
| 9b | Reminders firing on device (schedule/snooze/done/reboot restore) | **Code complete, device testing required** | `src/services/notifications.ts` — not verifiable in Expo Go/web |
| 10 | Calendar sync (server mapping, dedupe, recovery) | **Verified** | /calendar/pending, /sync, /unlink tested |
| 10b | Device-calendar writes (recurring) | **Code complete, device testing required** | `src/services/calendar.ts` |
| 11 | Chunked upload & recovery | **Verified** | init/chunk/complete, 409-on-incomplete, idempotent complete, retry logic present |
| 12 | Daily AI cap | **Verified** | over-limit → 429; env default; per-user; /ai-usage |
| 13 | Android configuration (permissions, plugins, FG service) | **Build testing required** | app.json + plugins set; must be validated in a build |
| 14 | APK build readiness | **Build testing required** | eas.json `preview` profile + local Gradle path documented |
| 15 | AAB build readiness | **Build testing required** | eas.json `production` (app-bundle) profile |
| 16 | Background/locked-screen recording | **Code complete, device testing required** | `app/record.tsx` + UIBackgroundModes + FG-service perms |
| 17 | Scheduled notifications | **Code complete, device testing required** | device-only |
| 18 | Snooze / Done actions | **Code complete, device testing required** | device-only |
| 19 | Notification restoration after reboot | **Code complete, device testing required** | `syncAndSchedule()` on launch; device-only |
| 20 | Device-calendar writes | **Code complete, device testing required** | device-only |
| 21 | Share-sheet export | **Code complete, device testing required** | `expo-sharing`; device-only |
| 22 | Privacy policy | **Production setup required** | `PRIVACY_AND_DATA_HANDLING.md` drafted; a published, linked policy URL is required for store submission |
| 23 | Crash reporting | **Production setup required** | NOT integrated (no Sentry/Crashlytics). Recommend adding before store release |
| 24 | Production logging & monitoring | **Production setup required** | app logs to stdout + `/api/health`; central log aggregation/alerting to be set up on the VPS |
| 25 | Backup & recovery | **Production setup required** | procedure documented in `OPERATIONS_RUNBOOK.md`; automated Mongo/Qdrant backups must be configured on the VPS |

**Explicitly NOT verified (require a physical device):** items 9b, 16, 17, 18, 19, 20, 21.
**Not production-ready** — this is a pre-APK checkpoint pending independent review, APK build, and device testing.
