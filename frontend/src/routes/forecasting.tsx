import { createFileRoute } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { FolderOpen, Plus, Save, Trash2 } from "lucide-react";
import { Slider } from "@/components/ui/slider";
import { usePeriod } from "@/components/period-context";
import { useDeltaBasin } from "@/components/delta-basin-context";
import { useAuth } from "@/components/auth-context";
import {
  DataTable,
  EmptyState,
  Metric,
  NewBadge,
  Panel,
  PageHeader,
  PeriodSelector,
  SyntheticNote,
} from "@/components/ui-kit";
import { formatBopd, formatPct, formatSigned, formatSignedPct } from "@/data/delta-basin";
import type { ProductionRow } from "@/data/delta-basin";
import { deleteSavedForecast, listSavedForecasts, saveForecast, type SavedForecast } from "@/data/workflow";

export const Route = createFileRoute("/forecasting")({
  head: () => ({
    meta: [
      { title: "Forecasting — Delta Basin" },
      {
        name: "description",
        content: "Build and compare what-if production scenarios side by side.",
      },
    ],
  }),
  component: ForecastingPage,
});

type Scenario = { id: string; name: string; uptimeAdjustment: number; forecastAdjustment: number };

/** Same illustrative linear model the original single-scenario panel used -
 * production scales with uptime, forecast scales with a flat demand shift.
 * Deliberately client-side and ephemeral, nothing here is persisted. */
function project(rows: ProductionRow[], uptimeAdjustment: number, forecastAdjustment: number) {
  let actual = 0;
  let forecast = 0;
  for (const r of rows) {
    const adjustedUptime = Math.max(r.uptimePct + uptimeAdjustment, 0);
    const scaledActual = r.uptimePct > 0 ? r.actualBopd * (adjustedUptime / r.uptimePct) : r.actualBopd;
    const scaledForecast = r.forecastBopd * (1 + forecastAdjustment / 100);
    actual += scaledActual;
    forecast += scaledForecast;
  }
  return { actual, forecast, attainment: forecast ? (actual / forecast) * 100 : 0 };
}

let nextId = 1;

