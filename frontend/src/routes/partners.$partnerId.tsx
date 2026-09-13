import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { CheckCircle2, MessageCircleQuestion, XCircle } from "lucide-react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { chartAxis, chartMonthAxis, chartTooltip } from "@/components/chart-theme";
import { ChartFrame } from "@/components/chart-frame";
import {
  DataTable,
  EmptyState,
  ExportCsvButton,
  FieldName,
  Metric,
  NewBadge,
  PageHeader,
  Panel,
  PrintButton,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import { type CashCall, formatNumber, formatPct, formatSignedPct, formatUsd, VARIANCE_TOLERANCE } from "@/data/delta-basin";
import { useDeltaBasin, deltaBasinQueryKey, fetchDeltaBasinRaw } from "@/components/delta-basin-context";
import { useAuth } from "@/components/auth-context";
import {
  addCashCallAction,
  getCashCallActions,
  type CashCallAction,
  type CashCallActionType,
} from "@/data/workflow";

export const Route = createFileRoute("/partners/$partnerId")({
  loader: async ({ params, context }) => {
    const raw = await context.queryClient.ensureQueryData({
      queryKey: deltaBasinQueryKey,
      queryFn: fetchDeltaBasinRaw,
      staleTime: Number.POSITIVE_INFINITY,
    });
    const partner = raw.partners.find((p) => p.id === params.partnerId);
    if (!partner) throw notFound();
    return { name: partner.name };
  },
  head: ({ loaderData }) => {
    if (!loaderData) {
      return { meta: [{ title: "Partner not found — Delta Basin" }, { name: "robots", content: "noindex" }] };
    }
    const title = `${loaderData.name} — JV partner profile`;
    const description = `Equity share, settlement history, dispute count and variance trend for ${loaderData.name} in the Delta Basin joint venture.`;
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
  notFoundComponent: PartnerNotFound,
  component: PartnerProfilePage,
});

function PartnerNotFound() {
  return (
    <>
      <PageHeader eyebrow="JV Reconciliation" title="Partner not found" description="This partner is not part of the Delta Basin joint venture." />
      <Link to="/reconciliation" className="text-sm text-foreground underline">
        Back to JV Reconciliation
      </Link>
    </>
  );
}

const stageLabel: Record<string, string> = {
  submitted: "Submitted",
  "under-review": "Under review",
  settled: "Settled",
  disputed: "Disputed",
};

function timestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
  });
}

const actionLabel: Record<CashCallActionType, string> = {
  approved: "Approved",
  disputed: "Disputed",
  clarification_requested: "Clarification requested",
};

const actionIcon: Record<CashCallActionType, typeof CheckCircle2> = {
  approved: CheckCircle2,
  disputed: XCircle,
  clarification_requested: MessageCircleQuestion,
};

