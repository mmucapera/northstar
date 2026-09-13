import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
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
import { CheckCircle2, TrendingUp } from "lucide-react";
import {
  DataTable,
  EmptyState,
  ExportCsvButton,
  Metric,
  PageHeader,
  Panel,
  PeriodSelector,
  PrintButton,
  FieldName,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import { chartAxis, chartMonthAxis, chartTooltip } from "@/components/chart-theme";
import { ChartFrame } from "@/components/chart-frame";
import { FieldSchematic } from "@/components/field-schematic";
import { formatBopd, formatNumber, formatPct, formatSigned } from "@/data/delta-basin";
import { useDeltaBasin } from "@/components/delta-basin-context";

export const Route = createFileRoute("/production")({
  head: () => ({
    meta: [
      { title: "Production & Operations — Delta Basin" },
      {
        name: "description",
        content:
          "Actual vs. forecast production in bopd, well uptime by field, fleet trend and downtime causes for the Delta Basin pilot.",
      },
      { property: "og:title", content: "Production & Operations — Delta Basin" },
      {
        property: "og:description",
        content: "Field-level output against forecast, well uptime and downtime causes.",
      },
    ],
  }),
  component: ProductionPage,
});

function ProductionPage() {
  const { periodId } = usePeriod();
  const {
    downtimeCauseDirection,
    downtimeCauses,
    downtimeForPeriod,
    downtimeTrend,
    fieldById,
    periodLabel,
    productionForPeriod,
    summaryForPeriod,
    uptimeTrend,
  } = useDeltaBasin();
  const rows = productionForPeriod(periodId);
  const s = summaryForPeriod(periodId);
  const trend = uptimeTrend();
  const downtime = downtimeForPeriod(periodId);
  const causeTrend = downtimeTrend();
  const causeDirection = downtimeCauseDirection();
  const downtimeHours = downtime.reduce((t, d) => t + d.hours, 0);

  type FieldSortKey = "field" | "actual" | "forecast" | "variance" | "wells" | "uptime" | "status";
  const [fieldSort, setFieldSort] = useState<{ key: FieldSortKey; dir: "asc" | "desc" } | null>(null);
  const sortedRows = useMemo(() => {
    if (!fieldSort) return rows;
    const dir = fieldSort.dir === "asc" ? 1 : -1;
    const valueOf = (r: (typeof rows)[number]): string | number => {
      switch (fieldSort.key) {
        case "field":
          return fieldById(r.fieldId).name;
        case "actual":
          return r.actualBopd;
        case "forecast":
          return r.forecastBopd;
        case "variance":
          return r.actualBopd - r.forecastBopd;
        case "wells":
          return r.wellsOnline;
        case "uptime":
          return r.uptimePct;
        case "status":
          return r.status;
      }
    };
    return [...rows].sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return (av - bv) * dir;
    });
  }, [rows, fieldSort, fieldById]);
  function toggleFieldSort(key: FieldSortKey) {
    setFieldSort((prev) => (prev?.key === key ? (prev.dir === "asc" ? { key, dir: "desc" } : null) : { key, dir: "asc" }));
  }

  return (
    <>
      <PageHeader
        eyebrow={`Production & Operations · ${periodLabel(periodId)}`}
        title="Field output and well uptime"
        description="Status is watch below 94% uptime or under 93% of forecast, and down below 88% uptime. Downtime causes are placeholder categories until source systems capture them."
        actions={
          <>
            <PrintButton />
            <PeriodSelector />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Actual output" value={formatBopd(s.actual)} />
        <Metric label="Forecast" value={formatBopd(s.forecast)} />
        <Metric
          label="Attainment"
          value={formatPct(s.forecastAttainmentPct)}
          tone={s.forecastAttainmentPct < 95 ? "warning" : "positive"}
        />
        <Metric
          label="Wells online"
          value={`${s.wellsOnline}/${s.wellsTotal}`}
          tone={s.uptimePct < 92 ? "critical" : s.uptimePct < 95 ? "warning" : "positive"}
          delta={`${formatPct(s.uptimePct)} fleet uptime`}
        />
      </div>

      <Panel
        title="Field & terminal schematic"
        note="Simplified diagram — not a geographic map"
      >
        <FieldSchematic periodId={periodId} />
      </Panel>

      <Link
        to="/forecasting"
        className="flex items-center justify-between gap-3 rounded-lg border border-primary/30 bg-primary/5 px-4 py-3 text-sm transition-colors hover:bg-primary/10"
      >
        <span className="flex items-center gap-2 text-foreground">
          <TrendingUp className="size-4 text-primary" aria-hidden />
          Model an uptime or demand shift for this data — build a what-if scenario
        </span>
        <span className="tabular text-xs uppercase tracking-[0.1em] text-primary">Open forecasting →</span>
      </Link>

      <Panel
        title="Field detail"
        note={periodLabel(periodId)}
        actions={
          <ExportCsvButton
            filename={`production-${periodId}.csv`}
            headers={["Field", "Export point", "Actual bopd", "Forecast bopd", "Variance bopd", "Wells online", "Wells total", "Uptime %", "Status"]}
            rows={rows.map((r) => [
              fieldById(r.fieldId).name,
              fieldById(r.fieldId).exportPoint,
              r.actualBopd,
              r.forecastBopd,
              r.actualBopd - r.forecastBopd,
              r.wellsOnline,
              r.wellsTotal,
              r.uptimePct,
              r.status,
            ])}
          />
        }
      >
        {rows.length === 0 ? (
          <EmptyState
            title="No field readings for this period."
            hint="Nothing was published by the production pipeline for the selected period."
          />
        ) : (
        <DataTable
          head={[
            { label: "Field", key: "field" },
            { label: "Actual bopd", key: "actual" },
            { label: "Forecast bopd", key: "forecast" },
            { label: "Variance", key: "variance" },
            { label: "Wells", key: "wells" },
            { label: "Uptime %", key: "uptime" },
            { label: "Status", key: "status" },
          ]}
          sort={fieldSort}
          onSort={(key) => toggleFieldSort(key as FieldSortKey)}
        >
          {sortedRows.map((r) => {
            const variance = r.actualBopd - r.forecastBopd;
            return (
              <tr key={r.fieldId} className="border-b border-border last:border-0 hover:bg-surface-2">
                <td className="px-3 py-2">
                  <FieldName name={fieldById(r.fieldId).name} className="block text-foreground" />
                  <FieldName
                    name={fieldById(r.fieldId).exportPoint}
                    className="text-xs text-muted-foreground"
                  />
                </td>
                <td className="tabular px-3 py-2 text-right">{formatNumber(r.actualBopd)}</td>
                <td className="tabular px-3 py-2 text-right text-muted-foreground">
                  {formatNumber(r.forecastBopd)}
                </td>
                <td className={`tabular px-3 py-2 text-right ${variance < 0 ? "text-critical" : "text-positive"}`}>
                  {formatSigned(variance)}
                </td>
                <td className="tabular px-3 py-2 text-right">
                  {r.wellsOnline}/{r.wellsTotal}
                </td>
                <td className="tabular px-3 py-2 text-right">{formatPct(r.uptimePct)}</td>
                <td className="px-3 py-2 text-right">
                  <StatusPill status={r.status} />
                </td>
              </tr>
            );
          })}
        </DataTable>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Fleet uptime trend" note="Trailing 12 months, %" height={240} expandedHeight={440}>
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <LineChart data={trend}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={40} domain={[80, 100]} />
                <Tooltip {...chartTooltip} />
                <Line isAnimationActive={false} type="monotone" dataKey="uptimePct" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
        <Panel title="Downtime causes" note={`Deferred hours, ${periodLabel(periodId)}`}>
          {downtimeHours === 0 ? (
            <EmptyState
              icon={CheckCircle2}
              title="No deferred hours this period."
              hint="Every field ran without recorded downtime, so there is nothing to break down by cause."
            />
          ) : (
          <ResponsiveContainer width="100%" height={240}>
            <BarChart data={downtime} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" horizontal={false} />
              <XAxis type="number" {...chartAxis} />
              <YAxis type="category" dataKey="cause" {...chartAxis} width={140} />
              <Tooltip {...chartTooltip} />
              <Bar isAnimationActive={false} dataKey="hours" fill="var(--chart-2)" radius={[0, 2, 2, 0]} />
            </BarChart>
          </ResponsiveContainer>
          )}
        </Panel>
      </div>

      <ChartFrame
        title="Downtime causes over time"
        note="Deferred hours by cause, trailing 12 months — stacked"
        height={260}
        expandedHeight={460}
        actions={
          <ExportCsvButton
            filename="downtime-causes-trend.csv"
            headers={["Period", ...downtimeCauses, "Total"]}
            rows={causeTrend.map((r) => [
              String(r["period"]),
              ...downtimeCauses.map((c) => Number(r[c] ?? 0)),
              Number(r["total"] ?? 0),
            ])}
          />
        }
      >
        {(h) => (
        <ResponsiveContainer width="100%" height={h}>
          <BarChart data={causeTrend}>
            <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
            <XAxis dataKey="period" {...chartMonthAxis} />
            <YAxis {...chartAxis} width={44} />
            <Tooltip {...chartTooltip} />
            <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
              <Bar
                isAnimationActive={false}
                stackId="downtime"
                dataKey="Facility maintenance"
                fill="var(--chart-1)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                isAnimationActive={false}
                stackId="downtime"
                dataKey="Flowline integrity"
                fill="var(--chart-2)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                isAnimationActive={false}
                stackId="downtime"
                dataKey="Power / generation"
                fill="var(--chart-3)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                isAnimationActive={false}
                stackId="downtime"
                dataKey="Third-party export deferral"
                fill="var(--chart-4)"
                radius={[0, 0, 0, 0]}
              />
              <Bar
                isAnimationActive={false}
                stackId="downtime"
                dataKey="Unplanned shut-in"
                fill="var(--chart-5)"
                radius={[0, 0, 0, 0]}
              />
          </BarChart>
        </ResponsiveContainer>
        )}
      </ChartFrame>
      <Panel title="Cause direction" note="Last six months vs. first six of the window">
        <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {causeDirection.map((d) => (
            <div
              key={d.cause}
              className="flex items-center justify-between gap-3 rounded-md border border-border bg-surface/60 px-3 py-2"
            >
              <span className="text-xs text-foreground">{d.cause}</span>
              <span
                className={`tabular text-xs ${
                  d.direction === "worsening"
                    ? "text-critical"
                    : d.direction === "improving"
                      ? "text-positive"
                      : "text-muted-foreground"
                }`}
              >
                {d.changePct >= 0 ? "+" : ""}
                {d.changePct.toFixed(0)}% · {d.direction}
              </span>
            </div>
          ))}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Direction compares the average deferred hours of the last six months against the first six
          months of the window.
        </p>
      </Panel>

      <SyntheticNote>
        Synthetic data, pre-discovery. Downtime causes in particular are a hypothesis — the category
        list is meant to be corrected in discovery, not defended.
      </SyntheticNote>
    </>
  );
}
