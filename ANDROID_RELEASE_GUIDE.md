# Android Release Guide — Student Assistant

The **runtime** is fully independent of Emergent (self-hosted backend + your own
OpenAI/Google keys). You can produce the installable **APK/AAB** two ways —
choose either; both are independent of the Emergent editor.

## App identity (already set in `frontend/app.json`)
- Visible name: **Student Assistant**
- Android package: `com.ravindertulsiani.studentassistant`
- iOS bundle id: `com.ravindertulsiani.studentassistant`
- Scheme: `studentassistant` (OAuth redirect + share intents)
- Bump `version` + `android.versionCode` on each release.

## Permissions declared (`app.json`)
- `RECORD_AUDIO`, `FOREGROUND_SERVICE`, `FOREGROUND_SERVICE_MICROPHONE` — lecture / active-listening recording (background + screen-locked).
- iOS `UIBackgroundModes: ["audio"]` — background recording on iOS.
- `POST_NOTIFICATIONS` — reminders, briefings, reviews.
- `READ_CALENDAR`, `WRITE_CALENDAR` (+ iOS `NSCalendars*UsageDescription`) — device calendar.
- `CAMERA`, `READ_MEDIA_IMAGES` — Capture Anything.

Config plugins wired in `app.json`: `expo-audio` (mic), `expo-notifications`,
`expo-calendar`, `expo-web-browser`, `expo-router`, `expo-splash-screen`.

## Build config
`frontend/eas.json` defines three profiles:
- `development` — dev client APK (internal).
- `preview` — standalone **APK** for side-loading / QA.
- `production` — **AAB** (app-bundle) for Google Play, `autoIncrement` on.

### Option A — EAS Build (managed cloud, your own Expo account)
```bash
cd frontend
npm i -g eas-cli
eas login                       # your own (free) Expo account
eas init                        # writes extra.eas.projectId into app.json
# set build-time public env (or use EAS secrets):
#   EXPO_PUBLIC_BACKEND_URL=https://api.ravindertulsiani.com
#   EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID / EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID
eas build -p android --profile preview       # -> installable APK
eas build -p android --profile production     # -> AAB for Play Console
```
EAS manages the keystore, or run `eas credentials` to bring your own.

### Option B — Fully local build (no cloud, Gradle on your machine)
Requires Android SDK + JDK 17.
```bash
cd frontend
npx expo prebuild -p android           # generates the native android/ project
cd android
./gradlew assembleRelease              # -> app/build/outputs/apk/release/app-release.apk
./gradlew bundleRelease                # -> app/build/outputs/bundle/release/app-release.aab
```
Signing: create a keystore (`keytool -genkeypair ...`) and reference it in
`android/gradle.properties` + `android/app/build.gradle` (`signingConfigs`).
For Google Sign-In, register the keystore **SHA-1** on the Android OAuth client.

> The Emergent **Publish** button is also available as a convenience, but is NOT
> required — Options A and B produce the same app, which talks only to your
> backend and your API keys.

## Google Sign-In prerequisites
- Google Cloud Console → Credentials → OAuth client IDs (Web + Android).
- Android client needs the package name + signing **SHA-1**.
- Add the `studentassistant` scheme redirect for `expo-auth-session`.

## Device test matrix (see PHASE2_STATUS.md for the live tracking table)
Install · Upgrade · Google sign-in · **Foreground/locked-screen recording** ·
**Chunked upload of a 90-min lecture + interruption/retry** · **Scheduled
notification fires** · **Notification Done/Snooze actions** · **Reminders survive
a reboot** (open app → `/reminders/sync` reschedules) · **Device calendar write +
dedupe on re-sync** · Share/import PDF/DOCX · **Data export via share sheet** ·
Account deletion.
