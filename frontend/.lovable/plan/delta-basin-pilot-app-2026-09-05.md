# Delta Basin — pilot app

Build the Delta Basin pilot as a working web app: the three dashboards described in the PRD, plus a cleaned-up version of the PRD itself, all in one dark "control-room" interface running on realistic sample data (no database, no login).

## Pages

- **/** — Overview. One screen with the health of all three areas: net JV variance, production vs. forecast, TRIR, plus alert strip for anything needing attention (disputed cash calls, wells down, new incidents).
- **/reconciliation** — Allocated vs. lifted volumes per partner and field for the current period, variance in barrels and %, status flag (within tolerance / watch / investigate), cash-call status (settled / pending / disputed), and a 12-month net-variance trend. Click a partner to see their history.
- **/production** — Actual vs. forecast production (bopd) per field, wells online/total with uptime %, normal/watch/down status, 12-month fleet uptime trend, and a downtime-cause breakdown.
- **/hse** — TRIR on a rolling 12-month basis, monthly incident log, incident trend, cumulative exposure-hours trend.
- **/prd** — The product document itself, restructured with a sticky contents sidebar, clean section numbering, and live links into the three dashboards so figures point at the real screens instead of screenshots.

## Improvements over the current solution

- Overview page the PRD doesn't have — the "executive" persona currently has no single place to look.
- Period selector shared across all three dashboards, so the same month applies everywhere.
- Explicit tolerance thresholds shown in the UI, so a "watch" flag explains itself.
- A visible "synthetic data — pre-discovery" marker and a data-freshness timestamp, matching the honesty the PRD insists on.
- Partner drill-through (listed as "Could" in the PRD) included, since it costs little on sample data.
- Downtime-cause breakdown stubbed with plausible categories so discovery can react to something concrete.
- Export current view to CSV on each dashboard table.

## Design

Dark control-room: deep slate surfaces, amber and teal accents for warning/healthy states, a red reserved for disputes and downtime, condensed monospaced figures for numbers, dense tables. Restrained motion. All colors defined as design tokens.

## Technical notes

- TanStack Start routes, one file per page; shared app shell with side navigation in the root route.
- Sample data generated deterministically in `src/data/` (partners, fields, 12 months of periods, and the three fact sets) so figures stay stable across reloads and totals reconcile between pages.
- Charts with Recharts; tables as plain semantic markup with sticky headers.
- Per-page title/description metadata.
- No backend; if you later want editable records or logins, that can be added on top without reworking the pages.
