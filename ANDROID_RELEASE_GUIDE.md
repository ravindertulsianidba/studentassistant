# Android Release Guide — Student Assistant

The **runtime** is fully independent of Emergent (self-hosted backend + your own OpenAI/Google keys). Producing the installable **APK/AAB** uses Emergent's build/publish flow.

## App identity (already set in `frontend/app.json`)
- Visible name: **Student Assistant**
- Android package: `com.ravindertulsiani.studentassistant`
- iOS bundle id: `com.ravindertulsiani.studentassistant`
- Scheme: `studentassistant` (used for OAuth redirect + share intents)
- `versionCode` / `version` bump on each release.

## Permissions declared
- `RECORD_AUDIO`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE` — lecture/active-listening recording.
- `POST_NOTIFICATIONS` — reminders & briefings.
- `READ_CALENDAR`, `WRITE_CALENDAR` — device calendar (Phase 2).
- `CAMERA`, `READ_MEDIA_IMAGES` — Capture Anything.

## Build the APK / AAB
1. In the Emergent editor, click **Publish** (top-right) to produce an Android build.
2. Provide the required signing credentials when prompted; Emergent manages the keystore and returns a **test APK** and a **store-ready AAB**.
3. Set build-time env before building:
   - `EXPO_PUBLIC_BACKEND_URL=https://api.ravindertulsiani.com`
   - `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`
4. Install the APK on a device/emulator for testing; upload the AAB to Google Play Console for release.

> The build tooling is provided by Emergent, but the shipped app talks **only** to your backend and your API keys. No Emergent subscription is needed for the app to run after install.

## Google Sign-In prerequisites
- Create OAuth client IDs in Google Cloud Console (Web + Android). The Android client needs your app's **package name** and **SHA-1** (from the signing keystore used by the build).
- Add the app scheme redirect for `expo-auth-session`.

## Test matrix (perform on device + emulator)
Install · Upgrade · Google sign-in · Background recording · Screen lock · Device restart · Notifications · Calendar write · File/share imports · Account deletion. See KNOWN_LIMITATIONS.md for what still needs a device build to verify.
