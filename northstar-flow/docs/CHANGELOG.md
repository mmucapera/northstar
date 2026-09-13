for consistency with the upstream Northstar naming convention.
# Changelog

## 2026-04-17

### Migrate file-naming.yaml to per-source DB config

Filename parsing config (extension, must-contain filter, regex pattern, source
code, file format) was previously loaded from `file-naming.yaml` as module-level
globals. Now each `poller_source` row carries its own filename config, enabling
different ADLS sources to use different filename conventions.

#### northstar-flow-DB

- **`migrations/012_add_filename_config_to_poller_source.sql`** — Adds 5 columns
  to `poller_source`: `filename_extension`, `filename_must_contain`,
  `filename_pattern`, `source_code`, `source_file_format`. DEFAULT constraints
  auto-populate existing rows for backward compatibility.

#### northstar-flow

- **`app/config.py`** — Added 5 fields to `ADLSSourceConfig`; expanded SELECT and
  mapping in `load_adls_sources_from_db()`.
- **`app/services/adls_poller.py`** — Removed YAML loading block and `import yaml`;
  added per-instance `_filename_re` compilation in `__init__`; replaced all 5 global
  references with `self.source_config.*`; converted `_parse_filename_segments` from
  `@staticmethod` to instance method; added deprecation log for legacy YAML file.
- **`app/models/schemas.py`** — Added filename config fields to `PollerSourceInfo`,
  `PollerSourceCreate`, and `PollerSourceUpdate`.
- **`app/services/poller_registry.py`** — Expanded INSERT in `add_source`, `allowed`
  set and reload SELECT in `update_source`, and `PollerSourceInfo` construction in
  `list_sources`, `add_source`, and `update_source`.
- **`app/api/poller.py`** — `create_source` passes 5 new fields to `ADLSSourceConfig`.

### Configurable late arrival scope per domain

Late arrival batch scoping was hardcoded to `domain_code + package_def`. Different
domains need different scoping. Added `late_arrival_scope_field` column to
`domain_config` with values `'package_def'` (default), `'extraction_def'`, or
`'both'`. NULL is treated as `'package_def'` everywhere (backward compatible).

Also fixes a **runtime NameError bug** in `medallion_orchestrator.py` where
undefined variable `extraction_def` in a logger call caused crashes.

#### northstar-flow-DB

- **`migrations/011_add_late_arrival_scope_field.sql`** — New migration adding
  `late_arrival_scope_field` column with CHECK constraint.
- **`Tables/domain_config.sql`** — Added column and constraint to DDL.
- **`StoredProcedures/get_late_arrivals_pending.sql`** — Added
  `late_arrival_scope_field` to SELECT; updated ORDER BY to include
  `extraction_def`.
- **`StoredProcedures/get_s2g_ready.sql`** — Replaced hardcoded `package_def`-only
  NOT EXISTS with scope-aware blocking logic using
  `COALESCE(dc.late_arrival_scope_field, 'package_def')`.
- **`extract_processor_notebook.Notebook/notebook-content.py`** —
  - `detect_late_arrival()`: Added `scope_field` parameter; builds WHERE clause
    dynamically based on scope.
  - Consolidated two separate `domain_config` queries into one (manifest pattern,
    cutoff, and scope field).
  - Call site passes `scope_field=late_arrival_scope`.
- **`.sharedqueries/07_manage_domains.sql`** — Added `late_arrival_scope_field` to
  SELECT, INSERT template, and quick-view query.

#### northstar-flow

- **`app/services/medallion_orchestrator.py`** — Scope-aware grouping in
  `_check_late_arrivals()`; fixed NameError bug (undefined `extraction_def`);
  updated all log messages with scope info.
- **`streamlit_ui/pages/late_arrivals.py`** — Groupby includes `extraction_def`;
  blocker SQL matches both fields; added `extraction_def` input to rerun form.
- **`streamlit_ui/data/api_client.py`** — Added `extraction_def` parameter to
  `batch_rerun()`.

### Fix: `MedallionOrchestratorStatusResponse` missing fields

- **`app/models/schemas.py`** — Added 3 missing fields to `MedallionOrchestratorStatusResponse`:
  `late_arrivals_auto_replayed`, `late_arrivals_alerted`, `late_arrival_threshold_hours`.
  Fixed `grace_period_minutes` default from `30` to `5` (matching `config.py`).

### Documentation refresh

Full validation of both docs against the codebase.

#### northstar-flow

- **`docs/e2e-medallion-flow.md`** — Fixed `extraction_def` → `package_def` scoping
  references; documented auto-replay orchestration step (Phase 7); added missing env
  vars (`INS_ORCH_LATE_ARRIVAL_THRESHOLD_HOURS`, `INS_ORCH_LATE_ARRIVAL_CHECK_INTERVAL_SECONDS`);
  added missing SPs (`get_late_arrivals_pending`, `get_pending_extracts`,
  `create_workspace_signal`, `acknowledge_workspace_signal`); added missing tables
  (`poller_source`, `workspace_signal`); fixed `push_job.status` values
  (`PARTIAL`/`CANCELLED`, removed stale `RECALLED`); updated ADLS poller to reflect
  multi-source architecture and adaptive backoff; fixed poll interval default (10, not 30);
  added `package_def` to `BatchRerunRequest`/`BatchRerunResponse` docs; fixed S2G blocking
  scope description.
