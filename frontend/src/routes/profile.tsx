import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useState } from "react";
import { useAuth } from "@/components/auth-context";
import { useActivityLog } from "@/components/activity-log-context";
import { PageHeader, Panel, Metric, EmptyState, StatusPill, NewBadge } from "@/components/ui-kit";
import { FileClock } from "lucide-react";
import { LOG_VISIBILITY } from "@/data/auth";
import { getUserThresholds, setUserThreshold, type ThresholdKey } from "@/data/workflow";
import { THRESHOLD_DEFAULTS } from "@/data/threshold-defaults";

export const Route = createFileRoute("/profile")({
  head: () => ({
    meta: [{ title: "Profile & activity — Delta Basin" }, { name: "robots", content: "noindex" }],
  }),
  component: ProfilePage,
});

const roleLabel: Record<string, string> = {
  executive: "Executive",
  finance: "Finance",
  ops: "Ops",
  hse: "HSE",
};

function timestamp(iso: string) {
  return new Date(iso).toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const THRESHOLD_META: Record<ThresholdKey, { label: string; hint: string; min: number; max: number; step: number; unit: string }> = {
  variance_watch_pct: { label: "Variance — watch level", hint: "Flag a reconciliation record as 'watch' above this %.", min: 0.5, max: 10, step: 0.5, unit: "%" },
  variance_investigate_pct: { label: "Variance — investigate level", hint: "Flag as 'investigate' above this %.", min: 1, max: 15, step: 0.5, unit: "%" },
  uptime_alert_pct: { label: "Fleet uptime alert", hint: "Alert when fleet uptime drops below this %.", min: 70, max: 99, step: 1, unit: "%" },
  downtime_alert_hours: { label: "Downtime alert", hint: "Alert when a single cause exceeds this many hours/period.", min: 20, max: 500, step: 10, unit: "hrs" },
};

function ThresholdsPanel({ email }: { email: string }) {
  const [values, setValues] = useState<Record<ThresholdKey, number>>(THRESHOLD_DEFAULTS);
  const [saving, setSaving] = useState<ThresholdKey | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    getUserThresholds({ data: { email } })
      .then((saved) => {
        setValues((prev) => ({ ...prev, ...saved }));
        setLoaded(true);
      })
      .catch(() => setLoaded(true));
  }, [email]);

  async function update(key: ThresholdKey, value: number) {
    setValues((prev) => ({ ...prev, [key]: value }));
    setSaving(key);
    try {
      await setUserThreshold({ data: { email, metricKey: key, value } });
    } finally {
      setSaving(null);
    }
  }

  return (
    <Panel
      title="Your alert thresholds"
      note="Personal, saved to your account — used to flag/alert on this data as it loads."
      actions={<NewBadge />}
    >
      {!loaded ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {(Object.keys(THRESHOLD_META) as ThresholdKey[]).map((key) => {
            const meta = THRESHOLD_META[key];
            return (
              <label key={key} className="block">
                <div className="flex items-center justify-between text-xs text-muted-foreground">
                  <span>{meta.label}</span>
                  <span className="tabular text-foreground">
                    {values[key]}
                    {meta.unit}
                    {saving === key ? " · saving…" : ""}
                  </span>
                </div>
                <input
                  type="range"
                  min={meta.min}
                  max={meta.max}
                  step={meta.step}
                  value={values[key]}
                  onChange={(e) => void update(key, Number(e.target.value))}
                  className="mt-2 w-full accent-primary"
                />
                <p className="mt-1 text-[11px] text-muted-foreground">{meta.hint}</p>
              </label>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function ProfilePage() {
  const { user, ready } = useAuth();
  const { visibleEntries } = useActivityLog();
  const navigate = useNavigate();

  if (ready && !user) {
    navigate({ to: "/login" });
    return null;
  }
  if (!user) return null;

  const ownCount = visibleEntries.filter((e) => e.actorEmail === user.email).length;
  const otherCount = visibleEntries.length - ownCount;
  const visibleRoles = LOG_VISIBILITY[user.role];

  return (
    <>
      <PageHeader
        eyebrow="Account"
        title="Profile & activity"
        description={`Signed in as ${user.name} (${user.email}) — ${roleLabel[user.role]} role.`}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Metric label="Your role" value={roleLabel[user.role] ?? user.role} />
        <Metric label="Your actions logged" value={String(ownCount)} />
        <Metric
          label="Visible from others"
          value={String(otherCount)}
          hint={`Your role can see: ${visibleRoles.map((r) => roleLabel[r]).join(", ")}.`}
        />
      </div>

      <ThresholdsPanel email={user.email} />

      <Panel
        title="Activity log"
        note="Every logged change, newest first. Visibility follows role seniority — HSE sees only HSE, Ops sees Ops + HSE, Finance sees Finance + Ops + HSE, Executive sees all. You always see your own actions regardless of role."
      >
        {visibleEntries.length === 0 ? (
          <EmptyState
            icon={FileClock}
            title="No activity yet."
            hint="Actions like signing in or editing the materials catalogue will show up here."
          />
        ) : (
          <ul className="divide-y divide-border">
            {visibleEntries.map((e) => (
              <li key={e.id} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div className="min-w-0">
                  <p className="text-sm text-foreground">{e.detail}</p>
                  <p className="tabular mt-0.5 text-xs text-muted-foreground">
                    {e.actorName} · {e.actorEmail} · {timestamp(e.timestamp)}
                  </p>
                </div>
                <StatusPill status={roleLabel[e.actorRole] ?? e.actorRole} />
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}
