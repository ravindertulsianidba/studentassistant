import React, { createContext, useContext, useEffect, useState, useCallback } from "react";
import { storage } from "@/src/utils/storage";
import { api, setAuthTokens, clearAuthTokens } from "@/src/api";

const ACCESS = "sa_access_token";
const REFRESH = "sa_refresh_token";

type User = { id: string; email?: string; name?: string } | null;

type AuthCtx = {
  ready: boolean;
  user: User;
  signInWithGoogleToken: (idToken: string) => Promise<void>;
  devSignIn: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  deleteAccount: () => Promise<void>;
};

const Ctx = createContext<AuthCtx>({} as AuthCtx);
export const useAuth = () => useContext(Ctx);

async function persist(a: string, r: string) {
  await storage.secureSet(ACCESS, a);
  await storage.secureSet(REFRESH, r);
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<User>(null);

  const applyTokens = useCallback((a: string, r: string) => {
    setAuthTokens(a, r, (na, nr) => persist(na, nr));
  }, []);

  useEffect(() => {
    (async () => {
      const a = await storage.secureGet<string>(ACCESS, "");
      const r = await storage.secureGet<string>(REFRESH, "");
      if (a && r) {
        applyTokens(a, r);
        try {
          const me = await api.get("/me");
          setUser(me);
        } catch {
          clearAuthTokens();
          await storage.secureRemove(ACCESS);
          await storage.secureRemove(REFRESH);
        }
      }
      setReady(true);
    })();
  }, [applyTokens]);

  const afterLogin = async (data: any) => {
    await persist(data.access_token, data.refresh_token);
    applyTokens(data.access_token, data.refresh_token);
    setUser(data.user);
  };

  const signInWithGoogleToken = async (idToken: string) => {
    const data = await api.post("/auth/google", { id_token: idToken });
    await afterLogin(data);
  };
  const devSignIn = async (email: string) => {
    const data = await api.post("/auth/dev-login", { email });
    await afterLogin(data);
  };
  const signOut = async () => {
    const r = await storage.secureGet<string>(REFRESH, "");
    try { if (r) await api.post("/auth/logout", { refresh_token: r }); } catch {}
    clearAuthTokens();
    await storage.secureRemove(ACCESS);
    await storage.secureRemove(REFRESH);
    setUser(null);
  };
  const deleteAccount = async () => {
    try { await api.del("/me"); } catch {}
    await signOut();
  };

  return (
    <Ctx.Provider value={{ ready, user, signInWithGoogleToken, devSignIn, signOut, deleteAccount }}>
      {children}
    </Ctx.Provider>
  );
}
