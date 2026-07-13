const BASE = `${process.env.EXPO_PUBLIC_BACKEND_URL}/api`;

async function req(path: string, opts: RequestInit = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status}`);
  return res.json();
}

export const api = {
  get: (p: string) => req(p),
  post: (p: string, body?: any) => req(p, { method: "POST", body: JSON.stringify(body || {}) }),
  patch: (p: string, body?: any) => req(p, { method: "PATCH", body: JSON.stringify(body || {}) }),
  del: (p: string) => req(p, { method: "DELETE" }),
};
