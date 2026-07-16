/**
 * Billing service. The backend is the entitlement authority — this module NEVER grants
 * Premium locally. Native Google Play purchases use `expo-iap` (Google Play Billing Library),
 * loaded lazily and only on a native build with billing enabled, so the web / Expo Go bundle
 * is unaffected. When billing is disabled everything still works: Free + Starter Pack flows
 * are untouched and purchase actions report that subscriptions aren't available yet.
 */
import { Platform } from "react-native";
import { api } from "@/src/api";

export const BILLING_ENABLED =
  (process.env.EXPO_PUBLIC_BILLING_ENABLED || "false").toLowerCase() === "true";

export type UsageFeature = {
  label: string; used: number; allowance: number; remaining: number; pct: number;
};
export type BillingStatus = {
  plan: "free" | "premium"; state: string; cycle_type: string;
  cycle_start: string | null; cycle_end: string | null; renews: boolean;
  current_period_end: string | null; billing_enabled: boolean;
  features: Record<string, UsageFeature>;
  product?: { product_id: string; monthly_base_plan_id: string; annual_base_plan_id: string; package_name: string };
};

export async function fetchStatus(): Promise<BillingStatus> {
  return await api.get("/billing/status");
}
export async function fetchPlanConfig(): Promise<any> {
  return await api.get("/plan/config");
}
export async function logEvent(kind: string, plan?: string, reason?: string) {
  try { await api.post("/monetization/event", { kind, plan, reason }); } catch { /* non-blocking */ }
}

function nativeAvailable(): boolean {
  if (Platform.OS === "web" || !BILLING_ENABLED) return false;
  try {
    // eslint-disable-next-line @typescript-eslint/no-require-imports
    require("expo-iap");
    return true;
  } catch {
    return false;
  }
}
export const canPurchase = nativeAvailable;

export type PlayProduct = {
  basePlanId: string; productId: string; title?: string;
  localizedPrice?: string; currency?: string; billingPeriod?: string;
};

/** Load localized subscription offers from Google Play (device only). */
export async function loadProducts(productId: string): Promise<PlayProduct[]> {
  if (!nativeAvailable()) return [];
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const iap = require("expo-iap");
  try {
    if (iap.initConnection) await iap.initConnection();
    const subs = (await (iap.getSubscriptions?.({ skus: [productId] }) ??
                        iap.fetchProducts?.({ skus: [productId], type: "subs" }) ?? [])) as any[];
    const out: PlayProduct[] = [];
    for (const s of subs) {
      const offers = s.subscriptionOfferDetails || s.subscriptionOfferDetailsAndroid || [];
      for (const o of offers) {
        const phase = (o.pricingPhases?.pricingPhaseList || [])[0] || {};
        out.push({
          basePlanId: o.basePlanId || o.basePlanIdAndroid || "",
          productId: s.productId || productId,
          title: s.title, localizedPrice: phase.formattedPrice,
          currency: phase.priceCurrencyCode, billingPeriod: phase.billingPeriod,
        });
      }
    }
    return out;
  } catch {
    return [];
  }
}

/**
 * Start a subscription purchase for a base plan, then send the resulting purchase token to
 * the backend for Google-side verification. Returns the backend-verified status.
 */
export async function purchase(productId: string, basePlanId: string, obfuscatedAccountId: string) {
  if (!nativeAvailable()) throw new Error("Subscriptions aren't available in this build yet.");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const iap = require("expo-iap");
  const result = await (iap.requestSubscription?.({
    sku: productId, subscriptionOffers: [{ sku: productId, offerToken: basePlanId }],
    obfuscatedAccountIdAndroid: obfuscatedAccountId,
  }) ?? iap.requestPurchase?.({ request: { android: { skus: [productId] } }, type: "subs" }));
  const p: any = Array.isArray(result) ? result[0] : result;
  const purchaseToken = p?.purchaseToken || p?.purchaseTokenAndroid;
  if (!purchaseToken) throw new Error("Purchase did not complete.");
  const verified = await api.post("/billing/google/verify", {
    purchase_token: purchaseToken, product_id: productId, base_plan_id: basePlanId,
    obfuscated_account_id: obfuscatedAccountId,
  });
  try { if (iap.finishTransaction) await iap.finishTransaction({ purchase: p, isConsumable: false }); } catch { /* noop */ }
  return verified;
}

/** Restore previous purchases and re-verify with the backend. */
export async function restore() {
  if (!nativeAvailable()) throw new Error("Subscriptions aren't available in this build yet.");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const iap = require("expo-iap");
  const purchases = (await (iap.getAvailablePurchases?.() ?? [])) as any[];
  let last: any = null;
  for (const p of purchases) {
    const token = p?.purchaseToken || p?.purchaseTokenAndroid;
    if (token) last = await api.post("/billing/google/restore", { purchase_token: token });
  }
  return last || (await fetchStatus());
}
