"use client";

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthlyHseIncidents } from "@/lib/data";

export function IncidentTrendChart() {
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="mb-3 text-sm font-semibold text-ink-primary">Recordable incidents (12mo)</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={monthlyHseIncidents} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={false} />
          <Tooltip
            formatter={(value: number) => `${value} incident${value === 1 ? "" : "s"}`}
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
          />
          <Bar dataKey="recordableIncidentCount" name="Recordable incidents" fill="var(--series-2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
