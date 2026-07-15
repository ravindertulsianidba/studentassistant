#====================================================================================================
# START - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================

# THIS SECTION CONTAINS CRITICAL TESTING INSTRUCTIONS FOR BOTH AGENTS
# BOTH MAIN_AGENT AND TESTING_AGENT MUST PRESERVE THIS ENTIRE BLOCK

# Communication Protocol:
# If the `testing_agent` is available, main agent should delegate all testing tasks to it.
#
# You have access to a file called `test_result.md`. This file contains the complete testing state
# and history, and is the primary means of communication between main and the testing agent.
#
# Main and testing agents must follow this exact format to maintain testing data. 
# The testing data must be entered in yaml format Below is the data structure:
# 
## user_problem_statement: {problem_statement}
## backend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.py"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## frontend:
##   - task: "Task name"
##     implemented: true
##     working: true  # or false or "NA"
##     file: "file_path.js"
##     stuck_count: 0
##     priority: "high"  # or "medium" or "low"
##     needs_retesting: false
##     status_history:
##         -working: true  # or false or "NA"
##         -agent: "main"  # or "testing" or "user"
##         -comment: "Detailed comment about status"
##
## metadata:
##   created_by: "main_agent"
##   version: "1.0"
##   test_sequence: 0
##   run_ui: false
##
## test_plan:
##   current_focus:
##     - "Task name 1"
##     - "Task name 2"
##   stuck_tasks:
##     - "Task name with persistent issues"
##   test_all: false
##   test_priority: "high_first"  # or "sequential" or "stuck_first"
##
## agent_communication:
##     -agent: "main"  # or "testing" or "user"
##     -message: "Communication message between agents"

# Protocol Guidelines for Main agent
#
# 1. Update Test Result File Before Testing:
#    - Main agent must always update the `test_result.md` file before calling the testing agent
#    - Add implementation details to the status_history
#    - Set `needs_retesting` to true for tasks that need testing
#    - Update the `test_plan` section to guide testing priorities
#    - Add a message to `agent_communication` explaining what you've done
#
# 2. Incorporate User Feedback:
#    - When a user provides feedback that something is or isn't working, add this information to the relevant task's status_history
#    - Update the working status based on user feedback
#    - If a user reports an issue with a task that was marked as working, increment the stuck_count
#    - Whenever user reports issue in the app, if we have testing agent and task_result.md file so find the appropriate task for that and append in status_history of that task to contain the user concern and problem as well 
#
# 3. Track Stuck Tasks:
#    - Monitor which tasks have high stuck_count values or where you are fixing same issue again and again, analyze that when you read task_result.md
#    - For persistent issues, use websearch tool to find solutions
#    - Pay special attention to tasks in the stuck_tasks list
#    - When you fix an issue with a stuck task, don't reset the stuck_count until the testing agent confirms it's working
#
# 4. Provide Context to Testing Agent:
#    - When calling the testing agent, provide clear instructions about:
#      - Which tasks need testing (reference the test_plan)
#      - Any authentication details or configuration needed
#      - Specific test scenarios to focus on
#      - Any known issues or edge cases to verify
#
# 5. Call the testing agent with specific instructions referring to test_result.md
#
# IMPORTANT: Main agent must ALWAYS update test_result.md BEFORE calling the testing agent, as it relies on this file to understand what to test next.

#====================================================================================================
# END - Testing Protocol - DO NOT EDIT OR REMOVE THIS SECTION
#====================================================================================================



#====================================================================================================
# Testing Data - Main Agent and testing sub agent both should log testing data below this section
#====================================================================================================
## user_problem_statement: Phase 2 — real native Android + reliability backend for "Student Assistant" (AI academic executive assistant). Self-hostable, Emergent-independent. AI_PROVIDER=fixture in preview (deterministic) because the user's OpenAI key has no billing; live AI is BLOCKED until a funded key is provided.

