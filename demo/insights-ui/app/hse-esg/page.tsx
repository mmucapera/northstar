import { StatTile } from "@/components/StatTile";
import { PageHeader } from "@/components/PageHeader";
import { IncidentTrendChart } from "@/components/IncidentTrendChart";
import { HoursWorkedChart } from "@/components/HoursWorkedChart";
import { hseKpis, monthlyHseIncidents } from "@/lib/data";

const num = new Intl.NumberFormat("en-US");

export default function HseEsgPage() {
  const k = hseKpis();

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <PageHeader
        eyebrow="HSE & ESG"
        title="Delta Basin Joint Venture — safety performance"
        description="Recordable incidents and exposure hours rolled up across the JV, tracked against the industry-standard TRIR benchmark."
      />

      <section className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile
          label="TRIR"
          value={k.trir.toFixed(2)}
          delta={{ label: "per 200,000 hrs", tone: k.trir > 1 ? "critical" : k.trir > 0.5 ? "warning" : "good" }}
        />
        <StatTile label="Recordable incidents, trailing 12mo" value={String(k.trailing12moIncidents)} />
        <StatTile
          label="Last month"
          value={String(k.lastMonthIncidents)}
          delta={{ label: k.lastMonthIncidents > 0 ? "recordable incident(s)" : "incident-free", tone: k.lastMonthIncidents > 0 ? "warning" : "good" }}
        />
        <StatTile label="Exposure hours, trailing 12mo" value={`${num.format(k.hoursWorkedTrailing12mo)} hrs`} />
      </section>

      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <IncidentTrendChart />
        <HoursWorkedChart />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Monthly incident log</h2>
        <div className="overflow-x-auto rounded-card border border-line bg-card">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
                <th className="px-4 py-3">Month</th>
                <th className="px-4 py-3 text-right">Recordable incidents</th>
                <th className="px-4 py-3 text-right">Exposure hours (12mo cum.)</th>
              </tr>
            </thead>
            <tbody>
              {monthlyHseIncidents.map((m, i) => (
                <tr key={i} className="border-b border-line last:border-0">
                  <td className="px-4 py-3 font-medium text-ink-primary">{m.label}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{m.recordableIncidentCount}</td>
                  <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{num.format(m.hoursWorkedTrailing12mo)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </main>
  );
}
