"use client";

import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { fieldSummary } from "@/lib/data";

const bbl = new Intl.NumberFormat("en-US");

export function AllocatedLiftedChart() {
  const data = fieldSummary();
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="mb-3 text-sm font-semibold text-ink-primary">Allocated vs. lifted, by field</div>
      <ResponsiveContainer width="100%" height={260}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="field" tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} interval={0} angle={-12} textAnchor="end" height={50} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={false} tickFormatter={(v) => bbl.format(v / 1000) + "k"} />
          <Tooltip
            formatter={(value: number) => `${bbl.format(value)} bbl`}
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
          />
          <Legend wrapperStyle={{ fontSize: 12 }} />
          <Bar dataKey="allocatedBbl" name="Allocated" fill="var(--series-1)" radius={[4, 4, 0, 0]} />
          <Bar dataKey="liftedBbl" name="Lifted" fill="var(--series-2)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
