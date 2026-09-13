import { createFileRoute, Link } from "@tanstack/react-router";
import { useState } from "react";
import {
  Delta,
  PanelTitle,
  SeverityTag,
  Shell,
  Sparkline,
  StatusChip,
  TrendChart,
} from "@/components/dashboard";
import {
  ALERTS,
  KPIS,
  REGION_INVENTORY,
  SHIPMENTS,
  shipmentsCsv,
  type RangeKey,
} from "@/lib/data";
import { customerConfig } from "@/lib/config";
import { slugifyRegion } from "@/lib/slug";

export const Route = createFileRoute("/")({
  head: () => {
    const title = `${customerConfig.brand.name} — ${customerConfig.brand.productLine}`;
    return {
      meta: [
        { title },
        { name: "description", content: customerConfig.brand.description },
        { property: "og:title", content: title },
        { property: "og:description", content: customerConfig.brand.description },
        { property: "og:type", content: "website" },
        { name: "twitter:card", content: "summary_large_image" },
      ],
    };
  },
  component: OverviewPage,
});

function downloadCsv() {
  const blob = new Blob([shipmentsCsv(SHIPMENTS)], { type: "text/csv" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "dataset_oilandgas-shipments.csv";
  a.click();
  URL.revokeObjectURL(url);
}

function OverviewPage() {
  const [range, setRange] = useState<RangeKey>("24H");
  const kpi = KPIS[range];
  const spread = (kpi.brent - kpi.wti).toFixed(1);
  const kpiLabels = customerConfig.kpis;
  const tableLabels = customerConfig.table.shipments;

  return (
    <Shell range={range} onRangeChange={setRange} onExport={downloadCsv}>
      {/* KPI strip */}
      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Link
          to="/production"
          className="rounded-xl bg-card p-4 ring-1 ring-border transition-colors hover:ring-steel"
        >
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {kpiLabels.production.label}
            </span>
            <Delta value={kpi.production.delta} />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="font-mono text-2xl leading-none font-semibold">
              {kpi.production.value.toFixed(2)}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {kpiLabels.production.unit}
            </span>
          </div>
          <Sparkline data={kpi.production.spark} tone="steel" />
          <div className="mt-2 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            Sources →
          </div>
        </Link>

        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {kpiLabels.refineryUtil.label}
            </span>
            <Delta value={kpi.refineryUtil.delta} />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="font-mono text-2xl leading-none font-semibold">
              {kpi.refineryUtil.value.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {kpiLabels.refineryUtil.unit}
            </span>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-hi">
            <div
              className="h-full rounded-full bg-primary transition-all duration-500"
              style={{ width: `${kpi.refineryUtil.value}%` }}
            />
          </div>
        </div>

        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {kpiLabels.inventoryDays.label}
            </span>
            <Delta value={kpi.inventoryDays.delta} />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="font-mono text-2xl leading-none font-semibold">
              {kpi.inventoryDays.value.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {kpiLabels.inventoryDays.unit}
            </span>
          </div>
          <Sparkline data={kpi.inventoryDays.spark} tone="copper" />
        </div>

        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <div className="flex items-center justify-between">
            <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {kpiLabels.priceBenchmark.label}
            </span>
            <Delta value={kpi.brentDelta} />
          </div>
          <div className="mt-2 flex items-baseline gap-1">
            <span className="font-mono text-2xl leading-none font-semibold">
              ${kpi.brent.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-muted-foreground">
              {kpiLabels.priceBenchmark.unit}
            </span>
          </div>
          <div className="mt-2 font-mono text-[11px] text-muted-foreground">
            WTI ${kpi.wti.toFixed(1)} &nbsp;·&nbsp; spread{" "}
            <span className="text-steel">${spread}</span>
          </div>
        </div>
      </section>

      {/* Charts row */}
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
          <PanelTitle
            dot="bg-copper"
            title="Inventory by Region"
            right={
              <Link
                to="/inventory"
                className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground"
              >
                Detail →
              </Link>
            }
          />
          <div className="mt-4 space-y-3.5">
            {REGION_INVENTORY[range].map((r) => (
              <Link
                key={r.name}
                to="/inventory/$region"
                params={{ region: slugifyRegion(r.name) }}
                className="block rounded-md transition-colors hover:bg-hi/40"
              >
                <div className="flex items-center justify-between font-mono text-[11px]">
                  <span className="text-foreground">{r.name}</span>
                  <span className="text-muted-foreground">
                    {r.volumeM.toFixed(1)}M bbl
                  </span>
                </div>
                <div className="mt-1 h-2 overflow-hidden rounded-full bg-hi">
                  <div
                    className="h-full rounded-full bg-copper transition-all duration-500"
                    style={{ width: `${r.pct}%`, opacity: r.pct > 85 ? 1 : 0.5 + (r.pct / 100) * 0.4 }}
                  />
                </div>
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* Shipments + alerts */}
      <section className="mt-3 grid grid-cols-1 gap-3 xl:grid-cols-3">
        <div className="rounded-xl bg-card ring-1 ring-border xl:col-span-2">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <PanelTitle dot="bg-steel" title="Active Shipments" />
            <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
              128 vessels · 6 corridors
            </span>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead>
                <tr className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                  <th className="px-4 py-2 font-medium">{tableLabels.vessel}</th>
                  <th className="px-3 py-2 font-medium">{tableLabels.route}</th>
                  <th className="px-3 py-2 font-medium">{tableLabels.load}</th>
                  <th className="px-3 py-2 font-medium">{tableLabels.eta}</th>
                  <th className="px-4 py-2 text-right font-medium">{tableLabels.status}</th>
                </tr>
              </thead>
              <tbody className="font-mono text-xs">
                {SHIPMENTS.slice(0, 6).map((s) => (
                  <tr
                    key={s.id}
                    className="border-t border-border/70 transition-colors hover:bg-hi/30"
                  >
                    <td className="px-4 py-2.5 text-foreground">
                      <Link
                        to="/shipments/$id"
                        params={{ id: s.id }}
                        className="transition-colors hover:text-steel hover:underline"
                      >
                        {s.vessel}
                      </Link>
                    </td>
                    <td className="px-3 py-2.5 text-muted-foreground">{s.route}</td>
                    <td className="px-3 py-2.5 text-foreground">{s.load}</td>
                    <td className="px-3 py-2.5 text-muted-foreground">{s.eta}</td>
                    <td className="px-4 py-2.5 text-right">
                      <StatusChip status={s.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <Link
            to="/shipments"
            className="block border-t border-border px-4 py-2.5 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            View full shipments log →
          </Link>
        </div>

        <div className="flex flex-col rounded-xl bg-card ring-1 ring-border">
          <div className="flex items-center justify-between border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <span className="relative flex size-1.5">
                <span className="absolute inline-flex h-full w-full animate-pulse-soft rounded-full bg-danger" />
                <span className="relative inline-flex size-1.5 rounded-full bg-danger" />
              </span>
              <h2 className="text-sm font-semibold tracking-tight">Disruptions</h2>
            </div>
            <span className="font-mono text-[10px] text-danger">
              {ALERTS.length} ACTIVE
            </span>
          </div>
          <div className="flex-1 divide-y divide-border/70">
            {ALERTS.map((a) => (
              <div key={a.title} className="px-4 py-3">
                <div className="flex items-center gap-2">
                  <SeverityTag severity={a.severity} />
                  <span className="font-mono text-[10px] text-muted-foreground">
                    {a.time}
                  </span>
                </div>
                <p className="mt-1.5 text-xs text-foreground">{a.title}</p>
                <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                  {a.detail}
                </p>
              </div>
            ))}
          </div>
          <Link
            to="/alerts"
            className="mt-auto block border-t border-border px-4 py-2.5 font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
          >
            View full alert log →
          </Link>
        </div>
      </section>

      <footer className="mt-4 flex items-center justify-between font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        <span>{customerConfig.brand.footer}</span>
        <span className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-ok" />
          All systems nominal · last sync 12s ago
        </span>
      </footer>
    </Shell>
  );
}
