// Deterministic mock data for the "customer0" customer.
// All data is literal — no runtime randomness — so SSR and client render match.

import type {
  CustomerDataset,
  Kpis,
  RangeKey,
  RegionInventory,
  Shipment,
  TrendPoint,
} from "./types";

const KPIS: Record<RangeKey, Kpis> = {
  "24H": {
    production: {
      value: 4.28,
      delta: 2.4,
      spark: [40, 55, 48, 62, 70, 66, 80, 92],
    },
    refineryUtil: { value: 86.4, delta: 0.8 },
    inventoryDays: {
      value: 21.7,
      delta: -1.1,
      spark: [90, 85, 80, 74, 70, 62, 55, 48],
    },
    brent: 92.4,
    wti: 88.1,
    brentDelta: 3.2,
  },
  "7D": {
    production: {
      value: 4.19,
      delta: 1.2,
      spark: [44, 50, 58, 52, 64, 71, 76, 84],
    },
    refineryUtil: { value: 84.9, delta: -0.6 },
    inventoryDays: {
      value: 22.3,
      delta: 0.7,
      spark: [82, 78, 84, 80, 74, 70, 66, 68],
    },
    brent: 90.8,
    wti: 86.9,
    brentDelta: 1.6,
  },
  "30D": {
    production: {
      value: 4.05,
      delta: -0.9,
      spark: [72, 66, 60, 58, 52, 56, 50, 46],
    },
    refineryUtil: { value: 83.1, delta: -2.4 },
    inventoryDays: {
      value: 23.9,
      delta: 2.8,
      spark: [70, 74, 68, 76, 72, 80, 84, 88],
    },
    brent: 87.2,
    wti: 83.5,
    brentDelta: -1.8,
  },
};

// 9 points each, y-domain 3.0–5.0 M bpd
const PRODUCTION_TREND: Record<RangeKey, TrendPoint[]> = {
  "24H": [
    { actual: 3.9, target: 4.05 },
    { actual: 4.05, target: 4.1 },
    { actual: 4.0, target: 4.15 },
    { actual: 4.2, target: 4.25 },
    { actual: 4.15, target: 4.3 },
    { actual: 4.35, target: 4.45 },
    { actual: 4.3, target: 4.5 },
    { actual: 4.5, target: 4.6 },
    { actual: 4.45, target: 4.55 },
  ],
  "7D": [
    { actual: 3.75, target: 3.9 },
    { actual: 3.95, target: 4.0 },
    { actual: 3.85, target: 4.05 },
    { actual: 4.1, target: 4.2 },
    { actual: 4.0, target: 4.25 },
    { actual: 4.25, target: 4.4 },
    { actual: 4.15, target: 4.45 },
    { actual: 4.4, target: 4.55 },
    { actual: 4.3, target: 4.5 },
  ],
  "30D": [
    { actual: 4.3, target: 4.1 },
    { actual: 4.15, target: 4.05 },
    { actual: 4.2, target: 4.0 },
    { actual: 4.0, target: 3.95 },
    { actual: 4.05, target: 3.95 },
    { actual: 3.9, target: 3.9 },
    { actual: 3.95, target: 3.85 },
    { actual: 3.8, target: 3.8 },
    { actual: 3.85, target: 3.85 },
  ],
};

const REGION_INVENTORY: Record<RangeKey, RegionInventory[]> = {
  "24H": [
    { name: "US Gulf", volumeM: 3.2, pct: 78 },
    { name: "North Sea", volumeM: 2.1, pct: 52 },
    { name: "Middle East", volumeM: 4.6, pct: 92 },
    { name: "Asia-Pacific", volumeM: 5.8, pct: 99 },
    { name: "Western Europe", volumeM: 1.7, pct: 38 },
  ],
  "7D": [
    { name: "US Gulf", volumeM: 3.4, pct: 81 },
    { name: "North Sea", volumeM: 2.3, pct: 56 },
    { name: "Middle East", volumeM: 4.4, pct: 88 },
    { name: "Asia-Pacific", volumeM: 5.5, pct: 94 },
    { name: "Western Europe", volumeM: 1.9, pct: 42 },
  ],
  "30D": [
    { name: "US Gulf", volumeM: 3.8, pct: 88 },
    { name: "North Sea", volumeM: 2.6, pct: 63 },
    { name: "Middle East", volumeM: 4.1, pct: 82 },
    { name: "Asia-Pacific", volumeM: 5.1, pct: 86 },
    { name: "Western Europe", volumeM: 2.2, pct: 49 },
  ],
};

