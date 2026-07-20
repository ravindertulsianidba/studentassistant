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


## agent_communication (Phase 3B - Calendar backend):
##     -agent: "main"
##     -message: "Implemented Phase 3B provider-neutral calendar backend (routers/calendar.py) + Today/Weekly integration (routers/planner.py). TEST BACKEND ONLY — device calendar reads/writes are device-only and CANNOT be validated on web; do NOT mark real Google/Microsoft device sync as passed. Use POST /api/auth/dev-login {email} for tokens. Cases: (1) PUT /calendar/connection read_write->connected, read_only->read_only. (2) GET /calendar/pending returns SA events (external_id null) ONLY when connected+read_write else []. (3) POST /events then it appears in pending; POST /calendar/sync {mappings:{id:extid}} sets external_id + creates calendar_links; repeat sync is idempotent (no dup); pending drops it. (4) POST /calendar/external/ingest: title-only change to a linked non-highrisk (study) event auto-updates internal; a start/end change creates calendar_review kind external_edit and does NOT change internal until POST /calendar/review/{id}{approve:true}. (5) exam/recurring internal event: ANY change requires confirmation. (6) Deletion: ingest with window_start/window_end and linked external_id absent -> external_events deleted + calendar_review kind external_delete; approve deletes internal + link. (7) non-SA external events stored is_sa=false and never become tasks/timeline. (8) GET /calendar/external lists non-deleted. (9) POST /calendar/status permission_revoked sets connected false; sync_failed stores failure_reason. (10) GET /briefing?tz_offset_min=0: external event dated today appears in today_classes external:true, not duplicated when SA-linked; overlapping timed events -> 'Schedule conflict' risk; stats include external_today + calendar_review. (11) two-user isolation on connection/links/external/review. (12) Regression: tasks/events CRUD, briefing buckets, timeline, reminders still 200. (13) Safeguard: DELETE /me for a password account requires correct password (403 otherwise); dev-login accounts (no password) delete without one."

## agent_communication (Phase 3C - Active Listening + Diagnostics backend):
##     -agent: "main"
##     -message: "Implemented Phase 3C backend: Active Listening sessions (routers/listen.py) + Diagnostics (routers/diagnostics.py). TEST BACKEND ONLY. Use POST /api/auth/dev-login {email}. Active Listening cases: (1) POST /listen/start {course} -> session status 'listening'; GET /listen/active returns it; starting again returns the same active session (only one at a time). (2) /listen/{id}/pause -> 'paused'; /resume -> 'listening'. (3) /listen/{id}/append {text} accumulates transcript. (4) /listen/{id}/stop {transcript} with a transcript containing a deadline+exam -> status 'done', summary has items_detected>0, and detected items appear in AI Inbox (GET /review) and/or auto-created. (5) /listen/{id}/undo removes the items it created (review + committed) and sets status 'undone'; GET /review count drops back. (6) stop with empty transcript -> done, 0 items, no crash. Diagnostics cases: (7) GET /diagnostics?tz=America/New_York returns auth/backend/ai_provider/notifications/calendar/microphone/active_listening/recording/uploads/processing/last_transcription/last_study_notes/timezone; timezone echoes the tz param. (8) POST /diagnostics/device-state {mic_permission,notif_permission,recording} then GET /diagnostics reflects recording + notifications.permission. (9) POST /diagnostics/test-backend -> ok true. (10) POST /diagnostics/test-ai -> ok true with latency_ms (LIVE OpenAI). (11) POST /diagnostics/test-calendar-read -> returns connected + external_events_mirrored. (12) POST /diagnostics/retry-jobs -> ok with counts. (13) GET /diagnostics/report includes recent_ledger array. (14) Two-user isolation: user B cannot see user A's listen sessions or diagnostics data. (15) Regression: auth, /review, /events, /tasks, /briefing still 200. NOTE: device audio capture, background recording, persistent notification stop-action, and true background sync (expo-background-task) are DEVICE-ONLY and must NOT be marked passed from API tests."

