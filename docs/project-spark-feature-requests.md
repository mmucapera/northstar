# Project Spark — feature requests for Lovable

**Status (2026-09-06):** `Project Spark` is now the canonical CUSTOMER0 pilot frontend, replacing
`demo/insights-ui` (which retires — may be redone later, differently, if needed). `UX/`
(another oil & gas customer) is untouched — separate customer, separate data domain, not part of
this decision.

**How to use this doc:** each item below is written close to how you'd actually prompt Lovable —
copy the **Ask** line into the Lovable chat, adjust to taste. Items are grouped by priority, not
by module, since a couple of these (esp. #1–2) are real bugs worth fixing before anything else
gets layered on top.

The workflow going forward is **frontend-first**: Lovable defines the shape, then
`northstar-formation`'s Fabric models get built or revised to match it — the reverse of how the pilot
started. Every item below that has a data implication says so under **Fabric implication**, so
that work is tracked as it comes in rather than rediscovered later.

---

## Priority 1 — Fix before adding anything else

### 1. Broken product images in the Materials Catalogue
**Problem:** `ProductPhoto` renders a broken-image icon for every product — `imageUrl` is
declared in the `Product` type but never populated in `src/data/catalog.ts`.
**Ask:** *"Every product in the Materials Catalogue shows a broken image icon. Either generate a
simple placeholder (a category icon or a flat-color swatch with the SKU prefix) for every product,
or remove the image slot from the product cards and table entirely."*
**Fabric implication:** none — pure frontend data-generation gap.

### 2. Node engine mismatch
**Problem:** `@tanstack/start-server-core` and related packages require Node ≥22.12; the project
ran fine locally on Node 20.20.2 but only after an `EBADENGINE` warning. This will eventually bite
in CI or on a teammate's machine with a stricter Node install.
**Ask:** *"Pin the required Node version in package.json's `engines` field and document it in the
README, so `npm install` fails loudly on an unsupported Node version instead of warning and
continuing."*
**Fabric implication:** none.

---

## Priority 2 — Lean into what's already there, with sharper labeling

### 3. Label the Materials Catalogue as a capability showcase, not confirmed scope
**Problem:** nothing wrong with the module — it's well-built. The only real risk is someone
mistaking it for a validated CUSTOMER0 requirement when it's actually Lovable/our own forward-thinking
addition, not something from discovery.
**Ask:** *"Add a small 'Capability preview' badge next to 'Materials' in the sidebar nav, and a
one-line note at the top of the Materials page: 'Shown to illustrate platform breadth — not yet
scoped with CUSTOMER0.' Keep the JV Reconciliation / Production / HSE nav items unbadged, since those
are the confirmed pilot scope."*
**Fabric implication:** none — but see #10 below if Materials becomes real scope later.

### 4. Sharper disclosure where real place names carry fictional numbers
**Problem:** Bonny, Qua Iboe, Forcados, and Brass are real Niger Delta export terminals; "Ekpo" is
close to a real field name. The generic "Synthetic data, pre-discovery" footer is true but doesn't
call out *why* real names appear next to fake numbers — worth being explicit rather than relying
on a reader to infer it.
**Ask:** *"Expand the synthetic-data disclosure (footer + any tooltip on field/terminal names) to
say something like: 'Field and terminal names (Bonny, Qua Iboe, Forcados, Brass) are real Niger
Delta locations, used for realism. All volumes, values, partners, and incidents shown are entirely
fictional.' Make this specific enough that no one could mistake a figure for real intelligence."*
**Fabric implication:** none.

---

## Priority 3 — Depth features (these carry real Fabric implications)

### 5. Partner drill-in profile page
**Ask:** *"Make each partner in the JV Reconciliation table link to a dedicated profile page:
equity %, full settlement history, a running dispute count, and their variance trend already
shown inline today — but as a first-class page, not just an expanding chart."*
**Fabric implication:** `dim_partner` needs `EquityPct` (already in Spark's model, not yet in
`northstar-formation/models/customers/customer0/`). A settlement/dispute history implies a new
`fact_cash_call_event` table (see #6).

### 6. Cash-call status history, not just current status
**Problem:** today a cash call is a single current state (settled/pending/disputed). A real JV
accountant needs to see *when* it changed state and why.
**Ask:** *"Add a status-change trail to each cash call: submitted → under review →
settled/disputed, each with a timestamp and an optional note. Show it as a small timeline on the
partner drill-in page (#5)."*
**Fabric implication:** new `fact_cash_call_event` (or `_history`) table — `fact_reconciliation`
currently only carries current-state, this needs event grain. This is a genuine gold-layer
schema addition, not a relabeling.

### 7. Simple field/terminal schematic view
**Ask:** *"Add a lightweight schematic (not a real map — a simplified diagram is fine) showing the
5 fields, their export points, and current status color, so a viewer gets spatial context a table
can't give."*
**Fabric implication:** `dim_field` needs a position field (either real lat/long, or a simplified
`schematic_x`/`schematic_y` pair — real lat/long is unnecessary until real discovery, don't
over-build this).

### 8. Downtime-cause trend over time
**Problem:** today's downtime-cause chart is a current-period snapshot only.
**Ask:** *"Show downtime causes as a trend over the trailing 12 months, not just the current
period — is 'Flowline integrity' getting worse or better?"*
**Fabric implication:** needs a downtime-cause dimension plus a period-grain fact — currently
generated ad hoc in the frontend (`downtimeForPeriod`), not modeled in Fabric at all yet.

### 9. Incident severity mix, not just count
**Problem:** Spark's `Incident` type already captures severity (First aid / Medical treatment /
Restricted work / Lost time) per incident — genuinely more correct than what's currently in
`northstar-formation` (a monthly aggregate count only). The frontend just isn't visualizing it yet.
**Ask:** *"Add a stacked or grouped view of incident severity mix over time, using the severity
field already on each incident record."*
**Fabric implication — important, not just a nice-to-have:** `fact_hse_incidents` in
`northstar-formation/models/customers/customer0/` is currently monthly-aggregate grain
(`RecordableIncidentCount`, `HoursWorkedYtd`). Spark's incident-grain model (one row per incident,
with `Severity`, `FieldId`, `Recordable`) is the more correct design. **This should be corrected in
Fabric regardless of whether #9 ships** — it's a real schema gap between what's now the
source-of-truth design and what's already built.

### 10. Role-aware view switcher (mocked, no real auth yet)
**Ask:** *"Add a lightweight 'View as: Finance / Ops / HSE / Executive' switcher in the header
that filters the sidebar nav and Overview panels to that persona's slice — no real
authentication needed yet, just a preview of what row-level scoping will eventually look like."*
**Fabric implication:** none yet — this previews where partner-scoped row-level security
(already flagged as future scope in the PRD) will eventually attach.

### 11. If Materials Catalogue becomes real scope later
**Ask (only once confirmed with CUSTOMER0, not now):** *"Wire Materials Catalogue to the same
period/data-refresh pattern as the other three modules."*
**Fabric implication:** an entirely new domain — `dim_product`, `dim_supplier`,
`fact_inventory_snapshot` — not scoped anywhere in the current PRD. Don't build this in Fabric
until/unless CUSTOMER0 actually confirms it's needed; keep it frontend-only until then.

---

## Priority 4 — Polish

### 12. Empty-state audit
**Ask:** *"Confirm every panel has a designed empty state for a zero-data period — 'Fields off
plan' and 'Needs attention' already handle this well ('All fields normal', 'Nothing flagged'); make
sure the incident log, downtime chart, and Materials table degrade the same way."*

### 13. Print/PDF-friendly stylesheet per dashboard page
**Ask:** *"Add a print stylesheet (light-mode override, no sidebar/nav chrome) for each dashboard
page, the way board packs or partner-facing reports would need it — similar to what was done for
the standalone PRD document."*

### 14. Number-formatting consistency pass
**Ask:** *"Do a pass across all pages confirming bbl/bopd/USD/percent formatting is applied
consistently (thousands separators, decimal places, unit suffixes) — spot-checked fine in review,
worth making a formal, enforced convention as more pages get added."*

---

## Summary: what this means for `northstar-formation`

Once the above is prioritized and built in Lovable, here's what changes on the Fabric side to
match — this is the reverse-mapping the frontend-first workflow implies:

| Frontend feature | Fabric change needed |
|---|---|
| #5 Partner equity % | `dim_partner` + `EquityPct` column |
| #6 Cash-call history | New `fact_cash_call_event` table (event grain, not current-state) |
| #7 Field schematic | `dim_field` + position column(s) |
| #8 Downtime trend | New downtime-cause dimension + period-grain fact |
| #9 Incident severity | **Correct `fact_hse_incidents` to incident grain now** — not gated on #9 shipping |
| #11 Materials (if confirmed) | New domain: `dim_product`, `dim_supplier`, `fact_inventory_snapshot` |

Everything else in this doc (Priority 1, 2, 4) is frontend-only and needs no Fabric change.
