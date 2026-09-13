import type { ReactNode } from "react";
import { ArrowDown, ArrowUp, ArrowUpDown, ChevronDown, Download, Printer, Sparkles, type LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";
import { toCsv } from "@/data/delta-basin";
import { usePeriod } from "@/components/period-context";
import { useDeltaBasin } from "@/components/delta-basin-context";
import {
  DropdownMenu,
  DropdownMenuCheckboxItem,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";

export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
}: {
  eyebrow: string;
  title: string;
  description: string;
  actions?: ReactNode;
}) {
  return (
    <header className="border-b border-border pb-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="max-w-2xl">
          <p className="tabular text-[11px] uppercase tracking-[0.22em] text-primary">{eyebrow}</p>
          <h1 className="mt-2 font-display text-3xl font-semibold tracking-tight text-foreground">
            {title}
          </h1>
          <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{description}</p>
        </div>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
    </header>
  );
}

/** Small "New" flag for the interactive features added 2026-09 (assistant,
 * tickets, scenario modeling, cash-call approvals, case notes, incident
 * actions, alert thresholds) - reused across the nav and each feature's own
 * page/panel heading so it's spottable both ways. */
export function NewBadge({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "tabular inline-flex items-center gap-1 rounded-sm border border-primary/40 bg-primary/15 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-primary",
        className,
      )}
    >
      <Sparkles className="size-2.5" aria-hidden />
      New
    </span>
  );
}

export function PeriodSelector() {
  const { periodId, setPeriodId } = usePeriod();
  const { periods } = useDeltaBasin();
  return (
    <label className="no-print flex items-center gap-2 rounded-md border border-border bg-surface px-3 py-2">
      <span className="tabular text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        Period
      </span>
      <select
        value={periodId}
        onChange={(e) => setPeriodId(e.target.value)}
        className="tabular bg-transparent text-sm text-foreground outline-none"
        aria-label="Reporting period"
      >
        {[...periods].reverse().map((p) => (
          <option key={p.id} value={p.id} className="bg-surface text-foreground">
            {p.label}
          </option>
        ))}
      </select>
    </label>
  );
}

