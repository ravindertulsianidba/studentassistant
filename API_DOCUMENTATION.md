# API Documentation — Student Assistant

Base URL: `${BACKEND}/api`. All endpoints except `/health` and `/auth/*` require `Authorization: Bearer <access_token>`. All data is scoped to the authenticated user. Errors return `{ "detail": "..." }`.

## Auth
| Method | Path | Body | Notes |
|---|---|---|---|
| POST | `/auth/google` | `{id_token}` | Verifies Google ID token → issues JWTs. 503 if Google not configured. |
| POST | `/auth/dev-login` | `{email}` | **Test only**; 404 when `ALLOW_INSECURE_DEV=false`. |
| POST | `/auth/refresh` | `{refresh_token}` | Rotates refresh token, returns new access+refresh. |
| POST | `/auth/logout` | `{refresh_token}` | Revokes refresh token. |
| GET | `/me` | — | Current user profile. |
| DELETE | `/me` | — | Deletes account + all data, revokes sessions. |

Response of google/dev-login: `{access_token, refresh_token, expires_at, user:{id,email,name}}`.

## Core
| Method | Path | Purpose |
|---|---|---|
| POST | `/capture` `{text}` | NL → risk-based routing (auto-commit or AI Inbox). Returns `{committed, review}`. |
| POST | `/import` `{image_base64?|text?, filename?}` | Auto-classifies doc, stores source + chunks, sends items to AI Inbox. Returns `{doc_type, source_id, review}`. |
| GET | `/source/{id}` | Original source document + extracted text. |
| POST | `/transcribe` (multipart `file`, `course?`, `title?`) | Whisper transcription → `{transcript_id, text}`. |
| POST | `/notes/generate` `{title, course?, transcript}` | Structured study notes; keeps transcript. |
| GET | `/notes` · GET `/notes/{id}` | List / detail. |
| POST | `/search` `{query}` | Source-grounded answer over the user's own chunks. Returns `{answer, citations[]}`. |
| GET | `/tasks?status=` · POST · PATCH `/tasks/{id}` · DELETE | Tasks CRUD. |
| GET | `/events` · POST · DELETE `/events/{id}` | Events CRUD. |
| GET | `/timeline?kind=&course=&q=` | Memory feed (filters). |
| GET | `/review` · POST `/review/{id}/action` `{action, edited?}` | AI Inbox (approve/edit/ignore/delete). |
| GET | `/courses` · GET `/courses/{name}` | Course list / workspace. |
| GET | `/briefing` · `/evening-review` · `/weekly-review` | Assistant routines. |
| GET | `/prefs` · PUT `/prefs` | Notification times, reminder defaults, quiet hours, auto-create. |
| GET | `/export` | Full user data JSON. |
| GET | `/health` | Liveness + config flags (no auth). |

## Risk-based routing (capture/import)
- High-risk (recurring, exam, ambiguous date, deadline change, possible duplicate) → **always AI Inbox**.
- Calendar event → commit only if confidence ≥ 0.90, else AI Inbox.
- Task → auto-create if confidence ≥ 0.90 and `auto_create_tasks` pref on (with undo), else AI Inbox.
- Imported document items → always AI Inbox (source material requires approval).

## Relationship detection
Items carry an `entity`. On commit, normalized entity/title within the same course are matched: exact → link + audit deadline changes; partial (≥0.6 overlap) → flagged `possible_match` → AI Inbox. Never auto-merges when uncertain.