## backend:
##   - task: "Commitment state machine + reliability ledger"
##     implemented: true
##     working: "NA"
##     file: "backend/reliability.py, backend/server.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "capture/import create a commitment (detected). Auto-commit or review-approve transitions detected->confirmed->scheduled and writes a reminder. Task done -> commitment completed. Ledger (append-only) logs every transition, user-scoped. Endpoints GET /api/commitments, GET /api/ledger."
##   - task: "Dedicated reminder entity + retry + sync + snooze/status"
##     implemented: true
##     working: "NA"
##     file: "backend/reliability.py, backend/server.py"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "GET/POST /api/reminders, POST /api/reminders/{id}/status (delivered/failed w/ retry_count+max_retries, snoozed reschedules), PATCH reschedule, GET /api/reminders/sync (pending + routines for reboot restore), GET /api/reminders/health."
##   - task: "Idempotency on capture"
##     implemented: true
##     working: "NA"
##     file: "backend/reliability.py, backend/server.py"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Header Idempotency-Key on POST /api/capture; replay returns cached result, no duplicate commitments, no double AI-usage. Unique index (user_id,key)."
##   - task: "Per-user daily AI cap"
##     implemented: true
##     working: "NA"
##     file: "backend/reliability.py, backend/server.py"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "prefs.daily_ai_limit (default env DEFAULT_DAILY_AI_LIMIT=150, 0=unlimited). enforce_ai on capture/import/notes/search/transcribe/uploads-complete. Over-limit -> 429 clear message. GET /api/ai-usage."
##   - task: "Chunked resumable audio upload + transcribe"
##     implemented: true
##     working: "NA"
##     file: "backend/server.py"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "POST /api/uploads/init -> /uploads/{id}/chunk (multipart, index, idempotent re-send) -> /uploads/{id}/complete (assembles, refuses if missing chunks 409, transcribes via fixture, creates transcript+chunks)."
##   - task: "Native calendar sync mapping endpoints"
##     implemented: true
##     working: "NA"
##     file: "backend/server.py"
##     needs_retesting: true
##     priority: "medium"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "GET /api/calendar/pending (events with external_id null), POST /api/calendar/sync (record device event ids, dedupe), POST /api/calendar/unlink/{eid} (failure recovery)."
##   - task: "Semantic search w/ Qdrant + keyword fallback"
##     implemented: true
##     working: "NA"
##     file: "backend/vectorstore.py, backend/server.py"
##     needs_retesting: true
##     priority: "medium"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "QDRANT_URL empty in preview -> keyword fallback (mode=keyword). Response includes mode. Vector path uses ai_service.embed (deterministic in fixture). docker-compose adds qdrant service."
##   - task: "Provider-independent AI (fixture) + retry + embeddings"
##     implemented: true
##     working: "NA"
##     file: "backend/ai_service.py, backend/fixtures.py"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "AI_PROVIDER dispatch openai|fixture, no code change to swap. tenacity retry (non-fatal only). LIVE OpenAI still BLOCKED (no billing) — must revalidate capture/import/notes/search/transcribe accuracy once funded key set."

## frontend:
##   - task: "Native notifications, calendar, recording, settings, export"
##     implemented: true
##     working: "NA"
##     file: "frontend/src/services/*, frontend/app/record.tsx, frontend/app/(tabs)/profile.tsx"
##     needs_retesting: true
##     priority: "high"
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "IMPLEMENTED IN CODE. Native scheduled notifications, device-calendar writes, mic recording+background all REQUIRE an APK build — cannot verify in Expo Go/web. Web preview should still load, navigate, show Settings sections (reminders/calendar/AI cap/export) without crashing."

## metadata:
##   created_by: "main_agent"
##   version: "2.0"
##   test_sequence: 3
##   run_ui: false

## test_plan:
##   current_focus:
##     - "Commitment state machine + reliability ledger"
##     - "Dedicated reminder entity + retry + sync + snooze/status"
##     - "Idempotency on capture"
##     - "Per-user daily AI cap"
##     - "Chunked resumable audio upload + transcribe"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication:
##     -agent: "main"
##     -message: "Phase 2 backend implemented on AI_PROVIDER=fixture (deterministic). Please test BACKEND ONLY. Use POST /api/auth/dev-login {email} for tokens (ALLOW_INSECURE_DEV=true). Focus: (1) capture -> commitments state transitions + ledger entries + reminder created; (2) idempotency (same Idempotency-Key returns cached, no dup, ai-usage not double-incremented); (3) daily AI cap: PUT /api/prefs {daily_ai_limit:1} then 2nd AI call -> 429; reset by PUT back to 150; (4) reminders lifecycle: create, status delivered/failed(retry increments, pending after<max, failed at max)/snoozed(reschedules), /reminders/sync returns routines+pending, /reminders/health; (5) chunked upload init/chunk/complete incl 409 when chunks missing; (6) calendar pending/sync/unlink + dedupe; (7) search returns mode=keyword with citations from own data; (8) cross-user isolation on all new collections (commitments/ledger/reminders). Do NOT claim live-AI accuracy — provider is fixture. Skip frontend native features (need APK)."

