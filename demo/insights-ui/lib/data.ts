// Illustrative synthetic dataset - mirrors the real star schema built in
// northstar-formation/models/customers/customer0/ (dim_partner, dim_field, dim_period +
// fact_reconciliation, fact_production, fact_hse_incidents). Field names,
// partner labels, and figures are fictional composites - not sourced from
// Prospect A, CUSTOMER0, Prospect B, or any real operator.

export type PartnerRole = "Operator" | "Non-operating";
export type CashCallStatus = "settled" | "pending" | "disputed";
export type OpsStatus = "normal" | "watch" | "down";

export interface DimPartner {
  partner: string;
  partnerRole: PartnerRole;
}

export interface DimField {
  field: string;
  exportPoint: string;
}

export interface DimPeriod {
  period: string; // "2026-08"
  label: string; // "Aug"
  year: number;
  monthNumber: number;
}

export const dimPartners: DimPartner[] = [
  { partner: "Operator (JV Lead)", partnerRole: "Operator" },
  { partner: "State NOC Partner", partnerRole: "Non-operating" },
  { partner: "IOC Partner A", partnerRole: "Non-operating" },
  { partner: "IOC Partner B", partnerRole: "Non-operating" },
];

export const dimFields: DimField[] = [
  { field: "Adaeze Field", exportPoint: "Osun Terminal" },
  { field: "Okoro Swamp Block", exportPoint: "Egret FPSO" },
  { field: "Ibeno Terminal Block", exportPoint: "Ibeno Export Terminal" },
  { field: "Sango Field", exportPoint: "Antan FPSO" },
];

const MONTH_LABELS = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"];

export const dimPeriods: DimPeriod[] = MONTH_LABELS.map((label, i) => ({
  period: `p${i}`,
  label,
  year: i < 4 ? 2025 : 2026,
  monthNumber: i + 1,
}));

export const currentPeriod = dimPeriods[dimPeriods.length - 1].period;

export interface FactReconciliation {
  partner: string;
  field: string;
  period: string;
  allocatedBbl: number;
  liftedBbl: number;
  cashCallStatus: CashCallStatus;
}

// Current-period allocation/lifting/cash-call records, one per partner x field
// they hold interest in.
export const factReconciliationCurrent: FactReconciliation[] = [
  { partner: "Operator (JV Lead)", field: "Adaeze Field", period: currentPeriod, allocatedBbl: 412_000, liftedBbl: 405_600, cashCallStatus: "settled" },
  { partner: "State NOC Partner", field: "Adaeze Field", period: currentPeriod, allocatedBbl: 356_000, liftedBbl: 356_000, cashCallStatus: "settled" },
  { partner: "IOC Partner A", field: "Okoro Swamp Block", period: currentPeriod, allocatedBbl: 198_000, liftedBbl: 181_400, cashCallStatus: "pending" },
  { partner: "IOC Partner B", field: "Okoro Swamp Block", period: currentPeriod, allocatedBbl: 176_000, liftedBbl: 176_000, cashCallStatus: "settled" },
  { partner: "State NOC Partner", field: "Ibeno Terminal Block", period: currentPeriod, allocatedBbl: 289_000, liftedBbl: 254_300, cashCallStatus: "disputed" },
  { partner: "Operator (JV Lead)", field: "Ibeno Terminal Block", period: currentPeriod, allocatedBbl: 331_000, liftedBbl: 329_100, cashCallStatus: "settled" },
  { partner: "IOC Partner A", field: "Sango Field", period: currentPeriod, allocatedBbl: 142_000, liftedBbl: 129_800, cashCallStatus: "pending" },
  { partner: "State NOC Partner", field: "Sango Field", period: currentPeriod, allocatedBbl: 205_000, liftedBbl: 205_000, cashCallStatus: "settled" },
];

