// Native local notifications: permissions, reminder scheduling, routines,
// reboot restoration, snooze/done actions and health checks.
//
// NOTE: Local scheduled notifications do NOT fire in Expo Go / web preview.
// They require a development or production build. All calls are guarded so the
// app never crashes in the preview — they simply no-op off-device.
import { Platform } from "react-native";
import * as Notifications from "expo-notifications";
import { api } from "@/src/api";

const isDevice = Platform.OS === "ios" || Platform.OS === "android";
const WEEKDAY: Record<string, number> = { Sun: 1, Mon: 2, Tue: 3, Wed: 4, Thu: 5, Fri: 6, Sat: 7 };

let _wired = false;

export function wireHandlers() {
  if (_wired || !isDevice) return;
  _wired = true;
  Notifications.setNotificationHandler({
    handleNotification: async () => ({
      shouldShowBanner: true, shouldShowList: true,
      shouldPlaySound: true, shouldSetBadge: false,
    }),
  });
  // Respond to action buttons (Done / Snooze 10m) fired from a reminder.
  Notifications.addNotificationResponseReceivedListener(async (resp) => {
    try {
      const data: any = resp.notification.request.content.data || {};
      const rid = data.reminderId;
      if (!rid) return;
      const action = resp.actionIdentifier;
      if (action === "DONE") {
        await api.post(`/reminders/${rid}/status`, { status: "done", detail: "notif action" });
      } else if (action === "SNOOZE") {
        const when = new Date(Date.now() + 10 * 60 * 1000).toISOString();
        await api.post(`/reminders/${rid}/status`, { status: "snoozed", snooze_until: when });
        await scheduleOne({ id: rid, title: data.title || "Reminder", body: data.body, remind_at: when });
      }
    } catch {}
  });
}

export async function ensurePermission(): Promise<{ granted: boolean; canAskAgain: boolean }> {
  if (!isDevice) return { granted: false, canAskAgain: false };
  const cur = await Notifications.getPermissionsAsync();
  if (cur.granted) return { granted: true, canAskAgain: cur.canAskAgain };
  if (!cur.canAskAgain) return { granted: false, canAskAgain: false };
  const req = await Notifications.requestPermissionsAsync();
  return { granted: !!req.granted, canAskAgain: req.canAskAgain };
}

async function setupAndroid() {
  if (Platform.OS !== "android") return;
  await Notifications.setNotificationChannelAsync("reminders", {
    name: "Reminders", importance: Notifications.AndroidImportance.HIGH,
    vibrationPattern: [0, 250, 250, 250], lightColor: "#4F6B58",
  });
  await Notifications.setNotificationCategoryAsync("reminder", [
    { identifier: "DONE", buttonTitle: "Mark done" },
    { identifier: "SNOOZE", buttonTitle: "Snooze 10m" },
  ]);
}

async function scheduleOne(r: { id: string; title: string; body?: string; remind_at: string }) {
  const when = new Date(r.remind_at);
  if (isNaN(when.getTime()) || when.getTime() <= Date.now()) return null;
  return Notifications.scheduleNotificationAsync({
    content: {
      title: r.title, body: r.body || "Reminder", categoryIdentifier: "reminder",
      data: { reminderId: r.id, title: r.title, body: r.body },
    },
    trigger: { type: Notifications.SchedulableTriggerInputTypes.DATE, date: when },
  });
}

/**
 * Cancel ONLY the notifications this app manages (reminders + repeating routines),
 * identified by their content.data. This is used instead of
 * cancelAllScheduledNotificationsAsync so we never wipe unrelated/user notifications.
 * Returns the number cancelled.
 */
async function cancelManaged(opts: { reminders?: boolean; routines?: boolean } = { reminders: true, routines: true }) {
  if (!isDevice) return 0;
  const all = await Notifications.getAllScheduledNotificationsAsync();
  let n = 0;
  for (const req of all) {
    const data: any = req.content?.data || {};
    const isReminder = !!data.reminderId;
    const isRoutine = !!data.routine;
    if ((isReminder && opts.reminders) || (isRoutine && opts.routines)) {
      try { await Notifications.cancelScheduledNotificationAsync(req.identifier); n++; } catch {}
    }
  }
  return n;
}