## agent_communication (Pre-APK regression pass):
##     -agent: "main"
##     -message: "Refactored server.py (1118 LOC) into db.py/core.py/models.py/routers/{auth,content,planner,reliability}.py with NO intended behavior change. Provider is now AI_PROVIDER=openai (funded key, live). Found & fixed ONE regression: /api/briefing returned 500 (NameError: defaultdict) because a top-level import wasn't carried into routers/planner.py — fixed by restoring imports (defaultdict/re/io/time) in routers. Also fixed obsolete tests (conftest api fixture now authenticates; v1/v3 stale assertions updated). Full local suite: 70 passed (fixture mode). Live 6-flow AI validation all HTTP 200. Please RE-VERIFY BACKEND ONLY for regressions across ALL endpoint groups using POST /api/auth/dev-login {email} for tokens: auth+refresh+logout, user isolation (2 users), tasks/events CRUD, capture/import/notes/search (LIVE openai — expect 200 with real output), /briefing (MUST be 200, was the regression), timeline/courses/review, reminders lifecycle+sync+health, commitments+ledger, calendar pending/sync/unlink, chunked uploads init/chunk/complete(+409 incomplete, idempotent complete), idempotency on capture, daily AI cap (PUT /api/prefs {daily_ai_limit:1} -> 2nd capture 429 -> reset to 150), ai-usage, prefs, export, delete /me. Confirm NO route missing, NO 500s, NO broken auth/isolation. NOTE: transcribe/chunked-complete use LIVE Whisper now, so feed a REAL small audio if testing transcription (fake bytes will 503 — that's expected, not a bug). Skip all frontend/native (device-only)."

## agent_communication (Device-reported bug fixes):
##     -agent: "main"
##     -message: "User installed APK and reported: (1) completed tasks cannot be reopened/re-entered; (2) no way to EDIT a task/reminder details or date/time; (3) microphone does nothing on the capture screen; (4) bottom tab bar overlaps Android nav buttons. FIXES: (A) Tab bar now uses safe-area bottom inset (device-only to verify overlap). (B) NEW /app/frontend/app/item-detail.tsx modal: edit title/date-time(DateTimePicker)/priority/category(task) or type/location(event), Save (PATCH /tasks|/events), Mark done<->Reopen (task), Delete. Wired from Today: class rows->edit event, deadline rows->edit task, open-task text->edit task, plus 'Show completed' toggle listing done tasks (tap->reopen). Backend ADDED PATCH /api/events/{id} and DELETE already existed; PATCH /tasks supports status open<->done (reopen). (C) quick-capture mic now REALLY records via expo-audio and POSTs to /transcribe, inserting the transcript into the text box (recording+transcription is DEVICE-ONLY; web shows 'needs installed app'). TEST BOTH: BACKEND - PATCH /api/events/{id} (title/start update refreshes reminder), task status done->open reopen, GET /tasks?status=done, DELETE /events/{id}; ensure prior endpoints still fine (provider is LIVE openai). FRONTEND (web preview) - login via email + Continue; Today loads; tap an open task -> item-detail modal opens, edit title + change type + Save -> returns and reflects; create a task via + capture then complete it, tap 'Show completed' -> it lists -> tap it -> Reopen -> moves back to open; tap a deadline/class row -> edit modal; quick-capture screen renders and mic button present (DO NOT expect actual recording in web). Report any 500s/crashes. Native tab-bar overlap + real mic recording are DEVICE-ONLY (note as such)."

## agent_communication (Phase 3 - iteration 1: Today due-today + secure preview login):
##     -agent: "main"
##     -message: "Implemented Phase 3 §1 (Today due-today aggregation) and §2 (remove insecure preview sign-in from release)."

