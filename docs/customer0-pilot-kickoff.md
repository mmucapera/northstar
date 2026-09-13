# CUSTOMER0 pilot — kickoff questions

**Status (2026-09-06):** Fabric model rewritten to match Project Spark exactly — the frontend
(Lovable) is now the source of truth for shape, backend follows. 10 tables (4 dims, 6 facts),
verified end-to-end through the real toolchain. See "What was built" at the bottom.

**Status (2026-09-05):** Pipeline scaffold built and verified end-to-end on `main` (YAML models
→ generated SQL → Fabric notebooks → DataPipeline JSON → data-quality validation notebook, via
`northstar-formation`). This is a redo of earlier work that was mistakenly done on the stale
`feat/refactor_real_co` branch — that branch used an older nested `fct`/`opr` domain structure
that no longer exists on `main`. See "What was built" at the bottom for what's actually here.

Questions asked before starting the code phase on the CUSTOMER0 pilot, and the answers given
2026-09-05.

## 1. Where do things actually stand with the CEO(s) right now?

- [ ] General interest only — no discovery call yet
- [ ] A discovery call is scheduled or imminent
- [ ] We already have a specific ask or spec from one company

**Answer:** General interest only — no discovery call yet.

## 2. Which company should the code phase target first?

- [ ] Prospect B
- [ ] Prospect A
- [x] CUSTOMER0
- [ ] Not decided — pick based on engagement status

**Answer:** CUSTOMER0.

## 3. Should real implementation extend the existing production Northstar pipeline, or continue from the new demo app?

- [ ] Extend existing Northstar (northstar-formation / northstar-deploy / northstar-flow)
- [ ] Build forward from `demo/insights-ui`
- [ ] Both, in parallel
- [ ] Not sure — want tradeoffs explained first

**Answer:** Extend the existing Northstar pipeline (northstar-formation / northstar-deploy / northstar-flow)
— onboard CUSTOMER0 the same way prior customers were onboarded: new YAML
models, new pipeline definitions, real Fabric medallion pipeline.

## 4. Do we have any real access yet — sample data, schema docs, or an Azure tenant — from CUSTOMER0?

- [x] No — nothing yet
- [ ] Some docs or sample data already
- [ ] We have Azure tenant / environment access

**Answer:** No — nothing yet. No discovery call, no data, no environment access.

## What this means for the code phase

- No real CUSTOMER0 data or environment exists yet — anything built now uses synthetic data shaped
  like what discovery is likely to surface (same standard as `demo/insights-ui`).
- Since there's no discovery call yet, this work is necessarily speculative — it should be
  treated as "ready to plug real data into," not as a confirmed spec. Revisit every assumption
  once a real CUSTOMER0 discovery conversation happens.

## Important context discovered on `main`

`main` already has another oil & gas customer in progress, with its
own bronze/silver/gold models (`tanks`, `shipments`, `region_inventory`, `production_trend`,
`kpi_snapshots`, `disruption_alerts`) and a working prototype UI in `UX/` (React + TanStack Start
+ shadcn/ui, synced with Lovable) — a midstream/downstream supply-chain focus (storage, shipments,
disruptions), distinct from CUSTOMER0's upstream JV-reconciliation focus. `demo/insights-ui` on `main`
is an uninitialized stub — the fuller Next.js version of it only exists on the stale branch.

`main` also has a flattened model structure — `models/_base/{bronze,silver,gold,framework}` and
`models/customers/<customer>/{bronze,silver,gold,data_quality}`, no more `fct`/`opr` domain
subfolders. `framework/required_columns.yaml` is a shared, actively-enforced column contract
(not present on the old branch as a real check) — worth knowing: **that other oil & gas
customer's own models currently fail this check** (6 fails — missing the required bronze audit
columns), a pre-existing gap, not something to copy. CUSTOMER0's models below were built to actually
pass it.

## What was built

Three fact tables, matching the three views already proven in `demo/insights-ui` (on the stale
branch) — built directly under `models/customers/customer0/` with no shared `_base` layer, matching
that other oil & gas customer's precedent (`extends: null` at bronze, no base counterpart yet for
oil & gas):

- `reconciliation` — allocated vs. lifted volumes and cash-call status, by partner/field/period
- `production` — actual vs. forecast production and well uptime, by field/period
- `hse_incidents` — monthly recordable incidents and exposure hours (TRIR)

Each has bronze/silver/gold YAML in `northstar-formation/models/customers/customer0/`. Unlike that other oil
& gas customer, these include the full framework-required bronze audit columns (`Sourcefile`,
`Manifest_package`, `Load_date`, `ins_batchid`, etc.) and use `inherit_columns: true` in silver,
per what `_base/framework/required_columns.yaml` itself documents as the intended pattern. Natural
composite keys are used throughout (no hashed surrogate key column) — matching that other
customer's actual working style, not the older `xxhash64(...)` surrogate keys from the stale
branch.

