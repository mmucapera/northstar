// Well/wellbore/completion/facility subsurface data - correlated to the same
// fields as src/data/delta-basin.ts (obago, ekpo, warri-sw, ibeno, brass-c),
// mirroring the field/production dataset's deterministic-mock pattern.
// Naming matches the real gold-layer columns (gold/dim_well.yaml,
// gold/dim_wellbore.yaml, gold/dim_completion.yaml, gold/fact_production_volume.yaml,
// gold/fact_well_test.yaml, gold/fact_drilling_telemetry.yaml) translated to
// TS camelCase, not Project Spark's mock naming.

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function stableRand(seedStr: string, low = 0, high = 1) {
  let h = 0;
  for (let i = 0; i < seedStr.length; i++) {
    h = (Math.imul(31, h) + seedStr.charCodeAt(i)) | 0;
  }
  const r = mulberry32(h)();
  return low + r * (high - low);
}

const pick = <T,>(arr: readonly T[], r: number) => arr[Math.floor(r * arr.length) % arr.length]!;

export type WellType = "Oil producer" | "Gas producer" | "Water injector" | "Gas injector";
export type WellStatus = "Producing" | "Shut-in" | "Drilling" | "Suspended";

export type Well = {
  wellId: string;
  wellName: string;
  fieldId: string;
  facilityId: string;
  partnerId: string;
  wellType: WellType;
  status: WellStatus;
  spudDate: string;
  totalDepthM: number;
};

export type Wellbore = {
  wellboreId: string;
  wellId: string;
  wellboreName: string;
  trajectory: "Vertical" | "Deviated" | "Horizontal";
  isSidetrack: boolean;
  measuredDepthM: number;
  trueVerticalDepthM: number;
};

export type Completion = {
  completionId: string;
  wellboreId: string;
  wellId: string;
  completionType: "Single string" | "Dual string" | "Gas lift" | "ESP" | "Natural flow";
  reservoirUnit: string;
  perforationTopM: number;
  perforationBaseM: number;
  artificialLift: string;
  completionDate: string;
  isActive: boolean;
};

export type Facility = {
  facilityId: string;
  facilityName: string;
  facilityType: "Export terminal" | "Flowstation" | "Gas plant";
  fieldId: string | null;
  exportPoint: string;
  capacityBopd: number;
};

export type ProductionVolumeRow = {
  periodId: string;
  wellId: string;
  fieldId: string;
  facilityId: string;
  oilBbl: number;
  gasMscf: number;
  waterBbl: number;
  onstreamHours: number;
  waterCutPct: number;
};

export type DrillingTelemetryRow = {
  wellId: string;
  wellboreId: string;
  reportDate: string;
  depthM: number;
  ropMPerHr: number;
  wobKlbs: number;
  rpm: number;
  mudWeightPpg: number;
  flowRateGpm: number;
  npt: boolean;
};

// Same 5 fields as src/data/delta-basin.ts's generateMockRaw() - kept in
// sync deliberately so well/field references resolve against the same
// dataset shown on Production & Ops.
const fields = [
  { id: "obago", name: "Obago", exportPoint: "Bonny", wellsTotal: 42 },
  { id: "ekpo", name: "Ekpo North", exportPoint: "Qua Iboe", wellsTotal: 28 },
  { id: "warri-sw", name: "Warri SW", exportPoint: "Forcados", wellsTotal: 35 },
  { id: "ibeno", name: "Ibeno Deep", exportPoint: "Qua Iboe", wellsTotal: 19 },
  { id: "brass-c", name: "Brass Creek", exportPoint: "Brass", wellsTotal: 24 },
] as const;

const operatorPartnerId = "shoreline"; // matches partners[].role === "Operator" in delta-basin.ts

const wellTypes: WellType[] = ["Oil producer", "Oil producer", "Oil producer", "Gas producer", "Water injector", "Gas injector"];
const trajectories = ["Vertical", "Deviated", "Horizontal", "Deviated"] as const;
const completionTypes = ["Single string", "Dual string", "Gas lift", "ESP", "Natural flow"] as const;
const reservoirs = ["Agbada D-1", "Agbada E-3", "Benin Sand B", "Akata Lower", "Agbada C-7"];

