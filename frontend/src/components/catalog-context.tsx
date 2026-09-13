import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { products as seedProducts, type Product } from "@/data/catalog";
import { useActivityLog } from "@/components/activity-log-context";

const STORAGE_KEY = "delta-basin-catalog-v1";

type CatalogValue = {
  items: Product[];
  updateProduct: (id: string, patch: Partial<Product>) => void;
  resetCatalog: () => void;
};

const CatalogContext = createContext<CatalogValue | null>(null);

export function CatalogProvider({ children }: { children: ReactNode }) {
  const { record } = useActivityLog();
  const [items, setItems] = useState<Product[]>(seedProducts);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const parsed = JSON.parse(raw) as Product[];
        if (Array.isArray(parsed) && parsed.length > 0) setItems(parsed);
      }
    } catch {
      /* ignore malformed cache */
    }
  }, []);

  const value = useMemo<CatalogValue>(
    () => ({
      items,
      updateProduct: (id, patch) =>
        setItems((prev) => {
          const before = prev.find((p) => p.id === id);
          const next = prev.map((p) =>
            p.id === id
              ? { ...p, ...patch, updatedAt: new Date().toISOString().slice(0, 10) }
              : p,
          );
          try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
          } catch {
            /* storage unavailable */
          }
          if (before) {
            const fields = Object.keys(patch).join(", ");
            record("catalog.update", `Updated ${before.name} (${fields}).`);
          }
          return next;
        }),
      resetCatalog: () => {
        try {
          localStorage.removeItem(STORAGE_KEY);
        } catch {
          /* storage unavailable */
        }
        setItems(seedProducts);
        record("catalog.reset", "Reset the materials catalogue to its seed state.");
      },
    }),
    [items],
  );

  return <CatalogContext.Provider value={value}>{children}</CatalogContext.Provider>;
}

export function useCatalog() {
  const ctx = useContext(CatalogContext);
  if (!ctx) throw new Error("useCatalog must be used inside CatalogProvider");
  return ctx;
}
