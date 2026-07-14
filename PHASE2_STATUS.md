# Phase 2 Status — Honest Verification Matrix

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
| **Live OpenAI extraction / transcription / notes / search quality** | 🔴 | Live test attempts: BOTH supplied keys return **HTTP 429 · insufficient_quota** (key authenticates OK — 401 NOT returned — but the OpenAI account has no quota/credits). Blocked on account billing. See re-test checklist below |

## f. Semantic search (Qdrant)
| Item | Status | Evidence |
|---|---|---|
| Keyword fallback (always available) | ✅ | `mode:"keyword"` + citations |
| Qdrant integration + graceful degrade | 🧪 | `vectorstore.py`; Qdrant not running in preview (`QDRANT_URL` empty) |
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
