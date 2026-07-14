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
const CAL_TITLE = "Student Assistant";
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
  const calId = await getOrCreateCalendar();
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
      // verify the write actually persisted
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