Also added:
- `northstar-formation/models/customers/customer0/config/model_exclusions.yaml` — excludes all 125 shared
  FMCG/CPG `_base` models (other customers' demand-forecasting tables CUSTOMER0 has no
  relationship to). Without this, `transform` still compiles the entire `_base` catalog into
  CUSTOMER0's build output alongside its own 3 tables — harmless (the actual pipeline JSON was always
  correctly scoped to CUSTOMER0's tables only, verified by inspecting `pipeline-content.json`'s
  activity lists) but genuinely confusing to browse. This uses an existing mechanism already
  used by other customers (e.g. `models/customers/<customer>/config/model_exclusions.yaml`), just
  applied as a full allowlist-via-denylist here since CUSTOMER0 extends none of `_base` (`extends: null`
  everywhere). Note: this only affects `transform`'s output — `check-framework`/`orphans` don't
  read this file and will still report on the full merged catalog (125 unrelated models included);
  that's expected and harmless.
- `northstar-formation/data_pipelines/customers/customer0/` — `pl_bronze.yaml` / `pl_silver.yaml` /
  `pl_gold.yaml`, matching that other oil & gas customer's minimal `domain_prefix: ""`
  auto-discovery style (no manual notebook lists needed)
- `northstar-formation/models/customers/customer0/data_quality/validation.yaml` — uniqueness, not-null, enum,
  and range checks across all three tables
- `northstar-formation/models/_base/framework/required_columns.yaml` — registered `reconciliation`,
  `production`, `hse_incidents` in the shared `facts:` list so they're correctly classified as
  facts (not dimensions), matching every other customer's tables in this shared file
- **Dimensional model** (added after the initial commit `38ceaec8`, not yet committed):
  `dim_partner` (Partner, PartnerRole), `dim_field` (Field, ExportPoint), and `dim_period`
  (Period, Year, Quarter, MonthNumber, MonthName) — proper star schema instead of flat facts.
  Bronze/silver stay denormalized (raw extract shape, standard medallion practice); the split
  happens at gold, where `fact_reconciliation`/`fact_production` were trimmed to keys + measures
  only (`PartnerRole`/`ExportPoint` moved to their dims). `dim_partner`/`dim_field`/`dim_period`
  are genuine SCD dims (carry `valid_from`/`valid_to`/`is_current`, filtered `T.Is_current = 1`
  at gold) — they're intentionally *not* in `required_columns.yaml`'s `facts:` list, unlike the
  3 fact tables. `data_quality/validation.yaml` gained uniqueness checks on all 3 dims plus
  referential-integrity checks (every Partner/Field in the facts must exist in its dim).
  Verified: `check-framework` → 90 OK/0 fail (dims show `Kind=dim`, facts show `Kind=fact`),
  `transform` → 18 models (6 tables × 3 layers, exclusions still hold), pipeline JSON activity
  lists now include `DIM_PARTNER`/`DIM_FIELD`/`DIM_PERIOD` alongside the 3 facts.
