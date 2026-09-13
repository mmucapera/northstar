import { createFileRoute, Link } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight } from "lucide-react";
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
  FieldName,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import { chartAxis, chartMonthAxis, chartTooltip } from "@/components/chart-theme";
import { ChartFrame } from "@/components/chart-frame";
import { formatNumber, formatPct, formatSigned, formatSignedPct, VARIANCE_TOLERANCE } from "@/data/delta-basin";
import { useDeltaBasin } from "@/components/delta-basin-context";
import { useAuth } from "@/components/auth-context";
import { addCaseNote, getCaseNotes, resolveCaseNote, type ReconciliationCaseNote } from "@/data/workflow";

export const Route = createFileRoute("/reconciliation")({
  head: () => ({
    meta: [
      { title: "JV Reconciliation — Delta Basin" },
      {
        name: "description",
        content:
          "Allocated vs. lifted volumes, variance tolerance flags and cash-call status per joint-venture partner and field.",
      },
      { property: "og:title", content: "JV Reconciliation — Delta Basin" },
      {
        property: "og:description",
        content: "Partner-level allocated vs. lifted variance and cash-call status for the current period.",
      },
    ],
  }),
  component: ReconciliationPage,
});

function timestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" });
}

function CaseNotesRow({ periodId, fieldId, partnerId }: { periodId: string; fieldId: string; partnerId: string }) {
  const { user } = useAuth();
  const [notes, setNotes] = useState<ReconciliationCaseNote[] | null>(null);
  const [text, setText] = useState("");
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    getCaseNotes({ data: { periodId, fieldId, partnerId } })
      .then(setNotes)
      .catch(() => setNotes([]));
  }, [periodId, fieldId, partnerId]);

  async function add() {
    if (!user || !text.trim() || submitting) return;
    setSubmitting(true);
    try {
      await addCaseNote({
        data: {
          periodId,
          fieldId,
          partnerId,
          note: text.trim(),
          assignedToEmail: null,
          createdByEmail: user.email,
          createdByName: user.name,
        },
      });
      setNotes((prev) => [
        { id: Date.now(), note: text.trim(), assignedToEmail: null, status: "open", createdByEmail: user.email, createdByName: user.name, createdAt: new Date().toISOString() },
        ...(prev ?? []),
      ]);
      setText("");
    } finally {
      setSubmitting(false);
    }
  }

  async function resolve(id: number) {
    setNotes((prev) => prev?.map((n) => (n.id === id ? { ...n, status: "resolved" } : n)) ?? prev);
    await resolveCaseNote({ data: { id } }).catch(() => {});
  }

  return (
    <tr className="border-b border-border bg-surface/40 last:border-0">
      <td colSpan={8} className="px-3 py-3">
        {notes === null ? (
          <p className="text-xs text-muted-foreground">Loading notes…</p>
        ) : (
          <div className="space-y-2">
            {notes.length === 0 ? (
              <p className="text-xs text-muted-foreground">No case notes yet for this record.</p>
            ) : (
              notes.map((n) => (
                <div key={n.id} className="flex items-start justify-between gap-2 rounded-md border border-border bg-card px-3 py-2">
                  <div>
                    <p className="text-xs text-foreground">{n.note}</p>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">
                      {n.createdByName ?? n.createdByEmail} · {timestamp(n.createdAt)} UTC
                      {n.status === "resolved" ? " · resolved" : ""}
                    </p>
                  </div>
                  {n.status === "open" ? (
                    <button
                      type="button"
                      onClick={() => void resolve(n.id)}
                      className="shrink-0 rounded-md border border-border px-2 py-1 text-[10px] uppercase tracking-[0.08em] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
                    >
                      Resolve
                    </button>
                  ) : null}
                </div>
              ))
            )}
            <div className="flex gap-2">
              <input
                type="text"
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Add a note — assign an owner, explain the variance…"
                className="flex-1 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
              />
              <button
                type="button"
                disabled={!text.trim() || submitting}
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

function ReconciliationPage() {
  const { periodId } = usePeriod();
  const {
    fieldById,
    netVarianceTrend,
    partnerById,
    partnerVarianceHistory,
    periodLabel,
    reconciliationByPartner,
    reconciliationForPeriod,
    summaryForPeriod,
  } = useDeltaBasin();
  const summary = summaryForPeriod(periodId);
  const byPartner = reconciliationByPartner(periodId);
  const [selected, setSelected] = useState<string>(byPartner[0]!.partner.id);
  const history = partnerVarianceHistory(selected);
  const detail = reconciliationForPeriod(periodId).filter((r) => r.partnerId === selected);
  const trend = netVarianceTrend();
  const [expandedFieldId, setExpandedFieldId] = useState<string | null>(null);

  type Sort<K extends string> = { key: K; dir: "asc" | "desc" } | null;
  function toggleSort<K extends string>(setter: (v: Sort<K>) => void, prev: Sort<K>, key: K) {
    if (prev?.key === key) setter(prev.dir === "asc" ? { key, dir: "desc" } : null);
    else setter({ key, dir: "asc" });
  }
  function applySort<T>(rows: T[], sort: Sort<string>, valueOf: (r: T, key: string) => string | number) {
    if (!sort) return rows;
    const dir = sort.dir === "asc" ? 1 : -1;
    return [...rows].sort((a, b) => {
      const av = valueOf(a, sort.key);
      const bv = valueOf(b, sort.key);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return (av - bv) * dir;
    });
  }

  type PartnerSortKey = "partner" | "equity" | "allocated" | "lifted" | "variance" | "variancePct" | "flag" | "cashCall";
  const [partnerSort, setPartnerSort] = useState<Sort<PartnerSortKey>>(null);
  const sortedPartners = applySort(byPartner, partnerSort, (p, key) => {
    switch (key as PartnerSortKey) {
      case "partner":
        return p.partner.name;
      case "equity":
        return p.partner.equityPct;
      case "allocated":
        return p.allocatedBbl;
      case "lifted":
        return p.liftedBbl;
      case "variance":
        return p.varianceBbl;
      case "variancePct":
        return p.variancePct;
      case "flag":
        return p.flag;
      case "cashCall":
        return p.cashCallStatus;
    }
  });

  type FieldSortKey = "field" | "exportPoint" | "allocated" | "lifted" | "variancePct" | "flag" | "cashCall";
  const [fieldSort, setFieldSort] = useState<Sort<FieldSortKey>>(null);
  const sortedDetail = applySort(detail, fieldSort, (r, key) => {
    switch (key as FieldSortKey) {
      case "field":
        return fieldById(r.fieldId).name;
      case "exportPoint":
        return fieldById(r.fieldId).exportPoint;
      case "allocated":
        return r.allocatedBbl;
      case "lifted":
        return r.liftedBbl;
      case "variancePct":
        return r.variancePct;
      case "flag":
        return r.flag;
      case "cashCall":
        return r.cashCallStatus;
    }
  });

  return (
    <>
      <PageHeader
        eyebrow={`JV Reconciliation · ${periodLabel(periodId)}`}
        title="Allocated vs. lifted, per partner"
        description={`Variance is flagged watch at ${VARIANCE_TOLERANCE.watchPct}% and investigate at ${VARIANCE_TOLERANCE.investigatePct}% of allocated volume. Cash-call status follows the disputed record, not the average.`}
        actions={
          <>
            <PrintButton />
            <PeriodSelector />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Allocated" value={formatNumber(summary.allocated)} unit="bbl" />
        <Metric label="Lifted" value={formatNumber(summary.lifted)} unit="bbl" />
        <Metric
          label="Net variance"
          value={formatSignedPct(summary.netVariancePct)}
          tone={Math.abs(summary.netVariancePct) >= VARIANCE_TOLERANCE.watchPct ? "warning" : "positive"}
          delta={`${formatSigned(summary.netVarianceBbl)} bbl`}
        />
        <Metric
          label="Cash calls"
          value={`${summary.disputedCount} disputed`}
          tone={summary.disputedCount > 0 ? "critical" : "positive"}
          delta={`${summary.pendingCount} pending settlement`}
        />
      </div>

      <Panel
        title="Partner summary"
        note="Click a partner name for their full profile, or a row to drill in below"
        actions={
          <ExportCsvButton
            filename={`jv-reconciliation-${periodId}.csv`}
            headers={["Partner", "Role", "Allocated bbl", "Lifted bbl", "Variance bbl", "Variance %", "Flag", "Cash call", "Cash call USD"]}
            rows={byPartner.map((p) => [
              p.partner.name,
              p.partner.role,
              p.allocatedBbl,
              p.liftedBbl,
              p.varianceBbl,
              p.variancePct.toFixed(2),
              p.flag,
              p.cashCallStatus,
              p.cashCallUsd,
            ])}
          />
        }
      >
        <DataTable
          head={[
            { label: "Partner", key: "partner" },
            { label: "Equity %", key: "equity" },
            { label: "Allocated bbl", key: "allocated" },
            { label: "Lifted bbl", key: "lifted" },
            { label: "Variance bbl", key: "variance" },
            { label: "Variance %", key: "variancePct" },
            { label: "Flag", key: "flag" },
            { label: "Cash call", key: "cashCall" },
          ]}
          sort={partnerSort}
          onSort={(key) => toggleSort(setPartnerSort, partnerSort, key as PartnerSortKey)}
        >
          {sortedPartners.map((p) => (
            <tr
              key={p.partner.id}
              onClick={() => setSelected(p.partner.id)}
              className={`cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-surface-2 ${
                selected === p.partner.id ? "bg-surface-2" : ""
              }`}
            >
              <td className="px-3 py-2">
                <Link
                  to="/partners/$partnerId"
                  params={{ partnerId: p.partner.id }}
                  onClick={(e) => e.stopPropagation()}
                  className="block text-foreground underline decoration-border underline-offset-4 hover:decoration-foreground"
                >
                  {p.partner.name}
                </Link>
                <span className="text-xs text-muted-foreground">{p.partner.role}</span>
              </td>
              <td className="tabular px-3 py-2 text-right text-muted-foreground">{formatPct(p.partner.equityPct)}</td>
              <td className="tabular px-3 py-2 text-right">{formatNumber(p.allocatedBbl)}</td>
              <td className="tabular px-3 py-2 text-right">{formatNumber(p.liftedBbl)}</td>
              <td
                className={`tabular px-3 py-2 text-right ${p.varianceBbl < 0 ? "text-critical" : "text-positive"}`}
              >
                {formatSigned(p.varianceBbl)}
              </td>
              <td className="tabular px-3 py-2 text-right">{formatSignedPct(p.variancePct)}</td>
              <td className="px-3 py-2 text-right">
                <StatusPill status={p.flag} />
              </td>
              <td className="px-3 py-2 text-right">
                <StatusPill status={p.cashCallStatus} />
              </td>
            </tr>
          ))}
        </DataTable>
      </Panel>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartFrame title="Net variance trend" note="JV level, trailing 12 months" height={230} expandedHeight={440}>
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <BarChart data={trend}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={40} />
                <Tooltip {...chartTooltip} />
                <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                <Bar isAnimationActive={false} dataKey="variancePct" name="Net variance %" fill="var(--chart-1)" radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
        <ChartFrame title={`${partnerById(selected).name} — variance history`} note="Trailing 12 months, %" height={230} expandedHeight={440}>
          {(h) => (
            <ResponsiveContainer width="100%" height={h}>
              <LineChart data={history}>
                <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="period" {...chartMonthAxis} />
                <YAxis {...chartAxis} width={40} />
                <Tooltip {...chartTooltip} />
                <Legend wrapperStyle={{ fontSize: 11, color: "var(--muted-foreground)" }} />
                <Line isAnimationActive={false} type="monotone" dataKey="variancePct" name="Variance %" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          )}
        </ChartFrame>
      </div>

      <Panel
        title={`${partnerById(selected).name} — field records, ${periodLabel(periodId)}`}
        note="Click a row to open case notes"
        actions={
          <div className="flex items-center gap-2">
          <NewBadge />
          <ExportCsvButton
            filename={`jv-records-${selected}-${periodId}.csv`}
            headers={["Field", "Export point", "Allocated bbl", "Lifted bbl", "Variance bbl", "Variance %", "Flag", "Cash call"]}
            rows={detail.map((r) => [
              fieldById(r.fieldId).name,
              fieldById(r.fieldId).exportPoint,
              r.allocatedBbl,
              r.liftedBbl,
              r.varianceBbl,
              r.variancePct.toFixed(2),
              r.flag,
              r.cashCallStatus,
            ])}
          />
          </div>
        }
      >
        {detail.length === 0 ? (
          <EmptyState
            title="No field records for this partner in this period."
            hint="Either no liftings were allocated, or the period predates this partner joining the venture."
          />
        ) : (
        <DataTable
          head={[
            "",
            { label: "Field", key: "field" },
            { label: "Export point", key: "exportPoint" },
            { label: "Allocated bbl", key: "allocated" },
            { label: "Lifted bbl", key: "lifted" },
            { label: "Variance %", key: "variancePct" },
            { label: "Flag", key: "flag" },
            { label: "Cash call", key: "cashCall" },
          ]}
          sort={fieldSort}
          onSort={(key) => toggleSort(setFieldSort, fieldSort, key as FieldSortKey)}
        >
          {sortedDetail.map((r) => {
            const expanded = expandedFieldId === r.fieldId;
            return (
              <>
                <tr
                  key={r.fieldId}
                  className="cursor-pointer border-b border-border last:border-0 hover:bg-surface-2"
                  onClick={() => setExpandedFieldId(expanded ? null : r.fieldId)}
                >
                  <td className="w-6 px-2 py-2 text-muted-foreground">
                    {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
                  </td>
                  <td className="px-3 py-2 text-foreground">
                    <FieldName name={fieldById(r.fieldId).name} />
                  </td>
                  <td className="px-3 py-2 text-right text-muted-foreground">
                    <FieldName name={fieldById(r.fieldId).exportPoint} />
                  </td>
                  <td className="tabular px-3 py-2 text-right">{formatNumber(r.allocatedBbl)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatNumber(r.liftedBbl)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatSignedPct(r.variancePct)}</td>
                  <td className="px-3 py-2 text-right">
                    <StatusPill status={r.flag} />
                  </td>
                  <td className="px-3 py-2 text-right">
                    <StatusPill status={r.cashCallStatus} />
                  </td>
                </tr>
                {expanded ? (
                  <CaseNotesRow key={`${r.fieldId}-notes`} periodId={periodId} fieldId={r.fieldId} partnerId={selected} />
                ) : null}
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
