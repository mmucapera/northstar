import { StatTile } from "@/components/StatTile";
import { PageHeader } from "@/components/PageHeader";
import { ProductionChart } from "@/components/ProductionChart";
import { UptimeTrendChart } from "@/components/UptimeTrendChart";
import { ProductionTable } from "@/components/ProductionTable";
import { productionKpis } from "@/lib/data";

const num = new Intl.NumberFormat("en-US");

export default function ProductionPage() {
  const k = productionKpis();
  const forecastVariancePct = ((k.totalActualBopd - k.totalForecastBopd) / k.totalForecastBopd) * 100;

  return (
    <main className="mx-auto max-w-6xl px-6 py-10">
      <PageHeader
        eyebrow="Production & Operations"
        title="Delta Basin Joint Venture — current period"
        description="Field-level production against forecast, well uptime, and export point status across the JV's operated and non-operated fields."
      />

      <section className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile label="Total production" value={`${num.format(k.totalActualBopd)} bopd`} />
        <StatTile
          label="vs. forecast"
          value={`${forecastVariancePct >= 0 ? "+" : ""}${forecastVariancePct.toFixed(1)}%`}
          delta={{
            label: `${num.format(k.totalForecastBopd)} bopd forecast`,
            tone: forecastVariancePct < -10 ? "critical" : forecastVariancePct < -3 ? "warning" : "good",
          }}
        />
        <StatTile
          label="Fleet-wide well uptime"
          value={`${k.fleetUptimePct.toFixed(1)}%`}
          delta={{ label: k.fleetUptimePct < 85 ? "below target" : "on target", tone: k.fleetUptimePct < 75 ? "critical" : k.fleetUptimePct < 90 ? "warning" : "good" }}
        />
        <StatTile
          label="Fields down/watch"
          value={String(k.downCount)}
          delta={{ label: "of 4 fields", tone: k.downCount > 0 ? "critical" : "good" }}
        />
      </section>

      <section className="mb-6 grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ProductionChart />
        <UptimeTrendChart />
      </section>

      <section>
        <h2 className="mb-3 text-sm font-semibold text-ink-primary">Field-level operations detail</h2>
        <ProductionTable />
      </section>
    </main>
  );
}
