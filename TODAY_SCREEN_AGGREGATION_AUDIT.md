# Today-Screen Aggregation Audit (Phase 3 §1)

## Problem
Today could show "Your schedule is clear" while a task was due the same day,
because `/briefing` computed "today" in **UTC** and had **no due-today bucket** —
same-day tasks were only shown as "upcoming."

## Fix (implemented)
`GET /api/briefing?tz_offset_min=<minutes>` — the Android/web client passes its
local UTC offset (`-new Date().getTimezoneOffset()`), so "today" is the student's
**local** date. The endpoint now returns reconciled buckets:

| Field | Meaning |
|-------|---------|
| `due_today` | open tasks whose **local** due-date == today |
| `overdue` | open tasks whose local due-date < today |
| `deadlines` | open tasks due in the next 1–7 days (today excluded → no double-count) |
| `today_classes` | internal + external events on today's local date (+ recurring by weekday) |
| `has_timed_events` | true only if there are timed events today |

Rules:
- A task with a **date but no time** → due by **end of that local day** (date comparison).
- Completed tasks never appear in `due_today` (only `status:"open"` is queried).
- Tasks and events stay distinct concepts; Today shows both, no duplication.
- No calendar event is auto-created for a due-today task.

### Today screen (client)
- New **"Due today"** section (checkbox to complete, tap to edit).
- Schedule wording: timed events → list them; else if tasks due today → **"No timed
  events today."** + the due-today list; else → "Your schedule is clear today."

## Automated tests — `backend/tests/test_today_aggregation.py` (9/9 PASS)
due-today appears · due-tomorrow is upcoming (not today) · overdue separate ·
completed-today hidden · date-with-no-time = today · 11:59 PM today · timezone
shifts the day (UTC+14 vs UTC−11) · no-timed-events flag · external event today in schedule.

DST note: handled implicitly — the client sends its **current** offset each call, so
the correct local date is used across DST transitions (offset changes are reflected).

## Status: Verified (backend automated + testing_agent). Client rendering verified in web preview.
