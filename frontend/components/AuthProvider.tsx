"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import { usePathname } from "next/navigation";
import { api, setToken, toApiError } from "@/lib/api";
import type { ApiError } from "@/lib/api";
import { webApi } from "@/lib/workspace";
import type { PortalUser } from "@/lib/workspace";

interface AuthContextValue {
  ready: boolean;
  authenticated: boolean;
  user: PortalUser | null;
  email: string | null;
  error: ApiError | null;
  pending: boolean;
  refresh: () => Promise<void>;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => void;
}
const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState<PortalUser | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [pending, setPending] = useState(false);
  const refresh = useCallback(async () => {
    try {
      setUser(await webApi<PortalUser>("/me"));
    } catch {
      setUser(null);
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    setToken(null);
    if (pathname?.startsWith("/preview")) {
      setReady(true);
      return;
    }
    void refresh();
  }, [pathname, refresh]);

  useEffect(() => {
    if (!user) return;
    const timer = setInterval(
      () =>
        webApi("/auth/heartbeat", { method: "POST" }).catch(() => refresh()),
      60000,
    );
    return () => clearInterval(timer);
  }, [user, refresh]);

  const signIn = useCallback(
    async (email: string, password: string) => {
      setPending(true);
      setError(null);
      try {
        await api.login({ email, password });
        await refresh();
        return true;
      } catch (cause) {
        setError(toApiError(cause));
        return false;
      } finally {
        setPending(false);
      }
    },
    [refresh],
  );
  const signOut = useCallback(async () => {
    setError(null);
    try {
      await webApi("/auth/logout", { method: "POST" });
      setToken(null);
      setUser(null);
    } catch (cause) {
      setError(toApiError(cause));
    }
  }, []);
  const value = useMemo(
    () => ({
      ready,
      authenticated: Boolean(user),
      user,
      email: user?.email || null,
      error,
      pending,
      refresh,
      signIn,
      signOut,
    }),
    [ready, user, error, pending, refresh, signIn, signOut],
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}
export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) throw new Error("useAuth requires AuthProvider");
  return context;
}
