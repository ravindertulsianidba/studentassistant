# Known Limitations

_Student Assistant · updated for Phase 3A (Auth) + Phase 3B (Calendar) · June 2026_

## Google Sign-In — classification
- **Implemented in code**: ✅ (`/api/auth/google` + Expo `expo-auth-session/providers/google`).
- **Emulator tested**: ❌ not verified.
- **Real-device tested**: ❌ not verified.
- **Awaiting real-device validation**: ✅ — Google OAuth requires an installed build with
  the configured client IDs; it cannot complete in the web preview / Expo Go reliably.

## Email verification & password reset — production blocker
- Fully implemented and tested against a **mock mailer** (24… see auth report). Live email
  **delivery** is **BLOCKED** until real SMTP credentials are supplied and a real-inbox test
  passes. In production, if SMTP is not configured the app **fails safely** (HTTP 503) and
  never silently uses the mock mailer. `dev-login` and `dev-outbox` return 404 in production.

## Calendar (Phase 3B) — device-only items NOT validated on web
The backend contract, reconciliation, dedup, isolation and Today logic are verified
(24/24). The following require an installed APK/IPA build with real accounts and were
**not** marked as passed:
- Reading/writing the OS calendar via `expo-calendar` (device-only).
- Real **Google** and **Microsoft 365 / Outlook / Exchange** calendars synced to Android.
- Actual OS permission dialogs, `Linking.openSettings()` deep-link, and permission-revoked
  transitions on a device.
- Real network-retry behavior on the device.

### Background synchronization — best-effort only
Background calendar/reminder sync (`expo-background-task`) is **periodic best-effort
synchronization, subject to the Android operating-system scheduling and battery
restrictions**. It is **NOT** real-time, **NOT** immediate, does **NOT** run at guaranteed
exact intervals, and does **NOT** guarantee external-change detection while the app remains
closed. The immediate reconciliation mechanism is the **foreground AppState sync**;
background sync only supplements it. Background execution is DEVICE-ONLY and unverified on
web/Expo Go.

### Provider visibility caveat
If a provider's calendar is **not** exposed through the Android device calendar provider
(some Exchange/EAS or restricted enterprise accounts), Student Assistant cannot see it.
Recommended least-friction persistent connection in that case: add the account through the
device's native **Settings → Accounts** so it syncs into the OS calendar provider (then it
appears in "Choose a calendar"). **Do not** rely on repeated ICS imports as the normal
workflow — ICS may be used only as a **one-time** fallback, never for ongoing sync.

## Native features requiring a build (from earlier phases)
- Background/locked-screen lecture recording (`expo-audio`), local notification delivery &
  actions, device calendar writes, share-sheet export, document/photo pickers — implemented
  in code; require an installed build to verify.

## Other
- Rate limiting is in-memory (per process). A multi-instance deployment should move it to a
  shared store (e.g. Redis).
- Compromised-password check uses a bundled common-password list (no live HIBP lookup).
- Onboarding first-run flag (`sa_onboarded`) is device-global, not per-user.
- Semantic search falls back to keyword mode unless `QDRANT_URL` is configured.
