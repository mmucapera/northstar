import { createFileRoute, Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { PageHeader, SyntheticNote } from "@/components/ui-kit";

export const Route = createFileRoute("/prd")({
  head: () => ({
    meta: [
      { title: "Documentation — Delta Basin CUSTOMER0 pilot" },
      {
        name: "description",
        content:
          "Requirements for Delta Basin: a single-tenant upstream data platform for JV reconciliation, production operations and HSE, built pre-discovery on synthetic data.",
      },
      { property: "og:title", content: "Delta Basin — Product requirements" },
      {
        property: "og:description",
        content: "Scope, data architecture, metrics and open questions for the CUSTOMER0 pilot. Draft v0.1, pre-discovery.",
      },
    ],
  }),
  component: PrdPage,
});

const sections = [
  ["summary", "Summary"],
  ["problem", "Problem & opportunity"],
  ["goals", "Goals & non-goals"],
  ["personas", "Users & personas"],
  ["scope", "Scope: MVP vs. future"],
  ["requirements", "Functional requirements"],
  ["architecture", "Data architecture & loads"],
  ["nfr", "Non-functional requirements"],
  ["metrics", "Success metrics"],
  ["roadmap", "Roadmap & milestones"],
  ["risks", "Risks & open questions"],
  ["glossary", "Appendix & glossary"],
] as const;

function Section({ id, n, title, children }: { id: string; n: string; title: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-8 border-t border-border pt-8">
      <h2 className="font-display text-xl font-semibold tracking-tight text-foreground">
        <span className="tabular mr-3 text-sm text-primary">{n}</span>
        {title}
      </h2>
      <div className="mt-4 space-y-4 text-sm leading-relaxed text-muted-foreground">{children}</div>
    </section>
  );
}

function Req({ pri, children }: { pri: "Must" | "Should" | "Could"; children: ReactNode }) {
  const tone =
    pri === "Must" ? "text-critical" : pri === "Should" ? "text-warning" : "text-muted-foreground";
  return (
    <li className="flex gap-3 border-b border-border py-2 last:border-0">
      <span className={`tabular w-14 shrink-0 text-[10px] uppercase tracking-[0.14em] ${tone}`}>{pri}</span>
      <span className="text-foreground/90">{children}</span>
    </li>
  );
}

function PrdPage() {
  return (
    <>
      <PageHeader
        eyebrow="Product requirements · Draft v0.1 · Pre-discovery"
        title="Delta Basin — CUSTOMER0 pilot"
        description="A single-tenant data platform for upstream joint-venture reconciliation, production operations and HSE performance, built ahead of discovery on synthetic data shaped to what an CUSTOMER0 engagement will most likely surface."
      />

      <div className="grid gap-8 lg:grid-cols-[200px_minmax(0,1fr)]">
        <nav className="hidden lg:block">
          <div className="sticky top-8">
            <p className="tabular text-[10px] uppercase tracking-[0.18em] text-muted-foreground">
              Contents
            </p>
            <ul className="mt-3 space-y-1.5">
              {sections.map(([id, label], i) => (
                <li key={id}>
                  <a
                    href={`#${id}`}
                    className="flex gap-2 text-xs text-muted-foreground transition-colors hover:text-foreground"
                  >
                    <span className="tabular text-primary/70">{String(i + 1).padStart(2, "0")}</span>
                    {label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>

        <article className="min-w-0 space-y-8">
          <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-border bg-border sm:grid-cols-4">
            {[
              ["Customer", "CUSTOMER0 (working name)"],
              ["Platform", "Microsoft Fabric"],
              ["Deployment", "Single-tenant, client Azure"],
              ["Status", "Draft — pre-discovery"],
            ].map(([k, v]) => (
              <div key={k} className="bg-card p-4">
                <dt className="tabular text-[10px] uppercase tracking-[0.16em] text-muted-foreground">{k}</dt>
                <dd className="mt-1 text-sm text-foreground">{v}</dd>
              </div>
            ))}
          </dl>

          <Section id="summary" n="01" title="Summary">
            <p>
              Delta Basin is a purpose-built insights platform for Niger Delta upstream joint-venture
              operators, adapting Northstar's medallion pipeline — already in production for three
              enterprise customers — to oil &amp; gas. CUSTOMER0 is the first upstream target, alongside
              another enterprise deployment's existing midstream/downstream build on the same platform.
            </p>
            <p>
              No discovery conversation has happened yet. The schema, the dashboards and the data are
              an informed hypothesis, built to be discovery-ready: correct in shape and mechanics,
              populated with synthetic data, so a real conversation can validate or correct
              assumptions against a working system rather than a slide deck.
            </p>
          </Section>

          <Section id="problem" n="02" title="Problem & opportunity">
            <p>
              CUSTOMER0 operates at a scale where production, joint-venture cash flow and safety data live
              across partner and operator systems that don't talk to each other. Three pain points are
              common across JV operators of this profile and form the working hypothesis:
            </p>
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">JV reconciliation friction.</strong> Allocated vs.
                lifted volumes, and the cash calls tied to them, are reconciled manually across partner
                spreadsheets — slow, error-prone, a common source of inter-partner disputes.
              </li>
              <li>
                <strong className="text-foreground">Production visibility lag.</strong> Field-level
                output, forecast variance and well uptime reach field engineers long before anyone who
                can act on a portfolio-wide trend.
              </li>
              <li>
                <strong className="text-foreground">Safety reporting overhead.</strong> HSE metrics are
                compiled periodically rather than tracked continuously, delaying the signal that should
                be driving operational decisions.
              </li>
            </ul>
          </Section>

          <Section id="goals" n="03" title="Goals & non-goals">
            <div className="grid gap-4 md:grid-cols-3">
              {[
                {
                  h: "Business goals",
                  items: [
                    "A working, demonstrable pilot fast enough to support an active leadership conversation.",
                    "Prove the platform generalises beyond FMCG/CPG into oil & gas, ahead of Prospect A and Prospect B.",
                    "Establish a reusable upstream schema pattern, not a one-off build.",
                  ],
                },
                {
                  h: "Product goals",
                  items: [
                    "One reconciliation view: allocated vs. lifted variance and cash-call status per partner, field and period.",
                    "One operations view: actual vs. forecast production and well uptime with a fleet trend.",
                    "One safety view: recordable incidents and TRIR on a consistent trailing-12-month basis.",
                  ],
                },
                {
                  h: "Non-goals (v1)",
                  items: [
                    "Not real-time — daily batch is the target cadence.",
                    "Not a replacement for the ERP or JV accounting system of record.",
                    "Not multi-tenant SaaS.",
                    "Not real data integration — that begins after discovery.",
                  ],
                },
              ].map((col) => (
                <div key={col.h} className="rounded-lg border border-border bg-card p-4">
                  <h3 className="font-display text-sm font-semibold text-foreground">{col.h}</h3>
                  <ul className="mt-3 space-y-2 text-xs leading-relaxed">
                    {col.items.map((it) => (
                      <li key={it}>{it}</li>
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          </Section>

          <Section id="personas" n="04" title="Users & personas">
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-surface-2">
                  <tr>
                    {["Persona", "Primary need", "Module"].map((h) => (
                      <th
                        key={h}
                        className="tabular px-3 py-2 text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["JV / Finance Accountant", "Variance and dispute status without chasing spreadsheets", "JV Reconciliation"],
                    ["Production Engineer / Ops Manager", "Spot forecast misses and well downtime early", "Production & Ops"],
                    ["HSE Officer", "A consistent, always-current TRIR", "HSE & ESG"],
                    ["Executive", "JV, production and safety health together", "Overview"],
                  ].map((r) => (
                    <tr key={r[0]} className="border-t border-border">
                      <td className="px-3 py-2 text-foreground">{r[0]}</td>
                      <td className="px-3 py-2">{r[1]}</td>
                      <td className="px-3 py-2 text-primary">{r[2]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="scope" n="05" title="Scope: MVP vs. future">
            <p>
              All four views are built and running against synthetic data — not screenshots. Open them
              directly:
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {[
                ["/", "Overview — cross-module health and open items"],
                ["/reconciliation", "JV Reconciliation — variance, cash calls, partner drill-through"],
                ["/production", "Production & Operations — output, uptime, downtime causes"],
                ["/hse", "HSE & ESG — TRIR, incident log, exposure hours"],
              ].map(([to, label]) => (
                <Link
                  key={to}
                  to={to as "/"}
                  className="rounded-md border border-border bg-surface px-3 py-2 text-xs text-foreground transition-colors hover:border-primary/50"
                >
                  {label}
                </Link>
              ))}
            </div>
            <p className="pt-2 font-medium text-foreground">Future scope (post-discovery)</p>
            <ul className="list-disc space-y-1.5 pl-5">
              <li>Real source-system integration, replacing the synthetic generator.</li>
              <li>Row-level security scoped by partner, so a non-operating partner sees only their allocations.</li>
              <li>Power BI embed option alongside the native UI.</li>
              <li>Cost / JV-budget and host-community ESG-spend domains.</li>
              <li>Reuse of the same dim/fact pattern for Prospect A and Prospect B.</li>
            </ul>
          </Section>

          <Section id="requirements" n="06" title="Functional requirements">
            <div className="space-y-6">
              <div>
                <h3 className="font-display text-sm font-semibold text-foreground">JV Reconciliation</h3>
                <ul className="mt-2">
                  <Req pri="Must">Allocated and lifted volumes per partner, per field, for the current period.</Req>
                  <Req pri="Must">Variance in bbl and %, flagged within-tolerance / watch / investigate against published thresholds.</Req>
                  <Req pri="Must">Cash-call status per record: settled, pending or disputed.</Req>
                  <Req pri="Should">12-month net-variance trend at JV level.</Req>
                  <Req pri="Could">Drill from summary into a partner's historical reconciliation records (built).</Req>
                </ul>
              </div>
              <div>
                <h3 className="font-display text-sm font-semibold text-foreground">Production & Operations</h3>
                <ul className="mt-2">
                  <Req pri="Must">Actual vs. forecast production (bopd) per field for the current period.</Req>
                  <Req pri="Must">Wells online/total and uptime %, with normal / watch / down status.</Req>
                  <Req pri="Should">12-month fleet-wide uptime trend.</Req>
                  <Req pri="Could">Downtime-cause breakdown once source systems capture it (stubbed).</Req>
                </ul>
              </div>
              <div>
                <h3 className="font-display text-sm font-semibold text-foreground">HSE & ESG</h3>
                <ul className="mt-2">
                  <Req pri="Must">TRIR from recordable incidents and exposure hours over a trailing-12-month window.</Req>
                  <Req pri="Must">Monthly incident log and 12-month incident trend.</Req>
                  <Req pri="Should">Cumulative exposure-hours trend over the same window.</Req>
                  <Req pri="Could">Host-community spend and ESG initiative tracking.</Req>
                </ul>
              </div>
              <div>
                <h3 className="font-display text-sm font-semibold text-foreground">Cross-cutting</h3>
                <ul className="mt-2">
                  <Req pri="Must">A single period selector that applies across every module, so figures always compare like with like.</Req>
                  <Req pri="Must">A visible synthetic-data marker and data-generation timestamp on every screen.</Req>
                  <Req pri="Should">Export the current table view to CSV for offline partner circulation.</Req>
                </ul>
              </div>
            </div>
          </Section>

          <Section id="architecture" n="07" title="Data architecture & daily loads">
            <div className="flex flex-wrap items-center gap-2 rounded-lg border border-border bg-card p-4">
              {["Source", "Bronze", "Silver", "Gold", "Serve"].map((step, i, arr) => (
                <span key={step} className="flex items-center gap-2">
                  <span className="tabular rounded-sm border border-border bg-surface-2 px-2.5 py-1 text-xs text-foreground">
                    {step}
                  </span>
                  {i < arr.length - 1 ? <span className="text-primary">→</span> : null}
                </span>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="font-display text-sm font-semibold text-foreground">Dimensions</h3>
                <ul className="tabular mt-2 space-y-1 text-xs">
                  <li>dim_partner — Partner, PartnerRole, EquityPct</li>
                  <li>dim_field — Field, ExportPoint, WellsTotal</li>
                  <li>dim_period — Period, Year, Quarter, Month</li>
                </ul>
              </div>
              <div className="rounded-lg border border-border bg-card p-4">
                <h3 className="font-display text-sm font-semibold text-foreground">Facts</h3>
                <ul className="tabular mt-2 space-y-1 text-xs">
                  <li>fact_reconciliation — AllocatedBbl, LiftedBbl, CashCallStatus</li>
                  <li>fact_production — ActualBopd, ForecastBopd, UptimePct</li>
                  <li>fact_hse_incidents — RecordableIncidentCount, HoursWorkedYtd</li>
                </ul>
              </div>
            </div>
            <ul className="mt-2">
              <Req pri="Must">A new day's bronze extract lands and flows through to gold nightly.</Req>
              <Req pri="Must">Until real source access exists, a synthetic daily-load generator produces a new extract on the same schedule, exercising bronze→silver→gold end to end.</Req>
              <Req pri="Should">Each simulated day introduces plausible variation — a dispute opening or closing, a well going down, an incident — so the pipeline is tested against change, not a replayed snapshot.</Req>
              <Req pri="Could">Late-arriving or corrected prior-day data, to exercise the existing replay mechanism against this schema.</Req>
            </ul>
            <p>
              Storage and compute stay decoupled: data lives in open Delta format on ADLS Gen2
              regardless of engine, Fabric Spark handles transforms for the pilot, Databricks stays a
              documented configuration option, and Fabric SQL Database holds orchestration state only.
              "Fabric vs. Databricks" is therefore a decision CUSTOMER0 can make later, not a lock-in this
              pilot forces.
            </p>
          </Section>

          <Section id="nfr" n="08" title="Non-functional requirements">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">Data sovereignty.</strong> Single-tenant deployment
                inside CUSTOMER0's own Azure tenant; data never leaves their environment.
              </li>
              <li>
                <strong className="text-foreground">Auditability.</strong> Every bronze record carries
                load lineage (Load_date, ins_batchid, Manifest_package).
              </li>
              <li>
                <strong className="text-foreground">Data quality.</strong> Uniqueness, not-null, enum,
                range and referential-integrity checks at silver for every table — 17 tests across 22
                table-checks as of this draft.
              </li>
              <li>
                <strong className="text-foreground">Security.</strong> Azure AD / service-principal auth
                for pipeline access; partner-scoped row-level security is future scope.
              </li>
              <li>
                <strong className="text-foreground">Framework compliance.</strong> All models pass the
                shared column contract — 90 OK / 0 fail.
              </li>
            </ul>
          </Section>

          <Section id="metrics" n="09" title="Success metrics">
            <div className="overflow-x-auto rounded-md border border-border">
              <table className="w-full text-sm">
                <thead className="bg-surface-2">
                  <tr>
                    {["Metric", "Target", "How it's measured"].map((h) => (
                      <th
                        key={h}
                        className="tabular px-3 py-2 text-left text-[10px] uppercase tracking-[0.14em] text-muted-foreground"
                      >
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[
                    ["Reconciliation cycle time", "Reduce vs. manual baseline", "Period close to all cash calls settled or disputed"],
                    ["Same-day production visibility", "100% of fields", "Fields with prior-day actuals by the next-day SLA"],
                    ["TRIR reporting lag", "Continuous, not monthly", "Age of the displayed TRIR vs. incident date"],
                    ["Pilot adoption", "Weekly active use across all personas", "Post-discovery instrumentation (not yet built)"],
                  ].map((r) => (
                    <tr key={r[0]} className="border-t border-border">
                      <td className="px-3 py-2 text-foreground">{r[0]}</td>
                      <td className="px-3 py-2">{r[1]}</td>
                      <td className="px-3 py-2">{r[2]}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Section>

          <Section id="roadmap" n="10" title="Roadmap & milestones">
            <ol className="space-y-3">
              {[
                ["Done", "Pilot build — synthetic data", "Star schema, dashboards, data-quality checks, framework compliance, verified against the real toolchain."],
                ["Next", "Daily simulated loads", "Scheduled generator producing a new extract nightly, exercising the pipeline continuously."],
                ["Blocked on CUSTOMER0", "Discovery & scoping", "Confirm pain points, source systems and data access. Every assumption here gets revisited."],
                ["Post-discovery", "Real data integration", "Replace the generator with real extracts; re-validate the schema against actual data shapes."],
                ["Mid-2027", "Production rollout & OTC showcase", "Phased rollout beyond pilot scope; demonstrated publicly at OTC 2027."],
              ].map(([tag, title, body]) => (
                <li key={title} className="rounded-lg border border-border bg-card p-4">
                  <span className="tabular text-[10px] uppercase tracking-[0.16em] text-primary">{tag}</span>
                  <p className="mt-1 text-sm font-medium text-foreground">{title}</p>
                  <p className="mt-1 text-xs leading-relaxed">{body}</p>
                </li>
              ))}
            </ol>
          </Section>

          <Section id="risks" n="11" title="Risks & open questions">
            <ul className="list-disc space-y-2 pl-5">
              <li>
                <strong className="text-foreground">No discovery call has happened.</strong> Every
                requirement is a hypothesis — the schema is designed to be corrected, not defended.
              </li>
              <li>
                <strong className="text-foreground">Fabric capacity cost at CUSTOMER0's scale.</strong> F-SKU
                pricing is flat regardless of usage and real volume estimates don't exist yet.
              </li>
              <li>
                <strong className="text-foreground">Unknown source-system landscape.</strong> Whether
                daily batch extraction is possible at all is unconfirmed.
              </li>
              <li>
                <strong className="text-foreground">NUPRC regulatory reporting.</strong> Not yet
                modelled; likely relevant to a production deployment.
              </li>
              <li>
                <strong className="text-foreground">Model-exclusion maintenance.</strong> The build
                currently excludes 125 unrelated FMCG base models by explicit list; an allowlist is
                needed before a third oil &amp; gas customer.
              </li>
            </ul>
          </Section>

          <Section id="glossary" n="12" title="Appendix & glossary">
            <dl className="grid gap-3 sm:grid-cols-2">
              {[
                ["bopd", "Barrels of oil per day — a production rate."],
                ["bbl", "Barrel of oil — a volume unit."],
                ["TRIR", "Total Recordable Incident Rate — incidents per 200,000 exposure hours."],
                ["JOA", "Joint Operating Agreement — governs cost and revenue sharing between partners."],
                ["Cash call", "A partner's required contribution toward JV costs for a period."],
                ["Medallion", "Bronze (raw) → Silver (cleaned) → Gold (modelled) data layering."],
              ].map(([term, def]) => (
                <div key={term} className="rounded-md border border-border bg-card p-3">
                  <dt className="tabular text-xs text-primary">{term}</dt>
                  <dd className="mt-1 text-xs">{def}</dd>
                </div>
              ))}
            </dl>
          </Section>

          <SyntheticNote>
            Draft v0.1, pre-discovery — every figure and assumption in this document and in the
            dashboards it links to is synthetic or hypothesised until a real CUSTOMER0 discovery
            conversation happens.
          </SyntheticNote>
        </article>
      </div>
    </>
  );
}