// Single scheduling authority + concurrency guard: overlapping launch/login/
// foreground/refresh calls await the SAME run instead of racing (which produced
// duplicate routine notifications).
let _syncInFlight: Promise<{ scheduled: number; routines: number }> | null = null;

/**
 * Rebuilds the local schedule from the server. Idempotent: it cancels only the
 * notifications it manages (by semantic identity in content.data) and reschedules
 * exactly one per reminder/routine. Safe to call repeatedly.
 */
export async function syncAndSchedule(): Promise<{ scheduled: number; routines: number }> {
  if (!isDevice) return { scheduled: 0, routines: 0 };
  if (_syncInFlight) return _syncInFlight;
  _syncInFlight = (async () => {
    const perm = await ensurePermission();
    if (!perm.granted) return { scheduled: 0, routines: 0 };
    await setupAndroid();

    const sync = await api.get("/reminders/sync");

    // Replace managed reminders (dedupe by reminderId).
    await cancelManaged({ reminders: true, routines: false });
    let scheduled = 0;
    for (const r of sync.reminders || []) {
      const notifId = await scheduleOne(r);
      if (notifId) {
        scheduled++;
        try { await api.post(`/reminders/${r.id}/status`, { status: "scheduled", external_id: notifId }); } catch {}
      }
    }

    // Replace managed routines (dedupe by routine key). The server omits
    // evening_review when there is nothing to review, so empty accounts get none.
    await cancelManaged({ reminders: false, routines: true });
    const seen = new Set<string>();
    let routines = 0;
    for (const rt of sync.routines || []) {
      if (seen.has(rt.key)) continue;      // never schedule the same routine twice
      seen.add(rt.key);
      const [h, m] = String(rt.time || "09:00").split(":").map((n: string) => parseInt(n, 10));
      if (rt.repeat === "daily") {
        await Notifications.scheduleNotificationAsync({
          content: { title: rt.title, body: rt.body, data: { routine: rt.key } },
          trigger: { type: Notifications.SchedulableTriggerInputTypes.DAILY, hour: h || 9, minute: m || 0 },
        });
        routines++;
      } else if (rt.repeat === "weekly") {
        await Notifications.scheduleNotificationAsync({
          content: { title: rt.title, body: rt.body, data: { routine: rt.key } },
          trigger: {
            type: Notifications.SchedulableTriggerInputTypes.WEEKLY,
            weekday: WEEKDAY[rt.weekday] || 1, hour: h || 18, minute: m || 0,
          },
        });
        routines++;
      }
    }
    return { scheduled, routines };
  })();
  try {
    return await _syncInFlight;
  } finally {
    _syncInFlight = null;
  }
}

/**
 * On logout, cancel this app's routine + reminder notifications so the previous
 * account never receives notifications intended for it on this device.
 */
export async function cancelAllRoutinesAndReminders(): Promise<number> {
  return cancelManaged({ reminders: true, routines: true });
}

export async function health() {
  if (!isDevice) return { permission: "unavailable", scheduledOnDevice: 0 };
  const perm = await Notifications.getPermissionsAsync();
  const all = await Notifications.getAllScheduledNotificationsAsync();
  return { permission: perm.granted ? "granted" : "denied", scheduledOnDevice: all.length };
}


export async function sendTestNotification(): Promise<{ ok: boolean; reason?: string }> {
  if (!isDevice) return { ok: false, reason: "Notifications run in the installed app, not the web preview." };
  const perm = await ensurePermission();
  if (!perm.granted) return { ok: false, reason: "Notification permission not granted." };
  await Notifications.scheduleNotificationAsync({
    content: { title: "GotU", body: "Test notification — reminders are working." },
    trigger: { seconds: 2 } as any,
  });
  return { ok: true };
}
