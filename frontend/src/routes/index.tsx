import { createFileRoute, Link } from "@tanstack/react-router";
import { AlertTriangle, ArrowUpRight, CheckCircle2, CircleAlert, PackageCheck } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePeriod } from "@/components/period-context";
import { useCatalog } from "@/components/catalog-context";
import { useView, personaById } from "@/components/view-context";
import { ProductPhoto } from "@/components/product-photo";
import { MarketsPanel } from "@/components/markets-panel";
import { ReorderableWidgets, type DashboardWidget } from "@/components/reorderable-widgets";
import { stockStatus } from "@/data/catalog";
import {
  EmptyState,
  Metric,
  PageHeader,
  Panel,
  PeriodSelector,
  PrintButton,
  FieldName,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import {
  formatBbl,
  formatBopd,
  formatNumber,
  formatPct,
  formatSignedPct,
  formatUsd,
} from "@/data/delta-basin";
import { useDeltaBasin } from "@/components/delta-basin-context";
import { chartAxis, chartMonthAxis, chartTooltip } from "@/components/chart-theme";
import { ChartFrame } from "@/components/chart-frame";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Delta Basin — Upstream JV, production and safety overview" },
      {
        name: "description",
        content:
          "Single view of joint-venture reconciliation, field production and HSE performance for the Delta Basin CUSTOMER0 pilot.",
      },
      { property: "og:title", content: "Delta Basin — Upstream operations overview" },
      {
        property: "og:description",
        content:
          "Joint-venture variance, production attainment and TRIR in one control-room view. Synthetic pilot data.",
      },
    ],
  }),
  component: Overview,
});

