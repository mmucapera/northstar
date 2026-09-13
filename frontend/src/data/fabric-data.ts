// Server-only: fetches gold.* from the Fabric lakehouse's SQL analytics
// endpoint and reshapes it into the RawDeltaBasin shape delta-basin.ts's
// query factory expects. Never bundled to the client - createServerFn's
// handler body is compiled into a server-only chunk, and the mssql/
// @azure-identity imports live only inside this file.

import { createServerFn } from "@tanstack/react-start";
import type {
  CashCallStage,
  CashCallStatus,
  IncidentSeverity,
  ProductionStatus,
  RawDeltaBasin,
  VarianceFlag,
} from "@/data/delta-basin";

async function fetchGoldData(): Promise<RawDeltaBasin> {
  const server = process.env["FABRIC_SQL_ENDPOINT"];
  const database = process.env["FABRIC_DATABASE_ID"];
  if (!server || !database) {
    throw new Error("FABRIC_SQL_ENDPOINT / FABRIC_DATABASE_ID not configured");
  }

  const [{ default: sql }, { DefaultAzureCredential }] = await Promise.all([
    import("mssql"),
    import("@azure/identity"),
  ]);

  const credential = new DefaultAzureCredential();
  const tokenResponse = await credential.getToken("https://database.windows.net/.default");
  if (!tokenResponse) throw new Error("Failed to acquire an Azure AD token for the SQL endpoint");

  const pool = await sql.connect({
    server,
    database,
    authentication: {
      type: "azure-active-directory-access-token",
      options: { token: tokenResponse.token },
    },
    options: { encrypt: true },
  });

  try {
    const [
      partnersRes,
      fieldsRes,
      periodsRes,
      causesRes,
      reconRes,
      prodRes,
      downtimeRes,
      exposureRes,
      incidentsRes,
      cashCallRes,
    ] = await Promise.all([
      pool.request().query("SELECT PartnerId, PartnerName, PartnerRole, EquityPct FROM gold.dim_partner"),
      pool.request().query("SELECT FieldId, FieldName, ExportPoint, WellsTotal FROM gold.dim_field"),
      pool
        .request()
        .query("SELECT PeriodId, Label, Year, MonthNumber, Quarter FROM gold.dim_period ORDER BY PeriodId"),
      pool.request().query("SELECT CauseId, CauseName FROM gold.dim_downtime_cause"),
      // gold.fact_* tables carry only the integer surrogate keys (PartnerId_key
      // etc, hash of the natural key - see gold/fact_reconciliation.yaml and
      // dim_partner.yaml) rather than the dims' text values, so the natural
      // string keys this app displays/routes on come back via a join here.
      pool
        .request()
        .query(
          `SELECT p.PeriodId, f.FieldId, pt.PartnerId, r.AllocatedBbl, r.LiftedBbl, r.VarianceBbl, r.VariancePct, r.Flag, r.CashCallStatus, r.CashCallUsd
           FROM gold.fact_reconciliation r
           JOIN gold.dim_period p ON r.PeriodId_key = p.PeriodId_key
           JOIN gold.dim_field f ON r.FieldId_key = f.FieldId_key
           JOIN gold.dim_partner pt ON r.PartnerId_key = pt.PartnerId_key`,
        ),
      pool
        .request()
        .query(
          `SELECT p.PeriodId, f.FieldId, pr.ActualBopd, pr.ForecastBopd, pr.WellsOnline, pr.UptimePct, pr.OpsStatus
           FROM gold.fact_production pr
           JOIN gold.dim_period p ON pr.PeriodId_key = p.PeriodId_key
           JOIN gold.dim_field f ON pr.FieldId_key = f.FieldId_key`,
        ),
      pool
        .request()
        .query(
          `SELECT p.PeriodId, c.CauseId, d.Hours
           FROM gold.fact_downtime d
           JOIN gold.dim_period p ON d.PeriodId_key = p.PeriodId_key
           JOIN gold.dim_downtime_cause c ON d.CauseId_key = c.CauseId_key`,
        ),
      pool
        .request()
        .query(
          `SELECT p.PeriodId, e.HoursWorked
           FROM gold.fact_hse_exposure e
           JOIN gold.dim_period p ON e.PeriodId_key = p.PeriodId_key`,
        ),
      pool
        .request()
        .query(
          `SELECT i.IncidentId, p.PeriodId, i.IncidentDate, f.FieldId, i.Severity, i.Recordable, i.Description
           FROM gold.fact_hse_incidents i
           JOIN gold.dim_period p ON i.PeriodId_key = p.PeriodId_key
           JOIN gold.dim_field f ON i.FieldId_key = f.FieldId_key`,
        ),
      pool
        .request()
        .query(
          `SELECT p.PeriodId, pt.PartnerId, f.FieldId, cc.Stage, cc.EventTimestamp, cc.Note
           FROM gold.fact_cash_call_event cc
           JOIN gold.dim_period p ON cc.PeriodId_key = p.PeriodId_key
           JOIN gold.dim_partner pt ON cc.PartnerId_key = pt.PartnerId_key
           JOIN gold.dim_field f ON cc.FieldId_key = f.FieldId_key`,
        ),
    ]);

    const fieldsById = new Map<string, number>();
    fieldsRes.recordset.forEach((f: any) => fieldsById.set(f.FieldId, f.WellsTotal));

    console.log(
      "[fabric-data] fetched:",
      "partners", partnersRes.recordset.length,
      "fields", fieldsRes.recordset.length,
      "periods", periodsRes.recordset.length,
      "reconciliation", reconRes.recordset.length,
    );

    return {
      partners: partnersRes.recordset.map((p: any) => ({
        id: p.PartnerId,
        name: p.PartnerName,
        role: p.PartnerRole,
        equityPct: Number(p.EquityPct),
      })),
      fields: fieldsRes.recordset.map((f: any) => ({
        id: f.FieldId,
        name: f.FieldName,
        exportPoint: f.ExportPoint,
        wellsTotal: f.WellsTotal,
      })),
      periods: periodsRes.recordset.map((p: any) => ({
        id: p.PeriodId,
        label: p.Label,
        year: p.Year,
        month: p.MonthNumber,
        quarter: p.Quarter,
      })),
      downtimeCauses: causesRes.recordset.map((c: any) => ({ id: c.CauseId, name: c.CauseName })),
      reconciliation: reconRes.recordset.map((r: any) => ({
        periodId: r.PeriodId,
        partnerId: r.PartnerId,
        fieldId: r.FieldId,
        allocatedBbl: Number(r.AllocatedBbl),
        liftedBbl: Number(r.LiftedBbl),
        varianceBbl: Number(r.VarianceBbl),
        variancePct: Number(r.VariancePct),
        flag: r.Flag as VarianceFlag,
        cashCallStatus: r.CashCallStatus as CashCallStatus,
        cashCallUsd: Number(r.CashCallUsd),
      })),
      production: prodRes.recordset.map((r: any) => ({
        periodId: r.PeriodId,
        fieldId: r.FieldId,
        actualBopd: Number(r.ActualBopd),
        forecastBopd: Number(r.ForecastBopd),
        wellsOnline: r.WellsOnline,
        wellsTotal: fieldsById.get(r.FieldId) ?? r.WellsOnline,
        uptimePct: Number(r.UptimePct),
        status: r.OpsStatus as ProductionStatus,
      })),
      downtime: downtimeRes.recordset.map((r: any) => ({
        periodId: r.PeriodId,
        causeId: r.CauseId,
        hours: Number(r.Hours),
      })),
      hseExposure: exposureRes.recordset.map((r: any) => ({
        periodId: r.PeriodId,
        hoursWorked: Number(r.HoursWorked),
      })),
      incidents: incidentsRes.recordset.map((r: any) => ({
        id: r.IncidentId,
        periodId: r.PeriodId,
        date: new Date(r.IncidentDate).toISOString().slice(0, 10),
        fieldId: r.FieldId,
        severity: r.Severity as IncidentSeverity,
        recordable: Boolean(r.Recordable),
        description: r.Description,
      })),
      cashCallEvents: cashCallRes.recordset.map((r: any) => ({
        periodId: r.PeriodId,
        partnerId: r.PartnerId,
        fieldId: r.FieldId,
        stage: r.Stage as CashCallStage,
        timestamp: new Date(r.EventTimestamp).toISOString(),
        note: r.Note ?? "",
      })),
    };
  } finally {
    await pool.close();
  }
}

