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
    throw new Error(typeof e.detail === "string" ? e.detail : `Request failed (${res.status})`);
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
