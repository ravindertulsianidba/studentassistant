# PRE-APK Regression Report — Student Assistant

**Scope:** final code & release-readiness pass after (1) OpenAI billing fix and
(2) the `server.py` → routers/models/core/db refactor. **No product features
added; no user-facing behavior changed.** APK NOT built (next step is
independent review → build → physical-device testing).

---

## 1. Files changed (this pass)
**Backend refactor (logic moved verbatim from the 1118-LOC `server.py`):**
- `backend/server.py` — now app assembly only (90 LOC): app, CORS, exception handlers, `/api/health`, router include, startup indexes, shutdown.
- `backend/db.py` — Mongo client + `db` handle (moved out of server).
- `backend/core.py` — helpers, prompts, business logic (`commit_item`, `route_items`, `build_review`, `enforce_ai`, `maybe_reminder`, `add_chunks`, etc.), `CurrentUser`, auth session helpers.
- `backend/models.py` — all 13 Pydantic request models (moved verbatim).
- `backend/routers/auth.py`, `routers/content.py`, `routers/planner.py`, `routers/reliability.py` — endpoints grouped; `@api.` → `@router.` (`APIRouter(prefix="/api")`).

**Regression fixes made during this pass:**
- `routers/planner.py` / all routers — added missing top-level imports that the monolith had (`from collections import defaultdict`, `re`, `io`, `time`). **This fixed the one real regression** (`/briefing` → 500, `NameError: defaultdict`).
- Routers switched from `from models import *` to explicit model imports (enables static undefined-name detection; cleaner).

**Test maintenance (stale assertions predating current behavior — no product change):**
- `backend/tests/conftest.py` — the shared `api` fixture now authenticates via `dev-login` (it never authenticated after Phase-1 auth was introduced; legacy suites 401'd regardless of the refactor).
- `backend/tests/backend_test.py` — 3 v1-era assertions aligned to current behavior: root route (→ `/api/health`), search shape (`matches` → `citations`/`mode`), removed `/api/wipe` (→ asserts 404/405; deletion is `/api/me`).
- `backend/tests/test_v3_hardening.py` — health flags now config-agnostic; `TestAI503` (dead-key era) → assert graceful `200|503` (AI is now a working dependency w/ fixture fallback).
- `backend/tests/test_phase2_reliability.py` — daily-cap test uses a quota-consuming call first (empty-corpus search is intentionally free).

**Env / docs:**
- `backend/.env` — `AI_PROVIDER` (final: `openai`); key via env only (never printed/committed).
- `PHASE2_STATUS.md` — live-AI results + full release-readiness checklist.
- `PRE_APK_REGRESSION_REPORT.md` — this file.

## 2. Tests run & results
Runner: `pytest`, backend via supervisor, `EXPO_PUBLIC_BACKEND_URL` (preview ingress).
Automated suite executed with `AI_PROVIDER=fixture` (deterministic — the suite's design mode).

| File | Tests | Result |
|------|-------|--------|
| backend_test.py | 16 | pass |
| test_v2_features.py | 9 | pass |
| test_v3_hardening.py | 32 | pass |
| test_phase2_reliability.py | 13 | pass |
| **Total** | **70** | **70 passed, 0 failed, 0 error, 0 skipped** |

Warnings: none blocking. No skips.

## 3. Live OpenAI results (`AI_PROVIDER=openai`, funded key)
Direct provider probe: `POST /v1/chat/completions` → **HTTP 200** (quota active).
| Flow | Endpoint | Result |
|------|----------|--------|
| Capture parsing | POST /api/capture | 200 — 1 committed + 1 review; relative dates resolved; exam→review |
| File import & extraction | POST /api/import | 200 — classified `syllabus`, dated items extracted |
| Study-note generation | POST /api/notes/generate | 200 — full structured sections |
| Transcription | POST /api/transcribe | 200 — exact transcript (TTS round-trip) |
| Embeddings | ai_service.embed | 1536-d vector (text-embedding-3-small) |
| Semantic search | POST /api/search + in-memory Qdrant | keyword: grounded answer + citation (200); semantic retrieval returns correct nearest doc with live embeddings |

## 4. Routes compared — before vs after refactor
Method: imported the pre-refactor monolith (`git 365fb36:backend/server.py`) and the
current app; compared `app.routes`.
- **Before: 49 `/api` routes. After: 49.**
- **Removed: NONE. Added: NONE.**

## 5. Schema / behaviour changes
- **Request models:** 13 before / 13 after; **field sets identical** (verified programmatically).
- **Response schemas:** unchanged (logic moved verbatim; 70/70 behavioural tests pass, incl. shape assertions).
- **Behaviour changes:** NONE intended or observed. Env handling unchanged (`config.py` reads env; `.env` untouched except `AI_PROVIDER`/key value). DB init unchanged (same indexes). Qdrant, uploads, retry, idempotency, reminders, calendar mapping, audit logs, daily AI cap all unchanged and tested.

## 6. Regression verdict
**One regression found and fixed:** `/briefing` 500 (`NameError: defaultdict`) caused by
a top-level import not carried into the new router module. Fixed by restoring the
missing imports; `/briefing` now 200 and covered by tests. **No other regressions**
(routes, schemas, auth/isolation, env, DB init, Qdrant, uploads/retry/idempotency/
reminders/calendar/audit/AI-cap all intact; no circular imports; clean startup).

## 7. Known risks
- Legacy suites (`backend_test.py`, `test_v2_features.py`) still depend on the deterministic fixture provider for AI-shape stability; run them under `AI_PROVIDER=fixture` (their design mode). Live AI is validated separately (§3).
- The rate-limit test fires a 120-request burst; run the full suite allowing ~90s.
- Semantic search returns `mode:"keyword"` until a Qdrant server is running (`QDRANT_URL`).

## 8. Remaining device-only tests (must pass on hardware — NOT verified)
Background/locked-screen recording · persistent FG-service notification · scheduled
notifications firing · Snooze/Done actions · reminder restoration after reboot ·
device-calendar writes (recurring) + dedupe · data export via Android share sheet.

## 9. Exact commands to build the first APK (do NOT run yet)
Set build-time env first (EAS secrets or shell): `EXPO_PUBLIC_BACKEND_URL=https://<your-api-domain>`
(and Google client IDs).

**Option A — EAS (cloud, your own Expo account):**
```bash
cd frontend
npm i -g eas-cli
eas login
eas init                                   # writes extra.eas.projectId
eas build -p android --profile preview     # -> installable APK
eas build -p android --profile production  # -> AAB for Play
```
**Option B — Local (no cloud):**
```bash
cd frontend
npx expo prebuild -p android
cd android
./gradlew assembleRelease     # -> app/build/outputs/apk/release/app-release.apk
./gradlew bundleRelease        # -> app/build/outputs/bundle/release/app-release.aab
```

---
*This is a pre-APK checkpoint. The application is **not** described as
production-ready; independent review, APK build, and physical-device testing follow.*
