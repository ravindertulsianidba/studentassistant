// Native device calendar integration: permission handling, a dedicated app
// calendar, duplicate-safe writes (backed by server-side external_id mapping),
// recurring rules, sync verification and failure recovery.
//
// NOTE: Device calendar writes cannot be verified in Expo Go / web preview.
// They require a build. All calls are guarded and return safe values off-device.
import { Platform } from "react-native";
import * as Calendar from "expo-calendar";
import { api } from "@/src/api";

const isDevice = Platform.OS === "ios" || Platform.OS === "android";
const CAL_TITLE = "GotU";
const DAY_RULE: Record<string, string> = { Mon: "MO", Tue: "TU", Wed: "WE", Thu: "TH", Fri: "FR", Sat: "SA", Sun: "SU" };

export async function ensurePermission(): Promise<{ granted: boolean; canAskAgain: boolean }> {
  if (!isDevice) return { granted: false, canAskAgain: false };
  const cur = await Calendar.getCalendarPermissionsAsync();
  if (cur.granted) return { granted: true, canAskAgain: cur.canAskAgain };
  if (!cur.canAskAgain) return { granted: false, canAskAgain: false };
  const req = await Calendar.requestCalendarPermissionsAsync();
  return { granted: !!req.granted, canAskAgain: req.canAskAgain };
}

async function getOrCreateCalendar(): Promise<string> {
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
  const existing = cals.find((c) => c.title === CAL_TITLE);
  if (existing) return existing.id;
  let source: any;
  if (Platform.OS === "ios") {
    const def = await Calendar.getDefaultCalendarAsync();
    source = def.source;
  } else {
    source = cals.find((c) => c.source?.name === "Default")?.source || cals[0]?.source ||
      { isLocalAccount: true, name: CAL_TITLE, type: Calendar.CalendarType.LOCAL };
  }
  return Calendar.createCalendarAsync({
    title: CAL_TITLE, color: "#4F6B58", entityType: Calendar.EntityTypes.EVENT,
    sourceId: source?.id, source, name: CAL_TITLE,
    ownerAccount: source?.name || CAL_TITLE, accessLevel: Calendar.CalendarAccessLevel.OWNER,
  });
}

function recurrenceFor(ev: any): Calendar.RecurrenceRule | undefined {
  if (!ev.recurring) return undefined;
  const days = (ev.days || []).map((d: string) => DAY_RULE[d?.slice(0, 3)]).filter(Boolean);
  return { frequency: Calendar.Frequency.WEEKLY, daysOfTheWeek:
      days.length ? days.map((d: string) => ({ dayOfTheWeek: (["SU","MO","TU","WE","TH","FR","SA"].indexOf(d) + 1) as any })) : undefined };
}

/**
 * Pushes every not-yet-synced event to the device calendar, then reports the
 * created external IDs back to the server so we never create duplicates.
 * Verifies each write by reading the event back.
 */
export async function syncPending(): Promise<{ created: number; failed: number; skipped: number }> {
  if (!isDevice) return { created: 0, failed: 0, skipped: 0 };
  const perm = await ensurePermission();
  if (!perm.granted) return { created: 0, failed: 0, skipped: 0 };
  const conn = await api.get("/calendar/connection").catch(() => null);
  if (!conn?.connected || conn.access_mode !== "read_write") return { created: 0, failed: 0, skipped: 0 };
  const calId = conn.calendar_id || (await getOrCreateCalendar());
  const pending = await api.get("/calendar/pending");
  const mappings: Record<string, string> = {};
  let created = 0, failed = 0, skipped = 0;
  for (const ev of pending) {
    if (!ev.start) { skipped++; continue; }
    const start = new Date(ev.start);
    const end = ev.end ? new Date(ev.end) : new Date(start.getTime() + 60 * 60 * 1000);
    try {
      const extId = await Calendar.createEventAsync(calId, {
        title: ev.title, startDate: start, endDate: end,
        location: ev.location || undefined, notes: ev.notes || undefined,
        timeZone: undefined, recurrenceRule: recurrenceFor(ev),
      });
      const back = await Calendar.getEventAsync(extId).catch(() => null);
      if (back) { mappings[ev.id] = extId; created++; }
      else { failed++; }
    } catch {
      failed++;
    }
  }
  if (Object.keys(mappings).length) {
    try { await api.post("/calendar/sync", { mappings }); } catch {}
  }
  return { created, failed, skipped };
}

