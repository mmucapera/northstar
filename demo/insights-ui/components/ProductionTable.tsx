import { productionRows, opsStatusTone, type OpsStatus } from "@/lib/data";
import { Badge } from "./Badge";

const num = new Intl.NumberFormat("en-US");

const statusLabel: Record<OpsStatus, string> = {
  normal: "Normal",
  watch: "Watch",
  down: "Down",
};

export function ProductionTable() {
  const rows = productionRows();
  return (
    <div className="overflow-x-auto rounded-card border border-line bg-card">
      <table className="w-full min-w-[720px] text-sm">
        <thead>
          <tr className="border-b border-line text-left text-xs font-medium uppercase tracking-wide text-ink-muted">
            <th className="px-4 py-3">Field</th>
            <th className="px-4 py-3">Export point</th>
            <th className="px-4 py-3 text-right">Wells online</th>
            <th className="px-4 py-3 text-right">Uptime</th>
            <th className="px-4 py-3 text-right">Actual (bopd)</th>
            <th className="px-4 py-3">Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b border-line last:border-0">
              <td className="px-4 py-3 font-medium text-ink-primary">{row.field}</td>
              <td className="px-4 py-3 text-ink-secondary">{row.exportPoint}</td>
              <td className="px-4 py-3 text-right tabular-nums text-ink-primary">
                {row.wellsOnline}/{row.wellsTotal}
              </td>
              <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{row.uptimePct.toFixed(1)}%</td>
              <td className="px-4 py-3 text-right tabular-nums text-ink-primary">{num.format(row.actualBopd)}</td>
              <td className="px-4 py-3">
                <Badge tone={opsStatusTone(row.opsStatus)} label={statusLabel[row.opsStatus]} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