function buildFacilities(): Facility[] {
  const rows: Facility[] = [];
  const terminals = [...new Set(fields.map((f) => f.exportPoint))];
  terminals.forEach((t, i) => {
    rows.push({
      facilityId: `fac-term-${t.toLowerCase()}`,
      facilityName: `${t} Export Terminal`,
      facilityType: "Export terminal",
      fieldId: null,
      exportPoint: t,
      capacityBopd: 220_000 + i * 45_000,
    });
  });
  fields.forEach((f, i) => {
    rows.push({
      facilityId: `fac-${f.id}-flow`,
      facilityName: `${f.name} Flowstation`,
      facilityType: "Flowstation",
      fieldId: f.id,
      exportPoint: f.exportPoint,
      capacityBopd: Math.round(45_000 + stableRand(`fac-cap-${f.id}`) * 30_000),
    });
    if (i % 2 === 0) {
      rows.push({
        facilityId: `fac-${f.id}-gas`,
        facilityName: `${f.name} Gas Plant`,
        facilityType: "Gas plant",
        fieldId: f.id,
        exportPoint: f.exportPoint,
        capacityBopd: 0,
      });
    }
  });
  return rows;
}

export const facilities = buildFacilities();
const flowstationByField = Object.fromEntries(
  facilities.filter((f) => f.facilityType === "Flowstation").map((f) => [f.fieldId!, f.facilityId]),
);

function buildWells(): Well[] {
  const statusesWeighted: [WellStatus, number][] = [
    ["Producing", 0.78],
    ["Shut-in", 0.09],
    ["Suspended", 0.07],
    ["Drilling", 0.06],
  ];
  const rows: Well[] = [];
  fields.forEach((f) => {
    for (let w = 0; w < f.wellsTotal; w++) {
      const wellId = `WEL-${f.id}-${String(w + 1).padStart(3, "0")}`;
      const a = stableRand(`well-type-${wellId}`);
      const b = stableRand(`well-status-${wellId}`);
      const c = stableRand(`well-spud-${wellId}`);
      let cum = 0;
      let status: WellStatus = statusesWeighted[statusesWeighted.length - 1]![0];
      for (const [name, weight] of statusesWeighted) {
        cum += weight;
        if (b <= cum) {
          status = name;
          break;
        }
      }
      const spudYear = 2005 + Math.floor(c * 18);
      const spudMonth = 1 + Math.floor(stableRand(`well-spud-m-${wellId}`) * 12);
      const spudDay = 1 + Math.floor(stableRand(`well-spud-d-${wellId}`) * 27);
      rows.push({
        wellId,
        wellName: `${f.name.split(" ")[0]}-${String(w + 1).padStart(2, "0")}`,
        fieldId: f.id,
        facilityId: flowstationByField[f.id]!,
        partnerId: operatorPartnerId,
        wellType: pick(wellTypes, a),
        status,
        spudDate: `${spudYear}-${String(spudMonth).padStart(2, "0")}-${String(spudDay).padStart(2, "0")}`,
        totalDepthM: Math.round(2400 + stableRand(`well-depth-${wellId}`) * 1900),
      });
    }
  });
  return rows;
}

export const wells = buildWells();
export const wellById = (id: string) => wells.find((w) => w.wellId === id);

function buildWellbores(): Wellbore[] {
  const rows: Wellbore[] = [];
  wells.forEach((w) => {
    const count = stableRand(`wb-count-${w.wellId}`) > 0.72 ? 2 : 1;
    for (let b = 0; b < count; b++) {
      const wbId = `${w.wellId}-B${b + 1}`;
      const traj = pick(trajectories, stableRand(`wb-traj-${wbId}`));
      const factor = traj === "Horizontal" ? 1.35 : traj === "Deviated" ? 1.12 : 1;
      const md = Math.round(w.totalDepthM * factor + b * 240);
      rows.push({
        wellboreId: wbId,
        wellId: w.wellId,
        wellboreName: `${w.wellName}${b === 0 ? "" : `ST${b}`}`,
        trajectory: traj,
        isSidetrack: b > 0,
        measuredDepthM: md,
        trueVerticalDepthM: w.totalDepthM,
      });
    }
  });
  return rows;
}

export const wellbores = buildWellbores();

function buildCompletions(): Completion[] {
  return wellbores.map((wb) => {
    const cId = `${wb.wellboreId}-C1`;
    const r = stableRand(`comp-top-${cId}`);
    const top = Math.round(wb.trueVerticalDepthM * (0.82 + r * 0.08));
    const ctype = pick(completionTypes, stableRand(`comp-type-${cId}`));
    return {
      completionId: cId,
      wellboreId: wb.wellboreId,
      wellId: wb.wellId,
      completionType: ctype,
      reservoirUnit: pick(reservoirs, stableRand(`comp-res-${cId}`)),
      perforationTopM: top,
      perforationBaseM: top + Math.round(20 + stableRand(`comp-base-${cId}`) * 90),
      artificialLift: ctype === "ESP" ? "Electric submersible pump" : ctype === "Gas lift" ? "Continuous gas lift" : "None",
      completionDate: `${2010 + Math.floor(stableRand(`comp-year-${cId}`) * 15)}-${String(1 + Math.floor(stableRand(`comp-month-${cId}`) * 12)).padStart(2, "0")}-15`,
      isActive: !wb.isSidetrack || stableRand(`comp-active-${cId}`) > 0.4,
    };
  });
}

