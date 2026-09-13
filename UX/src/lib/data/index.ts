// Active-customer data selector.
// Picks the literal dataset matching the customer chosen via VITE_CUSTOMER
// (see src/lib/config). All datasets share the CustomerDataset shape.

import { CUSTOMER_ID, type CustomerId } from "@/lib/config";
import { customer0Dataset } from "./customer0";
import type { CustomerDataset } from "./types";

const DATASETS: Record<CustomerId, CustomerDataset> = {
  customer0: customer0Dataset,
};

const active: CustomerDataset = DATASETS[CUSTOMER_ID];

export const KPIS = active.KPIS;
export const PRODUCTION_TREND = active.PRODUCTION_TREND;
export const REGION_INVENTORY = active.REGION_INVENTORY;
export const SHIPMENTS = active.SHIPMENTS;
export const ALERTS = active.ALERTS;
export const TANKS = active.TANKS;

export * from "./types";
