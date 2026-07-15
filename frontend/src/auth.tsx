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
  signUp: (email: string, password: string, fullName?: string) => Promise<{ email: string }>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  verifyEmail: (token: string) => Promise<void>;
  resendVerification: (email: string) => Promise<void>;
  forgotPassword: (email: string) => Promise<void>;
  resetPassword: (token: string, password: string) => Promise<void>;
  devSignIn: (email: string) => Promise<void>;
  signOut: () => Promise<void>;
  revokeAllSessions: () => Promise<void>;
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
  const signUp = async (email: string, password: string, fullName?: string) => {
    const data = await api.post("/auth/register", { email, password, full_name: fullName });
    return { email: data.email || email };
  };
  const signInWithPassword = async (email: string, password: string) => {
    const data = await api.post("/auth/login", { email, password });
    await afterLogin(data);
  };
  const verifyEmail = async (token: string) => { await api.post("/auth/verify-email", { token }); };
  const resendVerification = async (email: string) => { await api.post("/auth/resend-verification", { email }); };
  const forgotPassword = async (email: string) => { await api.post("/auth/forgot-password", { email }); };
  const resetPassword = async (token: string, password: string) => { await api.post("/auth/reset-password", { token, password }); };
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
  const revokeAllSessions = async () => {
    try { await api.post("/auth/logout-all", {}); } catch {}
    await signOut();
  };
  const deleteAccount = async () => {
    try { await api.del("/me"); } catch {}
    await signOut();
  };

  return (
    <Ctx.Provider value={{ ready, user, signInWithGoogleToken, signUp, signInWithPassword,
      verifyEmail, resendVerification, forgotPassword, resetPassword,
      devSignIn, signOut, revokeAllSessions, deleteAccount }}>
      {children}
    </Ctx.Provider>
  );
}