## agent_communication (Pre-build auth-screen cleanup):
##     -agent: "main"
##     -message: "Cleaned the normal login screen: removed dev email field, 'Quick sign-in (dev)', 'dev-only' divider, and 'Google Sign-In activates in the installed app build' + the nonfunctional Google placeholder. Normal /login now shows ONLY: Create Account / Sign In (email+password), Forgot Password, and Continue with Google ONLY when GOOGLE_ENABLED (client IDs present — currently hidden in preview). Dev login moved to hidden internal route /dev-login guarded by __DEV__ AND EXPO_PUBLIC_ENABLE_DEV_LOGIN==='true' (default false in preview .env) — it Redirects to /login otherwise. TEST FRONTEND (web preview): (1) /login shows Sign In + Create Account tabs, email, password, Forgot password; NO 'dev-only', NO 'Quick sign-in', NO 'activates in the installed', NO dev email field, NO Google button (not configured). (2) Real email/password works in preview: register a fresh tester+<ts>@uni.edu via Create Account (password 'correct horse battery staple') -> 'Verify your email' screen; then complete verification by fetching the token from GET /api/auth/dev-outbox (ALLOW_INSECURE_DEV=true in preview) and POST /api/auth/verify-email, then Sign In on /login -> lands on app (onboarding or Today). (3) Navigating to /dev-login in the browser Redirects to /login (dev route absent by default because EXPO_PUBLIC_ENABLE_DEV_LOGIN=false). TEST BACKEND: (4) /api/auth/dev-login gating is config-based (returns 404 when ALLOW_INSECURE_DEV=false — already verified iteration 8; in this preview it is true so returns 200, that's expected). Do NOT fail on that. Just confirm the endpoint exists and email/password endpoints all work. NOTE: dev-login/dev-outbox 404-in-prod is controlled by ALLOW_INSECURE_DEV and cannot be toggled here. Auth (17/17 it8), onboarding (8/8 it9), calendar (24/24 it10), listen+diagnostics (20/20 it11) already passed — only verify this cleanup + preview email/password."

## agent_communication (Monetization / entitlements / cost control):
##     -agent: "main"
##     -message: "IMPORTANT: staging is now production-style — ALLOW_INSECURE_DEV=false so /api/auth/dev-login and /api/auth/dev-outbox return 404. Authenticate using the SEEDED verified account email='montest.user@decisivlabs.dev' password='StarterPack#2026!' (POST /api/auth/login). Re-seed if needed: python backend/tests/seed_montest_user.py. Implemented Free/Starter-Pack/Premium entitlements, usage metering + cost ledger, Google Play billing behind BILLING_ENABLED=false, retention cleanup, paywall. BACKEND cases: (1) GET /api/billing/status (auth) -> plan 'free', state 'free', features has audio_minutes/ai_import/import_pages/memory_question/ai_briefing with used/allowance/remaining; product block present. (2) GET /api/usage/status same shape. (3) GET /api/plan/config -> free_starter + premium allowance maps, billing_enabled false. (4) Metering enforcement: with the seeded account, POST /api/search {query:'...'} that returns a grounded AI answer consumes 1 memory_question; after 5 it returns HTTP 402 with structured detail {error:'limit_reached',feature:'memory_question',consumed,allowance,reset_date}. NOTE consuming requires the user to have some captured/imported source content to ground on; if none, /search returns early WITHOUT consuming (that is correct). (5) POST /api/import {text:'CS101 midterm on Dec 5'} consumes 1 ai_import + 1 import_pages; after 2 imports the 3rd -> 402 limit_reached. (6) POST /api/billing/google/verify -> 503 'not yet available' (BILLING_ENABLED false) and NEVER grants premium. (7) POST /api/monetization/event {kind:'paywall_impression'} -> ok; unknown kind -> 400. (8) GET /api/admin/monetization and /api/admin/cost-projection -> 403 for the non-admin seeded user. (9) Regression: /api/tasks, /api/events, /api/briefing, /api/review still 200; manual task creation still works (Free never blocked). (10) Free data never lost: after limits reached, GET existing tasks/notes still 200. FRONTEND (web preview, use seeded login then Skip onboarding): (a) /diagnostics shows 'Plan & usage' card: Free (Starter Pack), 5 usage bars, Upgrade/Restore/Manage buttons. (b) /paywall renders headline, Annual(Best value)+Monthly both visible, 'Price shown at checkout', 'Subscriptions launch soon', auto-renew disclosure, Restore/Manage/Privacy/Terms. (c) Manual task creation in Today works without paywall. NOTE device-only (DO NOT mark passed from web): expo-iap purchase/restore, real Google Play verification, RTDN. Retention + monetization core already unit-tested (backend/tests/test_monetization.py, test_retention.py PASS). BILLING is MOCKED-OFF via BILLING_ENABLED=false (no real Play transactions)."

