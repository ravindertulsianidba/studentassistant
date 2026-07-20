// @ts-nocheck
/**
 * Focused billing tests for the pure orchestration core (billingCore.ts).
 * Runs in plain Node (compiled by scripts/run-billing-tests.sh). No expo-iap / RN needed.
 *
 * Covers: real offer-token selection, obfuscated account id, and the event-based
 * PurchaseCoordinator (success / error / cancellation / duplicate / pending / verify-failure /
 * finish-only-after-backend / restore-verifies-before-finish), plus a static check that Paywall
 * and Premium both use the shared obfuscatedAccountId helper (and no "acct" constant remains).
 */
import * as fs from "fs";
import * as path from "path";
import {
  BillingError, PurchaseCoordinator, normalizeSubscriptions, obfuscatedAccountId, selectOffer,
} from "./billingCore";

let passed = 0;
function ok(cond: any, msg: string) {
  if (!cond) throw new Error("FAIL: " + msg);
  passed++;
}
async function expectReject(p: Promise<any>, codeOrMsg?: string) {
  try { await p; } catch (e: any) { if (codeOrMsg) ok(e.code === codeOrMsg || String(e.message).includes(codeOrMsg), `reject ${codeOrMsg} (got ${e.code}/${e.message})`); return e; }
  throw new Error("FAIL: expected promise to reject");
}

// ---- fixtures ----
const PRODUCT = "student_assistant_premium";
function rawSubs() {
  return [{
    productId: PRODUCT, title: "Premium",
    subscriptionOffers: [
      { basePlanIdAndroid: "monthly", offerTokenAndroid: "OFFER_TOKEN_MONTHLY_abc", displayPrice: "CA$11.99", currency: "CAD", pricingPhasesAndroid: { pricingPhaseList: [{ billingPeriod: "P1M" }] } },
      { basePlanIdAndroid: "annual", offerTokenAndroid: "OFFER_TOKEN_ANNUAL_xyz", displayPrice: "CA$109.99", currency: "CAD", pricingPhasesAndroid: { pricingPhaseList: [{ billingPeriod: "P1Y" }] } },
    ],
  }];
}

function mockDeps(overrides: any = {}) {
  const calls: string[] = [];
  const deps = {
    launchPurchase: async () => { calls.push("launch"); },
    verify: async () => { calls.push("verify"); return { plan: "premium" }; },
    finish: async () => { calls.push("finish"); },
    getToken: (p: any) => p?.purchaseToken,
    isPending: (p: any) => p?.purchaseState === "pending",
    isUserCancelled: (e: any) => e?.code === "user-cancelled",
    ...overrides,
  };
  return { deps, calls };
}

