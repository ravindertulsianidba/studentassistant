# Phase 3B Acceptance Test Report

_Provider-neutral calendar sync · backend suite `test_calendar_phase3b.py` — 24/24 PASS
(`test_reports/iteration_10.json`)_

## Legend
- ✅ PASS (automated backend / API contract, simulating the device)
- 📱 DEVICE-ONLY — requires an installed APK/IPA build; NOT validated on web and NOT
  marked as passed.

## Requested test matrix
| # | Requirement | Result |
|---|---|---|
| 1 | Google calendar synced to Android appears/reads | 📱 DEVICE-ONLY |
| 2 | Microsoft 365 / Outlook synced to Android appears/reads | 📱 DEVICE-ONLY |
| 3 | Read-only calendar selection | ✅ PASS (status read_only; pending gated to []) |
| 4 | Read-write calendar selection | ✅ PASS (status connected; pending populated) |
| 5 | Existing external event appears in Today | ✅ PASS (briefing today_classes external=true) · 📱 device read to populate mirror |
| 6 | Approved internal event appears externally | ✅ PASS (pending→sync→link) · 📱 actual OS write |
| 7 | Internal edit updates external event | ✅ PASS (pending/link model) · 📱 actual OS write |
| 8 | External edit updates linked internal event | ✅ PASS (auto low-risk; confirm high-risk) |
| 9 | External deletion detected | ✅ PASS (window ingest → external_delete review) |
| 10 | Recurring-event approval works | ✅ PASS (recurring change always requires confirmation; recurring only reaches pending once committed) |
| 11 | Duplicate prevention works | ✅ PASS (link keyed by internal_id; idempotent sync/ingest) |
| 12 | Permission revocation handled | ✅ PASS (/calendar/status permission_revoked → connected=false; UI shows state + Open Settings) |
| 13 | Network failure retried safely | ✅ PASS (idempotent upserts; status sync_failed with reason) · 📱 real retry on device |
| 14 | Two users cannot access each other's calendar data | ✅ PASS (isolation across connection/links/mirror/review) |

## Additional verified behavior
- Non-SA external events stored read-only (`is_sa=false`); never become tasks/timeline. ✅
- High-risk gating: time change, recurring, exam → confirmation, not auto-applied. ✅
- Confirmation apply/dismiss (`/calendar/review/{id}`). ✅
- Briefing conflict detection ('Schedule conflict' risk) + `stats.external_today` /
  `stats.calendar_review`. ✅
- Weekly review includes external workload. ✅
- Regression: tasks/events CRUD, briefing buckets, timeline, reminders → 200. ✅
- Safeguard: `DELETE /me` requires password for password accounts (403 without). ✅

## Honest status
Real device-calendar synchronization (items 1, 2, and the OS read/write halves of 5–7, 13)
is **implemented in code but NOT verified** — it can only be confirmed on an installed
build with actual Google/Microsoft accounts synced to the device. It is therefore **not**
marked as passed. All backend contract, reconciliation, dedup, isolation and Today-logic
behavior is verified (24/24).
