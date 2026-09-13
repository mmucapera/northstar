"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { monthlyHseIncidents } from "@/lib/data";

const num = new Intl.NumberFormat("en-US");

export function HoursWorkedChart() {
  return (
    <div className="rounded-card border border-line bg-card p-4">
      <div className="mb-3 text-sm font-semibold text-ink-primary">Exposure hours, trailing 12 months (cumulative)</div>
      <ResponsiveContainer width="100%" height={260}>
        <AreaChart data={monthlyHseIncidents} margin={{ top: 4, right: 8, left: 8, bottom: 4 }}>
          <defs>
            <linearGradient id="hoursFill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-1)" stopOpacity={0.35} />
              <stop offset="100%" stopColor="var(--series-1)" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={{ stroke: "var(--line)" }} />
          <YAxis tick={{ fontSize: 11, fill: "var(--ink-secondary)" }} tickLine={false} axisLine={false} tickFormatter={(v) => num.format(v / 1000) + "k"} />
          <Tooltip
            formatter={(value: number) => `${num.format(value)} hrs`}
            contentStyle={{ background: "var(--card)", border: "1px solid var(--line)", borderRadius: 8, fontSize: 12 }}
          />
          <Area type="monotone" dataKey="hoursWorkedTrailing12mo" name="Hours worked (12mo cum.)" stroke="var(--series-1)" strokeWidth={2} fill="url(#hoursFill)" />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
