import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import { PanelTitle, Shell, TrendChart } from "@/components/dashboard";
import { KPIS, REGION_INVENTORY, RANGES, type RangeKey } from "@/lib/data";
import { customerConfig } from "@/lib/config";
import { slugifyRegion } from "@/lib/slug";

export const Route = createFileRoute("/production")({
  head: () => {
    const title = `Production Sources — ${customerConfig.brand.name}`;
    const description =
      "Where crude production is coming from: regional contribution, trend across ranges, and refinery throughput context.";
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
  component: ProductionPage,
});

function ProductionPage() {
  const [range, setRange] = useState<RangeKey>("24H");
  const kpi = KPIS[range];
  const inventory = REGION_INVENTORY[range];
  const totalVolume = inventory.reduce((s, r) => s + r.volumeM, 0);
  const ranked = [...inventory].sort((a, b) => b.volumeM - a.volumeM);
  const leader = ranked[0]!;

  return (
    <Shell range={range} onRangeChange={setRange}>
      <div className="flex items-center justify-between">
        <div>
          <Link
            to="/"
            className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground"
          >
            ← Overview
          </Link>
          <h1 className="mt-1 text-sm font-semibold tracking-tight">
            Production Sources
          </h1>
          <p className="mt-0.5 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            {kpi.production.value.toFixed(2)} M bpd fleet-wide · {range.toLowerCase()}
          </p>
        </div>
      </div>

      <section className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="rounded-xl bg-card p-4 ring-1 ring-border xl:col-span-2">
          <PanelTitle
            dot="bg-steel"
            title="Production Trend"
            sub={`bpd · ${range.toLowerCase()}`}
            right={
              <div className="hidden gap-3 font-mono text-[10px] text-muted-foreground sm:flex">
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-steel" /> Actual
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="size-1.5 rounded-full bg-primary" /> Target
                </span>
              </div>
            }
          />
          <TrendChart range={range} />
        </div>

        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Refinery Throughput
          </span>
          <div className="mt-2 flex items-baseline gap-1 font-mono text-2xl leading-none font-semibold">
            {kpi.refineryUtil.value.toFixed(1)}
            <span className="text-xs font-normal text-muted-foreground">%</span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-hi">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${kpi.refineryUtil.value}%` }}
            />
          </div>
          <p className="mt-4 text-[11px] leading-relaxed text-muted-foreground">
            Downstream capacity currently absorbing output at{" "}
            {kpi.refineryUtil.value.toFixed(1)}% utilization — the ceiling
            production growth runs into before storage becomes the constraint.
          </p>
        </div>
      </section>

      <section className="mt-3 rounded-xl bg-card ring-1 ring-border">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <PanelTitle
            dot="bg-copper"
            title="Regional Contribution"
            sub="by tracked storage volume — a proxy for where barrels originate"
          />
        </div>
        <div className="space-y-3.5 p-4">
          {ranked.map((r) => {
            const share = (r.volumeM / totalVolume) * 100;
            return (
              <Link
                key={r.name}
                to="/inventory/$region"
                params={{ region: slugifyRegion(r.name) }}
                className="block rounded-md transition-colors hover:bg-hi/40"
              >
                <div className="flex items-center justify-between font-mono text-[11px]">
                  <span className="text-foreground">{r.name}</span>
                  <span className="text-muted-foreground">
                    {share.toFixed(0)}% · {r.volumeM.toFixed(1)}M bbl
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-hi">
                  <div
                    className="h-full rounded-full bg-copper transition-all duration-500"
                    style={{ width: `${share}%` }}
                  />
                </div>
              </Link>
            );
          })}
        </div>
        <div className="border-t border-border px-4 py-2.5 font-mono text-[10px] text-muted-foreground">
          {leader.name} is the largest single source at{" "}
          {((leader.volumeM / totalVolume) * 100).toFixed(0)}% of tracked volume.
        </div>
      </section>

      <section className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {RANGES.map((r) => (
          <div key={r} className="rounded-xl bg-card p-4 ring-1 ring-border">
            <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {r}
            </span>
            <div className="mt-2 flex items-baseline gap-1 font-mono text-xl leading-none font-semibold">
              {KPIS[r].production.value.toFixed(2)}
              <span className="text-xs font-normal text-muted-foreground">
                M bpd
              </span>
            </div>
            <div
              className={`mt-2 font-mono text-[11px] ${
                KPIS[r].production.delta >= 0 ? "text-ok" : "text-danger"
              }`}
            >
              {KPIS[r].production.delta >= 0 ? "▲" : "▼"}{" "}
              {Math.abs(KPIS[r].production.delta).toFixed(1)}% vs prior period
            </div>
          </div>
        ))}
      </section>

      <footer className="mt-4 flex items-center justify-between font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        <span>{customerConfig.brand.footer}</span>
        <span>Regional split derived from storage volume, not metered wellhead output</span>
      </footer>
    </Shell>
  );
}