// gold.* changes at most once a day (see the dummy-data pipeline) - opening a
// fresh SQL connection on every single page load is wasteful and adds
// avoidable exposure to connection timeouts. Cache the fetched result
// in-process for a few minutes instead of hitting the SQL endpoint every time.
const CACHE_TTL_MS = 5 * 60 * 1000;
let cache: { data: RawDeltaBasin; expiresAt: number } | null = null;
let inFlight: Promise<RawDeltaBasin> | null = null;

async function fetchGoldDataCached(): Promise<RawDeltaBasin> {
  const now = Date.now();
  if (cache && cache.expiresAt > now) return cache.data;
  if (inFlight) return inFlight; // dedupe concurrent requests during a cold cache
  inFlight = fetchGoldData()
    .then((data) => {
      cache = { data, expiresAt: Date.now() + CACHE_TTL_MS };
      return data;
    })
    .finally(() => {
      inFlight = null;
    });
  return inFlight;
}

/** Callable from client or server code - actually executes only on the
 * server (TanStack Start server function). Falls back to null on any
 * failure so the caller can fall back to mock data rather than crash. */
export const getDeltaBasinData = createServerFn({ method: "GET" }).handler(
  async (): Promise<RawDeltaBasin | null> => {
    try {
      return await fetchGoldDataCached();
    } catch (err) {
      console.error("[fabric-data] live fetch failed, caller should fall back to mock data:", err);
      return null;
    }
  },
);