export function ExportCsvButton({
  filename,
  headers,
  rows,
}: {
  filename: string;
  headers: string[];
  rows: (string | number)[][];
}) {
  const download = () => {
    const blob = new Blob([toCsv(headers, rows)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };
  return (
    <button
      type="button"
      onClick={download}
      className="inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
    >
      <Download className="size-3.5" aria-hidden />
      CSV
    </button>
  );
}

export function Panel({
  title,
  note,
  actions,
  children,
  className,
}: {
  title: string;
  note?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={cn("rounded-lg border border-border bg-card", className)}>
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-3">
        <div>
          <h2 className="font-display text-sm font-semibold tracking-wide text-foreground">{title}</h2>
          {note ? <p className="mt-0.5 text-xs text-muted-foreground">{note}</p> : null}
        </div>
        {actions}
      </div>
      <div className="p-4">{children}</div>
    </section>
  );
}

export function Metric({
  label,
  value,
  unit,
  delta,
  tone = "neutral",
  hint,
  onClick,
  active = false,
}: {
  label: string;
  value: string;
  unit?: string;
  delta?: string;
  tone?: "neutral" | "positive" | "warning" | "critical";
  hint?: string;
  /** When set, the card becomes a toggle button (e.g. "click to filter the
   * table below to just this") instead of a plain readout. */
  onClick?: () => void;
  active?: boolean;
}) {
  const toneClass = {
    neutral: "text-foreground",
    positive: "text-positive",
    warning: "text-warning",
    critical: "text-critical",
  }[tone];
  const body = (
    <>
      <p className="tabular text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{label}</p>
      <p className={cn("tabular mt-2 text-2xl font-semibold tracking-tight", toneClass)}>
        {value}
        {unit ? <span className="ml-1 text-sm font-normal text-muted-foreground">{unit}</span> : null}
      </p>
      {delta ? <p className="tabular mt-1 text-xs text-muted-foreground">{delta}</p> : null}
      {hint ? <p className="mt-2 text-xs leading-relaxed text-muted-foreground">{hint}</p> : null}
    </>
  );

  if (onClick) {
    return (
      <button
        type="button"
        onClick={onClick}
        aria-pressed={active}
        className={cn(
          "w-full rounded-lg border p-4 text-left transition-colors",
          active ? "border-primary/60 bg-primary/10" : "border-border bg-card hover:border-primary/40",
        )}
      >
        {body}
      </button>
    );
  }

  return <div className="rounded-lg border border-border bg-card p-4">{body}</div>;
}

const pillTones: Record<string, string> = {
  "within-tolerance": "border-positive/40 bg-positive/10 text-positive",
  normal: "border-positive/40 bg-positive/10 text-positive",
  settled: "border-positive/40 bg-positive/10 text-positive",
  "in-stock": "border-positive/40 bg-positive/10 text-positive",
  "low-stock": "border-warning/40 bg-warning/10 text-warning",
  "out-of-stock": "border-critical/40 bg-critical/10 text-critical",
  watch: "border-warning/40 bg-warning/10 text-warning",
  pending: "border-warning/40 bg-warning/10 text-warning",
  investigate: "border-critical/40 bg-critical/10 text-critical",
  disputed: "border-critical/40 bg-critical/10 text-critical",
  down: "border-critical/40 bg-critical/10 text-critical",
  submitted: "border-border bg-surface-2 text-muted-foreground",
  "under-review": "border-warning/40 bg-warning/10 text-warning",
};


export function StatusPill({ status }: { status: string }) {
  return (
    <span
      className={cn(
        "tabular inline-flex items-center rounded-sm border px-2 py-0.5 text-[10px] uppercase tracking-[0.12em]",
        pillTones[status] ?? "border-border bg-surface-2 text-muted-foreground",
      )}
    >
      {status.replace(/-/g, " ")}
    </span>
  );
}

export type DataTableColumn = string | { label: string; key: string };

export function DataTable({
  head,
  sort,
  onSort,
  headOverride,
  children,
}: {
  head: DataTableColumn[];
  /** Current sort, if the caller is managing sorted rows itself. */
  sort?: { key: string; dir: "asc" | "desc" } | null;
  /** Called with a column's key when its header is clicked - toggle
   * asc/desc/off is left to the caller so it can re-sort its own rows. */
  onSort?: (key: string) => void;
  /** Replaces the auto-generated header row entirely (e.g. for per-column
   * filter/sort dropdown menus) - `head` is still required for a11y/typing
   * but its rendering is skipped when this is set. */
  headOverride?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="max-h-[520px] overflow-auto rounded-md border border-border">
      <table className="w-full border-collapse text-sm">
        <thead className="sticky top-0 z-10 bg-surface-2">
          {headOverride ?? (
          <tr>
            {head.map((h, i) => {
              const label = typeof h === "string" ? h : h.label;
              const key = typeof h === "string" ? null : h.key;
              const isSorted = key !== null && sort?.key === key;
              return (
                <th
                  key={label + i}
                  scope="col"
                  className={cn(
                    "tabular whitespace-nowrap border-b border-border px-3 py-2 text-[10px] uppercase tracking-[0.14em] text-muted-foreground",
                    i === 0 ? "text-left" : "text-right",
                  )}
                >
                  {key !== null && onSort ? (
                    <button
                      type="button"
                      onClick={() => onSort(key)}
                      className={cn(
                        "inline-flex items-center gap-1 transition-colors hover:text-foreground",
                        i === 0 ? "" : "flex-row-reverse",
                        isSorted ? "text-foreground" : "",
                      )}
                    >
                      {label}
                      {isSorted ? (
                        sort!.dir === "asc" ? (
                          <ArrowUp className="size-3" aria-hidden />
                        ) : (
                          <ArrowDown className="size-3" aria-hidden />
                        )
                      ) : (
                        <ArrowUpDown className="size-3 opacity-40" aria-hidden />
                      )}
                    </button>
                  ) : (
                    label
                  )}
                </th>
              );
            })}
          </tr>
          )}
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

/** A DataTable header cell that opens a dropdown with sort ascending/
 * descending, and - when `values` is given - a checklist to filter that
 * column down to specific values (i.e. Excel-style column header menu). */
export function ColumnMenu({
  label,
  align = "right",
  sortDir,
  onSort,
  values,
  selected,
  onToggleValue,
  onClearFilter,
}: {
  label: string;
  align?: "left" | "right";
  sortDir?: "asc" | "desc" | null;
  onSort?: (dir: "asc" | "desc") => void;
  /** Distinct values present in this column, for the filter checklist. */
  values?: string[];
  selected?: Set<string>;
  onToggleValue?: (v: string) => void;
  onClearFilter?: () => void;
}) {
  const filterActive = !!selected && !!values && selected.size > 0 && selected.size < values.length;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          className={cn(
            "inline-flex items-center gap-1 transition-colors hover:text-foreground",
            align === "left" ? "" : "flex-row-reverse",
            sortDir || filterActive ? "text-foreground" : "",
          )}
        >
          {label}
          {sortDir === "asc" ? (
            <ArrowUp className="size-3" aria-hidden />
          ) : sortDir === "desc" ? (
            <ArrowDown className="size-3" aria-hidden />
          ) : (
            <ChevronDown className={cn("size-3", filterActive ? "text-primary" : "opacity-40")} aria-hidden />
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align={align === "left" ? "start" : "end"} className="w-56">
        {onSort ? (
          <>
            <DropdownMenuItem onSelect={() => onSort("asc")}>
              <ArrowUp className="size-3.5" aria-hidden />
              Sort ascending
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onSort("desc")}>
              <ArrowDown className="size-3.5" aria-hidden />
              Sort descending
            </DropdownMenuItem>
          </>
        ) : null}
        {onSort && values ? <DropdownMenuSeparator /> : null}
        {values && onToggleValue ? (
          <>
            <DropdownMenuLabel className="flex items-center justify-between text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
              Filter
              {filterActive && onClearFilter ? (
                <button type="button" onClick={onClearFilter} className="normal-case text-primary hover:underline">
                  Clear
                </button>
              ) : null}
            </DropdownMenuLabel>
            {values.map((v) => (
              <DropdownMenuCheckboxItem
                key={v}
                checked={!selected || selected.size === 0 || selected.has(v)}
                onSelect={(e) => e.preventDefault()}
                onCheckedChange={() => onToggleValue(v)}
              >
                {v}
              </DropdownMenuCheckboxItem>
            ))}
          </>
        ) : null}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export const SYNTHETIC_LOCATIONS_NOTE =
  "Field and terminal names (Bonny, Qua Iboe, Forcados, Brass) are real Niger Delta locations, used for realism. All volumes, values, partners, and incidents shown are entirely fictional.";

export function SyntheticNote({ children }: { children?: ReactNode }) {
  return (
    <p className="rounded-md border border-dashed border-border bg-surface/60 px-3 py-2 text-xs leading-relaxed text-muted-foreground">
      {children ??
        `Synthetic data, pre-discovery. Figures are shaped to what an CUSTOMER0 engagement is expected to surface and will be re-validated against real source systems. ${SYNTHETIC_LOCATIONS_NOTE} No figure on this page should be read as real operational or commercial intelligence.`}
    </p>
  );
}

export function FieldName({ name, className }: { name: string; className?: string }) {
  return (
    <span className={className} title={SYNTHETIC_LOCATIONS_NOTE}>
      {name}
    </span>
  );
}

export function EmptyState({
  title,
  hint,
  icon: Icon,
}: {
  title: string;
  hint?: string;
  icon?: LucideIcon;
}) {
  return (
    <div className="flex flex-col items-center justify-center rounded-md border border-dashed border-border bg-surface/40 px-4 py-8 text-center">
      {Icon ? <Icon className="mb-2 size-5 text-muted-foreground" aria-hidden /> : null}
      <p className="text-sm text-foreground">{title}</p>
      {hint ? (
        <p className="mt-1 max-w-sm text-xs leading-relaxed text-muted-foreground">{hint}</p>
      ) : null}
    </div>
  );
}

export function PrintButton() {
  return (
    <button
      type="button"
      onClick={() => window.print()}
      className="no-print inline-flex items-center gap-1.5 rounded-md border border-border bg-surface px-2.5 py-1.5 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
    >
      <Printer className="size-3.5" aria-hidden />
      Print
    </button>
  );
}
