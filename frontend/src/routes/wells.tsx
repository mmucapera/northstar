import { createFileRoute } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Drill } from "lucide-react";
import {
  DataTable,
  EmptyState,
  ExportCsvButton,
  Metric,
  NewBadge,
  PageHeader,
  Panel,
  StatusPill,
  SyntheticNote,
} from "@/components/ui-kit";
import { formatNumber, formatPct } from "@/data/delta-basin";
import {
  completionByWellId,
  drillingTelemetry,
  fieldNameById,
  latestProductionVolumes,
  wellbores,
  wells,
  type Well,
} from "@/data/wells";

export const Route = createFileRoute("/wells")({
  head: () => ({
    meta: [
      { title: "Wells & Subsurface — Delta Basin" },
      {
        name: "description",
        content:
          "Well, wellbore, completion and drilling telemetry detail for the Delta Basin pilot - complements field-level Production & Ops with well-level grain.",
      },
    ],
  }),
  component: WellsPage,
});

type WellSortKey = "well" | "field" | "type" | "status" | "depth" | "oil";

function WellsPage() {
  const volumes = useMemo(() => latestProductionVolumes(), []);
  const volumeByWellId = useMemo(() => new Map(volumes.map((v) => [v.wellId, v])), [volumes]);
  const telemetry = useMemo(() => drillingTelemetry(), []);

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const w of wells) counts[w.status] = (counts[w.status] ?? 0) + 1;
    return counts;
  }, []);

  const [sort, setSort] = useState<{ key: WellSortKey; dir: "asc" | "desc" } | null>({
    key: "oil",
    dir: "desc",
  });
  function toggleSort(key: string) {
    const k = key as WellSortKey;
    setSort((prev) => (prev?.key === k ? (prev.dir === "asc" ? { key: k, dir: "desc" } : null) : { key: k, dir: "asc" }));
  }

  const sortedWells = useMemo(() => {
    if (!sort) return wells;
    const dir = sort.dir === "asc" ? 1 : -1;
    const valueOf = (w: Well): string | number => {
      switch (sort.key) {
        case "well":
          return w.wellName;
        case "field":
          return fieldNameById(w.fieldId);
        case "type":
          return w.wellType;
        case "status":
          return w.status;
        case "depth":
          return w.totalDepthM;
        case "oil":
          return volumeByWellId.get(w.wellId)?.oilBbl ?? 0;
      }
    };
    return [...wells].sort((a, b) => {
      const av = valueOf(a);
      const bv = valueOf(b);
      if (typeof av === "string" || typeof bv === "string") return String(av).localeCompare(String(bv)) * dir;
      return (av - bv) * dir;
    });
  }, [sort, volumeByWellId]);

  const topWells = sortedWells.slice(0, 15);
  const drillingWells = wells.filter((w) => w.status === "Drilling");
  const latestTelemetryByWell = useMemo(() => {
    const map = new Map<string, (typeof telemetry)[number]>();
    for (const row of telemetry) {
      const existing = map.get(row.wellId);
      if (!existing || row.reportDate > existing.reportDate) map.set(row.wellId, row);
    }
    return map;
  }, [telemetry]);

  return (
    <>
      <PageHeader
        eyebrow="Wells & Subsurface"
        title="Well, wellbore and completion detail"
        description="Well-level production, well tests and drilling telemetry - complements the field-level Production & Ops view with well/wellbore/completion grain."
        actions={<NewBadge />}
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Metric label="Total wells" value={formatNumber(wells.length)} />
        <Metric
          label="Producing"
          value={formatNumber(statusCounts["Producing"] ?? 0)}
          tone="positive"
          delta={`${formatPct(((statusCounts["Producing"] ?? 0) / wells.length) * 100)} of fleet`}
        />
        <Metric label="Drilling" value={formatNumber(statusCounts["Drilling"] ?? 0)} tone="warning" />
        <Metric label="Wellbores" value={formatNumber(wellbores.length)} />
      </div>

      <Panel
        title="Top producing wells"
        note="Latest period, by oil volume"
        actions={
          <ExportCsvButton
            filename="top-wells.csv"
            headers={["Well", "Field", "Type", "Status", "Total depth (m)", "Oil (bbl)", "Water cut %"]}
            rows={topWells.map((w) => {
              const v = volumeByWellId.get(w.wellId);
              return [w.wellName, fieldNameById(w.fieldId), w.wellType, w.status, w.totalDepthM, v?.oilBbl ?? 0, v?.waterCutPct ?? 0];
            })}
          />
        }
      >
        {topWells.length === 0 ? (
          <EmptyState title="No wells found." />
        ) : (
          <DataTable
            head={[
              { label: "Well", key: "well" },
              { label: "Field", key: "field" },
              { label: "Type", key: "type" },
              { label: "Status", key: "status" },
              { label: "Depth (m)", key: "depth" },
              { label: "Oil (bbl)", key: "oil" },
            ]}
            sort={sort}
            onSort={toggleSort}
          >
            {topWells.map((w) => {
              const v = volumeByWellId.get(w.wellId);
              return (
                <tr key={w.wellId} className="border-b border-border last:border-0 hover:bg-surface-2">
                  <td className="px-3 py-2 text-foreground">{w.wellName}</td>
                  <td className="px-3 py-2 text-muted-foreground">{fieldNameById(w.fieldId)}</td>
                  <td className="px-3 py-2 text-muted-foreground">{w.wellType}</td>
                  <td className="px-3 py-2">
                    <StatusPill status={w.status.toLowerCase().replace(" ", "-")} />
                  </td>
                  <td className="tabular px-3 py-2 text-right">{formatNumber(w.totalDepthM)}</td>
                  <td className="tabular px-3 py-2 text-right">{formatNumber(v?.oilBbl ?? 0)}</td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      <Panel
        title="Drilling telemetry"
        note={`${drillingWells.length} well${drillingWells.length === 1 ? "" : "s"} currently drilling — latest daily report`}
        actions={<Drill className="size-4 text-muted-foreground" aria-hidden />}
      >
        {drillingWells.length === 0 ? (
          <EmptyState title="No wells are currently drilling." hint="Drilling telemetry appears here once a well's status is Drilling." />
        ) : (
          <DataTable
            head={["Well", "Wellbore", "Report date", "Depth (m)", "ROP (m/hr)", "WOB (klbs)", "Mud wt (ppg)", "NPT"]}
          >
            {drillingWells.map((w) => {
              const row = latestTelemetryByWell.get(w.wellId);
              if (!row) return null;
              return (
                <tr key={w.wellId} className="border-b border-border last:border-0 hover:bg-surface-2">
                  <td className="px-3 py-2 text-foreground">{w.wellName}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.wellboreId}</td>
                  <td className="px-3 py-2 text-muted-foreground">{row.reportDate}</td>
                  <td className="tabular px-3 py-2 text-right">{formatNumber(row.depthM)}</td>
                  <td className="tabular px-3 py-2 text-right">{row.ropMPerHr}</td>
                  <td className="tabular px-3 py-2 text-right">{row.wobKlbs}</td>
                  <td className="tabular px-3 py-2 text-right">{row.mudWeightPpg}</td>
                  <td className="px-3 py-2">
                    {row.npt ? <StatusPill status="watch" /> : <span className="text-xs text-muted-foreground">—</span>}
                  </td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      <Panel title="Completions" note="Active completion per wellbore, sample of drilling wells">
        {drillingWells.length === 0 ? (
          <EmptyState title="No active drilling completions." />
        ) : (
          <DataTable head={["Well", "Completion", "Type", "Reservoir", "Perforation (m)", "Active"]}>
            {drillingWells.map((w) => {
              const c = completionByWellId(w.wellId);
              if (!c) return null;
              return (
                <tr key={c.completionId} className="border-b border-border last:border-0 hover:bg-surface-2">
                  <td className="px-3 py-2 text-foreground">{w.wellName}</td>
                  <td className="px-3 py-2 text-muted-foreground">{c.completionId}</td>
                  <td className="px-3 py-2 text-muted-foreground">{c.completionType}</td>
                  <td className="px-3 py-2 text-muted-foreground">{c.reservoirUnit}</td>
                  <td className="tabular px-3 py-2 text-right">
                    {c.perforationTopM}–{c.perforationBaseM}
                  </td>
                  <td className="px-3 py-2">{c.isActive ? <StatusPill status="normal" /> : <StatusPill status="down" />}</td>
                </tr>
              );
            })}
          </DataTable>
        )}
      </Panel>

      <SyntheticNote />
    </>
  );
}
