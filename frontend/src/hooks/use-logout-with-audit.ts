import { useNavigate } from "@tanstack/react-router";
import { useAuth } from "@/components/auth-context";
import { useActivityLog } from "@/components/activity-log-context";
import { logAccessEvent } from "@/data/access-log";

/** Shared logout sequence - records the in-app activity-log entry, logs the
 * SQL-DB-backed access-log "logout" event (see access-log.ts), clears the
 * session, and redirects to /login. Used by both the manual "Log out" menu
 * item (app-shell.tsx) and the idle-timeout auto-logout (idle-logout.tsx),
 * so both paths stay audited identically. */
export function useLogoutWithAudit() {
  const { user, logout } = useAuth();
  const { record } = useActivityLog();
  const navigate = useNavigate();

  return (reason: "manual" | "idle" = "manual") => {
    if (!user) return;
    const suffix = reason === "idle" ? " (idle timeout)" : "";
    record("auth.logout", `${user.name} (${user.role}) signed out${suffix}.`);
    logAccessEvent({
      data: {
        eventType: "logout",
        timestamp: new Date().toISOString(),
        userEmail: user.email,
        userName: user.name,
        userRole: user.role,
        path: typeof window !== "undefined" ? window.location.pathname : "/",
        durationMs: null,
        referrer: null,
      },
    }).catch(() => {
      /* best-effort - never block sign-out on a logging failure */
    });
    logout();
    navigate({ to: "/login" });
  };
}
