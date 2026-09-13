import { Link } from "@tanstack/react-router";
import { useEffect, useState, type CSSProperties, type ReactNode } from "react";
import {
  PRODUCTION_TREND,
  RANGES,
  type RangeKey,
  type ShipmentStatus,
} from "@/lib/data";
import { customerConfig } from "@/lib/config";

export function Shell({
  children,
  range,
  onRangeChange,
  onExport,
}: {
  children: ReactNode;
  range: RangeKey;
  onRangeChange: (r: RangeKey) => void;
  onExport?: () => void;
}) {
  const theme = customerConfig.theme;

  return (
    <div
      className="min-h-screen bg-background font-sans text-sm text-foreground antialiased"
      style={
        {
          "--primary": theme.primary,
          "--ring": theme.primary,
          "--steel": theme.steel,
          "--copper": theme.copper,
          "--danger": theme.danger,
          "--ok": theme.ok,
        } as CSSProperties
      }
    >
      <header className="border-b border-border">
        <div className="mx-auto flex max-w-[1440px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-2.5">
          <Link to="/" className="flex items-center gap-2.5">
            <div className="grid size-7 place-items-center rounded-md bg-primary font-mono text-xs font-semibold text-primary-foreground">
              {customerConfig.brand.logoInitials}
            </div>
            <div className="leading-none">
              <div className="text-sm font-semibold tracking-tight">
                {customerConfig.brand.name}
              </div>
              <div className="font-mono text-[10px] tracking-[0.2em] text-muted-foreground uppercase">
                {customerConfig.brand.tagline}
              </div>
            </div>
          </Link>

          <nav className="ml-2 hidden items-center gap-1 font-mono text-[11px] tracking-wider uppercase md:flex">
            <NavItem to="/" label={customerConfig.nav.overview} exact />
            <NavItem to="/shipments" label={customerConfig.nav.shipments} />
            <NavItem to="/inventory" label={customerConfig.nav.inventory} />
            <NavItem to="/alerts" label={customerConfig.nav.alerts} />
            <NavItem to="/insights" label={customerConfig.nav.insights} />
          </nav>

          <div className="ml-auto flex flex-wrap items-center gap-2">
            <div className="flex items-center gap-2 rounded-lg bg-card px-3 py-1.5 ring-1 ring-border">
              <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                Range
              </span>
              {RANGES.map((r, i) => (
                <span key={r} className="flex items-center gap-2">
                  {i > 0 && <span className="text-muted-foreground/50">/</span>}
                  <button
                    onClick={() => onRangeChange(r)}
                    className={`font-mono text-xs transition-colors ${
                      range === r
                        ? "text-foreground"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                  >
                    {r}
                  </button>
                </span>
              ))}
            </div>

            <div className="flex items-center gap-2 rounded-lg bg-card px-3 py-1.5 ring-1 ring-border">
              <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                Region
              </span>
              <span className="flex items-center gap-1.5 font-mono text-xs text-foreground">
                <span className="size-1.5 rounded-full bg-steel" /> All
              </span>
            </div>

            <div className="hidden items-center gap-2 rounded-lg bg-card px-3 py-1.5 ring-1 ring-border md:flex">
              <span className="relative flex size-2">
                <span className="absolute inline-flex h-full w-full animate-pulse-soft rounded-full bg-ok" />
                <span className="relative inline-flex size-2 rounded-full bg-ok" />
              </span>
              <span className="font-mono text-[11px] text-ok">LIVE</span>
              <LiveClock />
            </div>

            <button
              onClick={onExport}
              className="flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-primary-foreground ring-1 ring-primary transition-colors hover:bg-primary/90"
            >
              Export
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-[1440px] px-4 py-4">{children}</main>
    </div>
  );
}

function NavItem({
  to,
  label,
  exact,
}: {
  to: string;
  label: string;
  exact?: boolean;
}) {
  return (
    <Link
      to={to}
      activeOptions={{ exact: exact ?? false }}
      className="rounded-md px-2.5 py-1 text-muted-foreground transition-colors hover:text-foreground"
      activeProps={{ className: "text-foreground bg-card ring-1 ring-border" }}
    >
      {label}
    </Link>
  );
}

function LiveClock() {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => {
    setNow(new Date());
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <>
      <span className="text-muted-foreground/50">·</span>
      <span className="font-mono text-[11px] text-muted-foreground">
        {now
          ? now.toLocaleTimeString("en-GB", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
              timeZone: "UTC",
            }) + " UTC"
          : "US/EU/ME"}
      </span>
    </>
  );
}

export function Sparkline({
  data,
  tone = "steel",
}: {
  data: number[];
  tone?: "steel" | "copper";
}) {
  const bar = tone === "steel" ? "bg-steel" : "bg-copper";
  return (
    <div className="mt-3 flex h-8 items-end gap-0.5">
      {data.map((h, i) => (
        <span
          key={i}
          className={`w-1 rounded-t-sm ${bar}`}
          style={{ height: `${h}%`, opacity: 0.35 + (i / data.length) * 0.65 }}
        />
      ))}
    </div>
  );
}

const STATUS_STYLE: Record<ShipmentStatus, string> = {
  "In Transit": "bg-steel/15 text-steel",
  Loading: "bg-copper/15 text-copper",
  Delayed: "bg-danger/15 text-danger",
  Queued: "bg-muted text-muted-foreground",
};

export function StatusChip({ status }: { status: ShipmentStatus }) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[10px] ${STATUS_STYLE[status]}`}
    >
      <span className="size-1.5 rounded-full bg-current" />
      {status}
    </span>
  );
}

const SEVERITY_STYLE: Record<string, string> = {
  CRITICAL: "bg-danger/15 text-danger",
  ELEVATED: "bg-primary/15 text-primary",
  WATCH: "bg-steel/15 text-steel",
};

export function SeverityTag({ severity }: { severity: string }) {
  return (
    <span
      className={`rounded-full px-2 py-0.5 font-mono text-[10px] ${SEVERITY_STYLE[severity] ?? SEVERITY_STYLE["WATCH"]}`}
    >
      {severity}
    </span>
  );
}

// y-domain 3.0–5.0 → y px in 0..160 viewBox
function toY(v: number) {
  return 160 - ((v - 3.0) / 2.0) * 150 - 5;
}

export function TrendChart({ range }: { range: RangeKey }) {
  const points = PRODUCTION_TREND[range];
  const x = (i: number) => (i * 640) / (points.length - 1);
  const actual = points.map((p, i) => `${x(i)},${toY(p.actual)}`).join(" ");
  const target = points.map((p, i) => `${x(i)},${toY(p.target)}`).join(" ");
  const area = `${actual} 640,160 0,160`;
  const last = points[points.length - 1]!;

  return (
    <div className="mt-4 flex h-40 items-stretch gap-2">
      <div className="flex flex-col justify-between py-0.5 font-mono text-[9px] text-muted-foreground">
        <span>5.0</span>
        <span>4.0</span>
        <span>3.0</span>
      </div>
      <div className="relative flex-1">
        <div className="absolute inset-0 flex flex-col justify-between">
          <div className="border-t border-border/60" />
          <div className="border-t border-border/60" />
          <div className="border-t border-border/60" />
          <div className="border-t border-border/60" />
        </div>
        <svg
          key={range}
          viewBox="0 0 640 160"
          preserveAspectRatio="none"
          className="relative h-full w-full"
        >
          <polyline
            points={target}
            fill="none"
            stroke="var(--color-primary)"
            strokeWidth="1.5"
            strokeDasharray="6 5"
            opacity="0.7"
          />
          <polyline
            points={area}
            fill="var(--color-steel)"
            fillOpacity="0.08"
            stroke="none"
          />
          <polyline
            points={actual}
            fill="none"
            stroke="var(--color-steel)"
            strokeWidth="2"
            className="animate-dashdraw"
          />
          <circle cx="640" cy={toY(last.actual)} r="3" fill="var(--color-steel)" />
        </svg>
        <div className="absolute right-0 bottom-1 left-0 flex justify-between font-mono text-[9px] text-muted-foreground">
          <span>W1</span>
          <span>W2</span>
          <span>W3</span>
          <span>W4</span>
        </div>
      </div>
    </div>
  );
}

export function Delta({ value, suffix = "%" }: { value: number; suffix?: string }) {
  const up = value >= 0;
  return (
    <span className={`font-mono text-[11px] ${up ? "text-ok" : "text-danger"}`}>
      {up ? "▲" : "▼"} {Math.abs(value).toFixed(1)}
      {suffix}
    </span>
  );
}

export function PanelTitle({
  dot,
  title,
  sub,
  right,
}: {
  dot: string;
  title: string;
  sub?: string;
  right?: ReactNode;
}) {
  return (
    <div className="flex items-center justify-between">
      <div className="flex items-center gap-2">
        <span className={`size-1.5 rounded-full ${dot}`} />
        <h2 className="text-sm font-semibold tracking-tight">{title}</h2>
        {sub && (
          <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            {sub}
          </span>
        )}
      </div>
      {right}
    </div>
  );
}
