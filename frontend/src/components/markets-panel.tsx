import { useEffect, useState } from "react";
import { TrendingDown, TrendingUp } from "lucide-react";
import { Panel, NewBadge } from "@/components/ui-kit";
import { getMarketsSnapshot, type MarketsSnapshot } from "@/data/markets";

const REFRESH_MS = 60_000;

function formatRate(rate: number) {
  return rate >= 100 ? rate.toFixed(1) : rate.toFixed(4);
}

export function MarketsPanel() {
  const [snapshot, setSnapshot] = useState<MarketsSnapshot | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await getMarketsSnapshot();
        if (!cancelled) setSnapshot(data);
      } catch {
        /* keep last-known snapshot on a transient failure */
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    void load();
    const id = window.setInterval(load, REFRESH_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const asOfLocal = snapshot?.fetchedAt
    ? new Date(snapshot.fetchedAt).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })
    : null;

  return (
    <Panel
      title="Markets"
      note="Crude benchmarks and USD reference rates, auto-refreshing"
      actions={<NewBadge />}
    >
      {loading && !snapshot ? (
        <p className="text-xs text-muted-foreground">Loading market data…</p>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2">
          <div>
            <p className="tabular text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Crude oil, per barrel
            </p>
            {snapshot?.oilError ? (
              <p className="mt-2 text-xs text-muted-foreground">{snapshot.oilError}</p>
            ) : (
              <div className="mt-2 space-y-2">
                {snapshot?.oil.map((o) => (
                  <div key={o.symbol} className="flex items-center justify-between">
                    <span className="text-sm text-foreground">{o.label}</span>
                    <span className="flex items-center gap-2">
                      <span className="tabular text-sm text-foreground">${o.price.toFixed(2)}</span>
                      <span
                        className={`tabular flex items-center gap-0.5 text-xs ${
                          o.changePct >= 0 ? "text-positive" : "text-critical"
                        }`}
                      >
                        {o.changePct >= 0 ? (
                          <TrendingUp className="size-3" aria-hidden />
                        ) : (
                          <TrendingDown className="size-3" aria-hidden />
                        )}
                        {o.changePct >= 0 ? "+" : ""}
                        {o.changePct.toFixed(2)}%
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
          <div>
            <p className="tabular text-[10px] uppercase tracking-[0.14em] text-muted-foreground">
              Exchange rates, vs. USD
            </p>
            {snapshot?.fxError ? (
              <p className="mt-2 text-xs text-muted-foreground">{snapshot.fxError}</p>
            ) : (
              <div className="mt-2 space-y-2">
                {snapshot?.fx.map((r) => (
                  <div key={r.code} className="flex items-center justify-between">
                    <span className="text-sm text-foreground">{r.label}</span>
                    <span className="tabular text-sm text-foreground">{formatRate(r.rate)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {asOfLocal ? (
        <p className="tabular mt-4 border-t border-border pt-2 text-[10px] uppercase tracking-[0.1em] text-muted-foreground">
          Refreshed {asOfLocal} · oil quotes may be delayed; FX is a daily reference rate
        </p>
      ) : null}
    </Panel>
  );
}