function Overview() {
  const { periodId } = usePeriod();
  const { shows, persona } = useView();
  const {
    alertsForPeriod,
    hseTrend,
    netVarianceTrend,
    periodLabel,
    productionForPeriod,
    fieldById,
    summaryForPeriod,
    uptimeTrend,
  } = useDeltaBasin();
  const s = summaryForPeriod(periodId);
  const allAlerts = alertsForPeriod(periodId);
  const alerts = allAlerts.filter((a) =>
    a.to === "/reconciliation"
      ? shows("jv")
      : a.to === "/production"
        ? shows("production")
        : a.to === "/hse"
          ? shows("hse")
          : true,
  );
  const { items } = useCatalog();
  const watchlist = items
    .filter((p) => stockStatus(p) !== "in-stock")
    .sort((a, b) => a.stockQty - b.stockQty)
    .slice(0, 6);
  const variance = netVarianceTrend();
  const uptime = uptimeTrend();
  const hse = hseTrend();
  const fieldsAtRisk = productionForPeriod(periodId).filter((r) => r.status !== "normal");

  const widgets: DashboardWidget[] = [
    {
      id: "attention",
      content: (
        <Panel
          title="Needs attention"
          note={`${alerts.length} open item(s) for ${periodLabel(periodId)} in the ${personaById(persona).label.toLowerCase()} view`}
        >
          {alerts.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="Nothing flagged for this period."
              hint="Variance, uptime and safety all sat inside tolerance, so there is nothing to action here."
            />
          ) : (
            <ul className="grid gap-2 md:grid-cols-2">
              {alerts.map((a, i) => (
                <li key={i}>
                  <Link
                    to={a.to}
                    className="flex items-start gap-3 rounded-md border border-border bg-surface p-3 transition-colors hover:border-primary/50"
                  >
                    {a.level === "critical" ? (
                      <CircleAlert className="mt-0.5 size-4 shrink-0 text-critical" aria-hidden />
                    ) : (
                      <AlertTriangle className="mt-0.5 size-4 shrink-0 text-warning" aria-hidden />
                    )}
                    <span className="min-w-0">
                      <span className="block text-sm text-foreground">{a.title}</span>
                      <span className="block text-xs text-muted-foreground">{a.detail}</span>
                    </span>
                    <ArrowUpRight className="ml-auto size-3.5 shrink-0 text-muted-foreground" aria-hidden />
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ),
    },
    { id: "markets", content: <MarketsPanel /> },
    {
      id: "trends",
      content: (
        <div className="grid gap-4 lg:grid-cols-3">
          {shows("jv") ? (
            <ChartFrame title="Net variance" note="12-month JV trend, %">
              {(h) => (
                <ResponsiveContainer width="100%" height={h}>
                  <AreaChart data={variance}>
                    <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="period" {...chartMonthAxis} />
                    <YAxis {...chartAxis} width={38} />
                    <Tooltip {...chartTooltip} />
                    <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                    <Area
                      isAnimationActive={false}
                      type="monotone"
                      dataKey="variancePct"
                      name="Net variance %"
                      stroke="var(--chart-1)"
                      fill="color-mix(in oklab, var(--chart-1) 20%, transparent)"
                      strokeWidth={2}
                    />
                  </AreaChart>
                </ResponsiveContainer>
              )}
            </ChartFrame>
          ) : null}
          {shows("production") ? (
            <ChartFrame title="Production" note="Actual vs. forecast, bopd">
              {(h) => (
                <ResponsiveContainer width="100%" height={h}>
                  <LineChart data={uptime}>
                    <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="period" {...chartMonthAxis} />
                    <YAxis {...chartAxis} width={48} />
                    <Tooltip {...chartTooltip} />
                    <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                    <Line isAnimationActive={false} type="monotone" dataKey="forecast" name="Forecast" stroke="var(--chart-4)" strokeDasharray="4 4" dot={false} />
                    <Line isAnimationActive={false} type="monotone" dataKey="actual" name="Actual" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </ChartFrame>
          ) : null}
          {shows("hse") ? (
            <ChartFrame title="TRIR" note="Rolling 12-month rate">
              {(h) => (
                <ResponsiveContainer width="100%" height={h}>
                  <LineChart data={hse}>
                    <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="period" {...chartMonthAxis} />
                    <YAxis {...chartAxis} width={38} />
                    <Tooltip {...chartTooltip} />
                    <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                    <Line isAnimationActive={false} type="monotone" dataKey="trir" name="TRIR" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
                  </LineChart>
                </ResponsiveContainer>
              )}
            </ChartFrame>
          ) : null}
        </div>
      ),
    },
  ];

  if (shows("production")) {
    widgets.push({
      id: "fields-off-plan",
      content: (
        <Panel title="Fields off plan" note="Anything not flagged normal this period">
          {fieldsAtRisk.length === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="All fields normal."
              hint="Every field held uptime and forecast attainment inside tolerance for this period."
            />
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {fieldsAtRisk.map((r) => (
                <li
                  key={r.fieldId}
                  className="flex items-center justify-between rounded-md border border-border bg-surface px-3 py-2"
                >
                  <FieldName name={fieldById(r.fieldId).name} className="text-sm text-foreground" />
                  <span className="flex items-center gap-2">
                    <span className="tabular text-xs text-muted-foreground">{formatPct(r.uptimePct)}</span>
                    <StatusPill status={r.status} />
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ),
    });
  }

  if (shows("materials")) {
    widgets.push({
      id: "materials",
      content: (
        <Panel
          title="Materials to replenish"
          note="Lowest stock in the catalogue"
          actions={
            <Link
              to="/products"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
            >
              Open catalogue
              <ArrowUpRight className="size-3.5" aria-hidden />
            </Link>
          }
        >
          {watchlist.length === 0 ? (
            <EmptyState
              icon={PackageCheck}
              title="Every product is above its reorder point."
              hint="Nothing in the catalogue needs a purchase request right now."
            />
          ) : (
            <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              {watchlist.map((p) => (
                <li key={p.id} className="flex items-center gap-3 rounded-md border border-border bg-surface px-3 py-2">
                  <ProductPhoto product={p} size={40} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm text-foreground">{p.name}</span>
                    <span className="tabular block text-[11px] text-muted-foreground">
                      {formatNumber(p.stockQty)} {p.unit} · {formatUsd(p.unitPriceUsd)}
                    </span>
                  </span>
                  <StatusPill status={stockStatus(p)} />
                </li>
              ))}
            </ul>
          )}
        </Panel>
      ),
    });
  }

  return (
    <>
      <PageHeader
        eyebrow={`Overview · ${periodLabel(periodId)} · ${personaById(persona).label} view`}
        title="Delta Basin operations overview"
        description={`${personaById(persona).blurb} Everything below is generated pilot data, held to the same shape real source systems will need to deliver.`}
        actions={
          <>
            <PrintButton />
            <PeriodSelector />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {shows("jv") ? (
          <Metric
            label="Net JV variance"
            value={formatSignedPct(s.netVariancePct)}
            tone={Math.abs(s.netVariancePct) >= 1.5 ? "warning" : "positive"}
            delta={`${formatBbl(s.netVarianceBbl)} lifted vs. allocated`}
          />
        ) : null}
        {shows("production") ? (
          <>
            <Metric
              label="Forecast attainment"
              value={formatPct(s.forecastAttainmentPct)}
              tone={s.forecastAttainmentPct < 95 ? "warning" : "positive"}
              delta={`${formatNumber(s.actual)} of ${formatBopd(s.forecast)}`}
            />
            <Metric
              label="Fleet uptime"
              value={formatPct(s.uptimePct)}
              tone={s.uptimePct < 92 ? "critical" : s.uptimePct < 95 ? "warning" : "positive"}
              delta={`${s.wellsOnline} of ${s.wellsTotal} wells online`}
            />
          </>
        ) : null}
        {shows("hse") ? (
          <Metric
            label="TRIR (trailing 12m)"
            value={s.trir.toFixed(2)}
            tone={s.trir > 0.6 ? "warning" : "positive"}
            delta={`${s.monthIncidents} recordable this period`}
          />
        ) : null}
      </div>

      <ReorderableWidgets page="overview" widgets={widgets} />

      <SyntheticNote />
    </>
  );
}
