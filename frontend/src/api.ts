const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

let accessToken: string | null = null;
let refreshToken: string | null = null;
let onTokens: ((a: string, r: string) => void) | null = null;

export function setAuthTokens(a: string | null, r: string | null, cb?: (a: string, r: string) => void) {
  accessToken = a;
  refreshToken = r;
  if (cb) onTokens = cb;
}
export function clearAuthTokens() {
  accessToken = null;
  refreshToken = null;
}

let onLimitReached: ((detail: any) => void) | null = null;
export function setLimitHandler(cb: ((detail: any) => void) | null) { onLimitReached = cb; }

async function req(path: string, opts: RequestInit = {}, retry = true): Promise<any> {
  const headers: any = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (accessToken) headers["Authorization"] = `Bearer ${accessToken}`;
  const res = await fetch(`${BASE}${path}`, { ...opts, headers });
  if (res.status === 401 && retry && refreshToken) {
    const r = await fetch(`${BASE}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });
    if (r.ok) {
      const d = await r.json();
      accessToken = d.access_token;
      refreshToken = d.refresh_token;
      onTokens?.(d.access_token, d.refresh_token);
      return req(path, opts, false);
    }
  }
  if (!res.ok) {
    const e = await res.json().catch(() => ({ detail: `Request failed (${res.status})` }));
    const detail = (e as any).detail;
    // Entitlement/limit responses carry a structured detail — surface the paywall.
    if (res.status === 402 && detail && typeof detail === "object") {
      onLimitReached?.(detail);
      const err: any = new Error(detail.message || "You've reached this allowance.");
      err.status = 402; err.payload = detail; err.kind = "limit";
      throw err;
    }
    const err: any = new Error(typeof detail === "string" ? detail : `Request failed (${res.status})`);
    err.status = res.status; err.payload = detail;
    // Sanitized AI failures (503 from the backend AIError handler) are never paywalls.
    if ((e as any).ai_error) {
      err.aiError = true;
      err.category = (e as any).error_category || "ai_unavailable";
      err.kind = "ai";
    }
    throw err;
  }
  return res.json();
}

export const api = {
  base: BASE,
  get: (p: string) => req(p),
  post: (p: string, body?: any) => req(p, { method: "POST", body: JSON.stringify(body || {}) }),
  patch: (p: string, body?: any) => req(p, { method: "PATCH", body: JSON.stringify(body || {}) }),
  del: (p: string, body?: any) => req(p, { method: "DELETE", body: body ? JSON.stringify(body) : undefined }),
  // raw fetch with auth header (for multipart uploads)
  authHeader: () => (accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
};