- **`docs/late-arrival-auto-replay.md`** — Full rewrite from "implementation plan" to
  reference doc. Removed stale "What's Missing" section (all items implemented). Fixed
  all `extraction_def` → `package_def` scoping. Corrected file path (`medallion.py`
  not `medallion_sync.py`). Updated embedded SP pseudocode to match actual code.
  Documented `_check_late_arrivals()` orchestrator method and config settings.

### Per-domain manifest filename pattern

Added configurable `manifest_filename_pattern` column to `domain_config`. Each
domain can now define a Python regex to match its manifest file inside ZIPs.
When `NULL`, the existing default behavior (files starting with `MetaData`) is
preserved.

#### northstar-flow-DB

- **`Tables/domain_config.sql`** — Added `manifest_filename_pattern` and
  `extraction_date_cutoff` columns to DDL.
- **`migrations/010_add_manifest_filename_pattern.sql`** — New migration to add
  the column.
- **`extract_processor_notebook.Notebook/notebook-content.py`** —
  `parse_manifest()` now accepts an optional `manifest_pattern` parameter;
  call site fetches pattern from `domain_config`.
- **`.sharedqueries/07_manage_domains.sql`** — Added `manifest_filename_pattern`
  to SELECT and INSERT templates.

### Rename domain codes: `FCT` -> `DP`, `OPR` -> `SP`

Domain codes used throughout the orchestrator and agent layers have been renamed
for consistency with the upstream Northstar naming convention.

#### Schema Note

- Domain rename logic is now represented in baseline SQL/shared queries for clean-create environments.

#### northstar-flow-DB

- **`.sharedqueries/07_manage_domains.sql`** — All example domain codes changed
  from `'FCT'` to `'DP'`.
- **`.sharedqueries/02_streamlit_queries.sql`** — Updated filter comments.
- **`.sharedqueries/04_manage_workspaces.sql`** — Updated domain filter example.
- **`.sharedqueries/05_update_pipeline_ids.sql`** — Updated workspace comment.
- **`.sharedqueries/05_update_pipeline_ids.sql`** — Updated comment.
- **`extract_processor_notebook.Notebook/notebook-content.py`** — Updated example
  filename and bronze path comments.

#### northstar-flow

- **`file-naming.yaml`** — Updated domain examples and filename sample.
- **`docs/e2e-medallion-flow.md`** — Updated all `OPR`/`FCT` references in
  filename examples, concurrency table, late-arrival design notes, and API
  request/response samples.

## 2026-04-16

### Rename `extraction_def` to `package_def` for late-arrival batch scoping

The late-arrival detection and auto-replay logic was incorrectly grouping batches
by `extraction_def`. The correct grouping key is `package_def`, which represents
the logical package scope for sequencing and replay.

#### northstar-flow

- **`app/models/schemas.py`** — Added `package_def` field to `BatchRerunRequest`
  and `BatchRerunResponse` schemas.
- **`app/api/medallion.py`** — Pass `package_def` through the batch-rerun endpoint
  to the stored procedure and response.
- **`app/services/medallion_orchestrator.py`** — Changed auto-replay grouping key
  from `extraction_def` to `package_def`; updated log messages accordingly.
- **`streamlit_ui/data/api_client.py`** — Renamed `extraction_def` parameter to
  `package_def` in `batch_rerun()` helper.
- **`streamlit_ui/pages/late_arrivals.py`** — Updated SQL queries, DataFrame
  grouping, column labels, blocker-detection joins, and the batch-rerun form to
  use `package_def` instead of `extraction_def`. Also improved NULL-safe join
  for blocker detection (`package_def IS NULL` handling).

#### northstar-flow-DB

- **`StoredProcedures/reset_late_arrival_batch.sql`** — Added `@package_def`
  parameter; applied `package_def` filter in all WHERE clauses (reset, replay,
  and result-set queries). Updated batch comment to reference `package_def`.
- **`StoredProcedures/get_late_arrivals_pending.sql`** — Changed ORDER BY from
  `extraction_def` to `package_def`.
- **`StoredProcedures/get_s2g_ready.sql`** — Added NULL-safe `package_def`
  filter in the late-arrival blocking subquery; updated comment to clarify
  scope is `domain + extraction_def + package_def`.
- **`extract_processor_notebook.Notebook/notebook-content.py`** —
  - `detect_late_arrival()`: Added `package_def` parameter; changed sequencing
    logic to use `package_def` instead of `extraction_def`; added NULL-safe
    SQL branch when `package_def` is None; updated log message.
  - Normal-mode call site: passes `manifest["package_def"]` to the detector.

#### Cleanup

- Deleted stale metadata TSV files:
  - `MetaData_DP_DemandPlanningWeekly_UnisonInsightsDEU2DemandPlanning_20260320_230020.tsv`
  - `MetaData_SP_Daily_UnisonInsights1ONE1_20260321_033024.tsv`
