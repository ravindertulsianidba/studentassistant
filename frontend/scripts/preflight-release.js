#!/usr/bin/env node
/* Release preflight — fails (exit 1) if any insecure/development option is enabled or a
 * required release setting is missing. Run: `npm run preflight:release`
 * Usage in CI/local before building a preview/pilot/production artifact. */
const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const fail = [];
const warn = [];
const ok = [];

function readEnv(file) {
  const p = path.join(ROOT, file);
  if (!fs.existsSync(p)) return null;
  const out = {};
  for (const line of fs.readFileSync(p, "utf8").split("\n")) {
    const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
    if (m) out[m[1]] = m[2].replace(/^["']|["']$/g, "").trim();
  }
  return out;
}

// Prefer real process env (CI), fall back to .env file.
const fileEnv = readEnv(".env") || {};
const E = (k) => (process.env[k] !== undefined ? process.env[k] : fileEnv[k]);

// 1) Insecure dev flags must be false/unset.
if (String(E("EXPO_PUBLIC_ENABLE_DEV_LOGIN") || "false").toLowerCase() === "true")
  fail.push("EXPO_PUBLIC_ENABLE_DEV_LOGIN must be false for release.");
else ok.push("EXPO_PUBLIC_ENABLE_DEV_LOGIN is false");

// ALLOW_INSECURE_DEV lives in the backend env; check if present locally.
const backendEnv = readEnv("../backend/.env") || {};
const allowInsecure = process.env.ALLOW_INSECURE_DEV ?? backendEnv.ALLOW_INSECURE_DEV;
if (allowInsecure !== undefined) {
  if (String(allowInsecure).toLowerCase() === "true")
    fail.push("Backend ALLOW_INSECURE_DEV must be false in production (enables dev-login/dev-outbox).");
  else ok.push("Backend ALLOW_INSECURE_DEV is false");
} else {
  warn.push("Backend ALLOW_INSECURE_DEV not visible here — ensure it is false on the production backend.");
}

// 2) Production backend URL configured and https.
const url = E("EXPO_PUBLIC_BACKEND_URL") || "";
if (!url) fail.push("EXPO_PUBLIC_BACKEND_URL is not set.");
else if (!/^https:\/\//.test(url)) fail.push(`EXPO_PUBLIC_BACKEND_URL must be https (got ${url}).`);
else ok.push("EXPO_PUBLIC_BACKEND_URL is set (https)");

// 3) Google OAuth: native react-native-nitro-google-signin reads only the Web client ID.
const gWeb = E("EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID");
if (gWeb) ok.push("Google Web client ID present (native Google Sign-In enabled)");
else warn.push("EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID not set locally — released builds inject it via eas.json profile env.");
if (E("EXPO_PUBLIC_GOOGLE_ANDROID_CLIENT_ID") || E("EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID"))
  warn.push("Legacy EXPO_PUBLIC_GOOGLE_ANDROID/IOS_CLIENT_ID set but unused — the app reads only the Web client ID.");

// 4) No hardcoded secrets bundled in frontend source.
const SECRET_RE = [
  /sk-[A-Za-z0-9]{20,}/,            // OpenAI-style
  /AIza[0-9A-Za-z\-_]{20,}/,        // Google API key
  /-----BEGIN [A-Z ]*PRIVATE KEY-----/,
  /SMTP_PASSWORD\s*[:=]\s*['"][^'"]+['"]/i,
];
function scan(dir) {
  for (const ent of fs.readdirSync(dir, { withFileTypes: true })) {
    if (ent.name === "node_modules" || ent.name.startsWith(".")) continue;
    const fp = path.join(dir, ent.name);
    if (ent.isDirectory()) scan(fp);
    else if (/\.(ts|tsx|js|jsx)$/.test(ent.name)) {
      const txt = fs.readFileSync(fp, "utf8");
      for (const re of SECRET_RE) if (re.test(txt)) fail.push(`Possible hardcoded secret in ${path.relative(ROOT, fp)}`);
    }
  }
}
["app", "src"].forEach((d) => fs.existsSync(path.join(ROOT, d)) && scan(path.join(ROOT, d)));
if (!fail.some((f) => f.startsWith("Possible hardcoded secret"))) ok.push("No hardcoded secrets detected in app/ or src/");

// 5) dev-login route self-guards on the flag (code check).
const devRoute = path.join(ROOT, "app", "dev-login.tsx");
if (fs.existsSync(devRoute)) {
  const t = fs.readFileSync(devRoute, "utf8");
  if (t.includes("EXPO_PUBLIC_ENABLE_DEV_LOGIN") && t.includes("__DEV__") && t.includes("Redirect"))
    ok.push("dev-login route is flag-guarded (__DEV__ + EXPO_PUBLIC_ENABLE_DEV_LOGIN)");
  else fail.push("dev-login route is not properly guarded.");
}
// Normal login screen must not contain dev UI test IDs.
const loginTsx = fs.readFileSync(path.join(ROOT, "app", "login.tsx"), "utf8");
if (/testID="dev-(signin|email)"|dev-only|Quick sign-in|activates in the installed/.test(loginTsx))
  fail.push("Normal login screen still contains development UI/wording.");
else ok.push("Normal login screen contains no development UI/wording");

// 6) app.json: locked production identity + android permissions + version fields.
const appJson = JSON.parse(fs.readFileSync(path.join(ROOT, "app.json"), "utf8"));
const expo = appJson.expo || {};
const android = expo.android || {};

// Locked production identity — must never drift.
const LOCKED_PACKAGE = "com.decisivlabs.studentassistant";
const LOCKED_SCHEME = "studentassistant";
if (android.package !== LOCKED_PACKAGE)
  fail.push(`app.json expo.android.package must be "${LOCKED_PACKAGE}" (got "${android.package}").`);
else ok.push(`Android package = ${LOCKED_PACKAGE}`);
if ((expo.ios || {}).bundleIdentifier !== LOCKED_PACKAGE)
  fail.push(`app.json expo.ios.bundleIdentifier must be "${LOCKED_PACKAGE}" (got "${(expo.ios || {}).bundleIdentifier}").`);
else ok.push(`iOS bundleIdentifier = ${LOCKED_PACKAGE}`);
if (expo.scheme !== LOCKED_SCHEME)
  fail.push(`app.json expo.scheme must be "${LOCKED_SCHEME}" (got "${expo.scheme}").`);
else ok.push(`App scheme = ${LOCKED_SCHEME}`);

if (!expo.version) fail.push("app.json expo.version (versionName) is missing.");
else ok.push(`versionName = ${expo.version}`);
if (android.versionCode === undefined) warn.push("app.json expo.android.versionCode not set (EAS can auto-increment).");
else ok.push(`versionCode = ${android.versionCode}`);
const perms = android.permissions || [];
["RECORD_AUDIO", "READ_CALENDAR", "WRITE_CALENDAR", "POST_NOTIFICATIONS"].forEach((p) => {
  if (!perms.includes(`android.permission.${p}`) && !perms.includes(p)) warn.push(`Android permission ${p} not declared in app.json.`);
});
ok.push(`Android permissions declared: ${perms.length}`);

// 7) eas.json build profiles present + release identity pinned in profile env.
const eas = JSON.parse(fs.readFileSync(path.join(ROOT, "eas.json"), "utf8"));
["preview", "production", "production-apk"].forEach((p) => {
  const prof = eas.build?.[p];
  if (!prof) { warn.push(`eas.json build profile "${p}" missing.`); return; }
  const penv = prof.env || {};
  if (!/^https:\/\/.+/.test(penv.EXPO_PUBLIC_BACKEND_URL || ""))
    fail.push(`eas.json profile "${p}" must pin a production https EXPO_PUBLIC_BACKEND_URL.`);
  if (!penv.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID)
    warn.push(`eas.json profile "${p}" does not pin EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID (Google button hidden in that build).`);
});
ok.push("eas.json build profiles + pinned release env checked");

// 7b) Native Google Sign-In config plugin present.
const plugins = (expo.plugins || []).map((pl) => (Array.isArray(pl) ? pl[0] : pl));
if (plugins.includes("react-native-nitro-google-signin"))
  ok.push("react-native-nitro-google-signin config plugin present");
else warn.push("react-native-nitro-google-signin config plugin not found in app.json plugins.");

// 7c) Billing config plugin + monetization gating.
if (plugins.includes("expo-iap")) ok.push("expo-iap billing config plugin present");
else warn.push("expo-iap config plugin not found in app.json plugins.");
const billingEnabled = /^true$/i.test(E("EXPO_PUBLIC_BILLING_ENABLED") || "");
const monetizationExpected = /^true$/i.test(E("EXPO_PUBLIC_MONETIZATION_EXPECTED") || "");
if (monetizationExpected && !billingEnabled)
  fail.push("Monetization is expected (EXPO_PUBLIC_MONETIZATION_EXPECTED=true) but EXPO_PUBLIC_BILLING_ENABLED is not true.");
else if (billingEnabled) ok.push("Billing enabled for this build");
else ok.push("Billing disabled (Free + Starter Pack only) — acceptable pre-Play-Console");

// 8) .env.example exists.
if (!fs.existsSync(path.join(ROOT, ".env.example"))) fail.push(".env.example is missing.");
else ok.push(".env.example present");

// ---- report ----
const line = (s) => process.stdout.write(s + "\n");
line("\n=== Release Preflight ===");
ok.forEach((o) => line("  ✓ " + o));
warn.forEach((w) => line("  ⚠ " + w));
if (fail.length) {
  fail.forEach((f) => line("  ✗ " + f));
  line(`\nRESULT: FAIL (${fail.length} blocking issue${fail.length > 1 ? "s" : ""}). Do NOT build a release.\n`);
  process.exit(1);
}
line("\nRESULT: PASS — safe to build a release.\n");
process.exit(0);
