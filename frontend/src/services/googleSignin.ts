/**
 * Native Google Sign-In (react-native-nitro-google-signin, Android Credential Manager).
 *
 * IMPORTANT: this is a NATIVE module. It is loaded lazily via require() and only on
 * native platforms so the web / Expo Go bundle never executes it (it would otherwise
 * crash at load because the native binary is absent). Google Sign-In therefore only
 * works in an installed development / preview / production build — never in Expo Go
 * or the web preview.
 *
 * The app reads ONLY the Web client ID. The Android OAuth client is resolved by Google
 * via the app's package name + signing SHA-1 (registered on the Android OAuth client),
 * so no Android client ID is read by the app and no google-services.json is required.
 * No client secret is used in the mobile app.
 */
import { Platform } from "react-native";

export const GOOGLE_WEB_CLIENT_ID = process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID || "";
export const GOOGLE_ENABLED = !!GOOGLE_WEB_CLIENT_ID && Platform.OS !== "web";

export type GoogleResult = { idToken: string; email?: string; name?: string };

let configured = false;

function loadModule(): any | null {
  if (Platform.OS === "web") return null;
  try {
    // Lazy require: only executed on a native build where the module exists.
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    return require("react-native-nitro-google-signin");
  } catch {
    return null;
  }
}

/** True only when the native Nitro Google module is present (installed build). */
export function nativeModuleAvailable(): boolean {
  const m = loadModule();
  return !!(m && m.GoogleOneTapSignIn);
}

/** Runs the One-Tap → create-account → explicit fallback chain and returns an ID token. */
export async function signInWithGoogle(): Promise<GoogleResult> {
  const mod = loadModule();
  if (!mod || !mod.GoogleOneTapSignIn) {
    throw new Error("Google Sign-In requires the installed app (unavailable in Expo Go / web).");
  }
  if (!GOOGLE_WEB_CLIENT_ID) throw new Error("Google Web client ID is not configured.");
  const { GoogleOneTapSignIn, isNoSavedCredentialFoundResponse, isSuccessResponse } = mod;

  if (!configured) {
    GoogleOneTapSignIn.configure({ webClientId: GOOGLE_WEB_CLIENT_ID });
    configured = true;
  }

  await GoogleOneTapSignIn.checkPlayServices();
  let response = await GoogleOneTapSignIn.signIn();
  if (isNoSavedCredentialFoundResponse(response)) response = await GoogleOneTapSignIn.createAccount();
  if (isNoSavedCredentialFoundResponse(response)) response = await GoogleOneTapSignIn.presentExplicitSignIn();

  if (!isSuccessResponse(response)) throw new Error("Google sign-in was cancelled or failed.");
  const { user, idToken } = response.data;
  if (!idToken) throw new Error("No ID token returned by Google.");
  return { idToken, email: user?.email, name: user?.name };
}
