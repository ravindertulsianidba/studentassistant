# Phase 3B — Interim APK Package (Physical Calendar Validation)

> ⚠️ **Calendar functionality is awaiting physical validation.** Backend contract +
> reconciliation are automated-test passed (24/24), but real device-calendar two-way sync
> with Google and Microsoft 365 / Outlook accounts has **not** been validated. This APK is
> for exactly that on-device verification.

## 1. APK location / how to produce it
No prebuilt binary is committed to the repo. Produce a side-loadable APK either way:
- **Emergent:** use the **Publish** button (top-right) to generate an Android build.
- **Independent (EAS):**
  ```bash
  cd frontend
  eas build --platform android --profile preview   # internal-distribution APK
  ```
  Download the `.apk` from the build URL EAS prints (or the Expo dashboard → Builds).
See `BUILD_AND_SIGNING.md` for full details and the production-APK/AAB profiles.

## 2. Installation instructions (Android)
1. Copy the `.apk` to the device (or open the EAS build link on the device).
2. Settings → allow "Install unknown apps" for your browser/file manager.
3. Tap the `.apk` to install. Launch **Student Assistant**.

## 3. Backend URL setup
- The app targets the backend from `EXPO_PUBLIC_BACKEND_URL` (baked in at build time).
- Confirm it points to your running backend (current preview:
  `https://semester-sync-7.preview.emergentagent.com`). All API calls use that base + `/api`.
- Health check from the device browser: open `<BACKEND_URL>/api/health` → expect JSON `ok`.

## 4. Calendar connection instructions
1. On the device, add the calendar account first: **Settings → Accounts → Add account**
   (Google and/or Microsoft/Exchange). Let it sync so it appears in the OS calendar.
2. In the app: **Settings → Connect Calendar**.
3. Grant the calendar permission when prompted (just-in-time).
4. Pick the calendar (Google / Microsoft 365 / Outlook / Exchange) and choose
   **Read & write** or **Read only**.
5. Use **Sync now** to force a sync; watch the status chip.

## 5. Physical-device test checklist
- [ ] Google calendar synced to Android is listed and connectable
- [ ] Microsoft 365 / Outlook calendar synced to Android is listed and connectable
- [ ] Read-only selection: app does NOT write; external events still appear in Today
- [ ] Read-write selection: an approved internal event is written to the external calendar
- [ ] An existing external event appears in **Today** (external badge) and Daily Briefing
- [ ] Editing the SA event in-app updates the external event on next sync
- [ ] Editing the linked event in the external calendar updates the internal one
      (low-risk auto; time/exam/recurring → confirmation in **Settings → Connect Calendar**)
- [ ] Deleting the linked event externally is detected and asks for confirmation
- [ ] Recurring event requires approval before first external creation
- [ ] No duplicate events after repeated syncs / retries
- [ ] Revoking calendar permission shows "Permission revoked" + Open Settings
- [ ] Airplane-mode during sync → "Sync failed" with reason; recovers on reconnect
- [ ] Diagnostics (**Settings → Diagnostics**): calendar connection, last sync, failures,
      "Test calendar read", "Create & delete test event" all behave correctly

## 6. Evidence required to accept
- Screen recording / screenshots of: calendar list showing a Google AND a Microsoft
  account; a Today screen with an external event; an approved event appearing in the OS
  calendar app; an external edit reflected in-app; a confirmation prompt; the Diagnostics
  screen after a successful sync.
- The exported diagnostic report (Diagnostics → Export diagnostic report).

## 7. Honest status
Until the checklist above passes on a real device with real Google + Microsoft accounts,
**provider-neutral calendar synchronization is NOT production-ready** and remains marked as
"implemented + automated-test passed, physical validation pending".
