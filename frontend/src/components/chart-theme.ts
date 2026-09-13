export const chartAxis = {
  stroke: "var(--muted-foreground)",
  tick: { fill: "var(--muted-foreground)", fontSize: 11 },
  tickLine: false,
  axisLine: false,
} as const;

/** For an X axis of month labels specifically - angled and given extra
 * height so labels don't run into each other the way horizontal ones do in
 * a narrow multi-column chart panel. Spread this instead of chartAxis on
 * any XAxis keyed on a period/month field. */
export const chartMonthAxis = {
  ...chartAxis,
  angle: -35,
  textAnchor: "end" as const,
  height: 50,
} as const;

export const chartTooltip = {
  contentStyle: {
    background: "var(--surface-2)",
    border: "1px solid var(--border)",
    borderRadius: "6px",
    fontSize: "12px",
    color: "var(--foreground)",
  },
  labelStyle: { color: "var(--muted-foreground)" },
  cursor: { stroke: "var(--grid)" },
} as const;
