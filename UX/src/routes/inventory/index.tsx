import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { Shell } from "@/components/dashboard";
import { TANKS, type RangeKey, type Tank } from "@/lib/data";
import { customerConfig } from "@/lib/config";
import { slugifyRegion } from "@/lib/slug";

export const Route = createFileRoute("/inventory/")({
  head: () => {
    const title = `Regional Inventory — ${customerConfig.brand.name}`;
    const description =
      "Tank-level crude inventory by region with capacity, fill level, and days of cover.";
    return {
      meta: [
        { title },
        { name: "description", content: description },
        { property: "og:title", content: title },
        { property: "og:description", content: description },
        { property: "og:type", content: "website" },
        { name: "twitter:card", content: "summary" },
      ],
    };
  },
  component: InventoryPage,
});

const REGIONS = ["All", "US Gulf", "North Sea", "Middle East", "Asia-Pacific", "Western Europe"];

const TANK_STATUS_STYLE: Record<Tank["status"], string> = {
  Nominal: "bg-ok/15 text-ok",
  High: "bg-copper/15 text-copper",
  Diverting: "bg-danger/15 text-danger",
};

function InventoryPage() {
  const [range, setRange] = useState<RangeKey>("24H");
  const [region, setRegion] = useState("All");
  const inventoryLabels = customerConfig.table.inventory;

  const tanks = TANKS.filter((t) => region === "All" || t.region === region);
  const totalCap = tanks.reduce((sum, t) => sum + t.capacityMbbl, 0);
  const weightedFill =
    tanks.reduce((sum, t) => sum + t.capacityMbbl * t.fillPct, 0) /
    Math.max(totalCap, 0.001);

  return (
    <Shell range={range} onRangeChange={setRange}>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            {inventoryLabels.tanksTracked}
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold">
            {tanks.length}
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            {inventoryLabels.totalCapacity}
          </span>
          <div className="mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold">
            {totalCap.toFixed(1)}
            <span className="text-xs font-normal text-muted-foreground">M bbl</span>
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            {inventoryLabels.avgFill}
          </span>
          <div className="mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold">
            {weightedFill.toFixed(0)}
            <span className="text-xs font-normal text-muted-foreground">%</span>
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            {inventoryLabels.above90}
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold text-copper">
            {tanks.filter((t) => t.fillPct >= 90).length}
          </div>
        </div>
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-1 rounded-xl bg-card p-3 ring-1 ring-border">
        <span className="mr-2 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
          Region
        </span>
        {REGIONS.map((r) => (
          <button
            key={r}
            onClick={() => setRegion(r)}
            className={`rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wider uppercase transition-colors ${
              region === r
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {r}
          </button>
        ))}
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tanks.map((t) => (
          <div key={t.id} className="rounded-xl bg-card p-4 ring-1 ring-border">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="size-1.5 rounded-full bg-copper" />
                <span className="font-mono text-sm font-semibold text-foreground">
                  {t.id}
                </span>
                <Link
                  to="/inventory/$region"
                  params={{ region: slugifyRegion(t.region) }}
                  className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground hover:underline"
                >
                  {t.region}
                </Link>
              </div>
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${TANK_STATUS_STYLE[t.status]}`}
              >
                {t.status}
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-1 font-mono text-xl leading-none font-semibold">
              {t.fillPct}
              <span className="text-xs font-normal text-muted-foreground">
                % full
              </span>
            </div>
            <div className="mt-2 h-2 overflow-hidden rounded-full bg-hi">
              <div
                className="h-full rounded-full bg-copper"
                style={{ width: `${t.fillPct}%` }}
              />
            </div>
            <div className="mt-3 flex justify-between font-mono text-[10px] text-muted-foreground">
              <span>Capacity {t.capacityMbbl.toFixed(1)}M bbl</span>
              <span>{t.daysOfCover.toFixed(1)} days of cover</span>
            </div>
          </div>
        ))}
      </div>
    </Shell>
  );
}
