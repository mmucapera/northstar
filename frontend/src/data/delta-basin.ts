// Delta Basin pilot dataset - types, a data-agnostic query factory, and a
// deterministic mock generator (used as fallback / local dev without a live
// Fabric connection). Real data comes from gold.* via src/server/fabric-data.ts,
// reshaped into the exact same RawDeltaBasin shape this file expects - every
// derived calculation below (variance flags, TRIR, cash-call trails, etc.)
// works identically either way.

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const DATA_GENERATED_AT = "2026-09-05T02:15:00Z";

// ---- types ------------------------------------------------------------------

export type Partner = {
  id: string;
  name: string;
  role: "Operator" | "Non-operating partner" | "State participant";
  equityPct: number;
};

export type Field = {
  id: string;
  name: string;
  exportPoint: string;
  wellsTotal: number;
};

export type Period = { id: string; label: string; year: number; month: number; quarter: number };

export type VarianceFlag = "within-tolerance" | "watch" | "investigate";
export type CashCallStatus = "settled" | "pending" | "disputed";

/** Variance tolerance bands, shown in the UI so a flag explains itself. */
export const VARIANCE_TOLERANCE = { watchPct: 1.5, investigatePct: 3 };

export function flagForVariance(variancePct: number): VarianceFlag {
  const abs = Math.abs(variancePct);
  if (abs >= VARIANCE_TOLERANCE.investigatePct) return "investigate";
  if (abs >= VARIANCE_TOLERANCE.watchPct) return "watch";
  return "within-tolerance";
}

export type ReconciliationRow = {
  periodId: string;
  partnerId: string;
  fieldId: string;
  allocatedBbl: number;
  liftedBbl: number;
  varianceBbl: number;
  variancePct: number;
  flag: VarianceFlag;
  cashCallStatus: CashCallStatus;
  cashCallUsd: number;
};

export type ProductionStatus = "normal" | "watch" | "down";

export type ProductionRow = {
  periodId: string;
  fieldId: string;
  actualBopd: number;
  forecastBopd: number;
  wellsOnline: number;
  wellsTotal: number;
  uptimePct: number;
  status: ProductionStatus;
};

export type DowntimeBreakdown = { cause: string; hours: number };

export type IncidentSeverity = "First aid" | "Medical treatment" | "Restricted work" | "Lost time";

export const incidentSeverities: IncidentSeverity[] = [
  "First aid",
  "Medical treatment",
  "Restricted work",
  "Lost time",
];

export type HseMonth = {
  periodId: string;
  recordableIncidents: number;
  hoursWorked: number;
};

export type Incident = {
  id: string;
  periodId: string;
  date: string;
  fieldId: string;
  severity: IncidentSeverity;
  recordable: boolean;
  description: string;
};

export type CashCallStage = "submitted" | "under-review" | "settled" | "disputed";

export type CashCallEvent = {
  stage: CashCallStage;
  timestamp: string;
  note?: string;
};

export type CashCall = {
  id: string;
  periodId: string;
  partnerId: string;
  fieldId: string;
  amountUsd: number;
  status: CashCallStatus;
  events: CashCallEvent[];
};

/** Raw shape any data source (mock generator or a real Fabric fetch) must
 * produce - one entry per gold.* table, unshaped/un-derived. */
export type RawDeltaBasin = {
  partners: Partner[];
  fields: Field[];
  periods: Period[];
  downtimeCauses: { id: string; name: string }[];
  reconciliation: ReconciliationRow[];
  production: ProductionRow[];
  downtime: { periodId: string; causeId: string; hours: number }[];
  hseExposure: { periodId: string; hoursWorked: number }[];
  incidents: Incident[];
  cashCallEvents: {
    periodId: string;
    partnerId: string;
    fieldId: string;
    stage: CashCallStage;
    timestamp: string;
    note: string;
  }[];
};

