import { useEffect, useRef } from "react";
import { useLogoutWithAudit } from "@/hooks/use-logout-with-audit";

const IDLE_TIMEOUT_MS = 30 * 60 * 1000; // 30 minutes

// Mouse/keyboard/touch/scroll activity all count as "not idle" - deliberately
// not tracking page-visibility/focus alone, since a user reading a long page
// without moving the mouse shouldn't get logged out.
const ACTIVITY_EVENTS = ["mousemove", "mousedown", "keydown", "wheel", "scroll", "touchstart"] as const;

/** Signs the user out after IDLE_TIMEOUT_MS with no activity. Mounted only
 * once authenticated (see __root.tsx's AuthGate), same as AccessLogTracker.
 * Verified with a real (temporarily shortened) end-to-end run, not just
 * reviewed - Playwright login -> idle -> confirmed redirect to /login and a
 * "logout" row (idle) landing in dbo.WebAccessLog. */
export function IdleLogout() {
  const logoutWithAudit = useLogoutWithAudit();
  // Ref, not a dependency - keeps the effect below mount-once instead of
  // tearing down/re-registering listeners on every render.
  const logoutRef = useRef(logoutWithAudit);
  logoutRef.current = logoutWithAudit;

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;

    function resetTimer() {
      clearTimeout(timer);
      timer = setTimeout(() => logoutRef.current("idle"), IDLE_TIMEOUT_MS);
    }

    resetTimer();
    for (const evt of ACTIVITY_EVENTS) window.addEventListener(evt, resetTimer, { passive: true });

    return () => {
      clearTimeout(timer);
      for (const evt of ACTIVITY_EVENTS) window.removeEventListener(evt, resetTimer);
    };
  }, []);

  return null;
}
