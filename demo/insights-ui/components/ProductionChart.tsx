"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { factProductionCurrent } from "@/lib/data";

const bopd = new Intl.NumberFormat("en-US");

export function ProductionChart() {
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="mb-3 text-sm font-semibold text-ink-primary">Actual vs. forecast production, by field</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={factProductionCurrent} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="field" tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} angle={-12} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={false} tickFormatter={(v) => bopd.format(v / 1000) + "k"} />
          <Tooltip
            formatter={(value: number) => `${bopd.format(value)} bopd`}
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="actualBopd" name="Actual" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="forecastBopd" name="Forecast" fill="var(--series-2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