## backend (Premium billing + admin cost-control — this task):
##   - task: "Administrative AI cost-control authorization"
##     implemented: true
##     working: true
##     file: "backend/routers/monetization.py, backend/reliability.py, backend/routers/planner.py, backend/core.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Daily AI cap is now admin-only. GET/PATCH /api/admin/ai-cap require verified admin (ADMIN_EMAILS, server-side email check) -> 403 for normal users. PUT /api/prefs strips daily_ai_limit. Effective cap = db.app_config(_id=ai_cap) -> env DEFAULT_DAILY_AI_LIMIT. Server-side 429 enforcement unchanged. Direct-module test test_admin_ai_cap.py PASS."
##         -working: true
##         -agent: "testing"
##         -comment: "VERIFIED ALL CASES. (1) Normal user GET/PATCH /api/admin/ai-cap -> 403. (2) Admin GET /api/admin/ai-cap -> 200 with {daily_ai_limit,source,unlimited}; admin PATCH {daily_ai_limit:2} -> 200 with updated value; admin PATCH {daily_ai_limit:-1} -> 400; reset to 150 successful. (3) Normal user PUT /api/prefs {daily_ai_limit:1,morning_time:'08:00'} -> 200, response has NO daily_ai_limit but morning_time='08:00'. (9) GET /api/admin/monetization & /api/admin/cost-projection -> 403 for normal user, 200 for admin. (10) Regression: /api/tasks, /api/events, /api/briefing, /api/review, /api/usage/status all return 200. Unit test test_admin_ai_cap.py PASS. AI cap enforcement (429 via /api/capture) SKIPPED as expected (AI service 503, covered by unit test)."
##   - task: "Google Play billing verify/refresh/restore/RTDN + entitlement/ack/reconcile"
##     implemented: true
##     working: true
##     file: "backend/routers/billing.py, backend/server.py, backend/billing_preflight.py"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: false
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "BILLING_ENABLED=true. Product/base-plan validated Google-side; token bound to one user (409 on reassign); backend acknowledgement only after grant (idempotent); normalized subscription record + token hash; POST /billing/google/refresh; 6h reconciliation loop; RTDN handles voided->revoked + lifecycle audit. Verify/restore/refresh fail closed (503/502, no local grant) without credentials. Direct-module test test_billing_verify.py PASS."
##         -working: true
##         -agent: "testing"
##         -comment: "VERIFIED ALL CASES. (4) GET /api/billing/status -> 200 with plan/state/features (audio_minutes/ai_import/import_pages/memory_question), product block, billing_enabled=true. (5) POST /api/billing/google/verify {purchase_token:'x'} -> 503 (no credentials) and never returns premium. (6) POST /api/billing/google/refresh -> 200 returning billing status, never grants premium. (7) POST /api/billing/google/rtdn (no auth) -> 401. (8) GET /api/plan/config -> 200 with premium.audio_minutes=240 (NOT 300) and free_starter present. Unit tests test_billing_verify.py (2 cases), test_monetization.py, test_admin_entitlements.py (2 cases) all PASS."

## frontend (Premium UI — this task):
##   - task: "Remove Advanced cost-protection section; add Premium card + Premium screen"
##     implemented: true
##     working: "NA"
##     file: "frontend/app/(tabs)/profile.tsx, frontend/app/premium.tsx, frontend/app/admin-cost-controls.tsx, frontend/src/services/billing.ts"
##     stuck_count: 0
##     priority: "high"
##     needs_retesting: true
##     status_history:
##         -working: "NA"
##         -agent: "main"
##         -comment: "Settings: cost-protection section removed; Premium card near top (Free->'Upgrade to Premium', Premium->'Manage Premium') opens /premium. Premium screen shows plan state, benefits from backend config (audio 240 min, never 300), Free-vs-Premium table, localized Play prices (no fake pricing when catalog missing), auto-renew disclosure, Restore/Manage/Privacy/Terms, refresh on focus+foreground. Web/unsupported shows accurate message (no broken button, no 'coming soon'). Hidden admin route /admin-cost-controls (not in nav). TS+ESLint clean."

## test_plan (current - Premium billing + admin cost-control):
##   current_focus:
##     - "Administrative AI cost-control authorization"
##     - "Google Play billing verify/refresh/restore/RTDN + entitlement/ack/reconcile"
##   stuck_tasks: []
##   test_all: false
##   test_priority: "high_first"