export const monthlyNetVariancePct: { label: string; variancePct: number }[] = [
  { label: "Sep", variancePct: -2.1 },
  { label: "Oct", variancePct: -1.4 },
  { label: "Nov", variancePct: -3.8 },
  { label: "Dec", variancePct: -1.9 },
  { label: "Jan", variancePct: -0.9 },
  { label: "Feb", variancePct: -4.6 },
  { label: "Mar", variancePct: -2.7 },
  { label: "Apr", variancePct: -1.1 },
  { label: "May", variancePct: -3.2 },
  { label: "Jun", variancePct: -2.4 },
  { label: "Jul", variancePct: -5.1 },
  { label: "Aug", variancePct: -3.6 },
];

export interface FactProduction {
  field: string;
  period: string;
  actualBopd: number;
  forecastBopd: number;
  wellsOnline: number;
  wellsTotal: number;
  uptimePct: number;
  opsStatus: OpsStatus;
}

export const factProductionCurrent: FactProduction[] = [
  { field: "Adaeze Field", period: currentPeriod, actualBopd: 38_400, forecastBopd: 41_000, wellsOnline: 11, wellsTotal: 12, uptimePct: 94.2, opsStatus: "normal" },
  { field: "Okoro Swamp Block", period: currentPeriod, actualBopd: 19_800, forecastBopd: 23_500, wellsOnline: 7, wellsTotal: 9, uptimePct: 81.6, opsStatus: "watch" },
  { field: "Ibeno Terminal Block", period: currentPeriod, actualBopd: 27_100, forecastBopd: 27_800, wellsOnline: 9, wellsTotal: 9, uptimePct: 96.8, opsStatus: "normal" },
  { field: "Sango Field", period: currentPeriod, actualBopd: 11_200, forecastBopd: 18_000, wellsOnline: 4, wellsTotal: 8, uptimePct: 58.3, opsStatus: "down" },
];

export const monthlyFleetUptimePct: { label: string; uptimePct: number }[] = [
  { label: "Sep", uptimePct: 91.2 },
  { label: "Oct", uptimePct: 90.4 },
  { label: "Nov", uptimePct: 88.9 },
  { label: "Dec", uptimePct: 89.6 },
  { label: "Jan", uptimePct: 92.1 },
  { label: "Feb", uptimePct: 87.3 },
  { label: "Mar", uptimePct: 90.8 },
  { label: "Apr", uptimePct: 91.5 },
  { label: "May", uptimePct: 86.4 },
  { label: "Jun", uptimePct: 88.7 },
  { label: "Jul", uptimePct: 84.1 },
  { label: "Aug", uptimePct: 82.7 },
];

export interface FactHseIncident {
  period: string;
  recordableIncidentCount: number;
  hoursWorkedYtd: number;
}

// Monthly exposure hours (not cumulative) - roughly steady, dipping slightly
// when Sango Field went down (see production.ts-equivalent narrative).
const MONTHLY_HOURS_WORKED = [410_000, 415_000, 415_000, 415_000, 205_000, 210_000, 205_000, 210_000, 215_000, 205_000, 210_000, 210_000];

