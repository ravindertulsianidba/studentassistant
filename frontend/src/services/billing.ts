/**
 * Billing service. The backend is the entitlement authority — this module NEVER grants
 * Premium locally. Native Google Play purchases use `expo-iap` (Google Play Billing Library),
 * loaded lazily and only on a native build with billing enabled, so the web / Expo Go bundle
 * is unaffected. When billing is disabled everything still works: Free + Starter Pack flows
 * are untouched and purchase actions report that subscriptions aren't available yet.
 */
import { Platform } from "react-native";
import { api } from "@/src/api";
import {
  BillingError, PlayProduct, PurchaseCoordinator,
  normalizeSubscriptions, obfuscatedAccountId as _obfId, selectOffer,
} from "@/src/services/billingCore";

export { BillingError };
export type { PlayProduct };

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

/**
 * Ask the backend to re-query Google Play for this account's stored purchase and return the
 * authoritative entitlement. The backend is the entitlement authority; this never grants locally
 * and fails safe (returns current status) when billing/credentials are unavailable.
 */
export async function refreshEntitlement(): Promise<BillingStatus> {
  try { return await api.post("/billing/google/refresh", {}); }
  catch { return await fetchStatus(); }
}

/**
 * Stable, non-reversible obfuscated account identifier tied to the authenticated user.
 * Centralized in billingCore so Premium and Paywall use identical logic.
 */
export function obfuscatedAccountId(userId?: string | null): string {
  return _obfId(userId);
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

// eslint-disable-next-line @typescript-eslint/no-require-imports
const loadIap = () => require("expo-iap");

const getToken = (p: any): string | undefined => p?.purchaseToken || p?.purchaseTokenAndroid || undefined;
const isPending = (p: any): boolean => String(p?.purchaseState ?? "").toLowerCase() === "pending";
// expo-iap 4.5.1 ErrorCode.UserCancelled === "user-cancelled".
const isUserCancelled = (e: any): boolean => {
  const c = String(e?.code ?? "").toLowerCase();
  return c === "user-cancelled" || c === "e_user_cancelled" || c.includes("cancel");
};

let _coordinator: PurchaseCoordinator | null = null;
let _listenersReady = false;
let _subs: Array<{ remove: () => void }> = [];

/** Initialize the purchase coordinator + event listeners exactly once. */
function ensureCoordinator(iap: any): PurchaseCoordinator {
  if (!_coordinator) {
    _coordinator = new PurchaseCoordinator({
      launchPurchase: async ({ productId, offerToken, obfuscatedAccountId }) => {
        // requestPurchase only LAUNCHES the flow; the result arrives via the listeners.
        await iap.requestPurchase({
          request: {
            google: {
              skus: [productId],
              subscriptionOffers: [{ sku: productId, offerToken }],
              obfuscatedAccountId,
            },
          },
          type: "subs",
        });
      },
      verify: async ({ purchaseToken }) => api.post("/billing/google/verify", { purchase_token: purchaseToken }),
      finish: async (purchase: any) => {
        if (iap.finishTransaction) await iap.finishTransaction({ purchase, isConsumable: false });
      },
      getToken, isPending, isUserCancelled,
    });
  }
  if (!_listenersReady) {
    const onUpdate = iap.purchaseUpdatedListener?.((purchase: any) => { void _coordinator!.handleUpdate(purchase); });
    const onError = iap.purchaseErrorListener?.((error: any) => { _coordinator!.handleError(error); });
    if (onUpdate) _subs.push(onUpdate);
    if (onError) _subs.push(onError);
    _listenersReady = true;
  }
  return _coordinator;
}

/** Tear down listeners (e.g., on sign-out). Safe to call repeatedly. */
export function removeBillingListeners() {
  for (const s of _subs) { try { s.remove(); } catch { /* noop */ } }
  _subs = [];
  _listenersReady = false;
}

/** Load localized subscription offers from Google Play (device only), preserving offer tokens. */
export async function loadProducts(productId: string): Promise<PlayProduct[]> {
  if (!nativeAvailable()) return [];
  const iap = loadIap();
  try {
    if (iap.initConnection) await iap.initConnection();
    const subs = (await (iap.fetchProducts?.({ skus: [productId], type: "subs" }) ??
                        iap.getSubscriptions?.({ skus: [productId] }) ?? [])) as any[];
    return normalizeSubscriptions(subs, productId);
  } catch {
    return [];
  }
}

/**
 * Start a subscription purchase for a base plan using the REAL Google Play offer token, driven
 * by the event listeners. Resolves ONLY after the backend verifies and entitlement is granted
 * (and the local transaction is finished). PENDING purchases resolve as pending (no grant).
 */
export async function purchase(productId: string, basePlanId: string, obfuscatedAccountId: string) {
  if (!nativeAvailable()) throw new BillingError("unavailable", "Subscriptions aren't available in this build yet.");
  const iap = loadIap();
  if (iap.initConnection) await iap.initConnection();
  const products = await loadProducts(productId);
  const offer = selectOffer(products, basePlanId); // throws if no real offer token -> no launch
  const coordinator = ensureCoordinator(iap);
  const outcome = await coordinator.startPurchase({ productId, offerToken: offer.offerToken, obfuscatedAccountId });
  if (outcome.status === "pending") {
    return { pending: true, ...(await fetchStatus()) };
  }
  return outcome.result ?? (await fetchStatus());
}

/** Restore previous purchases and re-verify server-side BEFORE finishing any transaction. */
export async function restore() {
  if (!nativeAvailable()) throw new BillingError("unavailable", "Subscriptions aren't available in this build yet.");
  const iap = loadIap();
  if (iap.initConnection) await iap.initConnection();
  const coordinator = ensureCoordinator(iap);
  // Use restore endpoint for reconciliation on restore.
  const restoreCoordinator = new PurchaseCoordinator({
    launchPurchase: () => {},
    verify: async ({ purchaseToken }) => api.post("/billing/google/restore", { purchase_token: purchaseToken }),
    finish: async (purchase: any) => { if (iap.finishTransaction) await iap.finishTransaction({ purchase, isConsumable: false }); },
    getToken, isPending, isUserCancelled,
  });
  void coordinator; // keep the main coordinator/listeners initialized
  let purchases: any[] = [];
  try {
    if (iap.restorePurchases) await iap.restorePurchases();
    purchases = (await (iap.getAvailablePurchases?.() ?? [])) as any[];
  } catch { purchases = []; }
  const last = await restoreCoordinator.reconcile(purchases);
  return last || (await fetchStatus());
}
