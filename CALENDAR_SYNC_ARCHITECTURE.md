# Calendar Sync Architecture — Phase 3B

_Student Assistant · provider-neutral two-way calendar synchronization_

## 1. Design principle
Student Assistant works with the calendar the student **already uses**. It never forces
Google Calendar. On device, `expo-calendar` talks to the OS **calendar provider**, which
already aggregates calendars synced from Google, Microsoft 365, Outlook, Exchange, CalDAV
and other Android/iOS-compatible accounts. The app authentication (email/password or
Google Sign-In) is **completely separate** from calendar-provider selection.

## 2. Components
```
┌────────────────────────────┐        ┌──────────────────────────────┐
│  Device (Expo / RN)        │        │  Backend (FastAPI + Mongo)    │
│  services/calendar.ts       │  HTTPS │  routers/calendar.py          │
│  - expo-calendar reads/writes◄──────►│  - connection / links / mirror│
│  - listCalendars()          │        │  - reconciliation + reviews   │
│  - fullSync() orchestrator  │        │  routers/planner.py           │
│  app/calendar-connect.tsx   │        │  - briefing/weekly integration│
└────────────────────────────┘        └──────────────────────────────┘
```
- **Device** owns the actual OS calendar reads/writes (device-only; not testable on web).
- **Backend** owns the source of truth for the connection choice, the internal↔external
  link mapping, a read-only mirror of external events, and all reconciliation decisions.

## 3. Libraries & APIs
- **`expo-calendar`** (SDK 54): `getCalendarsAsync`, `getEventsAsync`, `createEventAsync`,
  `getEventAsync`, `getCalendarPermissionsAsync`, `requestCalendarPermissionsAsync`.
- **Android calendar provider** (via expo-calendar) surfaces provider-synced calendars;
  provider is inferred from each calendar's `source` (`inferProvider`).
- Backend: FastAPI routes under `/api/calendar/*`, Motor/MongoDB collections.

## 4. Data model (MongoDB, all user-scoped)
- `calendar_connection` (1/user): `{user_id, connected, calendar_id, calendar_title,
  account_name, provider, access_mode(read_write|read_only), status, last_sync,
  failure_reason}`. Unique on `user_id`.
- `calendar_links` (1/SA-event written externally): `{user_id, internal_id, external_id,
  device_calendar_id, provider, account_name, sync_direction(outbound|inbound|two_way),
  status, failure_reason, last_sync}`. Unique on `(user_id, internal_id)`.
- `external_events` (read-only mirror): `{user_id, external_id, device_calendar_id, title,
  start, end, all_day, location, recurring, is_sa, internal_id, deleted, updated_at}`.
  Unique on `(user_id, external_id)`.
- `calendar_review` (high-risk confirmations): `{id, user_id, kind(external_edit|
  external_delete), internal_id, external_id, detail, proposed, status, created_at}`.

## 5. Two-way sync rules
- **Outbound (SA → external)**: only when `connected` + `access_mode=read_write`.
  `/calendar/pending` lists SA events with `external_id=null`. The device creates them,
  verifies the write, and reports back via `/calendar/sync` → the backend stores
  `external_id` + a `calendar_links` row. **Recurring events must be approved first**
  (they only reach `pending` once committed out of the AI Inbox).
- **Inbound (external → SA)**: the device reads a ±35-day window and posts to
  `/calendar/external/ingest`. The backend mirrors every event (`external_events`),
  reconciles linked ones, and detects deletions.
- **Non-SA external events**: stored read-only for **awareness + conflict** only. They are
  never turned into tasks and never create Memory/timeline entries.

## 6. Reconciliation & high-risk confirmation
For a linked event changed externally:
- Low-risk change (e.g. title on a normal event) → **auto-applied** to the internal event
  with an audit entry.
- **High-risk** change → queued to `calendar_review` for explicit confirmation, never
  auto-applied. High-risk = start/end **time change**, or the internal event is
  **recurring** or an **exam**. Deadline changes and deleted linked events are always
  high-risk. External deletion of a linked event → `external_delete` confirmation.

## 7. Duplicate prevention & idempotency
- Links are keyed by `internal_id` (unique). Once linked, the event leaves `pending`, so
  retries never create a second external copy.
- `external_events` upsert is keyed by `(user_id, external_id)` → repeated ingests are
  idempotent. `/calendar/sync` and `/calendar/link` are upserts (safe on retry).
- Failure recovery: `/calendar/unlink/{id}` clears the link so a fresh, safe re-create can
  occur without duplicating.

## 8. Background / ongoing sync
`fullSync()` runs: on **app open** (`app/_layout.tsx` when a user session exists), after
**connecting a calendar**, and on demand (**Sync now** in the Connect screen). It reads +
ingests, writes pending (if read_write), and reports status. Edits made in-app to SA
events flow out on the next sync. (Provider push/delta detection is used where the
platform supports it; otherwise interval/app-open polling.)

## 9. User-facing sync states
`connected` · `read_only` · `syncing` · `sync_failed` (with reason) · `permission_revoked`
· `disconnected` — surfaced on `app/calendar-connect.tsx` and never failing silently
(status is always reported back through `/calendar/status`).

## 10. Today reconciliation
`/briefing` merges: tasks due today, internal timed events, external timed events,
confirmed commitments and overdue items — de-duplicated (SA-linked externals are excluded
from the mirror so nothing shows twice), with conflict detection over the merged timed set.
