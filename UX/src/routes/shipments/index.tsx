import { createFileRoute, Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { Shell, StatusChip } from "@/components/dashboard";
import {
  SHIPMENTS,
  shipmentsCsv,
  type RangeKey,
  type ShipmentStatus,
} from "@/lib/data";
import { customerConfig } from "@/lib/config";

export const Route = createFileRoute("/shipments/")({
  head: () => {
    const title = `Shipments Log — ${customerConfig.brand.name}`;
    const description =
      "Full tanker and pipeline shipment log with routes, loads, ETAs, and live status across all corridors.";
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
  component: ShipmentsPage,
});

const STATUS_FILTERS: Array<ShipmentStatus | "All"> = [
  "All",
  "In Transit",
  "Loading",
  "Delayed",
  "Queued",
];

type SortKey = "vessel" | "load" | "eta" | "status";

function ShipmentsPage() {
  const [range, setRange] = useState<RangeKey>("24H");
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState<ShipmentStatus | "All">("All");
  const [sortKey, setSortKey] = useState<SortKey>("eta");
  const [asc, setAsc] = useState(true);
  const tableLabels = customerConfig.table.shipments;

  const rows = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = SHIPMENTS.filter(
      (s) =>
        (status === "All" || s.status === status) &&
        (q === "" ||
          s.vessel.toLowerCase().includes(q) ||
          s.route.toLowerCase().includes(q) ||
          s.corridor.toLowerCase().includes(q)),
    );
    const dir = asc ? 1 : -1;
    return [...filtered].sort((a, b) => {
      if (sortKey === "load") return (a.loadValueMbbl - b.loadValueMbbl) * dir;
      if (sortKey === "eta") return (a.etaDay - b.etaDay) * dir;
      return a[sortKey].localeCompare(b[sortKey]) * dir;
    });
  }, [query, status, sortKey, asc]);

  function exportCsv() {
    const blob = new Blob([shipmentsCsv(rows)], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "dataset_oilandgas-shipments.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  function toggleSort(key: SortKey) {
    if (key === sortKey) setAsc(!asc);
    else {
      setSortKey(key);
      setAsc(true);
    }
  }

  const th =
    "px-4 py-2 font-medium cursor-pointer select-none hover:text-foreground transition-colors";
  const arrow = (k: SortKey) =>
    sortKey === k ? (asc ? " ▲" : " ▼") : "";

  return (
    <Shell range={range} onRangeChange={setRange} onExport={exportCsv}>
      <div className="rounded-xl bg-card ring-1 ring-border">
        <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-steel" />
            <h1 className="text-sm font-semibold tracking-tight">
              Shipments Log
            </h1>
            <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
              {rows.length} of {SHIPMENTS.length} shown
            </span>
          </div>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search vessels, routes…"
              className="w-56 rounded-lg bg-background px-3 py-1.5 font-mono text-xs text-foreground ring-1 ring-border outline-none placeholder:text-muted-foreground focus:ring-ring"
            />
            <div className="flex items-center gap-1">
              {STATUS_FILTERS.map((f) => (
                <button
                  key={f}
                  onClick={() => setStatus(f)}
                  className={`rounded-full px-2.5 py-1 font-mono text-[10px] tracking-wider uppercase transition-colors ${
                    status === f
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

        <div className="overflow-x-auto">
          <table className="w-full text-left">
            <thead>
              <tr className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
                <th className={th} onClick={() => toggleSort("vessel")}>
                  {tableLabels.vessel}{arrow("vessel")}
                </th>
                <th className="px-3 py-2 font-medium">{tableLabels.route}</th>
                <th className="px-3 py-2 font-medium">{tableLabels.corridor}</th>
                <th className={th} onClick={() => toggleSort("load")}>
                  {tableLabels.load}{arrow("load")}
                </th>
                <th className={th} onClick={() => toggleSort("eta")}>
                  {tableLabels.eta}{arrow("eta")}
                </th>
                <th
                  className={`${th} text-right`}
                  onClick={() => toggleSort("status")}
                >
                  {tableLabels.status}{arrow("status")}
                </th>
              </tr>
            </thead>
            <tbody className="font-mono text-xs">
              {rows.map((s) => (
                <tr
                  key={s.id}
                  className="border-t border-border/70 transition-colors hover:bg-hi/30"
                >
                  <td className="px-4 py-2.5 text-foreground">
                    <Link
                      to="/shipments/$id"
                      params={{ id: s.id }}
                      className="transition-colors hover:text-steel hover:underline"
                    >
                      {s.vessel}
                    </Link>
                  </td>
                  <td className="px-3 py-2.5 text-muted-foreground">{s.route}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">
                    {s.corridor}
                  </td>
                  <td className="px-3 py-2.5 text-foreground">{s.load}</td>
                  <td className="px-3 py-2.5 text-muted-foreground">{s.eta}</td>
                  <td className="px-4 py-2.5 text-right">
                    <StatusChip status={s.status} />
                  </td>
                </tr>
              ))}
              {rows.length === 0 && (
                <tr className="border-t border-border/70">
                  <td
                    colSpan={6}
                    className="px-4 py-8 text-center text-muted-foreground"
                  >
                    No shipments match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </Shell>
  );
}
