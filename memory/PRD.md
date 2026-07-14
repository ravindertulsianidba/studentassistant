# Student Assistant — PRD

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