## backend (Phase 3A — Secure Email/Password Auth + SMTP):
##   - task: "Email/password auth (register, verify-email, login, forgot/reset password, resend, logout-all)"
##     implemented: true
##     working: "NA"
##     file: "backend/routers/auth.py, backend/security.py, backend/mailer.py, backend/auth.py, backend/core.py, backend/config.py, backend/models.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Argon2id hashing (pwdlib), single-use hashed time-limited email verification (24h) + reset (1h) tokens in db.auth_tokens, generic auth errors, IP+account in-memory rate limiting, brute-force lockout (5 fails -> 15 min), JWT access/refresh rotation with token_version (tv) claim for immediate revoke-all, reset revokes all sessions + bumps tv, email verification REQUIRED before login (403 only after correct password). Provider-neutral SMTP via env placeholders -> MockMailer in preview. Dev-only GET /api/auth/dev-outbox returns captured emails (parse token from text). Verified locally end-to-end via curl script (register->403 unverified->verify->reuse 400->login->wrong pw 401->forgot->reset->old token 401->new login->weak pw 422)."

## frontend (Phase 3A — auth UI):
##   - task: "Login screen tabs (Sign In / Create Account), Forgot Password, Check-email, verify-email & reset-password deep-link screens, revoke-all in Settings"
##     implemented: true
##     working: "NA"
##     file: "frontend/app/login.tsx, frontend/app/verify-email.tsx, frontend/app/reset-password.tsx, frontend/src/auth.tsx, frontend/app/_layout.tsx, frontend/app/(tabs)/profile.tsx"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Segmented Sign In/Create Account tabs, show/hide password, strength meter, confirm password, Forgot Password flow, Check-email state with resend cooldown + change email + back to sign in. /verify-email and /reset-password are public routes reading ?token=. Google Sign-In retained. Dev quick sign-in only in __DEV__. Settings has 'Sign out of all devices' (revoke-all)."

## test_plan (current):
##   current_focus:
##     - "Email/password auth (register, verify-email, login, forgot/reset password, resend, logout-all)"
##     - "Login screen tabs + verify/reset deep-link screens"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication (Phase 3A - Secure Auth):
##     -agent: "main"
##     -message: "Implemented Phase 3A secure email/password auth + SMTP (mock in preview). TEST BOTH. Mock mail: GET /api/auth/dev-outbox returns {messages:[{to,subject,text}]}; parse token from text 'verify-email?token=<T>' / 'reset-password?token=<T>'. BACKEND cases: (1) register sends 1 verification email; (2) login before verify -> 403; (3) verify with token -> ok; (4) reuse verify token -> 400 used; (5) expired token behavior (cannot force expiry easily — verify code path returns 400 for tampered token); (6) login after verify -> 200 session with tv claim; (7) wrong password -> 401 GENERIC 'Invalid email or password.'; (8) brute force: 5 wrong passwords -> 429 lockout; (9) forgot-password always 200 generic; (10) reset-password with token -> 200, then OLD access token -> 401 'Session expired' (tv bumped) and OLD refresh -> 401; (11) reused reset token -> 400; (12) weak password (<10) on register/reset -> 422; (13) duplicate register of verified account -> generic 200 (no leak); (14) two-user data isolation (register+verify 2 users, ensure /tasks etc scoped); (15) logout-all bumps tv (old access 401); (16) Google (/auth/google) still present, dev-login still 200 (ALLOW_INSECURE_DEV=true). Email normalization: MixedCase@X.com == mixedcase@x.com. FRONTEND (web preview, __DEV__): /login shows Sign In/Create Account tabs; Create Account -> fill name/email/password(>=10)/confirm -> strength meter -> submit -> 'Verify your email' check screen with Resend (cooldown) + 'Use a different email' + 'Back to sign in'. Forgot password link -> email -> 'Check your email'. Since real inbox isn't available, you can pull the token from /api/auth/dev-outbox and open /verify-email?token=<T> and /reset-password?token=<T> directly to confirm those screens render success/failure. Google button present. Do NOT test onboarding (not built yet). SMTP live delivery is NOT testable (placeholders) — mark as requiring live SMTP creds."

