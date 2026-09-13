import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { LOG_VISIBILITY } from "@/data/auth";
import type { PersonaId } from "@/components/view-context";
import { useAuth } from "@/components/auth-context";

const STORAGE_KEY = "delta-basin-activity-log-v1";
const MAX_ENTRIES = 500;

export type ActivityAction = "auth.login" | "auth.logout" | "catalog.update" | "catalog.reset";

export type ActivityLogEntry = {
  id: string;
  timestamp: string; // ISO
  actorEmail: string;
  actorName: string;
  actorRole: PersonaId;
  action: ActivityAction;
  detail: string;
};

type ActivityLogContextValue = {
  /** Every entry this browser has recorded, unfiltered - only used internally. */
  allEntries: ActivityLogEntry[];
  /** Entries the CURRENT signed-in user is allowed to see: their own, always,
   * plus anything from a role their role's hierarchy covers (LOG_VISIBILITY). */
  visibleEntries: ActivityLogEntry[];
  record: (action: ActivityAction, detail: string) => void;
};

const ActivityLogContext = createContext<ActivityLogContextValue>({
  allEntries: [],
  visibleEntries: [],
  record: () => {},
});

function loadEntries(): ActivityLogEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as ActivityLogEntry[];
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function ActivityLogProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [entries, setEntries] = useState<ActivityLogEntry[]>([]);

  useEffect(() => {
    setEntries(loadEntries());
  }, []);

  const value = useMemo<ActivityLogContextValue>(() => {
    const record = (action: ActivityAction, detail: string) => {
      if (!user) return;
      const entry: ActivityLogEntry = {
        id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
        timestamp: new Date().toISOString(),
        actorEmail: user.email,
        actorName: user.name,
        actorRole: user.role,
        action,
        detail,
      };
      setEntries((prev) => {
        const next = [entry, ...prev].slice(0, MAX_ENTRIES);
        try {
          window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        } catch {
          /* storage unavailable */
        }
        return next;
      });
    };

    const visibleRoles = user ? new Set(LOG_VISIBILITY[user.role]) : new Set<PersonaId>();
    const visibleEntries = user
      ? entries.filter((e) => e.actorEmail === user.email || visibleRoles.has(e.actorRole))
      : [];

    return { allEntries: entries, visibleEntries, record };
  }, [entries, user]);

  return <ActivityLogContext.Provider value={value}>{children}</ActivityLogContext.Provider>;
}

export const useActivityLog = () => useContext(ActivityLogContext);
