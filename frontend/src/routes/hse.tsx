import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePeriod } from "@/components/period-context";
import { ChevronDown, ChevronRight, ShieldCheck } from "lucide-react";
import {
  DataTable,
  EmptyState,
  ExportCsvButton,
  Metric,
  NewBadge,
  PageHeader,
  Panel,
  PeriodSelector,
  PrintButton,
  SyntheticNote,
} from "@/components/ui-kit";
import { chartAxis, chartMonthAxis, chartTooltip } from "@/components/chart-theme";
import { ChartFrame } from "@/components/chart-frame";
import { incidentSeverities, formatHours, formatCompactNumber } from "@/data/delta-basin";
import { useDeltaBasin } from "@/components/delta-basin-context";
import { useAuth } from "@/components/auth-context";
import { addIncidentAction, closeIncidentAction, getIncidentActions, type IncidentAction } from "@/data/workflow";

export const Route = createFileRoute("/hse")({
  head: () => ({
    meta: [
      { title: "HSE & ESG — Delta Basin" },
      {
        name: "description",
        content:
          "Rolling 12-month TRIR, monthly recordable incident log and exposure-hours trend for the Delta Basin pilot.",
      },
      { property: "og:title", content: "HSE & ESG — Delta Basin" },
      {
        property: "og:description",
        content: "Continuous TRIR, incident log and exposure hours instead of a monthly compile.",
      },
    ],
  }),
  component: HsePage,
});

function timestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });
}

function IncidentActionsRow({ incidentId }: { incidentId: string }) {
  const { user } = useAuth();
  const [items, setItems] = useState<IncidentAction[] | null>(null);
  const [note, setNote] = useState("");
  const [dueDate, setDueDate] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getIncidentActions({ data: { incidentId } })
      .then(setItems)
      .catch(() => setItems([]));
  }, [incidentId]);

  async function add() {
    if (!user || !note.trim() || submitting) return;
    setSubmitting(true);
    try {
      await addIncidentAction({
        data: {
          incidentId,
          note: note.trim(),
          assignedToEmail: null,
          dueDate: dueDate || null,
          createdByEmail: user.email,
          createdByName: user.name,
        },
      });
      setItems((prev) => [
        { id: Date.now(), note: note.trim(), assignedToEmail: null, dueDate: dueDate || null, status: "open", createdByEmail: user.email, createdByName: user.name, createdAt: new Date().toISOString() },
        ...(prev ?? []),
      ]);
      setNote("");
      setDueDate("");
    } finally {
      setSubmitting(false);
    }
  }

  async function close(id: number) {
    setItems((prev) => prev?.map((a) => (a.id === id ? { ...a, status: "closed" } : a)) ?? prev);
    await closeIncidentAction({ data: { id } }).catch(() => {});
  }

  return (
    <tr className="border-b border-border bg-surface/40 last:border-0">
      <td colSpan={6} className="px-3 py-3">
        {items === null ? (
          <p className="text-xs text-muted-foreground">Loading follow-up actions…</p>
        ) : (
          <div className="space-y-2">
            {items.length === 0 ? (
              <p className="text-xs text-muted-foreground">No corrective actions logged yet.</p>
            ) : (
              items.map((a) => (
                <div key={a.id} className="flex items-start justify-between gap-2 rounded-md border border-border bg-card px-3 py-2">
                  <div>
                    <p className="text-xs text-foreground">{a.note}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {a.createdByName ?? a.createdByEmail} · {timestamp(a.createdAt)} UTC
                      {a.dueDate ? ` · due ${a.dueDate}` : ""}
                      {a.status === "closed" ? " · closed" : ""}
                    </p>
                  </div>
                  {a.status === "open" ? (
                    <button
                      type="button"
                      onClick={() => void close(a.id)}
                      className="shrink-0 rounded-md border border-border px-2 py-1 text-[10px] uppercase tracking-[0.08em] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
                    >
                      Close
                    </button>
                  ) : null}
                </div>
              ))
            )}
            <div className="flex flex-wrap gap-2">
              <input
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="Corrective action or follow-up note…"
                className="min-w-[240px] flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
              />
              <input
                type="date"
                value={dueDate}
                onChange={(e) => setDueDate(e.target.value)}
                className="rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground outline-none focus:border-primary"
              />
              <button
                type="button"
                disabled={!note.trim() || submitting}
                onClick={() => void add()}
                className="rounded-md bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Adding…" : "Add"}
              </button>
            </div>
          </div>
        )}
      </td>
    </tr>
  );
}