function ScenarioCard({
  scenario,
  rows,
  baseline,
  onChange,
  onRemove,
  onSave,
  saving,
  removable,
}: {
  scenario: Scenario;
  rows: ProductionRow[];
  baseline: { actual: number; forecast: number; attainment: number };
  onChange: (next: Scenario) => void;
  onRemove: () => void;
  onSave: () => void;
  saving: boolean;
  removable: boolean;
}) {
  const projected = useMemo(
    () => project(rows, scenario.uptimeAdjustment, scenario.forecastAdjustment),
    [rows, scenario.uptimeAdjustment, scenario.forecastAdjustment],
  );
  const deltaActual = projected.actual - baseline.actual;
  const deltaAttainment = projected.attainment - baseline.attainment;
  const isBaseline = scenario.uptimeAdjustment === 0 && scenario.forecastAdjustment === 0;

  return (
    <Panel
      title={scenario.name}
      note="Illustrative linear model - not a substitute for reservoir/production engineering forecasts."
      actions={
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={onSave}
            disabled={saving}
            title="Save this scenario to your account"
            className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Save className="size-4" aria-hidden />
          </button>
          {removable ? (
            <button
              type="button"
              onClick={onRemove}
              aria-label={`Remove ${scenario.name}`}
              className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-critical/10 hover:text-critical"
            >
              <Trash2 className="size-4" aria-hidden />
            </button>
          ) : null}
        </div>
      }
    >
      <input
        type="text"
        value={scenario.name}
        onChange={(e) => onChange({ ...scenario, name: e.target.value })}
        aria-label="Scenario name"
        className="mb-4 w-full max-w-xs rounded-md border border-border bg-surface px-2 py-1 text-xs text-foreground outline-none focus:border-primary"
      />
      <div className="grid gap-6 sm:grid-cols-2">
        <div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Uptime adjustment</span>
            <span className="tabular text-foreground">{formatSigned(scenario.uptimeAdjustment, 1)} pts</span>
          </div>
          <Slider
            className="mt-3"
            value={[scenario.uptimeAdjustment]}
            onValueChange={([v]) => onChange({ ...scenario, uptimeAdjustment: v ?? 0 })}
            min={-15}
            max={15}
            step={0.5}
            aria-label="Uptime adjustment, percentage points"
          />
        </div>
        <div>
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span>Forecast / demand adjustment</span>
            <span className="tabular text-foreground">{formatSignedPct(scenario.forecastAdjustment, 0)}</span>
          </div>
          <Slider
            className="mt-3"
            value={[scenario.forecastAdjustment]}
            onValueChange={([v]) => onChange({ ...scenario, forecastAdjustment: v ?? 0 })}
            min={-20}
            max={20}
            step={1}
            aria-label="Forecast adjustment, percent"
          />
        </div>
      </div>

      <div className="mt-6 grid gap-4 sm:grid-cols-3">
        <Metric
          label="Projected actual"
          value={formatBopd(projected.actual)}
          delta={isBaseline ? "Baseline" : `${formatSigned(Math.round(deltaActual))} bopd vs. baseline`}
          tone={isBaseline ? "neutral" : deltaActual >= 0 ? "positive" : "critical"}
        />
        <Metric label="Projected forecast" value={formatBopd(projected.forecast)} />
        <Metric
          label="Projected attainment"
          value={formatPct(projected.attainment)}
          delta={isBaseline ? "Baseline" : `${formatSignedPct(deltaAttainment)} vs. baseline`}
          tone={isBaseline ? "neutral" : deltaAttainment >= 0 ? "positive" : "warning"}
        />
      </div>

      {!isBaseline ? (
        <button
          type="button"
          onClick={() => onChange({ ...scenario, uptimeAdjustment: 0, forecastAdjustment: 0 })}
          className="mt-4 text-xs text-muted-foreground underline underline-offset-2 hover:text-foreground"
        >
          Reset to baseline
        </button>
      ) : null}
    </Panel>
  );
}