// Trailing-12-month rolling view - hoursWorkedTrailing12mo is a running
// cumulative across the whole displayed window (Sep -> Aug), NOT a
// calendar-year YTD that resets in January. TRIR must be computed from
// incidents and hours over the *same* window, so both series need to cover
// the same span without a reset partway through - a resetting "YTD" here
// would silently understate hours (and overstate TRIR) for the back half
// of the window.
export const monthlyHseIncidents: { label: string; recordableIncidentCount: number; hoursWorkedTrailing12mo: number }[] = (() => {
  const labels = ["Sep", "Oct", "Nov", "Dec", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"];
  const incidents = [1, 0, 2, 1, 0, 1, 0, 1, 3, 1, 0, 2];
  let running = 0;
  return labels.map((label, i) => {
    running += MONTHLY_HOURS_WORKED[i];
    return { label, recordableIncidentCount: incidents[i], hoursWorkedTrailing12mo: running };
  });
})();

// --- Derived / joined views (mirroring what a BI semantic model would surface) ---

const partnerByName = new Map(dimPartners.map((p) => [p.partner, p]));
const fieldByName = new Map(dimFields.map((f) => [f.field, f]));

export interface ReconciliationRow extends FactReconciliation {
  partnerRole: PartnerRole;
  varianceBbl: number;
  variancePct: number;
}

export function reconciliationRows(): ReconciliationRow[] {
  return factReconciliationCurrent.map((r) => ({
    ...r,
    partnerRole: partnerByName.get(r.partner)?.partnerRole ?? "Non-operating",
    varianceBbl: r.liftedBbl - r.allocatedBbl,
    variancePct: ((r.liftedBbl - r.allocatedBbl) / r.allocatedBbl) * 100,
  }));
}

export function kpis() {
  const rows = factReconciliationCurrent;
  const totalAllocated = rows.reduce((s, r) => s + r.allocatedBbl, 0);
  const totalLifted = rows.reduce((s, r) => s + r.liftedBbl, 0);
  const netVarianceBbl = totalLifted - totalAllocated;
  const netVariancePct = (netVarianceBbl / totalAllocated) * 100;
  const openCashCalls = rows.filter((r) => r.cashCallStatus !== "settled").length;
  return { totalAllocated, totalLifted, netVarianceBbl, netVariancePct, openCashCalls };
}

export function varianceStatus(allocated: number, lifted: number): "good" | "warning" | "critical" {
  const pct = Math.abs(((lifted - allocated) / allocated) * 100);
  if (pct <= 2) return "good";
  if (pct <= 6) return "warning";
  return "critical";
}

export function fieldSummary() {
  const byField = new Map<string, { allocatedBbl: number; liftedBbl: number }>();
  for (const row of factReconciliationCurrent) {
    const cur = byField.get(row.field) ?? { allocatedBbl: 0, liftedBbl: 0 };
    cur.allocatedBbl += row.allocatedBbl;
    cur.liftedBbl += row.liftedBbl;
    byField.set(row.field, cur);
  }
  return Array.from(byField.entries()).map(([field, v]) => ({ field, ...v }));
}

export interface ProductionRow extends FactProduction {
  exportPoint: string;
  forecastVariancePct: number;
}

export function productionRows(): ProductionRow[] {
  return factProductionCurrent.map((p) => ({
    ...p,
    exportPoint: fieldByName.get(p.field)?.exportPoint ?? "Unknown",
    forecastVariancePct: ((p.actualBopd - p.forecastBopd) / p.forecastBopd) * 100,
  }));
}

export function productionKpis() {
  const rows = factProductionCurrent;
  const totalActualBopd = rows.reduce((s, r) => s + r.actualBopd, 0);
  const totalForecastBopd = rows.reduce((s, r) => s + r.forecastBopd, 0);
  const totalWellsOnline = rows.reduce((s, r) => s + r.wellsOnline, 0);
  const totalWellsTotal = rows.reduce((s, r) => s + r.wellsTotal, 0);
  const fleetUptimePct = (totalWellsOnline / totalWellsTotal) * 100;
  const downCount = rows.filter((r) => r.opsStatus === "down").length;
  return { totalActualBopd, totalForecastBopd, fleetUptimePct, downCount };
}

export function opsStatusTone(status: OpsStatus): "good" | "warning" | "critical" {
  if (status === "normal") return "good";
  if (status === "watch") return "warning";
  return "critical";
}

export function hseKpis() {
  const last = monthlyHseIncidents[monthlyHseIncidents.length - 1];
  const trailing12moIncidents = monthlyHseIncidents.reduce((s, m) => s + m.recordableIncidentCount, 0);
  // Both incidents and hours cover the same trailing-12-month window, so
  // this ratio is internally consistent (see note on hoursWorkedTrailing12mo).
  const trir = (trailing12moIncidents / last.hoursWorkedTrailing12mo) * 200_000;
  const lastMonthIncidents = last.recordableIncidentCount;
  return { trir, trailing12moIncidents, lastMonthIncidents, hoursWorkedTrailing12mo: last.hoursWorkedTrailing12mo };
}
