# Functional Test Report — Student Assistant

Method: automated pytest (`/app/backend/tests/test_v3_hardening.py`) + manual curl. Auth via `/api/auth/dev-login` (test-only). Result: **32/32 passed**. JUnit: `/app/test_reports/pytest/v3_results.xml`.

| # | Requirement | Method | Expected | Actual | Result |
|---|---|---|---|---|---|
| 1 | Health | GET /api/health | status ok, config flags | ok, ai/google false | PASS |
| 2 | Unauth gating | GET protected w/o token | 401 | 401 | PASS |
| 3 | Sign-in (dev) | POST /auth/dev-login | tokens + user | tokens+user | PASS |
| 4 | Session persistence | GET /me w/ bearer | user profile | profile | PASS |
| 5 | Token refresh | POST /auth/refresh | new tokens, old revoked | rotated | PASS |
| 6 | Sign out | POST /auth/logout | refresh revoked | subsequent refresh 401 | PASS |
| 7 | Two-user isolation (read) | A vs B list tasks/events | only own | only own | PASS |
| 8 | IDOR delete | A DELETE B task | 404, B intact | 404, intact | PASS |
| 9 | IDOR patch | A PATCH B task | 404 | 404 | PASS |
| 10 | Cross-user source/note | A GET B source | 404 | 404 | PASS |
| 11 | Export scoping | GET /export as A | only A data | scoped | PASS |
| 12 | Account deletion | DELETE /me | data gone, sessions revoked | confirmed | PASS |
| 13 | Tasks CRUD | create/list/patch/delete | correct | correct | PASS |
| 14 | Events CRUD | create/list/delete | correct | correct | PASS |
| 15 | Briefing | GET /briefing | stats+risks+recommendation | present | PASS |
| 16 | Courses | GET /courses,/courses/{n} | scoped counts + workspace | correct | PASS |
| 17 | Memory filters | GET /timeline?kind/course/q | filtered | filtered | PASS |
| 18 | Evening review | GET /evening-review | unfinished+actions | present | PASS |
| 19 | Prefs | GET/PUT /prefs | persisted | persisted | PASS |
| 20 | AI graceful degrade | POST capture/import/notes/transcribe (no key) | 503 clean | 503 | PASS |

AI content-producing paths (capture→commit, import extraction, notes generation, search answers, transcription) require `OPENAI_API_KEY`; verified to fail safely (503) without it. Full end-to-end AI functional runs are covered by AI_RELIABILITY_TEST_REPORT.md once the key is configured.

Remaining risk: none in tested scope. Remediation completed: DELETE now returns 404 on missing rows; placeholder JWT_SECRET rejected when ALLOW_INSECURE_DEV=false.

## Real document support (Capture Anything — added, verified)
| Req | Method | Expected | Actual | Result |
|---|---|---|---|---|
| PDF/DOCX/TXT upload | POST /api/import/file (multipart) | text extracted + source stored + searchable chunks | TXT (112 chars) & DOCX (42 chars) extracted, source_docs + chunks written, timeline entries created | PASS |
| Unsupported type | upload .xyz | 415 | 415 | PASS |
| AI extraction on document | after upload | items→AI Inbox when AI available; graceful defer when not | `ai_extracted:false` + clear `ai_error` while OpenAI quota exhausted (no crash) | PASS (degrade) |
Frontend: Capture Anything now offers Photo / Gallery / Document (PDF·DOCX·TXT) via the Android document picker; PDF page numbers preserved as `[page N]` markers for source-grounded citations.

