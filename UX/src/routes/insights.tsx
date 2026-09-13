import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { PanelTitle, Shell } from "@/components/dashboard";
import {
  KPIS,
  PRODUCTION_TREND,
  REGION_INVENTORY,
  RANGES,
  SHIPMENTS,
  TANKS,
  type RangeKey,
} from "@/lib/data";
import { customerConfig } from "@/lib/config";

export const Route = createFileRoute("/insights")({
  head: () => {
    const title = `Insights — ${customerConfig.brand.name}`;
    const description =
      "Cross-cutting analysis: production tracking accuracy, regional concentration risk, fleet corridor performance, and price benchmark spread.";
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
  component: InsightsPage,
});

function mean(xs: number[]) {
  return xs.reduce((a, b) => a + b, 0) / Math.max(xs.length, 1);
}

// One row per range: how tightly actual production tracked target.
function trackingByRange() {
  return RANGES.map((r) => {
    const points = PRODUCTION_TREND[r];
    const deviations = points.map((p) => p.actual - p.target);
    const avgDev = mean(deviations);
    const avgAbsDev = mean(deviations.map(Math.abs));
    const onPlan = points.filter((p) => p.actual >= p.target).length;
    return { range: r, avgDev, avgAbsDev, onPlan, total: points.length };
  });
}

// Herfindahl-style concentration index (0-1) over regional storage volume —
// higher means supply is concentrated in fewer regions.
function concentrationIndex(shares: number[]) {
  const total = shares.reduce((a, b) => a + b, 0) || 1;
  return shares.reduce((sum, v) => sum + (v / total) ** 2, 0);
}

function corridorBreakdown() {
  const byCorridor = new Map<
    string,
    { count: number; load: number; delayed: number }
  >();
  for (const s of SHIPMENTS) {
    const row = byCorridor.get(s.corridor) ?? { count: 0, load: 0, delayed: 0 };
    row.count += 1;
    row.load += s.loadValueMbbl;
    if (s.status === "Delayed") row.delayed += 1;
    byCorridor.set(s.corridor, row);
  }
  return [...byCorridor.entries()]
    .map(([corridor, v]) => ({ corridor, ...v }))
    .sort((a, b) => b.load - a.load);
}

function tankRiskByRegion() {
  const byRegion = new Map<
    string,
    { fillSum: number; minCover: number; count: number; hot: number }
  >();
  for (const t of TANKS) {
    const row =
      byRegion.get(t.region) ??
      { fillSum: 0, minCover: Infinity, count: 0, hot: 0 };
    row.fillSum += t.fillPct;
    row.minCover = Math.min(row.minCover, t.daysOfCover);
    row.count += 1;
    if (t.status !== "Nominal") row.hot += 1;
    byRegion.set(t.region, row);
  }
  return [...byRegion.entries()]
    .map(([region, v]) => ({
      region,
      avgFill: v.fillSum / v.count,
      minCover: v.minCover,
      hot: v.hot,
      count: v.count,
    }))
    .sort((a, b) => b.avgFill - a.avgFill);
}

function InsightsPage() {
  const [range, setRange] = useState<RangeKey>("24H");

  const tracking = useMemo(trackingByRange, []);
  const currentTracking = tracking.find((t) => t.range === range)!;
  const bestTracking = [...tracking].sort(
    (a, b) => a.avgAbsDev - b.avgAbsDev,
  )[0]!;
  const worstTracking = [...tracking].sort(
    (a, b) => b.avgAbsDev - a.avgAbsDev,
  )[0]!;

  const inventory = REGION_INVENTORY[range];
  const hhi = useMemo(
    () => concentrationIndex(inventory.map((r) => r.volumeM)),
    [inventory],
  );
  const topRegion = [...inventory].sort((a, b) => b.volumeM - a.volumeM)[0]!;
  const criticalRegions = inventory.filter((r) => r.pct >= 90);

  const corridors = useMemo(corridorBreakdown, []);
  const topCorridor = corridors[0]!;
  const totalDelayed = SHIPMENTS.filter((s) => s.status === "Delayed").length;

  const tankRisk = useMemo(tankRiskByRegion, []);
  const riskiestRegion = [...tankRisk].sort((a, b) => a.minCover - b.minCover)[0]!;

  const priceRows = RANGES.map((r) => KPIS[r]);
  const spreadTrend =
    priceRows[0]!.brent -
    priceRows[0]!.wti -
    (priceRows[2]!.brent - priceRows[2]!.wti);

  return (
    <Shell range={range} onRangeChange={setRange}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold tracking-tight">
            Insights &amp; Deep Dives
          </h1>
          <p className="mt-0.5 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            Cross-cutting analysis over production, storage, fleet &amp; pricing
          </p>
        </div>
      </div>

      {/* Headline callouts */}
      <section className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Callout
          dot="bg-steel"
          label="Best-tracked window"
          value={bestTracking.range}
          note={`avg ${bestTracking.avgAbsDev >= 0 ? "±" : ""}${bestTracking.avgAbsDev.toFixed(2)} M bpd off target`}
        />
        <Callout
          dot="bg-copper"
          label="Storage concentration"
          value={`${(hhi * 100).toFixed(0)} HHI`}
          note={`${topRegion.name} holds ${((topRegion.volumeM / inventory.reduce((s, r) => s + r.volumeM, 0)) * 100).toFixed(0)}% of tracked volume`}
        />
        <Callout
          dot={riskiestRegion.minCover < 12 ? "bg-danger" : "bg-primary"}
          label="Thinnest cover"
          value={`${riskiestRegion.minCover.toFixed(1)}d`}
          note={`${riskiestRegion.region} · lowest days-of-cover tank`}
        />
        <Callout
          dot="bg-steel"
          label="Busiest corridor"
          value={topCorridor.corridor}
          note={`${topCorridor.count} vessels · ${topCorridor.load.toFixed(1)}M bbl`}
        />
      </section>

      <section className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* Production tracking accuracy */}
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <PanelTitle
            dot="bg-steel"
            title="Production Tracking Accuracy"
            sub="actual vs target"
          />
          <div className="mt-4 space-y-3">
            {tracking.map((t) => (
              <div key={t.range}>
                <div className="flex items-center justify-between font-mono text-[11px]">
                  <span
                    className={
                      t.range === range ? "text-foreground" : "text-muted-foreground"
                    }
                  >
                    {t.range}
                  </span>
                  <span
                    className={t.avgDev >= 0 ? "text-ok" : "text-danger"}
                  >
                    {t.avgDev >= 0 ? "+" : ""}
                    {t.avgDev.toFixed(2)} M bpd avg
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-hi">
                  <div
                    className={`h-full rounded-full ${t.avgDev >= 0 ? "bg-ok" : "bg-danger"}`}
                    style={{ width: `${Math.min(100, (t.onPlan / t.total) * 100)}%` }}
                  />
                </div>
                <div className="mt-1 font-mono text-[10px] text-muted-foreground">
                  {t.onPlan}/{t.total} points at or above target
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-lg bg-hi/50 px-3 py-2 font-mono text-[10px] text-muted-foreground">
            Widest gap: <span className="text-foreground">{worstTracking.range}</span> at{" "}
            {worstTracking.avgAbsDev.toFixed(2)} M bpd average deviation.
          </div>
        </div>

        {/* Price benchmark spread */}
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <PanelTitle dot="bg-copper" title="Brent / WTI Spread" sub="by range" />
          <div className="mt-4 space-y-3">
            {RANGES.map((r) => {
              const k = KPIS[r];
              const spread = k.brent - k.wti;
              return (
                <div key={r} className="flex items-center gap-3">
                  <span
                    className={`w-8 font-mono text-[11px] ${
                      r === range ? "text-foreground" : "text-muted-foreground"
                    }`}
                  >
                    {r}
                  </span>
                  <div className="flex flex-1 items-center gap-2 font-mono text-[11px]">
                    <span className="text-steel">${k.brent.toFixed(1)}</span>
                    <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-hi">
                      <div
                        className="h-full rounded-full bg-copper"
                        style={{ width: `${(k.wti / k.brent) * 100}%` }}
                      />
                    </div>
                    <span className="text-copper">${k.wti.toFixed(1)}</span>
                  </div>
                  <span className="w-14 text-right font-mono text-[11px] text-muted-foreground">
                    Δ{spread.toFixed(1)}
                  </span>
                </div>
              );
            })}
          </div>
          <div className="mt-4 rounded-lg bg-hi/50 px-3 py-2 font-mono text-[10px] text-muted-foreground">
            Spread has {spreadTrend >= 0 ? "widened" : "narrowed"} by{" "}
            <span className="text-foreground">${Math.abs(spreadTrend).toFixed(1)}</span> from
            30D to 24H.
          </div>
        </div>
      </section>

      <section className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-2">
        {/* Regional concentration */}
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <PanelTitle
            dot="bg-primary"
            title="Regional Concentration"
            sub={range.toLowerCase()}
          />
          <div className="mt-4 space-y-3">
            {[...inventory]
              .sort((a, b) => b.volumeM - a.volumeM)
              .map((r) => {
                const total = inventory.reduce((s, x) => s + x.volumeM, 0);
                const share = (r.volumeM / total) * 100;
                return (
                  <div key={r.name}>
                    <div className="flex items-center justify-between font-mono text-[11px]">
                      <span className="text-foreground">{r.name}</span>
                      <span className="text-muted-foreground">
                        {share.toFixed(0)}% of volume · {r.pct}% full
                      </span>
                    </div>
                    <div className="mt-1 h-2 overflow-hidden rounded-full bg-hi">
                      <div
                        className="h-full rounded-full bg-primary"
                        style={{ width: `${share}%` }}
                      />
                    </div>
                  </div>
                );
              })}
          </div>
          {criticalRegions.length > 0 && (
            <div className="mt-4 rounded-lg bg-danger/10 px-3 py-2 font-mono text-[10px] text-danger">
              {criticalRegions.map((r) => r.name).join(", ")} at or above 90% fill.
            </div>
          )}
        </div>

        {/* Corridor performance */}
        <div className="rounded-xl bg-card ring-1 ring-border">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <PanelTitle dot="bg-steel" title="Corridor Performance" />
            <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
              {totalDelayed} delayed fleet-wide
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                  <th className="px-4 py-2 font-medium">Corridor</th>
                  <th className="px-3 py-2 text-right font-medium">Vessels</th>
                  <th className="px-3 py-2 text-right font-medium">Volume</th>
                  <th className="px-4 py-2 text-right font-medium">Delayed</th>
                </tr>
              </thead>
              <tbody className="font-mono text-xs">
                {corridors.map((c) => (
                  <tr
                    key={c.corridor}
                    className="border-t border-border/70 transition-colors hover:bg-hi/30"
                  >
                    <td className="px-4 py-2.5 text-foreground">{c.corridor}</td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">
                      {c.count}
                    </td>
                    <td className="px-3 py-2.5 text-right text-muted-foreground">
                      {c.load.toFixed(1)}M bbl
                    </td>
                    <td
                      className={`px-4 py-2.5 text-right ${
                        c.delayed > 0 ? "text-danger" : "text-muted-foreground"
                      }`}
                    >
                      {c.delayed || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <footer className="mt-4 flex items-center justify-between font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        <span>{customerConfig.brand.footer}</span>
        <span>Computed client-side from current dataset · no external calls</span>
      </footer>
    </Shell>
  );
}

function Callout({
  dot,
  label,
  value,
  note,
}: {
  dot: string;
  label: string;
  value: string;
  note: string;
}) {
  return (
    <div className="rounded-xl bg-card p-4 ring-1 ring-border">
      <div className="flex items-center gap-2">
        <span className={`size-1.5 rounded-full ${dot}`} />
        <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
          {label}
        </span>
      </div>
      <div className="mt-2 font-mono text-xl leading-none font-semibold">
        {value}
      </div>
      <div className="mt-2 text-[11px] text-muted-foreground">{note}</div>
    </div>
  );
}