## agent_communication (Premium billing + admin cost-control):
##     -agent: "main"
##     -message: "TEST BACKEND ONLY (device Play billing cannot run on server). ALLOW_INSECURE_DEV=true so dev-login works. Normal user: POST /api/auth/dev-login {email:'anyuser+<ts>@example.com'}. Admin: POST /api/auth/dev-login {email:'admin.montest@decisivlabs.dev'} (in ADMIN_EMAILS). CASES: (1) Normal user GET /api/admin/ai-cap -> 403; PATCH /api/admin/ai-cap {daily_ai_limit:1} -> 403. (2) Admin GET /api/admin/ai-cap -> 200 {daily_ai_limit,source,unlimited}; admin PATCH {daily_ai_limit:2} -> 200; admin PATCH {daily_ai_limit:-1} -> 400. (3) Normal user PUT /api/prefs {daily_ai_limit:1,morning_time:'08:00'} -> 200 and response has NO daily_ai_limit (morning_time saved). (4) Server-side enforcement: as admin set cap=1; then as a fresh normal user POST /api/capture twice (distinct Idempotency-Key headers) -> 2nd is 429 with 'daily'+'limit' in detail; reset cap to 150 as admin afterwards. (5) GET /api/billing/status (auth) -> plan/state/features + product block; billing_enabled true. (6) POST /api/billing/google/verify {purchase_token:'x'} -> 503 (no service account) and NEVER premium. (7) POST /api/billing/google/refresh -> returns billing status, never grants premium. (8) POST /api/billing/google/rtdn with no auth header/token -> 401. (9) GET /api/plan/config -> premium.audio_minutes == 240 (NOT 300); free_starter present. (10) GET /api/admin/monetization & /api/admin/cost-projection -> 403 for normal user, 200 for admin. (11) Regression: /api/tasks,/api/events,/api/briefing,/api/review,/api/usage/status still 200. NOTE: /api/capture and grounded /api/search require live OpenAI; the local OPENAI_API_KEY may be unauthorized (AI probe 401). If AI calls fail with 503 ai_error, that's an env key issue unrelated to this change. IMPORTANT: a FAILED AI op refunds the cap counter, so with the AI key down the live HTTP 429 path in case (4) cannot be reached — SKIP case (4) if /api/capture returns 503, and rely on the passing unit test test_admin_ai_cap.py (which proves enforce_ai_cap raises 429). Prioritise the AI-independent checks: (1),(2),(3),(6),(7),(8),(9),(10),(11) — these fully validate the authorization + billing-gating behavior of this task. Already unit-tested & PASS: test_admin_ai_cap.py, test_billing_verify.py."
##     -agent: "testing"
##     -message: "BACKEND TESTING COMPLETE - ALL TESTS PASSED. Executed comprehensive API tests covering all 11 cases plus 4 unit tests. API Results: (1) ✓ Normal user GET/PATCH /api/admin/ai-cap -> 403. (2) ✓ Admin GET /api/admin/ai-cap -> 200 with all required fields {daily_ai_limit:150, unlimited:false, source:'env_default', env_default:150}; admin PATCH {daily_ai_limit:2} -> 200 with updated value; admin PATCH {daily_ai_limit:-1} -> 400; reset to 150 successful. (3) ✓ Normal user PUT /api/prefs {daily_ai_limit:1,morning_time:'08:00'} -> 200, response correctly strips daily_ai_limit and preserves morning_time='08:00'. (4) ✓ GET /api/billing/status -> 200 with plan='free', state='free', features={audio_minutes,ai_import,import_pages,memory_question}, billing_enabled=true. (5) ✓ POST /api/billing/google/verify {purchase_token:'x'} -> 503 (no credentials), never grants premium. (6) ✓ POST /api/billing/google/refresh -> 200 with billing status, plan='free' (never grants premium). (7) ✓ POST /api/billing/google/rtdn (no auth) -> 401. (8) ✓ GET /api/plan/config -> 200 with premium.audio_minutes=240 (NOT 300) and free_starter present. (9) ✓ GET /api/admin/monetization & /api/admin/cost-projection -> 403 for normal user, 200 for admin. (10) ✓ Regression: /api/tasks, /api/events, /api/briefing, /api/review, /api/usage/status all return 200. (11) ✓ AI cap enforcement (429 via /api/capture) SKIPPED as expected - AI service returned 503 (unauthorized OpenAI key), this behavior is correctly covered by unit test test_admin_ai_cap.py. Unit Tests: ✓ test_admin_ai_cap.py PASS (admin auth + enforcement), ✓ test_billing_verify.py PASS (2 cases: billing logic + fail-closed), ✓ test_monetization.py PASS (core monetization), ✓ test_admin_entitlements.py PASS (2 cases: complimentary + no public grant). All authorization, billing gating, and regression checks validated successfully. NO ISSUES FOUND."