// ---- query factory ------------------------------------------------------------
// Every derived calculation the app needs, closed over one raw dataset. Called
// once with mock data (module load) and once with live data (per-request, in
// DeltaBasinProvider) - identical logic either way.

export function createDeltaBasin(raw: RawDeltaBasin) {
  const { partners, fields, periods, downtimeCauses: downtimeCauseRows } = raw;
  const { reconciliation, production, downtime, hseExposure, incidents, cashCallEvents } = raw;

  const currentPeriodId = periods[periods.length - 1]?.id ?? "";
  const downtimeCauses = downtimeCauseRows.map((c) => c.name);

  const partnerById = (id: string) => partners.find((p) => p.id === id)!;
  const fieldById = (id: string) => fields.find((f) => f.id === id)!;
  const periodLabel = (id: string) => periods.find((p) => p.id === id)?.label ?? id;
  const causeNameById = (id: string) => downtimeCauseRows.find((c) => c.id === id)?.name ?? id;

  function reconciliationForPeriod(periodId: string) {
    return reconciliation.filter((r) => r.periodId === periodId);
  }

  function reconciliationByPartner(periodId: string) {
    return partners.map((partner) => {
      const rows = reconciliationForPeriod(periodId).filter((r) => r.partnerId === partner.id);
      const allocatedBbl = rows.reduce((s, r) => s + r.allocatedBbl, 0);
      const liftedBbl = rows.reduce((s, r) => s + r.liftedBbl, 0);
      const varianceBbl = liftedBbl - allocatedBbl;
      const variancePct = allocatedBbl === 0 ? 0 : (varianceBbl / allocatedBbl) * 100;
      const disputed = rows.filter((r) => r.cashCallStatus === "disputed").length;
      const pending = rows.filter((r) => r.cashCallStatus === "pending").length;
      return {
        partner,
        rows,
        allocatedBbl,
        liftedBbl,
        varianceBbl,
        variancePct,
        flag: flagForVariance(variancePct),
        cashCallStatus: (disputed > 0 ? "disputed" : pending > 0 ? "pending" : "settled") as CashCallStatus,
        cashCallUsd: rows.reduce((s, r) => s + r.cashCallUsd, 0),
      };
    });
  }

  function netVarianceTrend() {
    return periods.map((p) => {
      const rows = reconciliationForPeriod(p.id);
      const allocated = rows.reduce((s, r) => s + r.allocatedBbl, 0);
      const lifted = rows.reduce((s, r) => s + r.liftedBbl, 0);
      return {
        period: p.label,
        variancePct: Number((allocated === 0 ? 0 : ((lifted - allocated) / allocated) * 100).toFixed(2)),
        varianceBbl: lifted - allocated,
      };
    });
  }

  function partnerVarianceHistory(partnerId: string) {
    return periods.map((p) => {
      const rows = reconciliation.filter((r) => r.periodId === p.id && r.partnerId === partnerId);
      const allocated = rows.reduce((s, r) => s + r.allocatedBbl, 0);
      const lifted = rows.reduce((s, r) => s + r.liftedBbl, 0);
      return {
        period: p.label,
        allocated,
        lifted,
        variancePct: Number((allocated === 0 ? 0 : ((lifted - allocated) / allocated) * 100).toFixed(2)),
      };
    });
  }

  function productionForPeriod(periodId: string) {
    return production.filter((r) => r.periodId === periodId);
  }

  function uptimeTrend() {
    return periods.map((p) => {
      const rows = productionForPeriod(p.id);
      const online = rows.reduce((s, r) => s + r.wellsOnline, 0);
      const total = rows.reduce((s, r) => s + r.wellsTotal, 0);
      return {
        period: p.label,
        uptimePct: Number((total === 0 ? 0 : (online / total) * 100).toFixed(1)),
        actual: rows.reduce((s, r) => s + r.actualBopd, 0),
        forecast: rows.reduce((s, r) => s + r.forecastBopd, 0),
      };
    });
  }

  function downtimeForPeriod(periodId: string): DowntimeBreakdown[] {
    const rows = downtime.filter((d) => d.periodId === periodId);
    return downtimeCauseRows.map((c) => ({
      cause: c.name,
      hours: rows.filter((d) => d.causeId === c.id).reduce((s, d) => s + d.hours, 0),
    }));
  }

  function downtimeTrend() {
    return periods.map((p) => {
      const row: Record<string, string | number> = { period: p.label, periodId: p.id };
      let total = 0;
      downtimeForPeriod(p.id).forEach((d) => {
        row[d.cause] = d.hours;
        total += d.hours;
      });
      row["total"] = total;
      return row;
    });
  }

  function downtimeCauseDirection() {
    const trend = downtimeTrend();
    const half = Math.floor(trend.length / 2);
    return downtimeCauses.map((cause) => {
      const early = half === 0 ? 0 : trend.slice(0, half).reduce((s, r) => s + Number(r[cause] ?? 0), 0) / half;
      const lateCount = trend.length - half;
      const late = lateCount === 0 ? 0 : trend.slice(half).reduce((s, r) => s + Number(r[cause] ?? 0), 0) / lateCount;
      const changePct = early === 0 ? 0 : ((late - early) / early) * 100;
      return {
        cause,
        earlyAvgHours: Math.round(early),
        lateAvgHours: Math.round(late),
        changePct,
        direction: (changePct > 5 ? "worsening" : changePct < -5 ? "improving" : "stable") as
          | "worsening"
          | "improving"
          | "stable",
      };
    });
  }

  const hseMonths: HseMonth[] = periods.map((p) => ({
    periodId: p.id,
    recordableIncidents: incidents.filter((i) => i.periodId === p.id && i.recordable).length,
    hoursWorked: hseExposure.find((e) => e.periodId === p.id)?.hoursWorked ?? 0,
  }));

  /** TRIR = recordable incidents per 200,000 exposure hours, trailing 12 months up to periodId. */
  function trirTrailing12(periodId: string): number {
    const end = periods.findIndex((p) => p.id === periodId);
    const window = hseMonths.slice(Math.max(0, end - 11), end + 1);
    const rec = window.reduce((s, m) => s + m.recordableIncidents, 0);
    const hours = window.reduce((s, m) => s + m.hoursWorked, 0);
    return hours === 0 ? 0 : (rec * 200_000) / hours;
  }

  function hseTrend() {
    let cumulative = 0;
    return hseMonths.map((m) => {
      cumulative += m.hoursWorked;
      return {
        period: periodLabel(m.periodId),
        incidents: m.recordableIncidents,
        hoursWorked: m.hoursWorked,
        cumulativeHours: cumulative,
        trir: Number(trirTrailing12(m.periodId).toFixed(2)),
      };
    });
  }

  function incidentSeverityTrend() {
    return periods.map((p) => {
      const monthIncidents = incidents.filter((i) => i.periodId === p.id);
      const row: Record<string, string | number> = { period: p.label, periodId: p.id };
      incidentSeverities.forEach((sev) => {
        row[sev] = monthIncidents.filter((i) => i.severity === sev).length;
      });
      row["total"] = monthIncidents.length;
      return row;
    });
  }

  function summaryForPeriod(periodId: string) {
    const rec = reconciliationForPeriod(periodId);
    const allocated = rec.reduce((s, r) => s + r.allocatedBbl, 0);
    const lifted = rec.reduce((s, r) => s + r.liftedBbl, 0);
    const prod = productionForPeriod(periodId);
    const actual = prod.reduce((s, r) => s + r.actualBopd, 0);
    const forecast = prod.reduce((s, r) => s + r.forecastBopd, 0);
    const wellsOnline = prod.reduce((s, r) => s + r.wellsOnline, 0);
    const wellsTotal = prod.reduce((s, r) => s + r.wellsTotal, 0);
    const monthIncidents = hseMonths.find((m) => m.periodId === periodId)?.recordableIncidents ?? 0;
    return {
      allocated,
      lifted,
      netVarianceBbl: lifted - allocated,
      netVariancePct: allocated === 0 ? 0 : ((lifted - allocated) / allocated) * 100,
      disputedCount: rec.filter((r) => r.cashCallStatus === "disputed").length,
      pendingCount: rec.filter((r) => r.cashCallStatus === "pending").length,
      actual,
      forecast,
      forecastAttainmentPct: forecast === 0 ? 0 : (actual / forecast) * 100,
      wellsOnline,
      wellsTotal,
      uptimePct: wellsTotal === 0 ? 0 : (wellsOnline / wellsTotal) * 100,
      trir: trirTrailing12(periodId),
      monthIncidents,
    };
  }

  function alertsForPeriod(periodId: string) {
    const alerts: { level: "critical" | "warning"; title: string; detail: string; to: string }[] = [];
    reconciliationByPartner(periodId)
      .filter((p) => p.cashCallStatus === "disputed")
      .forEach((p) =>
        alerts.push({
          level: "critical",
          title: `${p.partner.name} — cash call disputed`,
          detail: `Net variance ${p.variancePct.toFixed(2)}% across ${p.rows.length} field records.`,
          to: "/reconciliation",
        }),
      );
    productionForPeriod(periodId)
      .filter((r) => r.status !== "normal")
      .forEach((r) =>
        alerts.push({
          level: r.status === "down" ? "critical" : "warning",
          title: `${fieldById(r.fieldId).name} — ${r.status === "down" ? "wells down" : "below forecast"}`,
          detail: `${r.wellsTotal - r.wellsOnline} well(s) offline, uptime ${r.uptimePct.toFixed(1)}%.`,
          to: "/production",
        }),
      );
    const monthIncidents = incidents.filter((i) => i.periodId === periodId && i.recordable);
    if (monthIncidents.length > 0) {
      alerts.push({
        level: "warning",
        title: `${monthIncidents.length} recordable incident(s) this period`,
        detail: `Latest: ${monthIncidents[monthIncidents.length - 1]!.description}.`,
        to: "/hse",
      });
    }
    return alerts;
  }

  const cashCallsByRecord = new Map<string, CashCallEvent[]>();
  cashCallEvents.forEach((e) => {
    const key = `${e.periodId}|${e.partnerId}|${e.fieldId}`;
    const list = cashCallsByRecord.get(key) ?? [];
    list.push({ stage: e.stage, timestamp: e.timestamp, note: e.note });
    cashCallsByRecord.set(key, list);
  });

  /** submitted -> under-review -> settled/disputed trail for one reconciliation record. */
  function cashCallTrail(row: ReconciliationRow): CashCall {
    const key = `${row.periodId}|${row.partnerId}|${row.fieldId}`;
    const events = (cashCallsByRecord.get(key) ?? []).slice().sort((a, b) => a.timestamp.localeCompare(b.timestamp));
    return {
      id: `${row.periodId}-${row.partnerId}-${row.fieldId}`,
      periodId: row.periodId,
      partnerId: row.partnerId,
      fieldId: row.fieldId,
      amountUsd: row.cashCallUsd,
      status: row.cashCallStatus,
      events,
    };
  }

  function cashCallsForPartner(partnerId: string, periodId?: string): CashCall[] {
    return reconciliation
      .filter((r) => r.partnerId === partnerId && (periodId ? r.periodId === periodId : true))
      .map(cashCallTrail);
  }

  /** One aggregated settlement row per period for a partner. */
  function partnerSettlementHistory(partnerId: string) {
    return periods
      .map((p) => {
        const rows = reconciliation.filter((r) => r.periodId === p.id && r.partnerId === partnerId);
        const allocatedBbl = rows.reduce((s, r) => s + r.allocatedBbl, 0);
        const liftedBbl = rows.reduce((s, r) => s + r.liftedBbl, 0);
        const cashCallUsd = rows.reduce((s, r) => s + r.cashCallUsd, 0);
        const disputed = rows.filter((r) => r.cashCallStatus === "disputed").length;
        const pending = rows.filter((r) => r.cashCallStatus === "pending").length;
        const settled = rows.filter((r) => r.cashCallStatus === "settled").length;
        return {
          period: p,
          rows,
          allocatedBbl,
          liftedBbl,
          varianceBbl: liftedBbl - allocatedBbl,
          variancePct: allocatedBbl === 0 ? 0 : ((liftedBbl - allocatedBbl) / allocatedBbl) * 100,
          cashCallUsd,
          disputed,
          pending,
          settled,
          status: (disputed > 0 ? "disputed" : pending > 0 ? "pending" : "settled") as CashCallStatus,
        };
      })
      .reverse();
  }

  function partnerProfile(partnerId: string) {
    const partner = partnerById(partnerId);
    const history = partnerSettlementHistory(partnerId);
    const all = reconciliation.filter((r) => r.partnerId === partnerId);
    return {
      partner,
      history,
      disputeCount: all.filter((r) => r.cashCallStatus === "disputed").length,
      pendingCount: all.filter((r) => r.cashCallStatus === "pending").length,
      settledCount: all.filter((r) => r.cashCallStatus === "settled").length,
      lifetimeCashCallUsd: all.reduce((s, r) => s + r.cashCallUsd, 0),
      outstandingUsd: all
        .filter((r) => r.cashCallStatus !== "settled")
        .reduce((s, r) => s + r.cashCallUsd, 0),
    };
  }

  return {
    partners,
    fields,
    periods,
    currentPeriodId,
    downtimeCauses,
    reconciliation,
    production,
    incidents,
    hseMonths,
    partnerById,
    fieldById,
    periodLabel,
    causeNameById,
    reconciliationForPeriod,
    reconciliationByPartner,
    netVarianceTrend,
    partnerVarianceHistory,
    productionForPeriod,
    uptimeTrend,
    downtimeForPeriod,
    downtimeTrend,
    downtimeCauseDirection,
    trirTrailing12,
    hseTrend,
    incidentSeverityTrend,
    summaryForPeriod,
    alertsForPeriod,
    cashCallTrail,
    cashCallsForPartner,
    partnerSettlementHistory,
    partnerProfile,
  };
}

