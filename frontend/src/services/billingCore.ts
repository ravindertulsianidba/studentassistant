/**
 * Pure billing orchestration — NO react-native / expo-iap / network imports, so it is unit
 * testable in isolation. `billing.ts` injects the real expo-iap functions and backend client.
 *
 * Design notes (expo-iap 4.5.1 / OpenIAP):
 *  - A subscription purchase is EVENT-BASED. `requestPurchase` only launches the Play dialog; the
 *    completed purchase arrives via `purchaseUpdatedListener` (and failures/cancellations via
 *    `purchaseErrorListener`). We NEVER treat the requestPurchase return value as authoritative.
 *  - Each Android base plan (monthly/annual) has its own real `offerToken`; the base-plan ID is
 *    NOT a token. We select the offer whose base plan matches and pass its real offerToken.
 *  - The backend is the entitlement authority: we verify server-side, and only THEN finish the
 *    local transaction. Duplicate callbacks never cause duplicate verification/finish.
 */

export class BillingError extends Error {
  code: string;
  constructor(code: string, message?: string) {
    super(message || code);
    this.code = code;
    this.name = "BillingError";
  }
}

/** Normalized store product model — base plan ID and offer token are kept SEPARATE. */
export type PlayProduct = {
  productId: string;
  basePlanId: string;
  offerToken: string; // the REAL Google Play offer token (never the base-plan id)
  title?: string;
  localizedPrice?: string;
  currency?: string;
  billingPeriod?: string;
};

/**
 * Stable, non-reversible, user-specific obfuscated account identifier for Google Play.
 * Derived only from the internal user id (never email/name), opaque (a hash) so the raw id
 * is never sent to the store, and identical for the same user across Premium & Paywall.
 */
export function obfuscatedAccountId(userId?: string | null): string {
  const s = String(userId || "anon");
  const fnv = (input: string) => {
    let h = 0x811c9dc5;
    for (let i = 0; i < input.length; i++) {
      h ^= input.charCodeAt(i);
      h = Math.imul(h, 0x01000193);
    }
    return (h >>> 0).toString(16).padStart(8, "0");
  };
  return `sa_${fnv(s)}${fnv(s + "|sa")}`;
}

/** Convert raw expo-iap subscription products into the normalized model, preserving offer tokens. */
export function normalizeSubscriptions(rawSubs: any[], fallbackProductId: string): PlayProduct[] {
  const out: PlayProduct[] = [];
  for (const s of rawSubs || []) {
    const productId = s.productId || s.id || fallbackProductId;
    // Prefer the standardized cross-platform offers (offerTokenAndroid / basePlanIdAndroid),
    // fall back to the legacy Android-specific offer details (offerToken / basePlanId).
    const standardized = (s.subscriptionOffers || []).map((o: any) => ({
      basePlanId: o.basePlanIdAndroid ?? o.basePlanId ?? "",
      offerToken: o.offerTokenAndroid ?? o.offerToken ?? "",
      price: o.displayPrice ?? o.localizedPriceIOS,
      currency: o.currency,
      period: o.pricingPhasesAndroid?.pricingPhaseList?.[0]?.billingPeriod ?? periodToIso(o.period),
    }));
    const legacy = (s.subscriptionOfferDetailsAndroid || s.subscriptionOfferDetails || []).map((o: any) => {
      const phase = (o.pricingPhases?.pricingPhaseList || [])[0] || {};
      return {
        basePlanId: o.basePlanId ?? o.basePlanIdAndroid ?? "",
        offerToken: o.offerToken ?? "",
        price: phase.formattedPrice,
        currency: phase.priceCurrencyCode,
        period: phase.billingPeriod,
      };
    });
    const offers = standardized.length ? standardized : legacy;
    for (const o of offers) {
      out.push({
        productId,
        basePlanId: o.basePlanId,
        offerToken: o.offerToken,
        title: s.title,
        localizedPrice: o.price,
        currency: o.currency,
        billingPeriod: o.period,
      });
    }
  }
  return out;
}

function periodToIso(p?: string | null): string | undefined {
  if (!p) return undefined;
  return p; // OpenIAP periods are already ISO-8601 (e.g., "P1M", "P1Y")
}

/**
 * Select the offer for the chosen base plan and return its REAL offer token.
 * Fails safe (throws) if no matching offer or no offer token exists — the caller must NOT launch
 * billing in that case, and the base-plan id must never be substituted for the offer token.
 */
