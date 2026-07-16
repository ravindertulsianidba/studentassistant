# Phase 3B + 3C — Real-Device Test Checklist

Fill using `PHASE3_EVIDENCE_TEMPLATE.md` for each item. **Do not mark any device-only
workflow as passed without evidence** (screenshot/recording + diagnostic bundle reference).

Legend: [ ] pending · [P] pass · [F] fail · (S) server/automated already-passed.

## A. Authentication
- [ ] Google Sign-In completes and lands on Today
- [ ] Email registration → "check your email" screen
- [ ] Verification email received (needs live SMTP)
- [ ] Email/password sign-in after verification
- [ ] Password reset (email → link → new password)
- [ ] Logout
- [ ] Logout all devices (old session rejected afterwards)
- [ ] Account deletion (password confirmation required for password accounts)
- [ ] Dev/preview sign-in ABSENT from the release build

## B. Calendar
- [ ] Available device calendars appear (list shows accounts + providers)
- [ ] Google calendar connection
- [ ] Microsoft 365 / Outlook calendar connection
- [ ] Read-only mode: app does not write; external events still read
- [ ] Read-write mode: approved internal event written externally
- [ ] Existing external event appears in Today (External badge)
- [ ] Internal event writes externally
- [ ] Internal edit updates the external event
- [ ] External edit reconciles on next foreground/periodic sync (low-risk auto; high-risk confirm)
- [ ] External deletion detected → confirmation
- [ ] Recurring event requires approval before first external creation
- [ ] Duplicate prevention across repeated syncs/retries
- [ ] Permission revocation handled (status + Open Settings)
- [ ] Sync failure is visible (status + reason; no silent failure)

## C. Notifications
- [ ] Test notification works (Diagnostics)
- [ ] Reminder arrives with the app CLOSED
- [ ] Snooze works
- [ ] Reschedule works
- [ ] Mark Done works
- [ ] Daily Briefing arrives
- [ ] Evening Review arrives
- [ ] Weekly Review arrives
- [ ] Reminder restoration after device reboot
- [ ] Disabled notifications are detected (Diagnostics shows permission state)

## D. Active Listening
- [ ] Start / pause / resume / stop work
- [ ] Persistent notification appears while listening
- [ ] Screen lock does NOT terminate the session
- [ ] Audio is captured
- [ ] Transcript is created
- [ ] Commitments are extracted
- [ ] Tasks / AI Inbox items are created appropriately
- [ ] Session summary is accurate
- [ ] Undo removes created items
- [ ] Reliability Ledger updated (visible in support bundle)

## E. Lecture Recording
- [ ] Course selection works
- [ ] Recording survives screen lock
- [ ] Pause and resume work
- [ ] Local audio retained
- [ ] Upload succeeds
- [ ] Failed upload can retry
- [ ] Timestamped transcript generated
- [ ] Reorganized study notes generated
- [ ] Transcript and notes appear under the course
- [ ] Search finds captured lecture information
- [ ] Audio playback opens at the correct timestamp

## F. Diagnostics (Settings → Diagnostics)
- [ ] Test notification
- [ ] Test calendar read
- [ ] Create and delete test event
- [ ] Test microphone
- [ ] Test backend
- [ ] Test AI provider
- [ ] Retry failed jobs
- [ ] Copy Support Bundle (preview → cancel works → share works; sanitized)

## Automated coverage already passed (reference, not device)
(S) Auth 17/17 · Onboarding 8/8 · Calendar backend 24/24 · Active Listening + Diagnostics 20/20.