async function run() {
  // ---- offer selection: real token, per base plan, never the basePlanId ----
  const products = normalizeSubscriptions(rawSubs(), PRODUCT);
  ok(products.length === 2, "normalize produced 2 offers");
  const m = selectOffer(products, "monthly");
  ok(m.basePlanId === "monthly" && m.offerToken === "OFFER_TOKEN_MONTHLY_abc", "monthly selects monthly offer token");
  ok(m.offerToken !== m.basePlanId, "monthly: basePlanId is NOT used as offerToken");
  const a = selectOffer(products, "annual");
  ok(a.basePlanId === "annual" && a.offerToken === "OFFER_TOKEN_ANNUAL_xyz", "annual selects annual offer token");
  ok(a.offerToken !== a.basePlanId, "annual: basePlanId is NOT used as offerToken");
  // missing offer token blocks purchase
  const noToken = [{ productId: PRODUCT, basePlanId: "monthly", offerToken: "" }];
  let threw = false;
  try { selectOffer(noToken as any, "monthly"); } catch (e: any) { threw = e.code === "offer-token-missing"; }
  ok(threw, "missing offer token blocks purchase");
  let threw2 = false;
  try { selectOffer(products, "weekly"); } catch (e: any) { threw2 = e.code === "offer-not-found"; }
  ok(threw2, "unknown base plan blocks purchase");

  // ---- obfuscated account id ----
  ok(obfuscatedAccountId("user-123") === obfuscatedAccountId("user-123"), "same user -> same id");
  ok(obfuscatedAccountId("user-123") !== obfuscatedAccountId("user-999"), "different users -> different id");
  ok(!obfuscatedAccountId("user-123").includes("user-123"), "raw user id not exposed");

  // ---- coordinator: success (finish only AFTER verify) ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    await c.handleUpdate({ purchaseToken: "TOK1", purchaseState: "purchased" });
    const out = await p;
    ok(out.status === "verified", "success outcome verified");
    ok(calls.filter((x) => x === "verify").length === 1, "verify called once");
    ok(calls.filter((x) => x === "finish").length === 1, "finish called once");
    ok(calls.indexOf("verify") < calls.indexOf("finish"), "finish only AFTER backend verify");
  }

  // ---- coordinator: error callback (no finish) ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    c.handleError({ code: "network-error" });
    const e = await expectReject(p, "purchase-failed");
    ok(e instanceof BillingError, "error is BillingError");
    ok(!calls.includes("finish"), "no finish on error");
  }

  // ---- coordinator: user cancellation ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    c.handleError({ code: "user-cancelled" });
    await expectReject(p, "cancelled");
    ok(!calls.includes("finish"), "no finish on cancellation");
  }

  // ---- coordinator: duplicate callback is idempotent ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    // fire two updates for the same token concurrently
    const u1 = c.handleUpdate({ purchaseToken: "DUP", purchaseState: "purchased" });
    const u2 = c.handleUpdate({ purchaseToken: "DUP", purchaseState: "purchased" });
    await Promise.all([u1, u2]);
    await p;
    ok(calls.filter((x) => x === "verify").length === 1, "duplicate callback -> verify once");
    ok(calls.filter((x) => x === "finish").length === 1, "duplicate callback -> finish once");
  }

  // ---- coordinator: pending never grants ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    await c.handleUpdate({ purchaseToken: "PEND", purchaseState: "pending" });
    const out = await p;
    ok(out.status === "pending", "pending outcome");
    ok(!calls.includes("verify") && !calls.includes("finish"), "pending -> no verify/finish/grant");
  }

  // ---- coordinator: backend verification failure (no finish) ----
  {
    const { deps, calls } = mockDeps({ verify: async () => { calls.push("verify"); throw new BillingError("verify-failed"); } });
    const c = new PurchaseCoordinator(deps);
    const p = c.startPurchase({ productId: PRODUCT, offerToken: a.offerToken, obfuscatedAccountId: "sa_x" });
    await c.handleUpdate({ purchaseToken: "BAD", purchaseState: "purchased" });
    await expectReject(p);
    ok(calls.includes("verify") && !calls.includes("finish"), "verify failure -> no finish");
  }

  // ---- startPurchase without offer token never launches ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    await expectReject(c.startPurchase({ productId: PRODUCT, offerToken: "", obfuscatedAccountId: "sa_x" }), "offer-token-missing");
    ok(!calls.includes("launch"), "no launch without offer token");
  }

  // ---- restore verifies server-side BEFORE finishing ----
  {
    const { deps, calls } = mockDeps();
    const c = new PurchaseCoordinator(deps);
    const last = await c.reconcile([{ purchaseToken: "R1", purchaseState: "purchased" }]);
    ok(last && calls.indexOf("verify") < calls.indexOf("finish"), "restore verifies before finish");
  }
  {
    const { deps, calls } = mockDeps({ verify: async () => { calls.push("verify"); throw new Error("x"); } });
    const c = new PurchaseCoordinator(deps);
    await c.reconcile([{ purchaseToken: "R2", purchaseState: "purchased" }]);
    ok(calls.includes("verify") && !calls.includes("finish"), "restore does not finish unverified purchase");
  }

  // ---- static: Paywall & Premium use the shared helper; no "acct" constant remains ----
  const appDir = process.env.APP_DIR || path.resolve(process.cwd(), "app");
  const paywall = fs.readFileSync(path.join(appDir, "paywall.tsx"), "utf8");
  const premium = fs.readFileSync(path.join(appDir, "premium.tsx"), "utf8");
  ok(paywall.includes("billing.obfuscatedAccountId("), "paywall uses shared obfuscatedAccountId helper");
  ok(premium.includes("billing.obfuscatedAccountId("), "premium uses shared obfuscatedAccountId helper");
  ok(!/["']acct["']/.test(paywall), "paywall no longer uses the constant 'acct'");

  console.log(`PASS billingCore.test — ${passed} assertions`);
}

run().catch((e) => { console.error(e.message || e); process.exit(1); });