function HsePage() {
  const { periodId } = usePeriod();
  const { fieldById, incidentSeverityTrend, hseMonths, hseTrend, incidents, periodLabel, trirTrailing12 } =
    useDeltaBasin();
  const trend = hseTrend();
  const monthly = hseMonths.find((m) => m.periodId === periodId)!;
  const log = incidents.filter((i) => i.periodId === periodId);
  const [expandedIncidentId, setExpandedIncidentId] = useState<string | null>(null);
  const trir = trirTrailing12(periodId);
  const severityTrend = incidentSeverityTrend();
  const severityTotal = severityTrend.reduce((t, r) => t + Number(r["total"] ?? 0), 0);
  const recordable12 = hseMonths.reduce((s, m) => s + m.recordableIncidents, 0);
  const hours12 = hseMonths.reduce((s, m) => s + m.hoursWorked, 0);

  return (
    <>
      <PageHeader
        eyebrow={`HSE & ESG · ${periodLabel(periodId)}`}
        title="Safety performance, continuously"
        description="TRIR is recomputed on every load over the same trailing 12-month window, so the figure shown is never older than the last pipeline run."
        actions={
          <>
            <PrintButton />
            <PeriodSelector />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric
          label="TRIR (trailing 12m)"
          value={trir.toFixed(2)}
          tone={trir > 0.6 ? "warning" : "positive"}
          hint="Recordable incidents per 200,000 exposure hours."
        />
        <Metric label="Recordables, 12m" value={String(recordable12)} />
        <Metric label="Exposure hours, 12m" value={formatHours(hours12)} />
        <Metric
          label="This period"
          value={String(monthly.recordableIncidents)}
          unit="recordable"
          tone={monthly.recordableIncidents > 2 ? "warning" : "positive"}
          delta={`${formatHours(monthly.hoursWorked)} worked`}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Incidents & TRIR" note="Monthly recordables against the rolling rate" height={240} expandedHeight={440}>
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <BarChart data={trend}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={34} />
                <Tooltip {...chartTooltip} />
                <Bar isAnimationActive={false} dataKey="incidents" fill="var(--chart-3)" radius={[2, 2, 0, 0]} />
                <Line isAnimationActive={false} type="monotone" dataKey="trir" stroke="var(--chart-1)" strokeWidth={2} dot={false} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
        <ChartFrame title="Cumulative exposure hours" note="Trailing 12 months" height={240} expandedHeight={440}>
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <AreaChart data={trend}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={56} tickFormatter={formatCompactNumber} />
                <Tooltip {...chartTooltip} />
                <Area isAnimationActive={false}
                  type="monotone"
                  dataKey="cumulativeHours"
                  stroke="var(--chart-5)"
                  fill="color-mix(in oklab, var(--chart-5) 18%, transparent)"
                  strokeWidth={2}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
      </div>

      {severityTotal === 0 ? (
        <Panel title="Incident severity mix over time" note="Stacked count by severity, trailing 12 months">
          <EmptyState
            icon={ShieldCheck}
            title="No incidents recorded in the trailing 12 months."
            hint="Nothing to break down by severity across the current window."
          />
        </Panel>
      ) : (
        <ChartFrame
          title="Incident severity mix over time"
          note="Stacked count by severity, trailing 12 months"
          height={260}
          expandedHeight={460}
          actions={
            <ExportCsvButton
              filename="hse-severity-mix.csv"
              headers={["Period", ...incidentSeverities, "Total"]}
              rows={severityTrend.map((r) => [
                String(r["period"]),
                ...incidentSeverities.map((sev) => Number(r[sev] ?? 0)),
                Number(r["total"] ?? 0),
              ])}
            />
          }
        >
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <BarChart data={severityTrend}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={34} allowDecimals={false} />
                <Tooltip {...chartTooltip} />
                <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                <Bar isAnimationActive={false} stackId="sev" dataKey="First aid" fill="var(--chart-5)" />
                <Bar isAnimationActive={false} stackId="sev" dataKey="Medical treatment" fill="var(--chart-1)" />
                <Bar isAnimationActive={false} stackId="sev" dataKey="Restricted work" fill="var(--chart-2)" />
                <Bar isAnimationActive={false} stackId="sev" dataKey="Lost time" fill="var(--chart-3)" />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
      )}
      {severityTotal > 0 ? (
        <p className="-mt-2 text-xs text-muted-foreground">
          First aid cases are not recordable, so they sit outside TRIR but still show where exposure
          is building.
        </p>
      ) : null}

      <Panel
        title="Incident log"
        note={`${periodLabel(periodId)} — click a row to open follow-up actions`}
        actions={
          <div className="flex items-center gap-2">
          <NewBadge />
          <ExportCsvButton
            filename={`hse-incidents-${periodId}.csv`}
            headers={["Date", "Field", "Severity", "Recordable", "Description"]}
            rows={log.map((i) => [
              i.date,
              fieldById(i.fieldId).name,
              i.severity,
              i.recordable ? "yes" : "no",
              i.description,
            ])}
          />
          </div>
        }
      >
        {log.length === 0 ? (
          <EmptyState
            icon={ShieldCheck}
            title="No incidents logged for this period."
            hint="A clean month still counts — exposure hours keep accruing, so TRIR falls as the window rolls forward."
          />
        ) : (
          <DataTable head={["", "Date", "Field", "Severity", "Recordable", "Description"]}>
            {log.map((i) => {
              const expanded = expandedIncidentId === i.id;
              return (
                <>
                  <tr
                    key={i.id}
                    className="cursor-pointer border-b border-border last:border-0 hover:bg-surface-2"
                    onClick={() => setExpandedIncidentId(expanded ? null : i.id)}
                  >
                    <td className="w-6 px-2 py-2 text-muted-foreground">
                      {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                    </td>
                    <td className="tabular px-3 py-2 text-foreground">{i.date}</td>
                    <td className="px-3 py-2 text-right">{fieldById(i.fieldId).name}</td>
                    <td className="px-3 py-2 text-right">{i.severity}</td>
                    <td
                      className={`px-3 py-2 text-right ${i.recordable ? "text-warning" : "text-muted-foreground"}`}
                    >
                      {i.recordable ? "Yes" : "No"}
                    </td>
                    <td className="px-3 py-2 text-right text-muted-foreground">{i.description}</td>
                  </tr>
                  {expanded ? <IncidentActionsRow key={`${i.id}-actions`} incidentId={i.id} /> : null}
                </>
              );
            })}
          </DataTable>
        )}
      </Panel>

      <SyntheticNote />
    </>
  );
}
