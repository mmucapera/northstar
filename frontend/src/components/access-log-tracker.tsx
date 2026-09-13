import { useEffect, useRef } from "react";
import { useRouterState } from "@tanstack/react-router";
import { useAuth } from "@/components/auth-context";
import { logAccessEvent } from "@/data/access-log";

/** Logs one event per page visit - when the user navigates away from a page,
 * records how long they were on it. Known gap: the very last page before a
 * tab close/refresh isn't captured (would need a sendBeacon-compatible
 * endpoint, not attempted here) - everything else is. */
export function AccessLogTracker() {
  const { user } = useAuth();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const prevPath = useRef<string | null>(null);
  const enteredAt = useRef<string>(new Date().toISOString());
  const enteredAtMs = useRef<number>(Date.now());

  useEffect(() => {
    const leftPath = prevPath.current;
    const arrivedAt = enteredAt.current;
    const arrivedAtMs = enteredAtMs.current;

    if (leftPath !== null && user) {
      logAccessEvent({
        data: {
          eventType: "page_visit",
          timestamp: arrivedAt,
          userEmail: user.email,
          userName: user.name,
          userRole: user.role,
          path: leftPath,
          durationMs: Date.now() - arrivedAtMs,
          referrer: typeof document !== "undefined" ? document.referrer || null : null,
        },
      }).catch(() => {
        /* best-effort - never block navigation on a logging failure */
      });
    }

    prevPath.current = pathname;
    enteredAt.current = new Date().toISOString();
    enteredAtMs.current = Date.now();
  }, [pathname, user]);

  return null;
}