const SHIPMENTS: Shipment[] = [
  { id: "S-001", vessel: "Aurora Meridian", route: "Ras Tanura → Singapore", corridor: "ME → APAC", load: "2.0M bbl", loadValueMbbl: 2.0, eta: "14 Jun", etaDay: 14, status: "In Transit" },
  { id: "S-002", vessel: "Ironclad Vessel", route: "Houma → Rotterdam", corridor: "US → EU", load: "1.6M bbl", loadValueMbbl: 1.6, eta: "18 Jun", etaDay: 18, status: "Loading" },
  { id: "S-003", vessel: "Caspian Star", route: "Bassorah → Fujairah", corridor: "ME → ME", load: "1.2M bbl", loadValueMbbl: 1.2, eta: "11 Jun", etaDay: 11, status: "Delayed" },
  { id: "S-004", vessel: "Nordfjord Pioneer", route: "Sullom Voe → Le Havre", corridor: "NS → EU", load: "0.9M bbl", loadValueMbbl: 0.9, eta: "16 Jun", etaDay: 16, status: "In Transit" },
  { id: "S-005", vessel: "Tidewater Kestrel", route: "Kuwait → Pusan", corridor: "ME → APAC", load: "1.8M bbl", loadValueMbbl: 1.8, eta: "20 Jun", etaDay: 20, status: "Loading" },
  { id: "S-006", vessel: "Baltic Corridor", route: "Primorsk → Rostock", corridor: "RU → EU", load: "0.7M bbl", loadValueMbbl: 0.7, eta: "12 Jun", etaDay: 12, status: "In Transit" },
  { id: "S-007", vessel: "Meridian Dawn", route: "Houston → Antwerp", corridor: "US → EU", load: "1.1M bbl", loadValueMbbl: 1.1, eta: "22 Jun", etaDay: 22, status: "Queued" },
  { id: "S-008", vessel: "Severn Resolve", route: "Kuara → Ningbo", corridor: "AF → APAC", load: "1.4M bbl", loadValueMbbl: 1.4, eta: "25 Jun", etaDay: 25, status: "In Transit" },
  { id: "S-009", vessel: "Polaris Endeavor", route: "Es Sider → Trieste", corridor: "MED → EU", load: "0.6M bbl", loadValueMbbl: 0.6, eta: "13 Jun", etaDay: 13, status: "Delayed" },
  { id: "S-010", vessel: "Corvus Voyager", route: "Santos → Qingdao", corridor: "SA → APAC", load: "1.9M bbl", loadValueMbbl: 1.9, eta: "28 Jun", etaDay: 28, status: "In Transit" },
  { id: "S-011", vessel: "Halcyon Tide", route: "Mina al-Ahmadi → Ulsan", corridor: "ME → APAC", load: "1.5M bbl", loadValueMbbl: 1.5, eta: "19 Jun", etaDay: 19, status: "Queued" },
  { id: "S-012", vessel: "Verdant Star", route: "Cabinda → Galveston", corridor: "AF → US", load: "1.0M bbl", loadValueMbbl: 1.0, eta: "24 Jun", etaDay: 24, status: "Loading" },
];

const ALERTS = [
  {
    severity: "CRITICAL" as const,
    time: "09:42 UTC",
    title: "Strait of Hormuz — tanker traffic reduced 34% after advisory",
    detail: "Caspian Star rerouted · +36h ETA impact",
  },
  {
    severity: "ELEVATED" as const,
    time: "07:15 UTC",
    title: "Sturgeon River pipeline valve 4B — flow throttled to 62%",
    detail: "Est. recovery 14:00 UTC · 180k bpd held",
  },
  {
    severity: "WATCH" as const,
    time: "05:50 UTC",
    title: "Gulf terminal tank farm T-11 at 91% capacity",
    detail: "Divert 400k bbl to T-14 · auto-scheduled",
  },
];

const TANKS = [
  { id: "T-04", region: "US Gulf", capacityMbbl: 0.8, fillPct: 74, daysOfCover: 19.2, status: "Nominal" as const },
  { id: "T-11", region: "US Gulf", capacityMbbl: 1.2, fillPct: 91, daysOfCover: 22.8, status: "Diverting" as const },
  { id: "T-14", region: "US Gulf", capacityMbbl: 1.4, fillPct: 62, daysOfCover: 16.4, status: "Nominal" as const },
  { id: "N-02", region: "North Sea", capacityMbbl: 0.9, fillPct: 48, daysOfCover: 14.1, status: "Nominal" as const },
  { id: "N-07", region: "North Sea", capacityMbbl: 1.1, fillPct: 55, daysOfCover: 15.6, status: "Nominal" as const },
  { id: "M-01", region: "Middle East", capacityMbbl: 2.2, fillPct: 95, daysOfCover: 28.3, status: "High" as const },
  { id: "M-05", region: "Middle East", capacityMbbl: 2.6, fillPct: 89, daysOfCover: 26.1, status: "High" as const },
  { id: "A-03", region: "Asia-Pacific", capacityMbbl: 3.1, fillPct: 99, daysOfCover: 31.7, status: "High" as const },
  { id: "A-08", region: "Asia-Pacific", capacityMbbl: 2.9, fillPct: 97, daysOfCover: 30.2, status: "High" as const },
  { id: "E-06", region: "Western Europe", capacityMbbl: 0.7, fillPct: 34, daysOfCover: 9.8, status: "Nominal" as const },
  { id: "E-09", region: "Western Europe", capacityMbbl: 1.0, fillPct: 41, daysOfCover: 11.3, status: "Nominal" as const },
];

export const customer0Dataset: CustomerDataset = {
  KPIS,
  PRODUCTION_TREND,
  REGION_INVENTORY,
  SHIPMENTS,
  ALERTS,
  TANKS,
};
