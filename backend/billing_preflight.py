"""Billing release preflight (backend side).

Purpose: when billing is enabled, fail closed unless the production billing configuration is
present, while clearly distinguishing four categories so a human can act:
  - code_ready:            product/base-plan IDs and code configuration present
  - missing_credentials:   external secrets not yet provided (service account, RTDN auth)
  - missing_play_console:  external Google Play Console configuration to complete off-platform
  - native_rebuild:        whether a new Android binary is required

Run:  python -m billing_preflight
Testable with mocked env (no real Google credentials required). NEVER prints secret values.
Exit code is non-zero when there is a BLOCKING issue for an enabled-billing release.
"""
import sys
import config


def check() -> dict:
    code_ready, blocking, missing_credentials, missing_play_console, notes = [], [], [], [], []

    billing_on = config.BILLING_ENABLED

    # ---- code readiness (public, non-secret, must be present) ----
    if config.GOOGLE_PLAY_PACKAGE_NAME:
        code_ready.append(f"package_name={config.GOOGLE_PLAY_PACKAGE_NAME}")
    else:
        blocking.append("GOOGLE_PLAY_PACKAGE_NAME missing")

    for key, label in (
        (config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID, "subscription product id"),
        (config.GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID, "monthly base plan id"),
        (config.GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID, "annual base plan id"),
    ):
        if key:
            code_ready.append(f"{label}={key}")
        else:
            blocking.append(f"{label} missing")

    # ---- external credentials (secrets — presence only, never value) ----
    if config.GOOGLE_PLAY_SERVICE_ACCOUNT_JSON:
        code_ready.append("Google Play service-account credential reference present")
    else:
        missing_credentials.append(
            "GOOGLE_PLAY_SERVICE_ACCOUNT_JSON (Android Publisher service-account key path)")

    if config.PUBSUB_SERVICE_ACCOUNT_EMAIL or config.PUBSUB_VERIFICATION_TOKEN:
        code_ready.append("RTDN push authentication configured")
    else:
        missing_credentials.append(
            "PUBSUB_SERVICE_ACCOUNT_EMAIL or PUBSUB_VERIFICATION_TOKEN (authenticate RTDN push)")

    # ---- Play Console configuration reminders (cannot be verified from code) ----
    missing_play_console += [
        f"Create subscription '{config.GOOGLE_PLAY_SUBSCRIPTION_PRODUCT_ID}' with base plans "
        f"'{config.GOOGLE_PLAY_MONTHLY_BASE_PLAN_ID}' + '{config.GOOGLE_PLAY_ANNUAL_BASE_PLAN_ID}' and activate both",
        "Set Canadian prices (monthly CAD 11.99, annual CAD 109.99) and regional availability",
        "Configure grace period + account hold, link the service account, and wire RTDN Pub/Sub",
    ]

    # ---- native rebuild requirement ----
    # expo-iap ships native Google Play Billing code that must be compiled into the Android binary.
    notes.append(
        "Native rebuild: a new Android build is required ONLY if the installed binary was built "
        "without the expo-iap native module or with EXPO_PUBLIC_BILLING_ENABLED=false baked in. "
        "No JS/config change here alters native code.")

    # ---- fail-closed rules ----
    if billing_on and missing_credentials:
        # Enabled billing MUST have verification credentials; otherwise verification fails closed
        # (503) and Premium can never be granted — a release must not ship in that state.
        for m in missing_credentials:
            blocking.append(f"Billing enabled but credential missing: {m}")

    return {
        "billing_enabled": billing_on,
        "code_ready": code_ready,
        "missing_credentials": missing_credentials,
        "missing_play_console": missing_play_console,
        "native_rebuild": notes,
        "blocking": blocking,
        "pass": len(blocking) == 0,
    }


def main():
    r = check()
    out = sys.stdout.write
    out("\n=== Billing Preflight (backend) ===\n")
    out(f"billing_enabled = {r['billing_enabled']}\n")
    out("\n[code readiness]\n")
    for x in r["code_ready"]:
        out(f"  \u2713 {x}\n")
    out("\n[missing external credentials]\n")
    for x in r["missing_credentials"] or ["(none)"]:
        out(f"  \u2691 {x}\n")
    out("\n[missing Play Console configuration]\n")
    for x in r["missing_play_console"]:
        out(f"  \u2691 {x}\n")
    out("\n[native rebuild]\n")
    for x in r["native_rebuild"]:
        out(f"  \u2139 {x}\n")
    if r["blocking"]:
        out("\n[BLOCKING]\n")
        for x in r["blocking"]:
            out(f"  \u2717 {x}\n")
        out(f"\nRESULT: FAIL ({len(r['blocking'])} blocking). Do NOT ship an enabled-billing release.\n")
        sys.exit(1)
    out("\nRESULT: PASS — code is billing-ready. Complete the external items above before store review.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
