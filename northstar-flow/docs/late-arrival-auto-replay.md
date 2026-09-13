# Automatic Late Arrival Replay — Design & Implementation

> **Last updated**: 2026-04-17

## Context

When an extraction arrives out of sequence (e.g., extraction C arrives after D already processed B2S), the Fabric notebook sets `is_late_arrival = 1` on the extract, and the stored procedures block it from B2S/S2G processing. The orchestrator **automatically detects and replays** late arrivals within a configurable threshold (default: 48 hours), per domain. Beyond the threshold, the system logs an alert and leaves the late arrival for manual intervention via the Late Arrival Manager UI (`POST /medallion-sync/batch/rerun`).

### Sequence scope

Late arrival detection operates on `domain_code + package_def` scope (set in the notebook's `detect_late_arrival` function). `extraction_def` is irrelevant to sequence scoping — separate package definitions within the same domain are what define independent data sequences.

---

## Components

| Component | Status | File |
|---|---|---|
| `is_late_arrival` flag on `extract` table | Done | `northstar-flow-DB/Tables/extract.sql` |
| `late_arrival_alerted_at` on `extract` table | Done | `northstar-flow-DB/Tables/extract.sql` |
| `late_arrival_replay_threshold_hours` on `domain_config` | Done | `northstar-flow-DB/Tables/domain_config.sql` |
| `detect_late_arrival()` in notebook | Done | `northstar-flow-DB/extract_processor_notebook.Notebook/notebook-content.py` |
| `get_b2s_queue` SP filters `is_late_arrival = 0` | Done | `northstar-flow-DB/StoredProcedures/get_b2s_queue.sql` |
| `get_b2s_queue` SP ORDER BY includes `package_def` | Done | `ORDER BY extraction_date ASC, package_def ASC, extract_id ASC` |
| `get_s2g_ready` SP blocks when `is_late_arrival = 1` exists | Done | `northstar-flow-DB/StoredProcedures/get_s2g_ready.sql` (scoped by `package_def`) |
| `reset_late_arrival_batch` SP (skip/replay) | Done | `northstar-flow-DB/StoredProcedures/reset_late_arrival_batch.sql` (params: `@extraction_def`, `@package_def`) |
| `get_late_arrivals_pending` SP | Done | `northstar-flow-DB/StoredProcedures/get_late_arrivals_pending.sql` |
| `_check_late_arrivals()` orchestrator method | Done | `northstar-flow/app/services/medallion_orchestrator.py` |
| Config: threshold + check interval | Done | `northstar-flow/app/config.py` (`ins_orch_late_arrival_threshold_hours=48`, `ins_orch_late_arrival_check_interval_seconds=300`) |
| `POST /medallion-sync/batch/rerun` API endpoint | Done | `northstar-flow/app/api/medallion.py` |
| Late Arrival Manager UI page | Done | `northstar-flow/streamlit_ui/pages/late_arrivals.py` |
| Orchestrator status includes late arrival stats | Done | `late_arrivals_auto_replayed`, `late_arrivals_alerted`, `late_arrival_threshold_hours` in status response |

---

## How It Works

### Step 1: Detection (Notebook Time)

**File**: `northstar-flow-DB/extract_processor_notebook.Notebook/notebook-content.py`

At Step 4.5 of notebook processing, `detect_late_arrival()` checks:

```sql
SELECT COUNT(*) FROM medallion_sync ms
  JOIN extract e ON ms.extract_id = e.extract_id
 WHERE e.domain_code = @domain_code
   AND e.package_def = @package_def   -- sequence scope
   AND e.extraction_date > @extraction_date
   AND ms.b2s_status IN ('RUNNING', 'SUCCESS', 'FAILED')
```

If count > 0: this extract arrived after a newer one was already processed. Sets `is_late_arrival = 1`.

The extract is still processed normally (unzip, push to Bronze) — it's just flagged so the orchestrator skips it for B2S/S2G.

### Step 2: SP Guards (Orchestrator)

Late arrivals are excluded from normal processing:

| SP | Guard |
|----|-------|
| `get_b2s_pending_batches` | `AND e.[is_late_arrival] = 0` |
| `get_b2s_queue` | `AND e.[is_late_arrival] = 0` |
| `get_s2g_ready` | `NOT EXISTS` — blocks S2G per `domain_code + package_def` scope if any late arrival exists |

### Step 3: Pending Detection SP

**File**: `northstar-flow-DB/StoredProcedures/get_late_arrivals_pending.sql`

Called by the orchestrator's `_check_late_arrivals()` method. Returns late arrival extracts with eligibility info:

```sql
CREATE PROCEDURE [dbo].[get_late_arrivals_pending]
    @default_threshold_hours INT = 48
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        e.[extract_id],
        e.[domain_code],
        e.[extraction_def],
        e.[extraction_date],
        e.[package_def],
        e.[arrived_at],
        e.[late_arrival_alerted_at],
        DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME()) AS hours_since_arrival,
        COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours) AS threshold_hours,
        CASE
            WHEN DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME())
                 <= COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours)
            THEN 1 ELSE 0
        END AS eligible_for_auto_replay
    FROM [dbo].[extract] e
    INNER JOIN [dbo].[domain_config] dc ON e.[domain_code] = dc.[domain_code]
    WHERE e.[is_late_arrival] = 1
    ORDER BY e.[domain_code], e.[package_def], e.[extraction_date];
END;
```

### Step 4: Configuration

**File**: `northstar-flow/app/config.py`

```python
ins_orch_late_arrival_threshold_hours: int = 48        # global default
ins_orch_late_arrival_check_interval_seconds: int = 300  # check every 5 min
```

Per-domain override: `domain_config.late_arrival_replay_threshold_hours` (NULL = use global default).

### Step 5: Orchestrator Auto-Replay

**File**: `northstar-flow/app/services/medallion_orchestrator.py`

The `_check_late_arrivals()` method runs as Step 4 of the orchestration loop, gated by `ins_orch_late_arrival_check_interval_seconds`:

```python
if (now - last_late_arrival_check).total_seconds() >= late_arrival_interval:
    await cls._check_late_arrivals()
    last_late_arrival_check = now
```

Logic:
1. Call `get_late_arrivals_pending` SP with the global threshold
2. Group results by `(domain_code, package_def)`
3. For each group:
   - If `eligible_for_auto_replay = 1`: call `reset_late_arrival_batch` SP with `lookback_hours = threshold`, `package_def = group_key`
   - If `eligible_for_auto_replay = 0` and `late_arrival_alerted_at IS NULL`: log warning, mark `late_arrival_alerted_at` on the extract

Stats counters: `_late_arrivals_auto_replayed`, `_late_arrivals_alerted` — exposed in `GET /orchestrator/status`.

### Step 6: Manual Intervention (Operator API)

For late arrivals beyond the auto-replay threshold:

```
POST /medallion-sync/batch/rerun
```

Request (`BatchRerunRequest`):
```json
{
    "domain_code": "SP",
    "lookback_hours": 24,
    "extraction_def": "Daily",
    "package_def": "UnisonInsights1ONE1",
    "target_workspace_id": null
}
```

- `lookback_hours = 0`: Skip/discard (sets `b2s_status = 'SKIPPED'`, clears `is_late_arrival`)
- `lookback_hours > 0`: Replay (resets B2S/S2G for all extracts in the batch within the lookback window)

---

## DB Schema

These fields are part of the baseline table definitions (no incremental migration step required):

```sql
-- northstar-flow-DB/Tables/extract.sql
[package_def] NVARCHAR(200) NULL,
[is_late_arrival] BIT DEFAULT ((0)) NOT NULL,
[late_arrival_alerted_at] DATETIME2(7) NULL,

-- northstar-flow-DB/Tables/domain_config.sql
[late_arrival_replay_threshold_hours] INT NULL,
```

---

## Files

| File | Role |
|---|---|
| `northstar-flow-DB/Tables/domain_config.sql` | `late_arrival_replay_threshold_hours` column |
| `northstar-flow-DB/Tables/extract.sql` | `is_late_arrival`, `late_arrival_alerted_at`, `package_def` columns |
| `northstar-flow-DB/StoredProcedures/get_late_arrivals_pending.sql` | SP for auto-replay detection |
| `northstar-flow-DB/StoredProcedures/reset_late_arrival_batch.sql` | SP for skip/replay (params: `@extraction_def`, `@package_def`) |
| `northstar-flow-DB/StoredProcedures/get_b2s_queue.sql` | `ORDER BY extraction_date, package_def, extract_id` |
| `northstar-flow-DB/StoredProcedures/get_s2g_ready.sql` | Late arrival blocking scoped by `package_def` |
| `northstar-flow/app/config.py` | Threshold + check interval settings |
| `northstar-flow/app/services/medallion_orchestrator.py` | `_check_late_arrivals()` method |
| `northstar-flow/app/api/medallion.py` | `POST /medallion-sync/batch/rerun` endpoint |
| `northstar-flow/streamlit_ui/pages/late_arrivals.py` | Late Arrival Manager UI |