export type DeltaBasin = ReturnType<typeof createDeltaBasin>;

// ---- mock generator (fallback / local dev) -----------------------------------

const downtimeCauseSeed = [
  { id: "facility-maintenance", name: "Facility maintenance" },
  { id: "flowline-integrity", name: "Flowline integrity" },
  { id: "power-generation", name: "Power / generation" },
  { id: "third-party-export-deferral", name: "Third-party export deferral" },
  { id: "unplanned-shut-in", name: "Unplanned shut-in" },
];

const reviewNotes = [
  "Allocation statement matched against terminal lifting log.",
  "Awaiting operator confirmation of export point measurement.",
  "Second-tier review triggered by variance band.",
  "Volumes re-checked after meter proving report.",
];
const disputeNotes = [
  "Partner contests lifted volume at the export terminal.",
  "Variance exceeds tolerance; joint measurement review requested.",
  "Cargo timing dispute across period cut-off.",
];
const settleNotes = [
  "Funds received, statement closed.",
  "Settled net of prior period credit.",
  "Settled in full against the revised statement.",
];

function isoAt(year: number, month: number, day: number, hour: number) {
  return new Date(Date.UTC(year, month - 1, day, hour, 0, 0)).toISOString();
}

export function generateMockRaw(): RawDeltaBasin {
  const partners: Partner[] = [
    { id: "customer0", name: "CUSTOMER0 Upstream", role: "State participant", equityPct: 55 },
    { id: "shoreline", name: "Shoreline E&P", role: "Operator", equityPct: 20 },
    { id: "atlantic", name: "Atlantic Petroleum", role: "Non-operating partner", equityPct: 12.5 },
    { id: "creek", name: "Creek Energy", role: "Non-operating partner", equityPct: 7.5 },
    { id: "meridian", name: "Meridian Resources", role: "Non-operating partner", equityPct: 5 },
  ];

  const fields: Field[] = [
    { id: "obago", name: "Obago", exportPoint: "Bonny", wellsTotal: 42 },
    { id: "ekpo", name: "Ekpo North", exportPoint: "Qua Iboe", wellsTotal: 28 },
    { id: "warri-sw", name: "Warri SW", exportPoint: "Forcados", wellsTotal: 35 },
    { id: "ibeno", name: "Ibeno Deep", exportPoint: "Qua Iboe", wellsTotal: 19 },
    { id: "brass-c", name: "Brass Creek", exportPoint: "Brass", wellsTotal: 24 },
  ];

  // 12 trailing periods ending 2026-08.
  const periods: Period[] = Array.from({ length: 12 }, (_, i) => {
    const monthIndex = 8 - 1 - (11 - i); // 0-based from Sep 2025 -> Aug 2026
    const date = new Date(Date.UTC(2026, monthIndex, 1));
    const year = date.getUTCFullYear();
    const month = date.getUTCMonth() + 1;
    return {
      id: `${year}-${String(month).padStart(2, "0")}`,
      label: date.toLocaleString("en-US", { month: "short", year: "numeric", timeZone: "UTC" }),
      year,
      month,
      quarter: Math.floor((month - 1) / 3) + 1,
    };
  });
  const currentPeriodId = periods[periods.length - 1]!.id;

  const reconciliation: ReconciliationRow[] = [];
  periods.forEach((period, pi) => {
    fields.forEach((field, fi) => {
      partners.forEach((partner, qi) => {
        const rnd = mulberry32(pi * 977 + fi * 131 + qi * 17 + 5);
        const base = (180_000 + fi * 42_000) * (partner.equityPct / 100);
        const seasonal = 1 + Math.sin((pi + fi) / 2.4) * 0.06;
        const allocatedBbl = Math.round(base * seasonal * (0.96 + rnd() * 0.08));
        const drift = (rnd() - 0.45) * 0.062;
        const liftedBbl = Math.round(allocatedBbl * (1 + drift));
        const varianceBbl = liftedBbl - allocatedBbl;
        const variancePct = (varianceBbl / allocatedBbl) * 100;
        const flag = flagForVariance(variancePct);
        const isCurrent = period.id === currentPeriodId;
        const r = rnd();
        const cashCallStatus: CashCallStatus =
          flag === "investigate" && r > 0.35 ? "disputed" : isCurrent && r > 0.55 ? "pending" : "settled";
        reconciliation.push({
          periodId: period.id,
          partnerId: partner.id,
          fieldId: field.id,
          allocatedBbl,
          liftedBbl,
          varianceBbl,
          variancePct,
          flag,
          cashCallStatus,
          cashCallUsd: Math.round(allocatedBbl * 11.4),
        });
      });
    });
  });

  const production: ProductionRow[] = [];
  periods.forEach((period, pi) => {
    // Shared across every field in this period (not just per-field noise)
    // so the gap survives being summed into the aggregate actual-vs-forecast
    // chart, instead of averaging itself away - a slow swing plus a mild
    // late-window decline, standing in for a real "actual trailing forecast
    // as the pilot matures" narrative.
    const periodBias = 1 + Math.sin(pi / 4.2) * 0.07 - Math.max(0, pi - 14) * 0.0045;
    fields.forEach((field, fi) => {
      const rnd = mulberry32(pi * 613 + fi * 89 + 41);
      const forecastBopd = Math.round((34_000 + fi * 8_500) * (1 + Math.sin(pi / 3.1) * 0.04));
      const wellsOffline = Math.floor(rnd() * (fi === 2 && pi > 8 ? 6 : 4));
      const wellsOnline = field.wellsTotal - wellsOffline;
      const uptimePct = Number(((wellsOnline / field.wellsTotal) * (96 + rnd() * 4)).toFixed(1));
      const actualBopd = Math.round(forecastBopd * (uptimePct / 100) * periodBias * (0.98 + rnd() * 0.04));
      const status: ProductionStatus =
        uptimePct < 88 ? "down" : uptimePct < 94 || actualBopd < forecastBopd * 0.93 ? "watch" : "normal";
      production.push({
        periodId: period.id,
        fieldId: field.id,
        actualBopd,
        forecastBopd,
        wellsOnline,
        wellsTotal: field.wellsTotal,
        uptimePct,
        status,
      });
    });
  });

  const downtime: RawDeltaBasin["downtime"] = [];
  periods.forEach((period, pi) => {
    const rnd = mulberry32(pi * 31 + 7);
    downtimeCauseSeed.forEach((cause, i) => {
      downtime.push({
        periodId: period.id,
        causeId: cause.id,
        hours: Math.round(60 + rnd() * (i === 0 ? 340 : 220)),
      });
    });
  });

  const hseExposure: RawDeltaBasin["hseExposure"] = periods.map((period, pi) => {
    const rnd = mulberry32(pi * 271 + 3);
    return { periodId: period.id, hoursWorked: Math.round(410_000 + rnd() * 90_000) };
  });

  const incidentDescriptions = [
    "Dropped object during lifting operation",
    "Hand injury while handling valve assembly",
    "Slip on wet deck near separator skid",
    "Minor hydrocarbon release, contained",
    "Vehicle incident on access road",
    "Heat exhaustion during flowline inspection",
  ];
  const incidents: Incident[] = [];
  periods.forEach((period, pi) => {
    const countRnd = mulberry32(pi * 271 + 3);
    const baseCount = Math.floor(countRnd() * 4);
    const bonusRnd = mulberry32(pi * 503 + 11);
    const count = baseCount + (bonusRnd() > 0.6 ? 1 : 0);
    const rnd = mulberry32(pi * 503 + 11);
    for (let i = 0; i < count; i++) {
      const day = 2 + Math.floor(rnd() * 26);
      const severity = incidentSeverities[Math.floor(rnd() * incidentSeverities.length)]!;
      incidents.push({
        id: `${period.id}-${i}`,
        periodId: period.id,
        date: `${period.year}-${String(period.month).padStart(2, "0")}-${String(day).padStart(2, "0")}`,
        fieldId: fields[Math.floor(rnd() * fields.length)]!.id,
        severity,
        recordable: severity !== "First aid",
        description: incidentDescriptions[Math.floor(rnd() * incidentDescriptions.length)]!,
      });
    }
  });

  const cashCallEvents: RawDeltaBasin["cashCallEvents"] = [];
  reconciliation.forEach((row) => {
    const period = periods.find((p) => p.id === row.periodId)!;
    const pi = periods.indexOf(period);
    const fi = fields.findIndex((f) => f.id === row.fieldId);
    const qi = partners.findIndex((p) => p.id === row.partnerId);
    const rnd = mulberry32(pi * 733 + fi * 97 + qi * 29 + 13);

    const nextMonth = new Date(Date.UTC(period.year, period.month, 1));
    const y = nextMonth.getUTCFullYear();
    const m = nextMonth.getUTCMonth() + 1;
    const submittedDay = 2 + Math.floor(rnd() * 4);
    const reviewDay = submittedDay + 1 + Math.floor(rnd() * 4);
    const closeDay = reviewDay + 2 + Math.floor(rnd() * 8);

    cashCallEvents.push({
      periodId: row.periodId,
      partnerId: row.partnerId,
      fieldId: row.fieldId,
      stage: "submitted",
      timestamp: isoAt(y, m, submittedDay, 9),
      note: `Cash call raised for ${period.label} on ${fields.find((f) => f.id === row.fieldId)!.name}.`,
    });
    cashCallEvents.push({
      periodId: row.periodId,
      partnerId: row.partnerId,
      fieldId: row.fieldId,
      stage: "under-review",
      timestamp: isoAt(y, m, reviewDay, 11),
      note: reviewNotes[Math.floor(rnd() * reviewNotes.length)]!,
    });
    if (row.cashCallStatus === "disputed") {
      cashCallEvents.push({
        periodId: row.periodId,
        partnerId: row.partnerId,
        fieldId: row.fieldId,
        stage: "disputed",
        timestamp: isoAt(y, m, closeDay, 15),
        note: disputeNotes[Math.floor(rnd() * disputeNotes.length)]!,
      });
    } else if (row.cashCallStatus === "settled") {
      cashCallEvents.push({
        periodId: row.periodId,
        partnerId: row.partnerId,
        fieldId: row.fieldId,
        stage: "settled",
        timestamp: isoAt(y, m, closeDay, 14),
        note: settleNotes[Math.floor(rnd() * settleNotes.length)]!,
      });
    }
  });

  return {
    partners,
    fields,
    periods,
    downtimeCauses: downtimeCauseSeed,
    reconciliation,
    production,
    downtime,
    hseExposure,
    incidents,
    cashCallEvents,
  };
}

