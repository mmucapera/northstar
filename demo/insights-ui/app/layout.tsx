import type { Metadata } from "next";
import "./globals.css";
import { NavBar } from "@/components/NavBar";

export const metadata: Metadata = {
  title: "Niger Delta Insights — Demo",
  description: "Synthetic demo: upstream JV reconciliation, production operations, and HSE/ESG.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="font-sans antialiased min-h-screen">
        <NavBar />
        <div className="mx-auto max-w-6xl px-6 pt-4">
          <div className="rounded-card border border-line bg-surface px-4 py-2.5 text-xs text-ink-muted">
            Illustrative demo — synthetic composite data, not sourced from any client or real operator.
          </div>
        </div>
        {children}
      </body>
    </html>
  );
}