- **`demo/insights-ui`** — was an empty, uncommitted Next.js stub on `main` (only `next-env.d.ts`
  tracked); rebuilt it as the actual client-facing visual (Next.js 14 + Tailwind + Recharts),
  not `UX/` (that app's `CustomerDataset` type is hardcoded to another customer's downstream
  supply-chain shape — tanks, shipments, inventory — a poor fit for CUSTOMER0's upstream JV domain
  without a real type-system refactor; also Lovable-synced, better left alone). Three pages
  (`/`, `/production`, `/hse-esg`) mirroring the star schema above, with synthetic data
  literally computed as dims + facts joined at read time. Verified in a real headless-Chromium
  render (`npx playwright`, since `chromium-cli` wasn't available) — all three pages render with
  zero console errors. One real bug caught and fixed during that verification: the HSE page's
  "YTD" exposure hours reset every January while incidents were summed across the full 12-month
  window, so TRIR silently mixed two different periods — rebuilt as a genuine non-resetting
  trailing-12-month metric instead (see `lib/data.ts` `monthlyHseIncidents` comment).
- **No changes needed** to `northstar-formation/scripts/build_all_customers.sh` — it auto-discovers
  every folder under `models/customers/`, so customer0 is picked up automatically. Pipeline JSON
  generation will still require a real `CUSTOMER0_WORKSPACE_ID` env var once a Fabric workspace exists.
- **Not created**: an `northstar-deploy/configurations/customer0/` folder — that other oil & gas customer
  doesn't have one either yet, so this is deliberately left at parity with where the more mature
  oil & gas customer currently stands, rather than getting ahead of it.

**Verified, not just written** — ran the actual `northstar-formation` CLI end-to-end against these
models on `main`: `transform` (YAML → Spark SQL), `check-framework` (84 OK / 0 warn / 0 fail,
all three tables correctly classified as `fact`), `orphans` (no missing-upstream issues on the
new tables), `--generate-notebooks` (9 real Fabric notebooks), `generate-validation-notebook`
(12 tests / 14 table-checks), and `pipelines` (3 Fabric DataPipeline JSON files) all completed
successfully with real output inspected by hand. Re-verified after adding `model_exclusions.yaml`:
`transform` output dropped from 134 models / ~39 bronze notebooks to exactly 9 models / 3 bronze
notebooks (its own tables only), and the pipeline JSON activity lists were unchanged (still
`BRZ_RECONCILIATION`/`BRZ_PRODUCTION`/`BRZ_HSE_INCIDENTS` and their silver/gold equivalents),
confirming the exclusion only cleaned up local build clutter without touching what deploys.

## Rewritten to match Project Spark (2026-09-06)

Project Spark (Lovable) is now the canonical CUSTOMER0 frontend (`demo/insights-ui` retired — see
`docs/project-spark-feature-requests.md`). Workflow inverted: frontend defines the shape, Fabric
follows. The model above was rewritten field-for-field against
`Project Spark/src/data/delta-basin.ts` (read in full, not guessed at).

**Schema changes:**
- All dims/facts switched from name-based natural keys to **ID-based keys** matching Spark exactly
  (`PartnerId`/`FieldId`/`PeriodId`/`CauseId`, with separate `*Name`/`Label` display columns) —
  more correct (names can change without changing identity) and required for an exact match anyway.
- `dim_partner` gained `EquityPct`; `dim_field` gained `WellsTotal` (moved off `production`, since
  it's a static field attribute, not something that varies per period); `dim_period` gained
  `Period` (DATE) and `Label` ("Aug 2026") alongside the existing calendar columns.
- New `dim_downtime_cause` + `fact_downtime` (period × cause grain) — Spark's downtime-cause trend
  chart needed a real source, there wasn't one before.
- New `fact_cash_call_event` (one row per status-change event: submitted → under-review →
  settled/disputed, with timestamp + note) — backs Spark's per-partner cash-call timeline.
- **`hse_incidents` corrected from monthly-aggregate to incident grain** — this was flagged as a
  known gap in `docs/project-spark-feature-requests.md` (#9) and is now fixed regardless of
  whether that frontend feature ships: one row per incident (`IncidentId`, `FieldId`, `Severity`,
  `Recordable`, `Description`), matching Spark's `Incident` type. Exposure hours split into a new
  `hse_exposure` table (period grain) since hours-worked is a rostering metric, not tied to one
  incident — recordable counts are now derived from `hse_incidents`, not duplicated.
- **TRIR is intentionally not a stored column anywhere.** Spark recomputes it as a trailing-12-month
  rolling rate on every load (`trirTrailing12()` in `delta-basin.ts`); the Fabric equivalent is a
  Power BI DAX time-intelligence measure over `fact_hse_incidents` + `fact_hse_exposure`, not a
  physical gold column — keeps the figure from ever going stale, matching Spark's own stated design
  principle on the HSE page.
- `fact_reconciliation` gained `CashCallUsd` (raw bronze column) and a computed `Flag`
  (within-tolerance/watch/investigate) whose thresholds (1.5%/3%) are hard-copied from Spark's
  `VARIANCE_TOLERANCE` constant — **keep these two in sync by hand if either changes**, there's no
  shared source of truth between the two codebases for this value.

**A real, pre-existing bug found and fixed along the way:** `generate_ddl_notebook()` in
`src/northstar_formation/generators/ddl_notebook.py` still assumed the old `sql/{domain}/{layer}/*.sql`
folder layout from before the fct/opr flattening (commit `12a201d7`) and silently produced zero
DDL output for any customer using the new flat `sql/{layer}/*.sql` layout. Confirmed this affects
**other customers too**, not just customer0 — pre-existing platform-wide debt, not something introduced
here. Fixed to detect both layouts; re-verified DDL notebook generation for customer0 (30 tables) and
other customers on both the new flat layout (142 tables, previously silently broken) and the old
nested layout (124 tables, confirms it still works — no regression for customers still using it).

**Verified, not just written** (2026-09-06 round): full toolchain re-run against the rewritten
10-table model — `transform` → 30 models (matches 4 dims + 6 facts × 3 layers exactly, exclusions
still hold), `check-framework` → all 10 customer0 tables OK with correct fact/dim classification,
`orphans` → one confirmed tooling false-positive (`fact_reconciliation.Flag`, a multi-branch CASE
expression the orphan-tracer's column extractor doesn't parse — verified by direct SQL inspection
twice, documented inline in the YAML, not a real issue), `--generate-notebooks` → 30 real Fabric
notebooks + working DDL notebook, `generate-validation-notebook` → 29 tests / 38 table-checks, and
`pipelines` → 3 DataPipeline JSON files with activity lists confirmed to exactly match the 10
tables per layer (inspected `pipeline-content.json` directly, not assumed).
