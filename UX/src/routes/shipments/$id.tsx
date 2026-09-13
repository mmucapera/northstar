import { createFileRoute, Link, notFound } from "@tanstack/react-router";
import { StatusChip } from "@/components/dashboard";
import { Shell } from "@/components/dashboard";
import { SHIPMENTS } from "@/lib/data";
import { customerConfig } from "@/lib/config";
import { useState } from "react";
import type { RangeKey } from "@/lib/data";

export const Route = createFileRoute("/shipments/$id")({
  loader: ({ params }) => {
    const shipment = SHIPMENTS.find((s) => s.id === params.id);
    if (!shipment) throw notFound();
    return shipment;
  },
  head: ({ loaderData }) => {
    const title = `${loaderData?.vessel ?? "Shipment"} — ${customerConfig.brand.name}`;
    const description = loaderData
      ? `${loaderData.vessel} · ${loaderData.route} · ${loaderData.load} · ${loaderData.status}`
      : "Shipment detail.";
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
  component: ShipmentDetailPage,
  notFoundComponent: ShipmentNotFound,
});

function ShipmentDetailPage() {
  const shipment = Route.useLoaderData();
  const [range, setRange] = useState<RangeKey>("24H");

  const [origin, destination] = shipment.route.split(" → ");
  const corridorPeers = SHIPMENTS.filter(
    (s) => s.corridor === shipment.corridor && s.id !== shipment.id,
  );

  return (
    <Shell range={range} onRangeChange={setRange}>
      <Link
        to="/shipments"
        className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase transition-colors hover:text-foreground"
      >
        ← Shipments
      </Link>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-3 rounded-xl bg-card p-5 ring-1 ring-border">
        <div>
          <div className="flex items-center gap-2">
            <span className="size-1.5 rounded-full bg-steel" />
            <h1 className="text-lg font-semibold tracking-tight">
              {shipment.vessel}
            </h1>
            <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
              {shipment.id}
            </span>
          </div>
          <p className="mt-1 font-mono text-xs text-muted-foreground">
            {origin} <span className="text-steel">→</span> {destination}
          </p>
        </div>
        <StatusChip status={shipment.status} />
      </div>

      <section className="mt-3 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Load
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold">
            {shipment.load}
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            ETA
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold">
            {shipment.eta}
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Corridor
          </span>
          <div className="mt-2 font-mono text-2xl leading-none font-semibold">
            {shipment.corridor}
          </div>
        </div>
        <div className="rounded-xl bg-card p-4 ring-1 ring-border">
          <span className="font-mono text-[10px] tracking-[0.15em] text-muted-foreground uppercase">
            Status
          </span>
          <div className="mt-2">
            <StatusChip status={shipment.status} />
          </div>
        </div>
      </section>

      <section className="mt-3 rounded-xl bg-card ring-1 ring-border">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-semibold tracking-tight">
            Other vessels on {shipment.corridor}
          </h2>
          <span className="font-mono text-[10px] tracking-wider text-muted-foreground uppercase">
            {corridorPeers.length} found
          </span>
        </div>
        <div className="divide-y divide-border/70">
          {corridorPeers.map((s) => (
            <Link
              key={s.id}
              to="/shipments/$id"
              params={{ id: s.id }}
              className="flex items-center justify-between px-4 py-2.5 font-mono text-xs transition-colors hover:bg-hi/30"
            >
              <span className="text-foreground">{s.vessel}</span>
              <span className="text-muted-foreground">{s.route}</span>
              <StatusChip status={s.status} />
            </Link>
          ))}
          {corridorPeers.length === 0 && (
            <div className="px-4 py-6 text-center font-mono text-xs text-muted-foreground">
              No other vessels currently on this corridor.
            </div>
          )}
        </div>
      </section>
    </Shell>
  );
}

function ShipmentNotFound() {
  return (
    <Shell range="24H" onRangeChange={() => {}}>
      <div className="rounded-xl bg-card p-8 text-center ring-1 ring-border">
        <p className="text-sm text-foreground">Shipment not found.</p>
        <Link
          to="/shipments"
          className="mt-2 inline-block font-mono text-[11px] text-muted-foreground transition-colors hover:text-foreground"
        >
          ← Back to Shipments
        </Link>
      </div>
    </Shell>
  );
}
