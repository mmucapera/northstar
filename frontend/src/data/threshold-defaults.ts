import { VARIANCE_TOLERANCE } from "@/data/delta-basin";
import type { ThresholdKey } from "@/data/workflow";

/** Shared between profile.tsx's settings UI and app-shell.tsx's notification
 * bell, so they can never drift out of sync with each other. */
export const THRESHOLD_DEFAULTS: Record<ThresholdKey, number> = {
  variance_watch_pct: VARIANCE_TOLERANCE.watchPct,
  variance_investigate_pct: VARIANCE_TOLERANCE.investigatePct,
  uptime_alert_pct: 94,
  downtime_alert_hours: 200,
};