function CashCallTimeline({ call }: { call: CashCall }) {
  const { fieldById, periodLabel } = useDeltaBasin();
  const { user } = useAuth();
  const open = call.status === "pending";
  const [actions, setActions] = useState<CashCallAction[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState<CashCallActionType | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCashCallActions({ data: { periodId: call.periodId, fieldId: call.fieldId, partnerId: call.partnerId } })
      .then((rows) => {
        if (!cancelled) {
          setActions(rows);
          setLoaded(true);
        }
      })
      .catch(() => {
        if (!cancelled) setLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, [call.periodId, call.fieldId, call.partnerId]);

  async function act(action: CashCallActionType) {
    if (!user || submitting) return;
    setSubmitting(action);
    try {
      await addCashCallAction({
        data: {
          periodId: call.periodId,
          fieldId: call.fieldId,
          partnerId: call.partnerId,
          action,
          note: note.trim() || null,
          actedByEmail: user.email,
          actedByName: user.name,
        },
      });
      setActions((prev) => [
        { id: Date.now(), action, note: note.trim() || null, actedByEmail: user.email, actedByName: user.name, actedAt: new Date().toISOString() },
        ...prev,
      ]);
      setNote("");
    } finally {
      setSubmitting(null);
    }
  }

  return (
    <div className="rounded-md border border-border bg-surface/60 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <span className="block text-sm text-foreground">
            <FieldName name={fieldById(call.fieldId).name} />
          </span>
          <span className="text-xs text-muted-foreground">
            {periodLabel(call.periodId)} · {formatUsd(call.amountUsd)}
          </span>
        </div>
        <StatusPill status={call.status} />
      </div>
      <ol className="mt-3 space-y-3 border-l border-border pl-4">
        {call.events.map((e) => (
          <li key={e.stage} className="relative">
            <span
              className={`absolute -left-[21px] top-1 h-2 w-2 rounded-full ${
                e.stage === "disputed"
                  ? "bg-critical"
                  : e.stage === "settled"
                    ? "bg-positive"
                    : e.stage === "under-review"
                      ? "bg-warning"
                      : "bg-muted-foreground"
              }`}
            />
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs uppercase tracking-[0.12em] text-foreground">
                {stageLabel[e.stage] ?? e.stage}
              </span>
              <span className="tabular text-[11px] text-muted-foreground">{timestamp(e.timestamp)} UTC</span>
            </div>
            {e.note ? <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{e.note}</p> : null}
          </li>
        ))}
        {actions.map((a) => (
          <li key={a.id} className="relative">
            <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full bg-primary" />
            <div className="flex flex-wrap items-baseline gap-2">
              <span className="text-xs uppercase tracking-[0.12em] text-primary">{actionLabel[a.action]}</span>
              <span className="tabular text-[11px] text-muted-foreground">{timestamp(a.actedAt)} UTC</span>
              <span className="text-[11px] text-muted-foreground">— {a.actedByName ?? a.actedByEmail}</span>
            </div>
            {a.note ? <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{a.note}</p> : null}
          </li>
        ))}
        {open ? (
          <li className="relative">
            <span className="absolute -left-[21px] top-1 h-2 w-2 rounded-full border border-dashed border-muted-foreground" />
            <span className="text-xs text-muted-foreground">Awaiting settlement or dispute</span>
          </li>
        ) : null}
      </ol>

      {loaded && open && user ? (
        <div className="mt-4 border-t border-border pt-3">
          <input
            type="text"
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional note…"
            className="w-full rounded-md border border-border bg-surface px-3 py-1.5 text-xs text-foreground outline-none placeholder:text-muted-foreground focus:border-primary"
          />
          <div className="mt-2 flex flex-wrap gap-2">
            {(["approved", "disputed", "clarification_requested"] as const).map((a) => {
              const Icon = actionIcon[a];
              return (
                <button
                  key={a}
                  type="button"
                  disabled={submitting !== null}
                  onClick={() => void act(a)}
                  className="flex items-center gap-1.5 rounded-md border border-border bg-surface px-3 py-1.5 text-xs font-medium text-foreground transition-colors hover:bg-surface-2 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  <Icon className="size-3.5" aria-hidden />
                  {submitting === a ? "Saving…" : actionLabel[a]}
                </button>
              );
            })}
          </div>
        </div>
      ) : null}
    </div>
  );
}

function PartnerProfilePage() {
  const { partnerId } = Route.useParams();
  const { partnerProfile, partnerVarianceHistory, currentPeriodId, cashCallsForPartner, periodLabel } =
    useDeltaBasin();
  const profile = partnerProfile(partnerId);
  const history = profile.history;
  const trend = partnerVarianceHistory(partnerId);
  const [selectedPeriod, setSelectedPeriod] = useState<string>(currentPeriodId);
  const calls = cashCallsForPartner(partnerId, selectedPeriod);

  return (
    <>
      <PageHeader
        eyebrow="JV partner profile"
        title={profile.partner.name}
        description={`${profile.partner.role} · ${profile.partner.equityPct}% equity in the Delta Basin joint venture. Settlement history covers the trailing 12 periods.`}
        actions={
          <>
          <PrintButton />
          <Link
            to="/reconciliation"
            className="rounded-md border border-border px-3 py-1.5 text-xs uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
          >
            Back to reconciliation
          </Link>
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Equity share" value={formatPct(profile.partner.equityPct)} delta={profile.partner.role} />
        <Metric
          label="Open disputes"
          value={String(profile.disputeCount)}
          tone={profile.disputeCount > 0 ? "critical" : "positive"}
          delta={`${profile.pendingCount} pending · ${profile.settledCount} settled`}
        />
        <Metric label="Cash calls raised" value={formatUsd(profile.lifetimeCashCallUsd)} delta="Trailing 12 periods" />
        <Metric
          label="Outstanding"
          value={formatUsd(profile.outstandingUsd)}
          tone={profile.outstandingUsd > 0 ? "warning" : "positive"}
          delta="Not yet settled"
        />
      </div>

      <ChartFrame
        title="Variance trend"
        note={`Trailing 12 months, % of allocated. Investigate band ±${VARIANCE_TOLERANCE.investigatePct}%.`}
        height={240}
        expandedHeight={440}
      >
        {(h) => (
          <ResponsiveContainer width="100%" height={h}>
            <LineChart data={trend}>
              <CartesianGrid stroke="var(--grid)" strokeDasharray="3 3" vertical={false} />
              <XAxis dataKey="period" {...chartMonthAxis} />
              <YAxis {...chartAxis} width={40} />
              <Tooltip {...chartTooltip} />
              <ReferenceLine y={VARIANCE_TOLERANCE.investigatePct} stroke="var(--critical)" strokeDasharray="4 4" />
              <ReferenceLine y={-VARIANCE_TOLERANCE.investigatePct} stroke="var(--critical)" strokeDasharray="4 4" />
              <Line isAnimationActive={false} type="monotone" dataKey="variancePct" stroke="var(--chart-2)" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </ChartFrame>

      <Panel
        title="Settlement history"
        note="Select a period to see its cash-call trail"
        actions={
          <ExportCsvButton
            filename={`partner-settlements-${partnerId}.csv`}
            headers={["Period", "Allocated bbl", "Lifted bbl", "Variance bbl", "Variance %", "Cash call USD", "Settled", "Pending", "Disputed"]}
            rows={history.map((h) => [
              h.period.label,
              h.allocatedBbl,
              h.liftedBbl,
              h.varianceBbl,
              h.variancePct.toFixed(2),
              h.cashCallUsd,
              h.settled,
              h.pending,
              h.disputed,
            ])}
          />
        }
      >
        {history.length === 0 ? (
          <EmptyState
            title="No settlement history yet."
            hint="This partner has no cash calls in the trailing 12 periods."
          />
        ) : (
        <DataTable head={["Period", "Allocated bbl", "Lifted bbl", "Variance %", "Cash call", "Disputes", "Status"]}>
          {history.map((h) => (
            <tr
              key={h.period.id}
              onClick={() => setSelectedPeriod(h.period.id)}
              className={`cursor-pointer border-b border-border transition-colors last:border-0 hover:bg-surface-2 ${
                selectedPeriod === h.period.id ? "bg-surface-2" : ""
              }`}
            >
              <td className="px-3 py-2 text-foreground">{h.period.label}</td>
              <td className="tabular px-3 py-2 text-right">{formatNumber(h.allocatedBbl)}</td>
              <td className="tabular px-3 py-2 text-right">{formatNumber(h.liftedBbl)}</td>
              <td className={`tabular px-3 py-2 text-right ${h.varianceBbl < 0 ? "text-critical" : "text-positive"}`}>
                {formatSignedPct(h.variancePct)}
              </td>
              <td className="tabular px-3 py-2 text-right">{formatUsd(h.cashCallUsd)}</td>
              <td className="tabular px-3 py-2 text-right">{h.disputed}</td>
              <td className="px-3 py-2 text-right">
                <StatusPill status={h.status} />
              </td>
            </tr>
          ))}
        </DataTable>
        )}
      </Panel>

      <Panel
        title={`Cash-call trail — ${periodLabel(selectedPeriod)}`}
        note="Submitted → under review → settled or disputed, per field record"
        actions={<NewBadge />}
      >
        {calls.length === 0 ? (
          <EmptyState
            title={`No cash calls raised for ${periodLabel(selectedPeriod)}.`}
            hint="Pick another period in the settlement history above to see its trail."
          />
        ) : (
          <div className="grid gap-3 md:grid-cols-2">
            {calls.map((call) => (
              <CashCallTimeline key={call.id} call={call} />
            ))}
          </div>
        )}
      </Panel>

      <SyntheticNote />
    </>
  );
}
