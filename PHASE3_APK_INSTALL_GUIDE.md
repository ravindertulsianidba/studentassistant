# Phase 3 — APK Install & Physical-Validation Guide

> ⚠️ Calendar sync, notifications delivery, Active Listening audio, lecture recording, and
> background sync are **device-only** and are **not** accepted as passed until the checklist
> in `PHASE3_DEVICE_TEST_CHECKLIST.md` is completed with evidence
> (`PHASE3_EVIDENCE_TEMPLATE.md`).

## 1. Getting the APK
No binary is committed. Produce a side-loadable APK:
- **Emergent:** click **Publish** (top-right) → Android build → download `.apk`.
- **Independent (EAS):**
  ```bash
  cd frontend
  eas build --platform android --profile preview        # internal-distribution APK
  # signed standalone APK:  --profile production-apk
  # Play Store AAB:         --profile production
  ```
  Download from the EAS build URL / Expo dashboard → Builds. Full details + signing in
  `BUILD_AND_SIGNING.md`. Build profiles live in `frontend/eas.json`
  (`preview`=APK, `production`=AAB, `production-apk`=APK).

## 2. Install (Android)
1. Transfer the `.apk` to the device or open the build link on the device.
2. Allow "Install unknown apps" for your browser/file manager.
3. Tap the `.apk`, install, launch **Student Assistant**.

## 3. Required backend URL
- Baked in at build time via `EXPO_PUBLIC_BACKEND_URL`. Current preview:
  `https://semester-sync-7.preview.emergentagent.com`. All API calls use `<URL>/api`.
- Verify on device browser: `<BACKEND_URL>/api/health` → JSON `{"status":"ok",...}`.

## 4. Required environment variables (build-time, `frontend/.env`)
| Var | Purpose |
|---|---|
| `EXPO_PUBLIC_BACKEND_URL` | Backend base URL |
| `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID` | Google Sign-In (web/idToken) |
| `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID` | Google Sign-In (Android) |
| `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID` | Google Sign-In (iOS) |
| `EXPO_PUBLIC_EAS_PROJECT_ID` | (if using EAS Updates/push) |
Backend `.env` (server side): `MONGO_URL`, `JWT_SECRET`, `GOOGLE_CLIENT_ID`,
`ALLOW_INSECURE_DEV=false` in prod, and `SMTP_*` for live email (see Phase 3A audit).

## 5. Authentication instructions
- **Email/password:** Create Account → check email → verify → sign in. (Live email needs
  SMTP configured; otherwise verification is blocked in prod.)
- **Google:** "Continue with Google" (needs the Google client IDs above in the build).
- Note: the dev quick sign-in is **hidden in release builds** (only shown under `__DEV__`).

## 6. Calendar connection instructions
1. Device **Settings → Accounts → Add account** (Google and/or Microsoft/Exchange); let it sync.
2. App **Settings → Connect Calendar** → grant permission → pick calendar → Read&write / Read-only.
3. Use **Sync now**; watch the status chip. External events appear in **Today**.

## 7. Test-data setup
- In the external calendar app, create: one normal event today, one exam event, one
  recurring class — for external-read + high-risk-confirmation + recurring tests.
- In Student Assistant, capture a task due today and approve an event (for outbound write).
- For Active Listening/recording: pick any course and speak a couple of "assignment due…"
  and "exam on…" sentences.

## 8. Diagnostic report / support bundle export
- **Settings → Diagnostics**: run each safe action; then **Export diagnostic report** or
  **Copy Support Bundle** (preview → Share). The support bundle is **sanitized** (IDs,
  status, timestamps only — no audio/transcripts/tokens/credentials).

## 9. Known device-only limitations (must be validated on the build)
- Real Google + Microsoft/Outlook device-calendar two-way sync.
- OS permission dialogs + revoke transitions + `Open Settings` deep link.
- Notification delivery while app closed; reboot restoration; snooze/reschedule/mark-done.
- Active Listening audio + persistent notification + screen-lock survival + stop-from-notification.
- Lecture recording background/locked capture, resumable upload retry, audio↔transcript nav.
- **Periodic best-effort background sync** (expo-background-task): subject to Android OS
  scheduling & battery — NOT real-time/immediate/guaranteed. Foreground AppState sync is the
  immediate mechanism.
- Live SMTP email delivery (Phase 3A) — blocked until real credentials + inbox test.