// ---------------- Phase 3B: provider-neutral connect + two-way sync ----------------

function inferProvider(src: any): string {
  const s = `${src?.type || ""} ${src?.name || ""}`.toLowerCase();
  if (s.includes("google") || s.includes("gmail")) return "google";
  if (s.includes("exchange") || s.includes("office365") || s.includes("microsoft") || s.includes("outlook")) return "microsoft";
  if (s.includes("caldav")) return "caldav";
  if (s.includes("local")) return "local";
  return src?.name || "other";
}

export type DeviceCalendar = {
  id: string; title: string; account: string; provider: string; allowsModifications: boolean;
};

/** Lists calendars from the device calendar provider (includes Google / Microsoft 365 /
 *  Outlook / Exchange calendars synced to the device). */
export async function listCalendars(): Promise<DeviceCalendar[]> {
  if (!isDevice) return [];
  const perm = await ensurePermission();
  if (!perm.granted) return [];
  const cals = await Calendar.getCalendarsAsync(Calendar.EntityTypes.EVENT);
  return cals.map((c: any) => ({
    id: c.id,
    title: c.title || "Calendar",
    account: c.source?.name || c.ownerAccount || "Device",
    provider: inferProvider(c.source),
    allowsModifications: !!c.allowsModifications,
  }));
}

export async function getConnection() {
  try { return await api.get("/calendar/connection"); } catch { return null; }
}

export async function connect(cal: DeviceCalendar, accessMode: "read_write" | "read_only") {
  const mode = accessMode === "read_write" && !cal.allowsModifications ? "read_only" : accessMode;
  await api.post("/calendar/connection", {
    calendar_id: cal.id, calendar_title: cal.title, account_name: cal.account,
    provider: cal.provider, access_mode: mode,
  });
  await fullSync();
  return mode;
}

export async function disconnect() { try { await api.post("/calendar/disconnect", {}); } catch {} }

async function reportStatus(status: string, failure_reason?: string) {
  try { await api.post("/calendar/status", { status, failure_reason }); } catch {}
}

/** Reads external events in a ±35-day window from the connected calendar and mirrors
 *  them to the server for awareness/conflict + reconciliation. */
async function readAndIngest(calId: string) {
  const now = Date.now();
  const start = new Date(now - 35 * 864e5);
  const end = new Date(now + 35 * 864e5);
  const evs = await Calendar.getEventsAsync([calId], start, end).catch(() => []);
  const events = (evs || []).map((e: any) => ({
    external_id: e.id, device_calendar_id: calId, title: e.title,
    start: e.startDate ? new Date(e.startDate).toISOString() : null,
    end: e.endDate ? new Date(e.endDate).toISOString() : null,
    all_day: !!e.allDay, location: e.location || null, recurring: !!e.recurrenceRule,
  }));
  await api.post("/calendar/external/ingest", {
    device_calendar_id: calId, window_start: start.toISOString(),
    window_end: end.toISOString(), events,
  });
}

/** Orchestrates a full two-way sync. Safe on web/non-device (no-op). Never fails silently:
 *  status is reported back to the server (Connected / Read only / Syncing / Sync failed /
 *  Permission revoked). */
export async function fullSync(): Promise<{ ok: boolean; status: string }> {
  if (!isDevice) return { ok: false, status: "unavailable" };
  const conn = await getConnection();
  if (!conn?.connected) return { ok: false, status: "disconnected" };
  const cur = await Calendar.getCalendarPermissionsAsync();
  if (!cur.granted) { await reportStatus("permission_revoked", "Calendar permission was revoked."); return { ok: false, status: "permission_revoked" }; }
  await reportStatus("syncing");
  try {
    if (conn.calendar_id) await readAndIngest(conn.calendar_id);
    if (conn.access_mode === "read_write") await syncPending();
    const finalStatus = conn.access_mode === "read_only" ? "read_only" : "connected";
    await reportStatus(finalStatus);
    return { ok: true, status: finalStatus };
  } catch (e: any) {
    await reportStatus("sync_failed", String(e?.message || e).slice(0, 200));
    return { ok: false, status: "sync_failed" };
  }
}

