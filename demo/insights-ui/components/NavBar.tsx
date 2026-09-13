"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const links = [
  { href: "/", label: "JV Reconciliation" },
  { href: "/production", label: "Production & Operations" },
  { href: "/hse-esg", label: "HSE & ESG" },
];

export function NavBar() {
  const pathname = usePathname();
  return (
    <div className="border-b border-line bg-surface">
      <div className="mx-auto flex max-w-6xl items-center gap-1 px-6">
        {links.map((l) => {
          const active = l.href === "/" ? pathname === "/" : pathname.startsWith(l.href);
          return (
            <Link
              key={l.href}
              href={l.href}
              className={`relative px-3 py-4 text-sm font-medium transition-colors ${
                active ? "text-series-1" : "text-ink-secondary hover:text-ink-primary"
              }`}
            >
              {l.label}
              {active && <span className="absolute inset-x-3 bottom-0 h-0.5 rounded-full bg-series-1" />}
            </Link>
          );
        })}
      </div>
    </div>
  );
}
