# INS Orchestrator — E2E Setup Steps

## Prerequisites
- Azure Service Principal (SP) with access to ADLS
- Microsoft Fabric capacity

## Setup Steps

### 1. Create Orchestrator Workspace
- Create a new Fabric workspace for the orchestrator

### 2. Create Target Workspace
- Create a new Fabric workspace for the target (customer/tenant)

### 3. Add Service Principal to Both Workspaces
- Add the SP as a **member** to the orchestrator workspace
- Add the SP as a **member** to the target workspace

### 4. Grant Orchestrator Identity to Target Workspace
- Add the **workspace identity** of the orchestrator workspace to the target workspace

### 5. Run First-Time Setup
- Execute `northstar-flow-DB/.sharedqueries/01_first_time_setup.sql` against the orchestrator SQL endpoint
- This creates all required tables (`domain_config`, `extract`, `target_workspace`, `poller_source`, etc.)

### 6. Deploy Stored Procedures
- Deploy all SPs from `northstar-flow-DB/StoredProcedures/` to the orchestrator SQL endpoint
- Key SPs: `register_extract`, `get_b2s_queue`, `get_b2s_pending_batches`, `get_s2g_ready`, `create_push_job`

### 7. Update `.env` with Orchestrator IDs
- Set `INS_ORCH_FABRIC_WORKSPACE_ID` to the orchestrator workspace ID
- Set `INS_ORCH_NOTEBOOK_ID` to the extract processor notebook ID
- Set `INS_ORCH_SQL_ENDPOINT` to the lakehouse SQL analytics endpoint hostname
- Set `INS_ORCH_DATABASE` to the lakehouse database name
- Set SAS token env var (e.g. `INS_ORCH_ADLS_SAS_TOKEN`) referenced by `poller_source` rows

### 8. Update Notebook SQL Connection
- Open the extract processor notebook in the orchestrator workspace
- Update `SQL_SERVER` (line 112) to match `INS_ORCH_SQL_ENDPOINT` from `.env`
- Update `SQL_DATABASE` (line 113) to match `INS_ORCH_DATABASE` from `.env`
- Publish the notebook

### 9. Add ADLS Shortcut
- Open the Lakehouse in the orchestrator workspace
- Add a shortcut pointing to the ADLS container

### 9. Seed Configuration
Run these shared queries against the SQL endpoint (in order — FK dependencies):

1. **`07_manage_domains.sql`** — Insert `domain_config` rows (domain_code, schedule, cutoff, etc.)
2. **`04_manage_workspaces.sql`** — Insert `target_workspace` rows (workspace/lakehouse GUIDs, pipeline IDs)
3. **`08_manage_poller_sources.sql`** — Insert `poller_source` rows (storage account, container, SAS token env var ref)

### 10. No Incremental Migrations Required
- This repository is maintained as a clean-create baseline.
- Create the workspace DB once using `northstar-flow-DB/.sharedqueries/01_first_time_setup.sql`.
- If schema changes are needed later, recreate the workspace DB from the updated baseline.

---

## Known Issues & Troubleshooting (from E2E testing 2026-04-03)

### SQL Endpoint Typo
- The Fabric SQL endpoint hostname starts with the letter `o`, not the digit `0`
- Example: `o6nrus...` not `06nrus...`
- Symptom: `TCP Provider: Error code 0x2746 (10054)` — connection refused
- Fix: verify `.env` `INS_ORCH_SQL_ENDPOINT` against the JDBC connection string from Fabric portal

### poller_state missing source_id column
- Symptom: `Invalid column name 'source_id'` errors on poller state queries
- Cause: database was not created from the current baseline scripts
- Fix: recreate the workspace DB using `northstar-flow-DB/.sharedqueries/01_first_time_setup.sql`

### SAS Token Env Var Not Resolved
- `poller_source` rows store SAS tokens as env var references like `${INS_ORCH_ADLS_SAS_TOKEN}`
- `_interpolate_env_vars()` uses `os.environ.get()` to resolve them
- pydantic-settings reads `.env` into its own fields but does NOT export to `os.environ`
- Symptom: warning "Environment variable 'X' referenced in config is not set", then `AzureSigningError: Incorrect padding`
- Fix: `load_dotenv()` is now called at the top of `config.py` to export `.env` vars to `os.environ`

### DB Poller Source Not Loaded (falls back to legacy env vars)
- `load_adls_sources_from_db()` queries `dbo.poller_source` — if it returns 0 rows or fails, the app falls through to YAML, then legacy env vars
- Symptom: log says "using legacy env vars (single source: 'default')" even though `poller_source` has rows
- Causes: wrong SQL endpoint in `.env`, table not created yet, or connection failure
- Debug: check for `poller_source query returned N row(s)` log line; if missing, the DB query itself failed

### Historical Extracts Without Metadata File
- Older ZIP files may not contain a `MetaData*.tsv` manifest file
- `parse_manifest()` returns all `None` values if no manifest found
- `extraction_date` stays `NULL` on the extract row
- In SQL, `NULL >= cutoff` evaluates to `UNKNOWN` (falsy), so these extracts would be silently blocked by the cutoff filter
- Fix: all cutoff conditions in SPs now include `OR e.[extraction_date] IS NULL` so extracts without a manifest are never blocked

### Historical Extracts Copied to Bronze Despite Cutoff
- The `extraction_date_cutoff` check happens inside the notebook AFTER the ZIP is opened and manifest parsed
- The poller still detects, registers, and triggers notebooks for ALL files including historical ones
- The notebook sets `SKIPPED` status and exits early if `extraction_date < cutoff`
- Unzip/convert to staging still runs (needed to read the manifest), but push-to-bronze does NOT happen
- B2S and S2G pipelines also filter by cutoff as a safety net

### Notebook SQL Connection Mismatch
- The notebook has `SQL_SERVER` and `SQL_DATABASE` **hardcoded** in its parameters cell (lines 112–113)
- When you create a new orchestrator workspace, the lakehouse gets a new SQL endpoint and database name
- If the notebook still points at the old workspace's DB, extracts show `NOT_FOUND` because the notebook queries a different DB than the orchestrator registered them in
- Symptom: `extract_id=N not in NEW/TRIGGERED state (current=NOT_FOUND) — skipping to avoid double processing`
- Fix: update `SQL_SERVER` and `SQL_DATABASE` in the notebook to match `INS_ORCH_SQL_ENDPOINT` and `INS_ORCH_DATABASE` from `.env`

### 210+ Files Detected on First Run
- If the ADLS container has historical data, the poller will detect ALL files on startup
- This triggers notebook runs for every file — most will quickly get `SKIPPED` status if a cutoff is set
- This is expected behavior; `poller_state` tracks seen files so subsequent polls are quiet
