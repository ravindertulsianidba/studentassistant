# Student Assistant — PRD

## Implemented v4 (2026-07-14) — Phase 2: Native Android + Reliability
- **LIVE AI VALIDATED** (funded OpenAI key, `AI_PROVIDER=openai`): capture, import,
  study notes, Whisper transcription, chunked-upload transcription, source-grounded
  search, embeddings (1536-d) and Qdrant semantic retrieval — all verified HTTP 200
  with correct output. See PHASE2_STATUS.md.
- **Backend refactored** into `db.py` / `core.py` / `models.py` / `routers/*`
  (server.py 1118→90 LOC), **no functional change** — Phase-2 suite 13/13 pass.
- **Reliability core (backend, VERIFIED 13/13 tests)**: Commitment state machine
  (detected→confirmed→scheduled→completed/dismissed), append-only user-scoped
  **reliability ledger**, dedicated **Reminder** entity with retry (retry_count/
  max_retries, snooze reschedules), **idempotency** (`Idempotency-Key` on capture),
  and **per-user daily AI cap** (cost protection; admin default `DEFAULT_DAILY_AI_LIMIT`,
  0=unlimited, in-app tunable, 429 with clear message). New endpoints: `/commitments`,
  `/ledger`, `/reminders(/sync|/health|/{id}/status)`, `/calendar/(pending|sync|unlink)`,
  `/uploads/(init|chunk|complete)`, `/ai-usage`.
- **Provider-independent AI**: `AI_PROVIDER` dispatch `openai|fixture` (zero-code swap).
  Deterministic `fixtures.py` lets the whole pipeline be tested with NO key. tenacity
  retry on transient (not quota/auth) errors. Embeddings API added.
- **Semantic search**: Qdrant integration (`vectorstore.py`) with automatic keyword
  fallback (`mode` in response). `docker-compose.production.yml` ships a Qdrant service.
- **Native (implemented in code, require APK to VERIFY — see PHASE2_STATUS.md)**:
  `app/record.tsx` background/locked-screen recording (`expo-audio`, iOS `UIBackgroundModes`,
  Android FG-service) → chunked/resumable upload (`recordingUpload.ts`) with retry;
  local notifications + Done/Snooze + daily/weekly routines + reboot restoration
  (`notifications.ts`); device calendar write + recurrence + dedupe + recovery
  (`calendar.ts`); Settings screen wires reminders/calendar/AI-cap/export; data export
  via Android share sheet (`expo-sharing`).
- **Independent build**: `frontend/eas.json` (dev / preview APK / production AAB) +
  local Gradle path documented — NOT dependent on the Emergent Publish button.
- **BLOCKED**: live AI quality — supplied OpenAI key has no billing (429). Preview runs
  `AI_PROVIDER=fixture`. Live-AI + device re-test checklists in PHASE2_STATUS.md.

## Implemented v2 (2026-07-14) — UX & Intelligence Refinements
- Navigation simplified to 5 mental models: **Today, Capture (FAB), Memory, Courses, Settings**.
- **Timeline → Memory**: global search + type filter + course filter + jump-to-source (notes/courses).
- **Review Queue → AI Inbox** (modal): detected summary, source, confidence label (High/Needs review/Low), suggested action, Approve/Edit/Ignore/Delete.
- **Capture Anything**: one workflow — text/voice + attach photo/file; backend auto-classifies doc type (schedule/syllabus/email/etc.), no manual classification.
- **Home** feels like an executive assistant: AI prompt bar, KPI stats, AI Inbox summary, "What needs attention" proactive alerts, Recent memory.
- **Proactive intelligence**: overdue/"you promised to" nudges, multi-deadline & near-due warnings, missing schedule/syllabus alerts.
- **Relationship detection**: capture/import extract an `entity`; repeat mentions of same entity+course UPDATE the existing task/event (linked) instead of duplicating.
- **Course workspace** (/course/[name]): schedule, assignments/tasks, study notes, filtered memory.
- Confidence indicators surfaced throughout. Backend: 25/25 tests pass.

