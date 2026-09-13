import { createContext, useContext, useMemo, useState, type ReactNode } from "react";
import { useDeltaBasin } from "@/components/delta-basin-context";

type PeriodContextValue = { periodId: string; setPeriodId: (id: string) => void };

const PeriodContext = createContext<PeriodContextValue>({
  periodId: "",
  setPeriodId: () => {},
});

export function PeriodProvider({ children }: { children: ReactNode }) {
  const { currentPeriodId } = useDeltaBasin();
  const [periodId, setPeriodId] = useState(currentPeriodId);
  const value = useMemo(() => ({ periodId, setPeriodId }), [periodId]);
  return <PeriodContext.Provider value={value}>{children}</PeriodContext.Provider>;
}

export const usePeriod = () => useContext(PeriodContext);
