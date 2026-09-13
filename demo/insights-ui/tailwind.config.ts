import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        surface: "var(--surface)",
        ink: {
          primary: "var(--ink-primary)",
          secondary: "var(--ink-secondary)",
          muted: "var(--ink-muted)",
        },
        line: "var(--line)",
        card: "var(--card)",
        series: {
          1: "var(--series-1)",
          2: "var(--series-2)",
        },
        status: {
          good: "var(--status-good)",
          warning: "var(--status-warning)",
          critical: "var(--status-critical)",
        },
      },
      borderRadius: {
        card: "0.75rem",
      },
    },
  },
  plugins: [],
};
export default config;
