"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthlyNetVariancePct } from "@/lib/data";

export function VarianceTrendChart() {
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="mb-3 text-sm font-semibold text-ink-primary">Net variance trend (12mo)</div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={monthlyNetVariancePct} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <defs>
            <linearGradient id="varianceFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={false} tickFormatter={(v) => `${v}%`} />
          <Tooltip
            formatter={(value: number) => `${value.toFixed(1)}%`}
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
          />
          <Area type="monotone" dataKey="variancePct" name="Net variance" stroke="var(--series-1)" strokeWidth={2} fill="url(#varianceFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
