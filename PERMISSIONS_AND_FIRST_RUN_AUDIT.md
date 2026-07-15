# Permissions & First-Run Audit — Phase 3A

_Student Assistant · Onboarding intro + progressive, just-in-time permissions · June 2026_

## 1. Summary
A short first-run introduction is shown **after successful authentication** (never
before/instead of it). It ends with a "Recommended setup" step that requests only the
permissions the user opts into — **no "Approve All"**. Microphone and Camera are **not**
requested during onboarding; they are requested just-in-time at first use. Onboarding is
skippable and reopenable from Settings. Frontend tested: **8/8 behaviors pass**
(`test_reports/iteration_9.json`).

## 2. First-run flow (`frontend/app/onboarding.tsx`)
- Gated in `frontend/app/_layout.tsx`: an authenticated user with `sa_onboarded=false`
  is routed to `/onboarding`; completion sets the flag and routes to `/(tabs)`.
- **3 intro slides** (~60s): Capture anything · It remembers so you don't · Never miss
  what matters. Each slide has **Next** and a top **Skip**.
- **Recommended setup** step:
  - **Reminders & alerts** → "Enable" requests notification permission on tap.
  - **Calendar (optional)** → "Connect" requests calendar permission on tap.
  - **"Asked only when you need them"** info box: Microphone (first recording),
    Camera (first scan), Photos & files (system picker — no library access).
  - Actions: **Get started** and **Maybe later** (both finish onboarding).
- **No "Approve All"** control anywhere (verified: 0 occurrences).
- **Replay**: Settings → "Replay intro" (`replay-intro-btn`) resets `sa_onboarded` and
  relaunches the flow.

## 3. Permission model (progressive / just-in-time)
| Permission | Requested | Where | Handler |
|---|---|---|---|
| Notifications | During onboarding "Recommended setup" (opt-in) | `onboarding.tsx` | `services/notifications.ensurePermission()` |
| Calendar | During onboarding, optional (opt-in) | `onboarding.tsx` | `services/calendar.ensurePermission()` |
| Microphone | First recording / Active Listening only | record flow | (device-only) |
| Camera | First scan only | scan/import flow | (device-only) |
| Photos | Not requested — system photo picker | import flow | system picker |
| Documents | Not requested — system document picker (PDF/DOCX/TXT) | import flow | system picker |

### Permission-state handling
`ensurePermission()` (notifications & calendar) checks current status first, respects
`canAskAgain`, and returns `{granted, canAskAgain}`. The onboarding UI maps this to:
- `granted` → check badge shown.
- `denied` (can ask again) → gentle "you can enable later in Settings" hint (no dead-end).
- blocked (`canAskAgain=false`) → a **Settings** button that calls `Linking.openSettings()`.
- web/non-device → shown as "In app" (feature activates in the installed build).

No permission denial breaks the app — every capability degrades gracefully.

## 4. Tested (frontend, web preview)
- Fresh sign-in routes to `/onboarding`; slides advance; Skip works and is hidden on setup.
- Setup renders both permission cards + info box; **0** "Approve All".
- Get started / Maybe later land on Today; reload keeps user on tabs (persistence).
- Settings "Replay intro" re-launches onboarding; "Sign out of all devices" present.
- Tabs load without crashes.

## 5. Requires DEVICE (native build) validation
- Actual OS permission popups and grant/deny/blocked transitions for **Notifications**
  and **Calendar** (web preview cannot trigger native permission dialogs).
- Just-in-time **Microphone** (first recording) and **Camera** (first scan) prompts.
- `Linking.openSettings()` deep-link into app settings on Android/iOS.
These were NOT validated on web and must be checked on a real APK/IPA build.

## 6. Known-incomplete / deferred
- The permission cards on web show "In app" because native dialogs aren't available in
  the preview — expected, requires a device build.
- Onboarding flag `sa_onboarded` is device-global (not per-user); acceptable for MVP.