export const completions = buildCompletions();
export const completionByWellId = (wellId: string) => completions.find((c) => c.wellId === wellId);

/** Latest-period well-level production volume - shares a plausible field
 * total across producing/shut-in wells, same shape as
 * gold/fact_production_volume.yaml (well/field/facility grain). */
export function latestProductionVolumes(periodId = "2026-08"): ProductionVolumeRow[] {
  const rows: ProductionVolumeRow[] = [];
  const HOURS_PER_MONTH = 730;
  fields.forEach((f, fi) => {
    const fieldWells = wells.filter((w) => w.fieldId === f.id);
    const producers = fieldWells.filter((w) => w.status === "Producing" || w.status === "Shut-in");
    const fieldBopd = 34_000 + fi * 8_500;
    const share = fieldBopd / Math.max(1, producers.length);
    fieldWells.forEach((w) => {
      const key = `${periodId}-${w.wellId}`;
      const shut = w.status !== "Producing";
      const onstreamHours = shut
        ? Math.round(stableRand(`pv-hours-${key}`, 0, 180))
        : Math.round(HOURS_PER_MONTH * (0.9 + stableRand(`pv-hours2-${key}`, 0, 0.1)));
      const isInjector = w.wellType === "Water injector" || w.wellType === "Gas injector";
      const factor = isInjector ? 0 : 1;
      const bopd = factor * share * (0.7 + stableRand(`pv-rate-${key}`, 0, 0.6)) * (onstreamHours / HOURS_PER_MONTH);
      const oilBbl = Math.round(bopd * 30);
      const waterCutPct = Number((12 + stableRand(`pv-wc-${key}`, 0, 55)).toFixed(1));
      rows.push({
        periodId,
        wellId: w.wellId,
        fieldId: f.id,
        facilityId: w.facilityId,
        oilBbl,
        gasMscf: Math.round(oilBbl * (0.6 + stableRand(`pv-gas-${key}`, 0, 1.4))),
        waterBbl: Math.round((oilBbl * waterCutPct) / Math.max(1, 100 - waterCutPct)),
        onstreamHours,
        waterCutPct,
      });
    });
  });
  return rows;
}

/** Daily drilling telemetry for wells currently in Drilling status - a
 * 30-day trailing window. */
export function drillingTelemetry(): DrillingTelemetryRow[] {
  const rows: DrillingTelemetryRow[] = [];
  const drilling = wells.filter((w) => w.status === "Drilling");
  drilling.forEach((w) => {
    const wb = wellbores.find((b) => b.wellId === w.wellId);
    if (!wb) return;
    let depth = 600 + Math.round(stableRand(`dt-start-${w.wellId}`) * 400);
    for (let d = 0; d < 30; d++) {
      const key = `${w.wellId}-${d}`;
      const npt = stableRand(`dt-npt-${key}`) > 0.88;
      const rop = npt
        ? Number(stableRand(`dt-rop-${key}`, 0, 2).toFixed(1))
        : Number((6 + stableRand(`dt-rop2-${key}`, 0, 18)).toFixed(1));
      depth = Math.min(wb.measuredDepthM, Math.round(depth + rop * 20));
      const reportDate = new Date(Date.UTC(2026, 7, 1 + d));
      rows.push({
        wellId: w.wellId,
        wellboreId: wb.wellboreId,
        reportDate: reportDate.toISOString().slice(0, 10),
        depthM: depth,
        ropMPerHr: rop,
        wobKlbs: Math.round(12 + stableRand(`dt-wob-${key}`, 0, 28)),
        rpm: Math.round(60 + stableRand(`dt-rpm-${key}`, 0, 100)),
        mudWeightPpg: Number((9.2 + stableRand(`dt-mud-${key}`, 0, 3)).toFixed(1)),
        flowRateGpm: Math.round(420 + stableRand(`dt-flow-${key}`, 0, 380)),
        npt,
      });
    }
  });
  return rows;
}

export const fieldNameById = (id: string) => fields.find((f) => f.id === id)?.name ?? id;
