import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useState } from "react";
import { Shell } from "@/components/dashboard";
import { RANGES, REGION_INVENTORY, TANKS, type RangeKey, type Tank } from "@/lib/data";
import { customerConfig } from "@/lib/config";
import { findRegionBySlug } from "@/lib/slug";

export const Route = createFileRoute("/inventory/$region")({
  loader: ({ params }) => {
    const match = findRegionBySlug(REGION_INVENTORY["24H"], params.region);
    if (!match) throw notFound();
    return { name: match.name };
  },
  head: ({ loaderData }) => {
    const name = loaderData?.name ?? "Region";
    const title = `${name} — ${customerConfig.brand.name}`;
    const description = `Storage, tank status, and production share for ${name}.`;
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
  component: RegionPage,
  notFoundComponent: RegionNotFound,
});

const TANK_STATUS_STYLE: Record<Tank["status"], string> = {
  Nominal: "bg-ok/15 text-ok",
  High: "bg-copper/15 text-copper",
  Diverting: "bg-danger/15 text-danger",
};

function RegionPage() {
  const { name } = Route.useLoaderData();
  const [range, setRange] = useState<RangeKey>("24H");

  const tanks = TANKS.filter((t) => t.region === name);
  const totalCap = tanks.reduce((sum, t) => sum + t.capacityMbbl, 0);
  const weightedFill =
    tanks.reduce((sum, t) => sum + t.capacityMbbl * t.fillPct, 0) /
    Math.max(totalCap, 0.001);
  const minCover = Math.min(...tanks.map((t) => t.daysOfCover));

  return (
    <Shell range={range} onRangeChange={setRange}>
      <Link
        to="/inventory"
        className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground"
      >
        ← Inventory
      </Link>
      <div className="mt-1 flex items-center gap-2">
        <span className="size-1.5 rounded-full bg-copper" />
        <h1 className="text-sm font-semibold tracking-tight">{name}</h1>
        <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
          {tanks.length} tanks tracked
        </span>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Total Capacity
          </span>
          <div className="mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold">
            {totalCap.toFixed(1)}
            <span className="text-xs font-normal text-muted-foreground">M bbl</span>
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Weighted Fill
          </span>
          <div className="mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold">
            {weightedFill.toFixed(0)}
            <span className="text-xs font-normal text-muted-foreground">%</span>
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Thinnest Cover
          </span>
          <div
            className={`mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold ${
              minCover < 12 ? "text-danger" : ""
            }`}
          >
            {minCover.toFixed(1)}
            <span className="text-xs font-normal text-muted-foreground">days</span>
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            At/Above 90%
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold text-copper">
            {tanks.filter((t) => t.fillPct >= 90).length}
          </div>
        </div>
      </div>

      <div className="mt-3 rounded-xl bg-card p-4 ring-1 ring-border">
        <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
          Volume Across Ranges
        </span>
        <div className="mt-4 space-y-3">
          {RANGES.map((r) => {
            const row = REGION_INVENTORY[r].find((x) => x.name === name);
            if (!row) return null;
            return (
              <div key={r}>
                <div className="flex items-center justify-between font-mono text-[11px]">
                  <span
                    className={r === range ? "text-foreground" : "text-muted-foreground"}
                  >
                    {r}
                  </span>
                  <span className="text-muted-foreground">
                    {row.volumeM.toFixed(1)}M bbl · {row.pct}% full
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-hi">
                  <div
                    className="h-full rounded-full bg-copper transition-all duration-500"
                    style={{ width: `${row.pct}%` }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>

      <div className="mt-3 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
        {tanks.map((t) => (
          <div key={t.id} className="rounded-xl bg-card p-4 ring-1 ring-border">
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-semibold text-foreground">
                {t.id}
              </span>
              <span
                className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${TANK_STATUS_STYLE[t.status]}`}
              >
                {t.status}
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-1 font-mono text-xl leading-none font-semibold">
              {t.fillPct}
              <span className="text-xs font-normal text-muted-foreground">% full</span>
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
        {tanks.length === 0 && (
          <div className="rounded-xl bg-card p-8 text-center font-mono text-xs text-muted-foreground ring-1 ring-border md:col-span-2 xl:col-span-3">
            No individual tanks tracked for this region.
          </div>
        )}
      </div>
    </Shell>
  );
}

function RegionNotFound() {
  return (
    <Shell range="24H" onRangeChange={() => {}}>
      <div className="rounded-xl bg-card p-8 text-center ring-1 ring-border">
        <p className="text-sm text-foreground">Region not found.</p>
        <Link
          to="/inventory"
          className="mt-2 inline-block font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to Inventory
        </Link>
      </div>
    </Shell>
  );
}