export function selectOffer(products: PlayProduct[], basePlanId: string): PlayProduct {
  const match = (products || []).find((p) => p.basePlanId === basePlanId);
  if (!match) throw new BillingError("offer-not-found", "No offer for the selected plan.");
  if (!match.offerToken || match.offerToken === match.basePlanId) {
    throw new BillingError("offer-token-missing", "No valid purchase offer for the selected plan.");
  }
  return match;
}

export interface CoordinatorDeps {
  /** Launch the Play billing dialog ONLY. Its return value is ignored. */
  launchPurchase: (args: { productId: string; offerToken: string; obfuscatedAccountId: string }) => void | Promise<void>;
  /** Verify a purchase token with the backend (authority). Throws on failure. */
  verify: (args: { purchaseToken: string }) => Promise<any>;
  /** Finish/acknowledge the local transaction. Called ONLY after backend verification succeeds. */
  finish: (purchase: any) => void | Promise<void>;
  getToken: (purchase: any) => string | undefined;
  isPending: (purchase: any) => boolean;
  isUserCancelled: (error: any) => boolean;
}

export type PurchaseOutcome = { status: "verified" | "pending"; result?: any };

/**
 * Coordinates the event-based purchase lifecycle. One instance owns the listeners; call
 * handleUpdate/handleError from the listeners. Prevents duplicate verification/finish.
 */
export class PurchaseCoordinator {
  private deps: CoordinatorDeps;
  private finished = new Set<string>();
  private verifying = new Set<string>();
  private active: {
    resolve: (o: PurchaseOutcome) => void;
    reject: (e: any) => void;
  } | null = null;

  constructor(deps: CoordinatorDeps) {
    this.deps = deps;
  }

  /** Launch a purchase and resolve when the listener reports the authoritative outcome. */
  async startPurchase(args: { productId: string; offerToken: string; obfuscatedAccountId: string }): Promise<PurchaseOutcome> {
    if (!args.offerToken) {
      // Fail safe — never launch billing without a real offer token.
      throw new BillingError("offer-token-missing", "No valid purchase offer for the selected plan.");
    }
    const p = new Promise<PurchaseOutcome>((resolve, reject) => {
      this.active = { resolve, reject };
    });
    await this.deps.launchPurchase(args);
    return p;
  }

  /** Call from purchaseUpdatedListener. Verifies server-side, then finishes; idempotent. */
  async handleUpdate(purchase: any): Promise<void> {
    const token = this.deps.getToken(purchase);
    if (!token) return;

    // PENDING (e.g. slow card / cash payment): never verify, finish or grant Premium.
    if (this.deps.isPending(purchase)) {
      this.resolveActive({ status: "pending" });
      return;
    }
    // Duplicate callbacks must not cause duplicate verification/finish.
    if (this.finished.has(token) || this.verifying.has(token)) return;

    this.verifying.add(token); // synchronous guard BEFORE any await
    try {
      const result = await this.deps.verify({ purchaseToken: token });
      await this.deps.finish(purchase); // finish ONLY after backend success
      this.finished.add(token);
      this.resolveActive({ status: "verified", result });
    } catch (e) {
      // Do NOT finish on verification failure (transaction stays for retry/reconcile).
      this.rejectActive(e instanceof BillingError ? e : new BillingError("verify-failed"));
    } finally {
      this.verifying.delete(token);
    }
  }

  /** Call from purchaseErrorListener. Cancellation is a cancellation, not a technical error. */
  handleError(error: any): void {
    if (this.deps.isUserCancelled(error)) {
      this.rejectActive(new BillingError("cancelled", "Purchase cancelled."));
    } else {
      this.rejectActive(new BillingError("purchase-failed", "The purchase could not be completed."));
    }
  }

  /** Restore/reconcile: verify server-side, then finish. Never finishes an unverified purchase. */
  async reconcile(purchases: any[]): Promise<any> {
    let last: any = null;
    for (const purchase of purchases || []) {
      const token = this.deps.getToken(purchase);
      if (!token || this.finished.has(token)) continue;
      try {
        last = await this.deps.verify({ purchaseToken: token });
        await this.deps.finish(purchase);
        this.finished.add(token);
      } catch {
        // leave unfinished; a later refresh/RTDN/reconcile can retry
      }
    }
    return last;
  }

  private resolveActive(o: PurchaseOutcome) {
    const a = this.active;
    this.active = null;
    a?.resolve(o);
  }
  private rejectActive(e: any) {
    const a = this.active;
    this.active = null;
    a?.reject(e);
  }
}
