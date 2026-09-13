import { Link, useNavigate } from "@tanstack/react-router";
import {
  Activity,
  Bell,
  Boxes,
  CircleUserRound,
  Drill,
  FileText,
  GaugeCircle,
  HardHat,
  Info,
  LogOut,
  Rocket,
  Scale,
  Search,
  Settings,
  Sparkles,
  Ticket,
  TrendingUp,
  UserRound,
} from "lucide-react";
import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { NewBadge } from "@/components/ui-kit";
import { personaById, personas, useView, type PersonaSlice } from "@/components/view-context";
import { useAuth } from "@/components/auth-context";
import { useLogoutWithAudit } from "@/hooks/use-logout-with-audit";
import { useDeltaBasin } from "@/components/delta-basin-context";
import { getUserThresholds, type ThresholdKey } from "@/data/workflow";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";

const nav = [
  { to: "/", label: "Overview", icon: GaugeCircle, slice: null },
  { to: "/reconciliation", label: "JV Reconciliation", icon: Scale, slice: "jv" },
  { to: "/production", label: "Production & Ops", icon: Activity, slice: "production" },
  { to: "/wells", label: "Wells & Subsurface", icon: Drill, slice: "production", badge: "new" },
  { to: "/forecasting", label: "Forecasting", icon: TrendingUp, slice: null, badge: "new" },
  { to: "/hse", label: "HSE & ESG", icon: HardHat, slice: "hse" },
  { to: "/products", label: "Materials", icon: Boxes, slice: "materials", badge: "preview" },
  { to: "/assistant", label: "Assistant", icon: Sparkles, slice: null, badge: "new" },
  { to: "/tickets", label: "Tickets", icon: Ticket, slice: null, badge: "new" },
  { to: "/roadmap", label: "Roadmap", icon: Rocket, slice: null },
] as const;

const secondaryNav = [
  { to: "/prd", label: "Documentation", icon: FileText },
  { to: "/profile", label: "Settings", icon: Settings },
] as const;

/** Delta Basin's mark - a river delta fanning out from a single source, in
 * the app's existing primary teal. Inline SVG so there's no external asset
 * to host/version. */
export function DeltaBasinLogo({ className }: { className?: string }) {
  return (
    <span
      className={`flex size-8 shrink-0 items-center justify-center rounded-md bg-primary/15 ${className ?? ""}`}
      aria-hidden
    >
      <svg viewBox="0 0 24 24" className="size-[18px] text-primary" fill="none">
        <path d="M12 2.5 V13" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M12 13 L5.5 21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M12 13 L12 21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <path d="M12 13 L18.5 21" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="12" cy="2.5" r="1.6" fill="currentColor" />
      </svg>
    </span>
  );
}

