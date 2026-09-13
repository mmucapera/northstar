import type { Tone } from "./Badge";

const deltaClass: Record<Tone, string> = {
  good: "text-status-good",
  warning: "text-status-warning",
  critical: "text-status-critical",
};

export function StatTile({
  label,
  value,
  delta,
}: {
  label: string;
  value: string;
  delta?: { label: string; tone: Tone };
}) {
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="text-xs font-medium text-ink-muted">{label}</div>
      <div className="mt-1.5 text-2xl font-semibold text-ink-primary">{value}</div>
      {delta && <div className={`mt-1 text-xs font-medium ${deltaClass[delta.tone]}`}>{delta.label}</div>}
    </div>
  );
}
