// Shared types for per-customer datasets.
// All data is literal — no runtime randomness — so SSR and client render match.

export type RangeKey = "24H" | "7D" | "30D";

export const RANGES: RangeKey[] = ["24H", "7D", "30D"];

export type Kpis = {
  production: { value: number; delta: number; spark: number[] };
  refineryUtil: { value: number; delta: number };
  inventoryDays: { value: number; delta: number; spark: number[] };
  brent: number;
  wti: number;
  brentDelta: number;
};

export type TrendPoint = { actual: number; target: number };

export type RegionInventory = { name: string; volumeM: number; pct: number };

export type ShipmentStatus = "In Transit" | "Loading" | "Delayed" | "Queued";

export type Shipment = {
  id: string;
  vessel: string;
  route: string;
  corridor: string;
  load: string;
  loadValueMbbl: number;
  eta: string;
  etaDay: number;
  status: ShipmentStatus;
};

export type AlertSeverity = "CRITICAL" | "ELEVATED" | "WATCH";

export type DisruptionAlert = {
  severity: AlertSeverity;
  time: string;
  title: string;
  detail: string;
};

export type Tank = {
  id: string;
  region: string;
  capacityMbbl: number;
  fillPct: number;
  daysOfCover: number;
  status: "Nominal" | "High" | "Diverting";
};

export type CustomerDataset = {
  KPIS: Record<RangeKey, Kpis>;
  PRODUCTION_TREND: Record<RangeKey, TrendPoint[]>;
  REGION_INVENTORY: Record<RangeKey, RegionInventory[]>;
  SHIPMENTS: Shipment[];
  ALERTS: DisruptionAlert[];
  TANKS: Tank[];
};

export function shipmentsCsv(rows: Shipment[]): string {
  const header = "id,vessel,route,load,eta,status";
  const lines = rows.map((s) =>
    [s.id, s.vessel, `"${s.route}"`, s.load, s.eta, s.status].join(","),
  );
  return [header, ...lines].join("\n");
}
