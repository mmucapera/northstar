import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";

export type PersonaId = "executive" | "finance" | "ops" | "hse";

export type PersonaSlice =
  | "jv"
  | "production"
  | "hse"
  | "materials"
  | "alerts"
  | "docs";

export const personas: {
  id: PersonaId;
  label: string;
  blurb: string;
  slices: PersonaSlice[];
}[] = [
  {
    id: "executive",
    label: "Executive",
    blurb: "Everything, headline first — variance, output, safety and supply in one pass.",
    slices: ["alerts", "jv", "production", "hse", "materials", "docs"],
  },
  {
    id: "finance",
    label: "Finance",
    blurb: "Joint-venture variance, cash calls and settlement exposure.",
    slices: ["alerts", "jv", "materials", "docs"],
  },
  {
    id: "ops",
    label: "Ops",
    blurb: "Field output, well uptime, downtime causes and materials on hand.",
    slices: ["alerts", "production", "materials", "docs"],
  },
  {
    id: "hse",
    label: "HSE",
    blurb: "Recordables, TRIR and exposure hours across the asset base.",
    slices: ["alerts", "hse", "docs"],
  },
];

const STORAGE_KEY = "delta-basin-view-v1";

type ViewContextValue = {
  persona: PersonaId;
  setPersona: (id: PersonaId) => void;
  slices: PersonaSlice[];
  shows: (slice: PersonaSlice) => boolean;
};

const ViewContext = createContext<ViewContextValue>({
  persona: "executive",
  setPersona: () => {},
  slices: personas[0]!.slices,
  shows: () => true,
});

export function ViewProvider({ children }: { children: ReactNode }) {
  const [persona, setPersona] = useState<PersonaId>("executive");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY) as PersonaId | null;
    if (saved && personas.some((p) => p.id === saved)) setPersona(saved);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(STORAGE_KEY, persona);
  }, [persona]);

  const value = useMemo<ViewContextValue>(() => {
    const slices = (personas.find((p) => p.id === persona) ?? personas[0]!).slices;
    return {
      persona,
      setPersona,
      slices,
      shows: (slice: PersonaSlice) => slices.includes(slice),
    };
  }, [persona]);

  return <ViewContext.Provider value={value}>{children}</ViewContext.Provider>;
}

export const useView = () => useContext(ViewContext);

export const personaById = (id: PersonaId) => personas.find((p) => p.id === id) ?? personas[0]!;
