import { StatTile } from "@/components/StatTile";
import { PageHeader } from "@/components/PageHeader";
import { AllocatedLiftedChart } from "@/components/AllocatedLiftedChart";
import { VarianceTrendChart } from "@/components/VarianceTrendChart";
import { ReconciliationTable } from "@/components/ReconciliationTable";
import { kpis } from "@/lib/data";

const bbl = new Intl.NumberFormat("en-US");

export default function Home() {
  const k = kpis();

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <PageHeader
        eyebrow="JV Reconciliation"
        title="Delta Basin Joint Venture — current period"
        description="Allocated and lifted volumes reconciled across all non-operating partners, in one view none of their individual systems produce today."
      />

      <section className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Total allocated" value={`${bbl.format(k.totalAllocated)} bbl`} />
        <StatTile label="Total lifted" value={`${bbl.format(k.totalLifted)} bbl`} />
        <StatTile
          label="Net variance"
          value={`${k.netVariancePct.toFixed(1)}%`}
          delta={{
            label: `${k.netVarianceBbl >= 0 ? "+" : ""}${bbl.format(k.netVarianceBbl)} bbl vs. allocated`,
            tone: Math.abs(k.netVariancePct) > 4 ? "critical" : Math.abs(k.netVariancePct) > 2 ? "warning" : "good",
          }}
        />
        <StatTile
          label="Open cash calls"
          value={String(k.openCashCalls)}
          delta={{ label: "across 4 partners", tone: k.openCashCalls > 0 ? "warning" : "good" }}
        />
      </section>

      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <AllocatedLiftedChart />
        <VarianceTrendChart />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Partner-level reconciliation</h2>
        <ReconciliationTable />
      </section>
    </main>
  );
}
