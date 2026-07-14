# Privacy & Data Handling — Student Assistant

## Principles
Capture once; the AI organizes it. The student stays in control. Nothing is shared automatically; the app never sends, replies to, deletes, or modifies email.

## Data collected (per authenticated user)
Google account id/email/name; captures, tasks, events, courses; imported source documents & extracted text; lecture audio (optional retention) + transcripts + AI study notes; AI Inbox items; memory/timeline; audit history; preferences.

## Storage & security
- All records carry `user_id`; every read/write/search/delete/export is scoped to the authenticated user (enforced server-side).
- Auth: Google ID-token verified server-side; our own short-lived JWT access + rotating refresh tokens. Refresh tokens stored only as SHA-256 hashes; revoked on logout and account deletion.
- On device: tokens in Android secure storage (Keystore via expo-secure-store).
- In transit: HTTPS/TLS (Nginx). CORS restricted to configured origins. Rate limiting on auth/AI endpoints. File type & size validation. API errors sanitized (no stack traces / secrets in responses or logs).
- Secrets only in environment variables, never in source or the app bundle.

## Recording consent
The app shows a visible recording indicator and a persistent notification during capture, with one-tap stop. Users are reminded they are responsible for obtaining consent to record where required by their institution/jurisdiction.

## User controls
- Delete any single item: recording, transcript, study notes, source document, task, event, course.
- **Delete account** (`DELETE /api/me`): removes all user data and revokes all sessions.
- **Export** (`GET /api/export`): full JSON of the user's data.
- Configurable retention: choose to keep raw audio or delete it after transcription (transcript + actions retained).
- Cascade deletion of a source asks before removing derived items.

## Google Play Data Safety (summary to declare)
- Data collected: email, name, user content (audio/text/documents), app activity.
- Purpose: app functionality only. Not shared with third parties except the AI processor (OpenAI) strictly to provide the feature.
- Encrypted in transit. Users can request deletion in-app (account deletion).

## Third-party processors
- OpenAI (text extraction, OCR, transcription, study notes, search). Governed by OpenAI's API data policies.
- Google (sign-in/identity only).

## Drafts to finalize before Play release
`PRIVACY_POLICY` and `TERMS_OF_USE` public pages (host on ravindertulsiani.com), plus the in-app recording-consent disclosure (implemented on the login and capture screens).
