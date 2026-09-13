import { createContext, useContext, useMemo, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  createDeltaBasin,
  generateMockRaw,
  type DeltaBasin,
  type RawDeltaBasin,
} from "@/data/delta-basin";
import { getDeltaBasinData } from "@/data/fabric-data";

export const deltaBasinQueryKey = ["delta-basin"] as const;

/** Live Fabric data if configured and reachable, otherwise the deterministic
 * mock dataset - never throws, so the app always has something to render. */
export async function fetchDeltaBasinRaw(): Promise<RawDeltaBasin> {
  const live = await getDeltaBasinData();
  return live ?? generateMockRaw();
}

const DeltaBasinContext = createContext<DeltaBasin | null>(null);

export function DeltaBasinProvider({ children }: { children: ReactNode }) {
  // The root route's loader primes this exact query via queryClient.ensureQueryData
  // before the tree renders (SSR + client), so `data` is already resolved here -
  // no loading flash, no Suspense boundary needed.
  const { data } = useQuery({
    queryKey: deltaBasinQueryKey,
    queryFn: fetchDeltaBasinRaw,
    staleTime: Number.POSITIVE_INFINITY,
  });

  const value = useMemo(() => createDeltaBasin(data ?? generateMockRaw()), [data]);

  return <DeltaBasinContext.Provider value={value}>{children}</DeltaBasinContext.Provider>;
}

export function useDeltaBasin() {
  const ctx = useContext(DeltaBasinContext);
  if (!ctx) throw new Error("useDeltaBasin must be used inside DeltaBasinProvider");
  return ctx;
}
