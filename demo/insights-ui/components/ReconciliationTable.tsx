import { reconciliationRows, varianceStatus, type CashCallStatus } from "@/lib/data";
import { Badge, type Tone } from "./Badge";

const bbl = new Intl.NumberFormat("en-US");

const cashCallLabel: Record<CashCallStatus, string> = {
  settled: "Settled",
  pending: "Pending",
  disputed: "Disputed",
};
const cashCallTone: Record<CashCallStatus, Tone> = {
  settled: "good",
  pending: "warning",
  disputed: "critical",
};
const varianceLabel: Record<Tone, string> = {
  good: "Within tolerance",
  warning: "Watch",
  critical: "Investigate",
};

export function ReconciliationTable() {
  const rows = reconciliationRows();
  return (
    <div className="overflow-x-auto rounded-card border border-line bg-card">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
            <th className="px-4 py-3">Partner</th>
            <th className="px-4 py-3">Role</th>
            <th className="px-4 py-3">Field</th>
            <th className="px-4 py-3 text-right">Allocated</th>
            <th className="px-4 py-3 text-right">Lifted</th>
            <th className="px-4 py-3">Variance</th>
            <th className="px-4 py-3">Cash call</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const level = varianceStatus(row.allocatedBbl, row.liftedBbl);
            return (
              <tr key={i} className="border-b border-line last:border-0">
                <td className="px-4 py-3 font-medium text-ink-primary">{row.partner}</td>
                <td className="px-4 py-3 text-ink-secondary">{row.partnerRole}</td>
                <td className="px-4 py-3 text-ink-secondary">{row.field}</td>
                <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{bbl.format(row.allocatedBbl)}</td>
                <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{bbl.format(row.liftedBbl)}</td>
                <td className="px-4 py-3">
                  <Badge tone={level} label={varianceLabel[level]} />
                </td>
                <td className="px-4 py-3">
                  <Badge tone={cashCallTone[row.cashCallStatus]} label={cashCallLabel[row.cashCallStatus]} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
