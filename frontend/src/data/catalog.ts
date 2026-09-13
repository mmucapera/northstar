// Synthetic materials catalogue for the Delta Basin pilot.
// Products are the consumables and spares held across the field warehouses.

export type Category = {
  id: string;
  name: string;
  description: string;
};

export type Product = {
  id: string;
  sku: string;
  name: string;
  categoryId: string;
  supplier: string;
  location: string;
  unit: string;
  unitPriceUsd: number;
  stockQty: number;
  reorderPoint: number;
  imageUrl?: string | undefined;
  updatedAt: string;
};

export const categories: Category[] = [
  { id: "drilling", name: "Drilling", description: "Bits, mud chemicals and downhole consumables" },
  { id: "wellhead", name: "Wellhead & valves", description: "Trees, gate valves, actuators and seals" },
  { id: "rotating", name: "Rotating equipment", description: "Pumps, compressors and spare kits" },
  { id: "electrical", name: "Electrical & power", description: "Generation, switchgear and cabling" },
  { id: "ppe", name: "PPE & safety", description: "Personal protective equipment and rescue gear" },
  { id: "pipeline", name: "Pipeline & flowlines", description: "Line pipe, fittings and integrity kits" },
];

export const stockStatus = (p: Product) =>
  p.stockQty === 0 ? "out-of-stock" : p.stockQty <= p.reorderPoint ? "low-stock" : "in-stock";

export const products: Product[] = [
  ["DRL-1001", "PDC drill bit 12¼\"", "drilling", "Sahel Drilling Supply", "Warri Warehouse", "ea", 28400, 9, 4],
  ["DRL-1002", "Tricone bit 8½\"", "drilling", "Sahel Drilling Supply", "Warri Warehouse", "ea", 12750, 3, 4],
  ["DRL-1003", "Barite (API grade)", "drilling", "Niger Minerals", "Bonny Yard", "tonne", 310, 480, 200],
  ["DRL-1004", "Bentonite mud additive", "drilling", "Niger Minerals", "Bonny Yard", "tonne", 265, 92, 120],
  ["DRL-1005", "Corrosion inhibitor XR-9", "drilling", "Delta Chemicals", "Warri Warehouse", "drum", 890, 64, 30],
  ["DRL-1006", "Casing centraliser 9⅝\"", "drilling", "Portside Fabricators", "Forcados Store", "ea", 145, 0, 40],
  ["WHV-2001", "Gate valve 6\" 5000 psi", "wellhead", "Meridian Valve Co.", "Qua Iboe Store", "ea", 9800, 12, 6],
  ["WHV-2002", "Christmas tree assembly 4-1/16\"", "wellhead", "Meridian Valve Co.", "Qua Iboe Store", "ea", 168000, 2, 2],
  ["WHV-2003", "Hydraulic actuator kit", "wellhead", "Meridian Valve Co.", "Warri Warehouse", "kit", 7350, 7, 5],
  ["WHV-2004", "Ring joint gasket BX-156", "wellhead", "Portside Fabricators", "Bonny Yard", "ea", 210, 340, 120],
  ["WHV-2005", "Choke bean set (assorted)", "wellhead", "Atlantic Oilfield", "Forcados Store", "set", 1980, 5, 6],
  ["ROT-3001", "ESP pump 400 series", "rotating", "Hydrolift Systems", "Warri Warehouse", "ea", 96500, 4, 3],
  ["ROT-3002", "Centrifugal pump seal kit", "rotating", "Hydrolift Systems", "Warri Warehouse", "kit", 2250, 18, 10],
  ["ROT-3003", "Gas compressor valve plate", "rotating", "Atlantic Oilfield", "Bonny Yard", "ea", 4100, 6, 6],
  ["ROT-3004", "Turbine bearing assembly", "rotating", "Rotaflow Nigeria", "Qua Iboe Store", "ea", 15300, 2, 3],
  ["ROT-3005", "Lube oil ISO VG 46", "rotating", "Delta Chemicals", "Forcados Store", "drum", 620, 130, 60],
  ["ELE-4001", "1.5 MW diesel generator", "electrical", "Powerline West Africa", "Warri Warehouse", "ea", 412000, 1, 1],
  ["ELE-4002", "11 kV switchgear panel", "electrical", "Powerline West Africa", "Bonny Yard", "ea", 58400, 3, 2],
  ["ELE-4003", "Armoured cable 3-core 95mm²", "electrical", "Copperline Ltd", "Forcados Store", "m", 41, 4200, 2000],
  ["ELE-4004", "UPS battery bank 48V", "electrical", "Copperline Ltd", "Qua Iboe Store", "ea", 8600, 5, 4],
  ["ELE-4005", "Ex-rated junction box", "electrical", "Powerline West Africa", "Warri Warehouse", "ea", 340, 88, 40],
  ["PPE-5001", "FR coverall (set of 2)", "ppe", "SafeGear Nigeria", "Warri Warehouse", "set", 165, 610, 250],
  ["PPE-5002", "Safety helmet with visor", "ppe", "SafeGear Nigeria", "Bonny Yard", "ea", 48, 420, 200],
  ["PPE-5003", "H2S escape breathing set", "ppe", "SafeGear Nigeria", "Qua Iboe Store", "ea", 720, 74, 60],
  ["PPE-5004", "Fall arrest harness", "ppe", "Atlantic Oilfield", "Forcados Store", "ea", 240, 52, 60],
  ["PPE-5005", "Gas detector (4-gas)", "ppe", "SafeGear Nigeria", "Warri Warehouse", "ea", 980, 33, 25],
  ["PPE-5006", "Marine life jacket", "ppe", "SafeGear Nigeria", "Bonny Yard", "ea", 95, 0, 80],
  ["PIP-6001", "Line pipe 12\" API 5L X65", "pipeline", "Portside Fabricators", "Forcados Store", "m", 175, 2600, 1200],
  ["PIP-6002", "Flowline clamp repair kit", "pipeline", "Portside Fabricators", "Warri Warehouse", "kit", 1450, 14, 8],
  ["PIP-6003", "Weld-neck flange 12\" 600#", "pipeline", "Rotaflow Nigeria", "Bonny Yard", "ea", 520, 96, 50],
  ["PIP-6004", "Pig launcher spare set", "pipeline", "Rotaflow Nigeria", "Qua Iboe Store", "set", 6800, 2, 2],
  ["PIP-6005", "Cathodic protection anode", "pipeline", "Niger Minerals", "Forcados Store", "ea", 380, 118, 60],
  ["PIP-6006", "Leak sealing compound", "pipeline", "Delta Chemicals", "Warri Warehouse", "pail", 210, 47, 40],
].map(
  (row, i): Product => ({
    id: `p${i + 1}`,
    sku: row[0] as string,
    name: row[1] as string,
    categoryId: row[2] as string,
    supplier: row[3] as string,
    location: row[4] as string,
    unit: row[5] as string,
    unitPriceUsd: row[6] as number,
    stockQty: row[7] as number,
    reorderPoint: row[8] as number,
    updatedAt: "2026-09-01",
  }),
);

export const categoryById = (id: string) => categories.find((c) => c.id === id);

export { formatUsd } from "./delta-basin";
