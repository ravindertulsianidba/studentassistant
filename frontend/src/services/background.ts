/**
 * Phase 3C — TRUE background synchronization (device-only).
 *
 * Uses expo-background-task (OS-scheduled) to run calendar + reminder sync while the app
 * is NOT in the foreground. The OS decides exact timing (typically >= 15 min) and will
 * re-run the registered task after device restart. Foreground triggers (app open /
 * returning to active / after permission restore) are handled separately in _layout.
 *
 * NOTE: background execution CANNOT be validated in Expo Go or the web preview — it
 * requires an installed development/production build.
 */
import { Platform } from "react-native";
import * as BackgroundTask from "expo-background-task";
import * as TaskManager from "expo-task-manager";

import { fullSync } from "@/src/services/calendar";
import { syncAndSchedule } from "@/src/services/notifications";

const TASK = "student-assistant-bg-sync";
const isDevice = Platform.OS === "ios" || Platform.OS === "android";

if (isDevice && !TaskManager.isTaskDefined(TASK)) {
  TaskManager.defineTask(TASK, async () => {
    try {
      await fullSync();          // re-read external calendar, push approved events, report status
      await syncAndSchedule();   // rebuild reminder schedule (also restores after reboot)
      return BackgroundTask.BackgroundTaskResult.Success;
    } catch {
      return BackgroundTask.BackgroundTaskResult.Failed;
    }
  });
}

export async function registerBackgroundSync() {
  if (!isDevice) return;
  try {
    const status = await BackgroundTask.getStatusAsync();
    if (status === BackgroundTask.BackgroundTaskStatus.Restricted) return;
    await BackgroundTask.registerTaskAsync(TASK, { minimumInterval: 15 });
  } catch {
    // registration best-effort; foreground sync still covers most cases
  }
}
