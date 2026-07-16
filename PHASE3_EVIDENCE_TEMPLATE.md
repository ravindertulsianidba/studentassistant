# Phase 3 — Device Test Evidence Template

Copy this block once per test case in the checklist. Attach screenshots / screen
recordings and the exported support bundle. Do not mark device-only workflows passed
without completed evidence.

---
- **Test ID / name:** (e.g. B-06 External event appears in Today)
- **APK version:** (app_version from support bundle, e.g. 1.0.0 · build #)
- **Device model:** (e.g. Pixel 7)
- **Android version:** (e.g. Android 15)
- **Test date/time:** (ISO, with timezone)
- **Preconditions / test data:** (accounts connected, events created)
- **Steps:**
  1.
  2.
  3.
- **Expected result:**
- **Actual result:**
- **Pass / Fail:**
- **Screenshot / recording ref:** (file name or link)
- **Diagnostic bundle ref:** (support-bundle file name / timestamp)
- **Remaining limitation / notes:**
---

## Example (filled)
- **Test ID / name:** C-02 Reminder arrives with app closed
- **APK version:** 1.0.0 (build 3)
- **Device model:** Samsung Galaxy A54
- **Android version:** Android 14
- **Test date/time:** 2026-06-20T09:15:00-05:00
- **Preconditions:** Notifications granted; a reminder scheduled for 09:16; app force-closed.
- **Steps:** 1) Schedule reminder 2) Force-close app 3) Wait for 09:16
- **Expected result:** Notification appears with title/body while app closed.
- **Actual result:** _(fill)_
- **Pass / Fail:** _(fill)_
- **Screenshot / recording ref:** rec_c02.mp4
- **Diagnostic bundle ref:** bundle_2026-06-20T0917.json
- **Remaining limitation / notes:** _(fill)_
