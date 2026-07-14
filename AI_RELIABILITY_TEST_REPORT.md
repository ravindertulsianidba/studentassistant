# AI Reliability Test Report — Student Assistant

Status: **PENDING CREDENTIALS.** The AI layer, prompts, and risk rules are implemented and unit-safe (endpoints return clean 503 without a key). The fixed regression set below must be executed once `OPENAI_API_KEY` is configured. This file defines the suite and pass criteria; results will be filled after the key run.

## Fixed regression set (inputs)
1. Clear task — "Email the TA about my grade" → task, no invented date.
2. Clear calendar event — "Lecture Monday 9am room 204" → event, confidence ≥0.90.
3. Ambiguous date — "Submit the essay soon" → datetime=null, ambiguous → **AI Inbox**.
4. Ambiguous time — "Meet advisor Tuesday" (no time) → event to **AI Inbox**.
5. Recurring class — "I have chem lab every Tuesday 2pm" → recurring → **AI Inbox**.
6. Exam date — "Final exam Dec 12" → exam → **AI Inbox** (always).
7. Changed deadline — "Assignment 2 moved to Oct 20" (existing A2) → deadline-change → **AI Inbox**, audit preserves old date.
8. Two similar assignments — "Assignment 2" vs "the second SOC assignment" → possible_match → **AI Inbox**, no duplicate.
9. Personal task — "Buy groceries" → task, no course.
10. Gym commitment — "Go to the gym" → task, no invented date.
11. Multiple tasks in one sentence — "I need to study and go to the gym" → two separate tasks.
12. No actionable commitment — "That lecture was interesting" → no items.
13. Contradictory sources — two due dates for same item → conflict surfaced, newest ranked, **AI Inbox**.
14. Low-quality timetable image — extract classes → all to **AI Inbox** for approval.
15. Multi-page syllabus (text) — assignments/exams with page refs → **AI Inbox**, source-linked.
16. Unclear lecture audio — transcript with low-confidence flags; notes flag unclear material, invent nothing.

## Assertions (must all hold)
- No unsupported/ invented dates (rule 3,4,10).
- Exams and recurring schedules **always** enter AI Inbox (6,5,14).
- Ambiguous dates never silently committed (3,4).
- No duplicate tasks/events/courses created (8).
- Updated deadlines retain audit history (`/audit`) (7).
- Search answers cite `[Source: ...]` and refuse when unverifiable (source-grounded).
- Study notes never fabricate concepts/dates/exam topics; unclear material flagged.

## How to run
1. Set `OPENAI_API_KEY` in `backend/.env`; `restart backend`.
2. Execute the regression set via the testing agent (backend), one dev-login user.
3. Record per-case Expected/Actual/Pass and attach logs here.

Current partial evidence: routing logic verified by code + `test_v3_hardening.py` (503 degradation). Live content generation not yet exercised.