function ForecastingPage() {
  const { periodId } = usePeriod();
  const { productionForPeriod, periodLabel } = useDeltaBasin();
  const { user } = useAuth();
  const rows = productionForPeriod(periodId);
  const baseline = useMemo(() => project(rows, 0, 0), [rows]);

  const [scenarios, setScenarios] = useState<Scenario[]>([
    { id: `s${nextId++}`, name: "Scenario 1", uptimeAdjustment: 0, forecastAdjustment: 0 },
  ]);
  const [saved, setSaved] = useState<SavedForecast[] | null>(null);
  const [savingId, setSavingId] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    listSavedForecasts({ data: { email: user.email } })
      .then(setSaved)
      .catch(() => setSaved([]));
  }, [user]);

  function addScenario() {
    setScenarios((prev) => [
      ...prev,
      { id: `s${nextId++}`, name: `Scenario ${prev.length + 1}`, uptimeAdjustment: 0, forecastAdjustment: 0 },
    ]);
  }

  function updateScenario(next: Scenario) {
    setScenarios((prev) => prev.map((s) => (s.id === next.id ? next : s)));
  }

  function removeScenario(id: string) {
    setScenarios((prev) => prev.filter((s) => s.id !== id));
  }

  async function saveScenario(s: Scenario) {
    if (!user) return;
    setSavingId(s.id);
    try {
      await saveForecast({
        data: {
          email: user.email,
          name: s.name,
          periodId,
          uptimeAdjustment: s.uptimeAdjustment,
          forecastAdjustment: s.forecastAdjustment,
        },
      });
      const refreshed = await listSavedForecasts({ data: { email: user.email } });
      setSaved(refreshed);
    } finally {
      setSavingId(null);
    }
  }

  function loadSaved(f: SavedForecast) {
    setScenarios((prev) => [
      ...prev,
      {
        id: `s${nextId++}`,
        name: f.name,
        uptimeAdjustment: f.uptimeAdjustment,
        forecastAdjustment: f.forecastAdjustment,
      },
    ]);
  }

  async function deleteSaved(id: number) {
    if (!user) return;
    setSaved((prev) => prev?.filter((f) => f.id !== id) ?? prev);
    await deleteSavedForecast({ data: { id, email: user.email } }).catch(() => {});
  }

  return (
    <>
      <PageHeader
        eyebrow={`Forecasting · ${periodLabel(periodId)}`}
        title="What-if scenario modeling"
        description="Build one or more production scenarios and compare them against this period's baseline. Adjustments stay unsaved unless you explicitly save a scenario — purely illustrative."
        actions={
          <>
            <NewBadge />
            <PeriodSelector />
          </>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <Metric label="Baseline actual" value={formatBopd(baseline.actual)} />
        <Metric label="Baseline forecast" value={formatBopd(baseline.forecast)} />
        <Metric label="Baseline attainment" value={formatPct(baseline.attainment)} />
      </div>

      <Panel title="Saved forecasts" note="Scenarios you've explicitly saved to your account">
        {saved === null ? (
          <p className="text-xs text-muted-foreground">Loading…</p>
        ) : saved.length === 0 ? (
          <EmptyState
            title="No saved forecasts yet."
            hint="Use the save icon on a scenario below to keep it for next time."
          />
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {saved.map((f) => (
              <li
                key={f.id}
                className="flex items-center justify-between gap-2 rounded-md border border-border bg-surface px-3 py-2"
              >
                <span className="min-w-0">
                  <span className="block truncate text-sm text-foreground">{f.name}</span>
                  <span className="tabular block text-[11px] text-muted-foreground">
                    {formatSigned(f.uptimeAdjustment, 1)} pts · {formatSignedPct(f.forecastAdjustment, 0)} ·{" "}
                    {periodLabel(f.periodId)}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-1">
                  <button
                    type="button"
                    onClick={() => loadSaved(f)}
                    title="Load into a new scenario card"
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-primary/10 hover:text-primary"
                  >
                    <FolderOpen className="size-4" aria-hidden />
                  </button>
                  <button
                    type="button"
                    onClick={() => void deleteSaved(f.id)}
                    title="Delete"
                    className="rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-critical/10 hover:text-critical"
                  >
                    <Trash2 className="size-4" aria-hidden />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      {scenarios.length > 1 ? (
        <Panel title="Compare scenarios" note="Side by side against this period's baseline">
          <DataTable head={["Scenario", "Uptime adj.", "Forecast adj.", "Projected actual", "Projected attainment", "Δ actual vs. baseline"]}>
            {scenarios.map((s) => {
              const p = project(rows, s.uptimeAdjustment, s.forecastAdjustment);
              return (
                <tr key={s.id} className="border-b border-border last:border-0">
                  <td className="px-3 py-2 text-left text-foreground">{s.name}</td>
                  <td className="tabular px-3 py-2 text-right">{formatSigned(s.uptimeAdjustment, 1)} pts</td>
                  <td className="tabular px-3 py-2 text-right">{formatSignedPct(s.forecastAdjustment, 0)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatBopd(p.actual)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatPct(p.attainment)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatSigned(Math.round(p.actual - baseline.actual))} bopd</td>
                </tr>
              );
            })}
          </DataTable>
        </Panel>
      ) : null}

      <div className="space-y-4">
        {scenarios.map((s) => (
          <ScenarioCard
            key={s.id}
            scenario={s}
            rows={rows}
            baseline={baseline}
            onChange={updateScenario}
            onRemove={() => removeScenario(s.id)}
            onSave={() => void saveScenario(s)}
            saving={savingId === s.id}
            removable={scenarios.length > 1}
          />
        ))}
      </div>

      <button
        type="button"
        onClick={addScenario}
        className="flex items-center justify-center gap-2 rounded-lg border border-dashed border-border px-4 py-3 text-sm text-muted-foreground transition-colors hover:border-primary/40 hover:text-primary"
      >
        <Plus className="size-4" aria-hidden />
        New scenario
      </button>

      <SyntheticNote />
    </>
  );
}