## Implemented v3 (2026-07-14) — Production Hardening (Phase 1)
- **Emergent runtime removed**: provider-independent `ai_service.py` (OpenAI); `emergentintegrations`/`litellm` uninstalled; no `EMERGENT_LLM_KEY` in code. Fail-fast `config.validate()`.
- **Auth + isolation**: Google ID-token verification + own JWT (access/refresh rotation, revoke), test-only dev-login; `user_id` on ALL entities; every op scoped. **32/32 backend audit tests pass**; 2-user isolation + IDOR enforced.
- **Security**: env CORS (no wildcard), rate limiting (429), upload size/type validation (413), sanitized 500s, hashed refresh tokens, DB indexes, account deletion + export, public delete-all removed.
- **Product**: risk-based AI Inbox routing (exams/recurring/ambiguous/deadline-change/possible-dup → always Inbox), relationship detection + deadline audit history, source-grounded chunked search with citations, evening/weekly reviews, source documents, transcription endpoint, prefs.
- **Frontend**: login screen + AuthContext (secure token storage, refresh, sign out, delete account); all API calls authenticated.
- **Deployment package**: Dockerfile, docker-compose.production.yml, Nginx+TLS, deploy/update/backup/restore scripts, `.env.example`, + 10 audit/guide docs.
- **Android metadata**: name "Student Assistant", package `com.ravindertulsiani.studentassistant`, scheme, mic/notification/calendar/foreground permissions.

### Pending (credentials / device build)
- 🔑 Live AI + real Google: need `OPENAI_API_KEY` + `GOOGLE_CLIENT_ID`.
- 📱 Native Android (foreground recording while locked, device calendar writes, background notifications, share-sheet/PDF-DOCX pickers, APK/AAB): implemented in code/metadata, require a real build to verify. See KNOWN_LIMITATIONS.md.

## Original Problem Statement
Build "Student Assistant", an AI Academic Executive Assistant (Android-first, Expo/React Native) for university students. Not a tutor/note app. It captures, remembers, organizes, schedules, and follows up on everything a student manages during a semester — so they never forget a class, assignment, deadline, meeting, or commitment. Must feel modern, minimal, fast, calm, intelligent, and keep the user in control.

## User Choices (defaults chosen — user skipped clarification)
- AI model: **Claude Sonnet 4.6** via Emergent LLM key (emergentintegrations).
- Transcription: intended OpenAI Whisper (deferred — see backlog). Lecture notes use pasted/typed transcript for now.
- Scheduling: **in-app Smart Calendar + Tasks** (no Google OAuth friction). Google Calendar/Tasks sync deferred.
- Design: calm minimal light theme (sage green + bone white), SpaceGrotesk (display) + Manrope (body).

## Architecture
- **Backend**: FastAPI + MongoDB (motor). All routes under `/api`. LLM via emergentintegrations (Claude Sonnet 4.6). Collections: tasks, events, timeline, review, notes, imports.
- **Frontend**: Expo Router file-based routing. Bottom tabs (Today, Timeline, [Capture FAB], Review, You) + modal routes (quick-capture, import, notes, search). Theme tokens in `src/theme.ts`, API client `src/api.ts`, shared UI `src/components/ui.tsx`.

## Implemented (2026-07-13)
- AI Commitment Capture: natural language → structured events/tasks with confidence scoring; >=0.75 auto-added, else Review Queue.
- Smart Calendar (events) + Smart Tasks (CRUD, mark done) — in-app.
- Review Queue: approve (commits) / edit title / ignore.
- Schedule/Syllabus/Email Import: camera/gallery image → Claude OCR extraction → Review Queue.
- AI Study Notes: transcript → structured notes (overview, key concepts, definitions, examples, relationships, professor emphasis, dates, exam topics, action items, review recs). Keeps original transcript.
- Daily Briefing: greeting, KPI stats, today's classes, deadlines, Smart Risk Detection.
- Weekly Review (AI summary + workload + recommendations) in Profile.
- Search Everything: natural-language LLM search across tasks/events/notes/timeline.
- Life Timeline: chronological, filterable by type.
- Privacy: export data, delete-all, clear recording/privacy messaging.
- Backend: 16/16 automated tests passing. Frontend: capture/timeline/review/notes/search/profile verified.

## Backlog (prioritized)
- **P0**: Lecture audio recording + Whisper transcription (currently transcript is pasted/typed).
- **P1**: Real Google Calendar + Google Tasks two-way sync (OAuth).
- **P1**: Evening Review flow (completed / reschedule / unfinished).
- **P1**: PDF/DOCX syllabus parsing (currently image-based only).
- **P2**: Recurring class events on the calendar view (weekly grid), conflict-detection UI.
- **P2**: Course tagging + per-course filtering across timeline/search.
- **P2**: Local morning/evening reminder scheduling.

## Next Tasks
1. Add audio recording (expo-audio) + Whisper transcription for lectures.
2. Build Evening Review screen.
3. Add a dedicated Calendar week/day view.