function ViewSwitcher() {
  const { persona, setPersona } = useView();
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="tabular text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
        View as
      </span>
      <div
        role="group"
        aria-label="View as persona"
        className="flex rounded-md border border-border bg-surface p-0.5"
      >
        {personas.map((p) => (
          <button
            key={p.id}
            type="button"
            onClick={() => setPersona(p.id)}
            aria-pressed={persona === p.id}
            className={`rounded-[5px] px-2.5 py-1 text-xs transition-colors ${
              persona === p.id
                ? "bg-primary/15 text-primary"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>
      <span
        title="Demo build only — a live deployment would derive your view from your signed-in role, not let you switch it here."
        className="flex items-center gap-1 rounded-sm border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-warning"
      >
        <Info className="size-2.5" aria-hidden />
        Demo only
      </span>
    </div>
  );
}

type Alert = { level: "warning" | "critical"; title: string; detail: string; to: string };

const DISMISSED_ALERTS_KEY = "delta-basin-dismissed-alerts-v1";

function loadDismissed(): Set<string> {
  try {
    const raw = window.localStorage.getItem(DISMISSED_ALERTS_KEY);
    return raw ? new Set(JSON.parse(raw) as string[]) : new Set();
  } catch {
    return new Set();
  }
}

function saveDismissed(keys: Set<string>) {
  try {
    window.localStorage.setItem(DISMISSED_ALERTS_KEY, JSON.stringify([...keys]));
  } catch {
    /* storage unavailable - clearing just won't persist across reloads */
  }
}

function NotificationBell() {
  const { user } = useAuth();
  const { currentPeriodId, summaryForPeriod, downtimeForPeriod, periodLabel } = useDeltaBasin();
  const [thresholds, setThresholds] = useState<Record<ThresholdKey, number> | null>(null);
  const [dismissed, setDismissed] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setDismissed(loadDismissed());
  }, []);

  useEffect(() => {
    if (!user) return;
    getUserThresholds({ data: { email: user.email } })
      .then((saved) => {
        setThresholds({
          variance_watch_pct: saved.variance_watch_pct ?? 1.5,
          variance_investigate_pct: saved.variance_investigate_pct ?? 3,
          uptime_alert_pct: saved.uptime_alert_pct ?? 94,
          downtime_alert_hours: saved.downtime_alert_hours ?? 200,
        });
      })
      .catch(() => {});
  }, [user]);

  if (!user || !thresholds) return null;

  const s = summaryForPeriod(currentPeriodId);
  const downtime = downtimeForPeriod(currentPeriodId);
  const alerts: Alert[] = [];

  if (Math.abs(s.netVariancePct) >= thresholds.variance_investigate_pct) {
    alerts.push({
      level: "critical",
      title: "Net variance beyond your investigate threshold",
      detail: `${s.netVariancePct.toFixed(2)}% vs. your ${thresholds.variance_investigate_pct}% threshold, ${periodLabel(currentPeriodId)}.`,
      to: "/reconciliation",
    });
  } else if (Math.abs(s.netVariancePct) >= thresholds.variance_watch_pct) {
    alerts.push({
      level: "warning",
      title: "Net variance beyond your watch threshold",
      detail: `${s.netVariancePct.toFixed(2)}% vs. your ${thresholds.variance_watch_pct}% threshold, ${periodLabel(currentPeriodId)}.`,
      to: "/reconciliation",
    });
  }
  if (s.uptimePct < thresholds.uptime_alert_pct) {
    alerts.push({
      level: "warning",
      title: "Fleet uptime below your alert threshold",
      detail: `${s.uptimePct.toFixed(1)}% vs. your ${thresholds.uptime_alert_pct}% threshold, ${periodLabel(currentPeriodId)}.`,
      to: "/production",
    });
  }
  for (const d of downtime) {
    if (d.hours >= thresholds.downtime_alert_hours) {
      alerts.push({
        level: "warning",
        title: `${d.cause} downtime beyond your alert threshold`,
        detail: `${Math.round(d.hours)} hrs vs. your ${thresholds.downtime_alert_hours} hr threshold, ${periodLabel(currentPeriodId)}.`,
        to: "/production",
      });
    }
  }

  const visibleAlerts = alerts.filter((a) => !dismissed.has(`${a.title}|${a.detail}`));

  function clearAll() {
    const next = new Set(dismissed);
    for (const a of visibleAlerts) next.add(`${a.title}|${a.detail}`);
    setDismissed(next);
    saveDismissed(next);
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Notifications"
          className="relative flex items-center justify-center rounded-full border border-border bg-surface p-2 text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
        >
          <Bell className="size-4" aria-hidden />
          {visibleAlerts.length > 0 ? (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-critical px-1 text-[10px] font-semibold text-white">
              {visibleAlerts.length}
            </span>
          ) : null}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-80">
        <div className="flex items-center justify-between gap-2 px-2 py-1.5">
          <DropdownMenuLabel className="p-0 text-xs">
            Notifications — against your thresholds (Profile)
          </DropdownMenuLabel>
          {visibleAlerts.length > 0 ? (
            <button
              type="button"
              onClick={clearAll}
              className="shrink-0 text-[10px] uppercase tracking-[0.08em] text-muted-foreground underline underline-offset-2 hover:text-foreground"
            >
              Clear all
            </button>
          ) : null}
        </div>
        <DropdownMenuSeparator />
        {visibleAlerts.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">Nothing over your thresholds right now.</p>
        ) : (
          visibleAlerts.map((a, i) => (
            <DropdownMenuItem key={i} asChild>
              <Link to={a.to} className="flex flex-col items-start gap-0.5 whitespace-normal">
                <span className={`text-xs font-medium ${a.level === "critical" ? "text-critical" : "text-warning"}`}>
                  {a.title}
                </span>
                <span className="text-[11px] text-muted-foreground">{a.detail}</span>
              </Link>
            </DropdownMenuItem>
          ))
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Quick-nav command palette - opens on Cmd/Ctrl+K or the header search
 * button, lists every page (main nav + Documentation/Settings) filtered by
 * what the current persona view can see, for fast keyboard-first jumps. */
function QuickNav() {
  const [open, setOpen] = useState(false);
  const { shows } = useView();
  const navigate = useNavigate();
  const visible = nav.filter((n) => n.slice === null || shows(n.slice as PersonaSlice));

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((v) => !v);
      }
    }
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  function go(to: string) {
    setOpen(false);
    navigate({ to });
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Search pages"
        className="flex items-center gap-2 rounded-full border border-border bg-surface px-3 py-2 text-xs text-muted-foreground transition-colors hover:bg-surface-2 hover:text-foreground"
      >
        <Search className="size-4" aria-hidden />
        <span className="hidden sm:inline">Search pages…</span>
        <kbd className="tabular hidden rounded border border-border bg-surface-2 px-1 py-0.5 text-[9px] sm:inline">
          ⌘K
        </kbd>
      </button>
      <CommandDialog open={open} onOpenChange={setOpen}>
        <CommandInput placeholder="Jump to a page…" />
        <CommandList>
          <CommandEmpty>No matching page.</CommandEmpty>
          <CommandGroup heading="Pages">
            {visible.map(({ to, label, icon: Icon }) => (
              <CommandItem key={to} value={label} onSelect={() => go(to)}>
                <Icon className="size-4" aria-hidden />
                {label}
              </CommandItem>
            ))}
          </CommandGroup>
          <CommandGroup heading="More">
            {secondaryNav.map(({ to, label, icon: Icon }) => (
              <CommandItem key={to} value={label} onSelect={() => go(to)}>
                <Icon className="size-4" aria-hidden />
                {label}
              </CommandItem>
            ))}
          </CommandGroup>
        </CommandList>
      </CommandDialog>
    </>
  );
}

/** Bottom-of-sidebar user card - replaces the old static synthetic-data
 * blurb (that disclosure still runs on every page via SyntheticNote, so
 * nothing is lost by giving this slot to something more useful instead).
 * Local time is read straight from the browser, not invented. */
function SidebarUserCard() {
  const { user } = useAuth();
  const [localTime, setLocalTime] = useState("");

  useEffect(() => {
    const update = () =>
      setLocalTime(
        new Date().toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }),
      );
    update();
    const id = window.setInterval(update, 30_000);
    return () => window.clearInterval(id);
  }, []);

  if (!user) return null;

  return (
    <div className="flex items-center gap-3">
      <CircleUserRound className="size-8 shrink-0 text-muted-foreground" aria-hidden />
      <div className="min-w-0">
        <p className="truncate text-xs font-medium text-foreground">{user.name}</p>
        <p className="tabular truncate text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          {personaById(user.role).label} view
        </p>
        <p className="tabular mt-1 text-[10px] text-muted-foreground">
          {localTime ? `${localTime} · ` : ""}CUSTOMER0 pilot, West Europe
        </p>
      </div>
    </div>
  );
}

function ProfileMenu() {
  const { user } = useAuth();
  const navigate = useNavigate();
  const logoutWithAudit = useLogoutWithAudit();
  if (!user) return null;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button
          type="button"
          aria-label="Account menu"
          className="flex items-center gap-2 rounded-full border border-border bg-surface p-1 pr-2.5 text-sm text-foreground transition-colors hover:bg-surface-2"
        >
          <CircleUserRound className="size-6 text-muted-foreground" aria-hidden />
          <span className="hidden max-w-[10rem] truncate sm:inline">{user.name}</span>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-64">
        <DropdownMenuLabel>
          <p className="truncate text-sm font-medium text-foreground">{user.name}</p>
          <p className="truncate text-xs font-normal text-muted-foreground">{user.email}</p>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={() => navigate({ to: "/profile" })}>
          <UserRound className="size-4" aria-hidden />
          View profile &amp; log statistics
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-critical focus:bg-critical/10 focus:text-critical"
          onSelect={() => logoutWithAudit("manual")}
        >
          <LogOut className="size-4" aria-hidden />
          Log out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const { shows } = useView();
  const visible = nav.filter((n) => n.slice === null || shows(n.slice as PersonaSlice));

  return (
    <div className="min-h-screen bg-background">
      <div className="mx-auto flex max-w-[1600px]">
        <aside className="no-print sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-border bg-sidebar lg:flex">
          <div className="flex items-center gap-2.5 border-b border-border px-5 py-5">
            <DeltaBasinLogo />
            <div>
              <p className="font-display text-lg font-semibold tracking-tight text-foreground">
                Delta&nbsp;Basin
              </p>
              <p className="tabular mt-0.5 text-[10px] uppercase tracking-[0.18em] text-primary">
                CUSTOMER0 pilot · v0.1
              </p>
            </div>
          </div>
          <nav className="flex flex-1 flex-col px-3 py-4">
            <ul className="space-y-1">
              {visible.map(({ to, label, icon: Icon, ...rest }) => (
                <li key={to}>
                  <Link
                    to={to}
                    activeOptions={{ exact: to === "/" }}
                    activeProps={{
                      className: "bg-sidebar-accent text-sidebar-accent-foreground border-primary/60",
                    }}
                    inactiveProps={{ className: "border-transparent text-muted-foreground" }}
                    className="flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  >
                    <Icon className="size-4" aria-hidden />
                    {label}
                    {"badge" in rest && rest.badge === "new" ? (
                      <NewBadge className="ml-auto" />
                    ) : "badge" in rest && rest.badge === "preview" ? (
                      <span className="tabular ml-auto rounded-sm border border-warning/40 bg-warning/10 px-1.5 py-0.5 text-[9px] uppercase tracking-[0.1em] text-warning">
                        Preview
                      </span>
                    ) : null}
                  </Link>
                </li>
              ))}
            </ul>
            <ul className="mt-auto space-y-1 border-t border-border pt-3">
              {secondaryNav.map(({ to, label, icon: Icon }) => (
                <li key={to}>
                  <Link
                    to={to}
                    activeProps={{ className: "bg-sidebar-accent text-sidebar-accent-foreground border-primary/60" }}
                    inactiveProps={{ className: "border-transparent text-muted-foreground" }}
                    className="flex items-center gap-2.5 rounded-md border-l-2 px-3 py-2 text-sm transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  >
                    <Icon className="size-4" aria-hidden />
                    {label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="border-t border-border px-5 py-4">
            <SidebarUserCard />
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="no-print sticky top-0 z-20 flex flex-wrap items-center justify-between gap-3 border-b border-border bg-sidebar px-4 py-3 md:px-8">
            <span className="flex items-center gap-2 lg:hidden">
              <DeltaBasinLogo className="size-7" />
              <span className="font-display text-sm font-semibold text-foreground">Delta Basin</span>
            </span>
            <ViewSwitcher />
            <div className="flex items-center gap-2">
              <QuickNav />
              <NotificationBell />
              <ProfileMenu />
            </div>
          </header>
          <div className="no-print flex items-center gap-3 overflow-x-auto border-b border-border bg-sidebar px-4 py-2 lg:hidden">
            {visible.map(({ to, label }) => (
              <Link
                key={to}
                to={to}
                activeOptions={{ exact: to === "/" }}
                activeProps={{ className: "text-primary" }}
                inactiveProps={{ className: "text-muted-foreground" }}
                className="whitespace-nowrap text-xs"
              >
                {label}
              </Link>
            ))}
          </div>
          <main className="grid-bg min-h-screen px-5 py-8 md:px-8">
            <div className="mx-auto max-w-[1240px] space-y-8">{children}</div>
          </main>
        </div>
      </div>
    </div>
  );
}
