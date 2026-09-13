export type Tone = "good" | "warning" | "critical";

const toneClass: Record<Tone, string> = {
  good: "text-status-good bg-status-good/10",
  warning: "text-status-warning bg-status-warning/15",
  critical: "text-status-critical bg-status-critical/10",
};

const toneIcon: Record<Tone, string> = {
  good: "✓",
  warning: "●",
  critical: "⚠",
};

export function Badge({ tone, label, icon }: { tone: Tone; label: string; icon?: string }) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-xs font-medium ${toneClass[tone]}`}>
      <span aria-hidden="true">{icon ?? toneIcon[tone]}</span>
      {label}
    </span>
  );
}
