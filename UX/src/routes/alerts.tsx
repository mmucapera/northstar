import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { SeverityTag, Shell } from "@/components/dashboard";
import { ALERTS, type AlertSeverity, type RangeKey } from "@/lib/data";
import { customerConfig } from "@/lib/config";

export const Route = createFileRoute("/alerts")({
  head: () => {
    const title = `Disruption Log — ${customerConfig.brand.name}`;
    const description =
      "Full disruption and alert log across the supply network, with severity breakdown and search.";
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
  component: AlertsPage,
});

const SEVERITY_FILTERS: Array<AlertSeverity | "All"> = [
  "All",
  "CRITICAL",
  "ELEVATED",
  "WATCH",
];

const SEVERITY_DOT: Record<AlertSeverity, string> = {
  CRITICAL: "bg-danger",
  ELEVATED: "bg-primary",
  WATCH: "bg-steel",
};

function AlertsPage() {
  const [range, setRange] = useState<RangeKey>("24H");
  const [severity, setSeverity] = useState<AlertSeverity | "All">("All");
  const [query, setQuery] = useState("");

  const counts = useMemo(() => {
    const c: Record<AlertSeverity, number> = { CRITICAL: 0, ELEVATED: 0, WATCH: 0 };
    for (const a of ALERTS) c[a.severity] += 1;
    return c;
  }, []);

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    return ALERTS.filter(
      (a) =>
        (severity === "All" || a.severity === severity) &&
        (q === "" ||
          a.title.toLowerCase().includes(q) ||
          a.detail.toLowerCase().includes(q)),
    );
  }, [severity, query]);

  return (
    <Shell range={range} onRangeChange={setRange}>
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-sm font-semibold tracking-tight">Disruption Log</h1>
          <p className="mt-0.5 font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            {ALERTS.length} total · {rows.length} shown
          </p>
        </div>
      </div>

      {/* Severity breakdown */}
      <section className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
        {(["CRITICAL", "ELEVATED", "WATCH"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setSeverity(severity === s ? "All" : s)}
            className={`rounded-xl bg-card p-4 text-left ring-1 transition-colors ${
              severity === s ? "ring-primary" : "ring-border hover:ring-border"
            }`}
          >
            <div className="flex items-center justify-between">
              <span className={`size-1.5 rounded-full ${SEVERITY_DOT[s]}`} />
              <span className="font-mono text-[10px] tracking-wider text-muted-foreground">
                {((counts[s] / Math.max(ALERTS.length, 1)) * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-2 font-mono text-2xl leading-none font-semibold">
              {counts[s]}
            </div>
            <div className="mt-1 font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
              {s}
            </div>
            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-hi">
              <div
                className={`h-full rounded-full ${SEVERITY_DOT[s]}`}
                style={{
                  width: `${(counts[s] / Math.max(ALERTS.length, 1)) * 100}%`,
                }}
              />
            </div>
          </button>
        ))}
      </section>

      <div className="mt-3 rounded-xl bg-card ring-1 ring-border">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="relative flex size-1.5">
              <span className="absolute inline-flex h-full w-full animate-pulse-soft rounded-full bg-danger" />
              <span className="relative inline-flex size-1.5 rounded-full bg-danger" />
            </span>
            <h2 className="text-sm font-semibold tracking-tight">Feed</h2>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search title, detail…"
              className="w-56 rounded-lg bg-background px-3 py-1.5 font-mono text-xs text-foreground ring-1 ring-border outline-none placeholder:text-muted-foreground focus:ring-ring"
            />
            <div className="flex items-center gap-1">
              {SEVERITY_FILTERS.map((f) => (
                <button
                  key={f}
                  onClick={() => setSeverity(f)}
                  className={`rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wider uppercase transition-colors ${
                    severity === f
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground"
                  }`}
                >
                  {f}
                </button>
              ))}
            </div>
          </div>
        </div>

        <div className="divide-y divide-border/70">
          {rows.map((a) => (
            <div key={a.title} className="px-4 py-3.5">
              <div className="flex items-center gap-2">
                <SeverityTag severity={a.severity} />
                <span className="font-mono text-[10px] text-muted-foreground">
                  {a.time}
                </span>
              </div>
              <p className="mt-1.5 text-xs text-foreground">{a.title}</p>
              <p className="mt-0.5 font-mono text-[10px] text-muted-foreground">
                {a.detail}
              </p>
            </div>
          ))}
          {rows.length === 0 && (
            <div className="px-4 py-8 text-center font-mono text-xs text-muted-foreground">
              No alerts match the current filters.
            </div>
          )}
        </div>
      </div>

      <footer className="mt-4 flex items-center justify-between font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
        <span>{customerConfig.brand.footer}</span>
        <span className="flex items-center gap-2">
          <span className="size-1.5 rounded-full bg-ok" />
          All systems nominal · last sync 12s ago
        </span>
      </footer>
    </Shell>
  );
}
