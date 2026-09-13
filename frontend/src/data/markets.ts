// Server-only: live market context (FX + crude benchmarks) for the pitch -
// oil & gas execs expect to see USD/NGN and Brent/WTI on a control-room
// screen. Both sources are free and require no API key, matching this
// session's pattern for the assistant's LLM key (start with a free/no-auth
// option, swap later if a paid data vendor is preferred):
//   - FX: open.er-api.com (no key, broad currency coverage incl. NGN -
//     Frankfurter/ECB was tried first but doesn't publish an NGN rate).
//     Free tier has no historical endpoint, so no day-over-day change is
//     shown for FX, only the live rate.
//   - Oil: Yahoo Finance's unofficial chart endpoint (query1.finance.yahoo.com) -
//     widely used, no key, but undocumented/unofficial and could change or
//     rate-limit without notice. Each side fails independently so one
//     outage doesn't blank both panels.
import { createServerFn } from "@tanstack/react-start";

export type FxRate = { code: string; label: string; rate: number };
export type OilQuote = { symbol: string; label: string; price: number; changePct: number };

export type MarketsSnapshot = {
  fx: FxRate[];
  fxAsOf: string | null;
  fxError: string | null;
  oil: OilQuote[];
  oilError: string | null;
  fetchedAt: string;
};

async function fetchFx(): Promise<{ fx: FxRate[]; asOf: string | null }> {
  const resp = await fetch("https://open.er-api.com/v6/latest/USD");
  if (!resp.ok) throw new Error(`FX fetch failed: ${resp.status}`);
  const body = (await resp.json()) as {
    result?: string;
    time_last_update_utc?: string;
    rates?: Record<string, number>;
  };
  if (body.result !== "success" || !body.rates) throw new Error("FX response malformed");
  const wanted: { code: string; label: string }[] = [
    { code: "NGN", label: "USD / NGN" },
    { code: "EUR", label: "USD / EUR" },
    { code: "GBP", label: "USD / GBP" },
  ];
  const fx = wanted
    .filter((w) => typeof body.rates?.[w.code] === "number")
    .map((w) => ({ code: w.code, label: w.label, rate: body.rates![w.code] }));
  return { fx, asOf: body.time_last_update_utc ?? null };
}

async function fetchOilSymbol(symbol: string, label: string): Promise<OilQuote> {
  const resp = await fetch(`https://query1.finance.yahoo.com/v8/finance/chart/${symbol}?interval=1d&range=5d`, {
    headers: { "User-Agent": "Mozilla/5.0" },
  });
  if (!resp.ok) throw new Error(`Oil fetch failed for ${symbol}: ${resp.status}`);
  const body = (await resp.json()) as {
    chart?: { result?: { meta?: { regularMarketPrice?: number; regularMarketChangePercent?: number } }[] };
  };
  const meta = body.chart?.result?.[0]?.meta;
  if (!meta || typeof meta.regularMarketPrice !== "number") throw new Error(`Oil response malformed for ${symbol}`);
  return { symbol, label, price: meta.regularMarketPrice, changePct: meta.regularMarketChangePercent ?? 0 };
}

async function fetchOil(): Promise<OilQuote[]> {
  const [wti, brent] = await Promise.all([
    fetchOilSymbol("CL=F", "WTI Crude"),
    fetchOilSymbol("BZ=F", "Brent Crude"),
  ]);
  return [brent, wti];
}

export const getMarketsSnapshot = createServerFn({ method: "GET" }).handler(async (): Promise<MarketsSnapshot> => {
  const [fxResult, oilResult] = await Promise.allSettled([fetchFx(), fetchOil()]);

  return {
    fx: fxResult.status === "fulfilled" ? fxResult.value.fx : [],
    fxAsOf: fxResult.status === "fulfilled" ? fxResult.value.asOf : null,
    fxError: fxResult.status === "rejected" ? "FX rates temporarily unavailable." : null,
    oil: oilResult.status === "fulfilled" ? oilResult.value : [],
    oilError: oilResult.status === "rejected" ? "Oil prices temporarily unavailable." : null,
    fetchedAt: new Date().toISOString(),
  };
});
