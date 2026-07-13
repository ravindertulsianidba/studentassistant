import { Redirect } from "expo-router";
// Placeholder route for the center FAB tab — the FAB opens the /capture modal
// directly, so this screen is never shown. Redirect keeps routing valid.
export default function CaptureTab() {
  return <Redirect href="/(tabs)" />;
}