export const mockDeltaBasin = createDeltaBasin(generateMockRaw());

// ---- pure formatting helpers (no data dependency) ----------------------------

export function formatNumber(n: number, digits = 0) {
  return n.toLocaleString("en-US", { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

/** Compact axis-tick formatting - 12,000,000 -> "12M", 12,000 -> "12k",
 * instead of a fixed /1000 divisor that reads "12000k" once values cross
 * into the millions. */
export function formatCompactNumber(n: number) {
  const abs = Math.abs(n);
  if (abs >= 1_000_000) return `${(n / 1_000_000).toLocaleString("en-US", { maximumFractionDigits: 1 })}M`;
  if (abs >= 1_000) return `${(n / 1_000).toLocaleString("en-US", { maximumFractionDigits: 1 })}k`;
  return String(n);
}

export function toCsv(headers: string[], rows: (string | number)[][]) {
  const esc = (v: string | number) => {
    const s = String(v);
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
  };
  return [headers.map(esc).join(","), ...rows.map((r) => r.map(esc).join(","))].join("\n");
}

/** Canonical USD formatting: cents below $1,000, whole dollars above. */
export function formatUsd(n: number) {
  const digits = Math.abs(n) < 1000 ? 2 : 0;
  return n.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

/** e.g. "1,240,500 bbl" */
export const formatBbl = (n: number) => `${formatNumber(Math.round(n))} bbl`;
/** e.g. "184,200 bopd" */
export const formatBopd = (n: number) => `${formatNumber(Math.round(n))} bopd`;
/** e.g. "94.2%" — two decimals for variance, one for rates. */
export const formatPct = (n: number, digits = 1) => `${formatNumber(n, digits)}%`;
/** e.g. "+1.24%" / "-0.80%" */
export const formatSignedPct = (n: number, digits = 2) =>
  `${n >= 0 ? "+" : "-"}${formatNumber(Math.abs(n), digits)}%`;
/** e.g. "+12,400" / "-3,100" */
export const formatSigned = (n: number, digits = 0) =>
  `${n >= 0 ? "+" : "-"}${formatNumber(Math.abs(n), digits)}`;
/** e.g. "12,400 hrs" */
export const formatHours = (n: number, digits = 0) => `${formatNumber(n, digits)} hrs`;
