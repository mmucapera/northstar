import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import type { DemoUser } from "@/data/auth";

const STORAGE_KEY = "delta-basin-auth-v1";

type AuthContextValue = {
  user: DemoUser | null;
  /** True once the client has checked localStorage for a session - avoids a
   * false "not logged in" flash during SSR/hydration. */
  ready: boolean;
  login: (user: DemoUser) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue>({
  user: null,
  ready: false,
  login: () => {},
  logout: () => {},
});

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<DemoUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setUser(JSON.parse(raw) as DemoUser);
    } catch {
      /* ignore malformed session */
    }
    setReady(true);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      ready,
      login: (u: DemoUser) => {
        setUser(u);
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(u));
        } catch {
          /* storage unavailable */
        }
      },
      logout: () => {
        setUser(null);
        try {
          window.localStorage.removeItem(STORAGE_KEY);
        } catch {
          /* storage unavailable */
        }
      },
    }),
    [user, ready],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export const useAuth = () => useContext(AuthContext);
