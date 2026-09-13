import { FieldName } from "@/components/ui-kit";
import { type ProductionStatus } from "@/data/delta-basin";
import { useDeltaBasin } from "@/components/delta-basin-context";

const statusColor: Record<ProductionStatus, string> = {
  normal: "var(--positive)",
  watch: "var(--warning)",
  down: "var(--critical)",
};

const statusLabel: Record<ProductionStatus, string> = {
  normal: "Normal",
  watch: "Watch",
  down: "Wells down",
};

/**
 * Simplified diagram — NOT a geographic map. Fields sit on the left, export
 * terminals on the right, with a flow line between them coloured by status.
 */
export function FieldSchematic({ periodId }: { periodId: string }) {
  const { fields, productionForPeriod } = useDeltaBasin();
  const rows = productionForPeriod(periodId);
  const byField = new Map(rows.map((r) => [r.fieldId, r]));

  const rowGap = 62;
  const topPad = 34;
  const height = topPad + fields.length * rowGap;
  const fieldX = 30;
  const terminalX = 470;

  const nodes = fields.map((f, i) => ({
    field: f,
    y: topPad + i * rowGap,
    row: byField.get(f.id)!,
  }));

  const terminalNames = Array.from(new Set(fields.map((f) => f.exportPoint))).sort((a, b) => {
    const mean = (name: string) => {
      const ns = nodes.filter((n) => n.field.exportPoint === name);
      return ns.reduce((s, n) => s + n.y, 0) / ns.length;
    };
    return mean(a) - mean(b);
  });
  const terminalGap = (height - topPad * 2) / Math.max(1, terminalNames.length - 1);

  const terminals = terminalNames.map((name, ti) => {
    const connected = nodes.filter((n) => n.field.exportPoint === name);
    const y = topPad + ti * terminalGap;
    const worst: ProductionStatus = connected.some((n) => n.row.status === "down")
      ? "down"
      : connected.some((n) => n.row.status === "watch")
        ? "watch"
        : "normal";
    const bopd = connected.reduce((s, n) => s + n.row.actualBopd, 0);
    return { name, y, worst, bopd, connected };
  });

  return (
    <div className="space-y-3">
      <svg
        viewBox={`0 0 660 ${height}`}
        className="w-full"
        role="img"
        aria-label="Schematic diagram of the five Delta Basin fields, their export terminals and current status"
      >
        {nodes.map((n) => {
          const t = terminals.find((x) => x.name === n.field.exportPoint)!;
          return (
            <path
              key={`flow-${n.field.id}`}
              d={`M ${fieldX + 190} ${n.y} C ${fieldX + 300} ${n.y}, ${terminalX - 100} ${t.y}, ${terminalX} ${t.y}`}
              fill="none"
              stroke={statusColor[n.row.status]}
              strokeWidth={1.5}
              strokeOpacity={0.55}
              strokeDasharray={n.row.status === "down" ? "5 4" : undefined}
            />
          );
        })}

        {nodes.map((n) => (
          <g key={n.field.id}>
            <rect
              x={fieldX}
              y={n.y - 20}
              width={190}
              height={40}
              rx={4}
              fill="var(--surface-2)"
              stroke="var(--border)"
            />
            <circle cx={fieldX + 16} cy={n.y} r={5} fill={statusColor[n.row.status]} />
            <text x={fieldX + 30} y={n.y - 3} fill="var(--foreground)" fontSize={12}>
              {n.field.name}
            </text>
            <text x={fieldX + 30} y={n.y + 12} fill="var(--muted-foreground)" fontSize={10}>
              {n.row.wellsOnline}/{n.row.wellsTotal} wells · {n.row.uptimePct.toFixed(1)}% uptime
            </text>
            <title>{`${n.field.name} — ${statusLabel[n.row.status]}, exports via ${n.field.exportPoint}`}</title>
          </g>
        ))}

        {terminals.map((t) => (
          <g key={t.name}>
            <rect
              x={terminalX}
              y={t.y - 18}
              width={160}
              height={36}
              rx={18}
              fill="var(--surface)"
              stroke={statusColor[t.worst]}
              strokeOpacity={0.6}
            />
            <text x={terminalX + 16} y={t.y - 2} fill="var(--foreground)" fontSize={12}>
              {t.name} terminal
            </text>
            <text x={terminalX + 16} y={t.y + 12} fill="var(--muted-foreground)" fontSize={10}>
              {t.bopd.toLocaleString("en-US")} bopd in
            </text>
            <title>{`${t.name} export terminal — ${statusLabel[t.worst]}`}</title>
          </g>
        ))}
      </svg>

      <div className="flex flex-wrap items-center gap-x-5 gap-y-2 text-xs text-muted-foreground">
        {(["normal", "watch", "down"] as ProductionStatus[]).map((s) => (
          <span key={s} className="inline-flex items-center gap-2">
            <span className="h-2 w-2 rounded-full" style={{ background: statusColor[s] }} />
            {statusLabel[s]}
          </span>
        ))}
        <span>
          Diagram only — positions are schematic, not geographic. Terminals:{" "}
          {terminals.map((t, i) => (
            <span key={t.name}>
              {i > 0 ? ", " : ""}
              <FieldName name={t.name} />
            </span>
          ))}
          .
        </span>
      </div>
    </div>
  );
}
