# Build & Signing — Independent APK / AAB

_Student Assistant · usable outside the Emergent Publish button_

App identifiers (from `frontend/app.json`):
- Android package: `com.decisivlabs.studentassistant`
- iOS bundle: `com.decisivlabs.studentassistant`
- App scheme: `studentassistant` (OAuth redirect + deep links)
- Production backend URL: `https://studentassistant-api.decisivlabs.com`
- Version: `1.0.0`

## Build profiles (`frontend/eas.json`)
| Profile | Output | Use |
|---|---|---|
| `development` | APK (dev client) | debugging with dev menu |
| `preview` | **APK** | internal QA / side-loading (physical calendar tests) |
| `production` | **AAB** | Play Store upload |
| `production-apk` | **APK** | signed standalone APK for direct install |

## Prerequisites (outside Emergent)
```bash
npm install -g eas-cli
cd frontend
eas login                     # your own Expo account
```

## Independent APK (side-loadable, for physical device testing)
```bash
cd frontend
eas build --platform android --profile preview
#   → produces a downloadable .apk (internal distribution)
# or a production-signed APK:
eas build --platform android --profile production-apk
```

## Independent AAB (Play Store)
```bash
cd frontend
eas build --platform android --profile production
#   → produces .aab for Play Console upload
```

## iOS
```bash
eas build --platform ios --profile preview       # ad-hoc / TestFlight internal
eas build --platform ios --profile production     # App Store
```

## Signing
- **Android**: on first `eas build`, EAS generates and stores an upload keystore
  (`Keystore: Generate new`). To manage/download it:
  ```bash
  eas credentials --platform android
  ```
  Keep the keystore + key alias/passwords backed up securely — losing them prevents Play
  Store updates. To use your own keystore, choose "Set up a new keystore → I want to
  upload my own" in `eas credentials`.
- **iOS**: `eas credentials --platform ios` manages the distribution certificate and
  provisioning profile (EAS can auto-generate with your Apple account).

## Local (no EAS servers) alternative
```bash
cd frontend
npx expo prebuild --platform android          # generates native android/ project
cd android && ./gradlew assembleRelease        # APK at app/build/outputs/apk/release/
#   ./gradlew bundleRelease                     # AAB at app/build/outputs/bundle/release/
```
Configure signing in `android/app/build.gradle` (`signingConfigs.release`) with your
keystore for local release builds.

## Runtime configuration for a build
- `EXPO_PUBLIC_BACKEND_URL` is pinned to the production API
  `https://studentassistant-api.decisivlabs.com` via the `env` block of the
  `preview` / `production` / `production-apk` profiles in `frontend/eas.json`, so
  release builds always target production regardless of the local `.env`.
- Set the Google client IDs (`EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`,
  `EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID`, optional `EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID`)
  and `EXPO_PUBLIC_EAS_PROJECT_ID` in the build environment / EAS secrets before building.
  The app calls the backend at `EXPO_PUBLIC_BACKEND_URL` + `/api`.
