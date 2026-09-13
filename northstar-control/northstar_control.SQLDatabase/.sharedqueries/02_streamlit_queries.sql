-- =============================================================================
-- INS Orchestrator — Streamlit Dashboard Queries
-- =============================================================================
-- All SQL queries used by the Streamlit UI pages.
-- These are the same queries embedded in the Python code, collected here
-- for reference, ad-hoc analysis, and testing.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Dashboard: Medallion pipeline status aggregation
-- Source: streamlit_ui/pages/dashboard.py
-- ─────────────────────────────────────────────────────────────────────────────

-- Filter dropdowns
SELECT DISTINCT domain_code FROM dbo.extract ORDER BY domain_code;
SELECT target_workspace_id, target_workspace_name FROM dbo.target_workspace ORDER BY target_workspace_name;

-- Main dashboard aggregation (pass NULL for "all")
DECLARE @domain NVARCHAR(20) = NULL;       -- e.g. 'DP' or NULL for all
DECLARE @workspace NVARCHAR(100) = NULL;   -- target_workspace_id or NULL for all

SELECT
    e.[domain_code],
    ms.[target_workspace_id],
    tw.[target_workspace_name],
    SUM(CASE WHEN ms.[bronze_status] = 'LOADED'      THEN 1 ELSE 0 END) AS bronze_loaded,
    SUM(CASE WHEN ms.[b2s_status] = 'NOT_STARTED'    THEN 1 ELSE 0 END) AS b2s_not_started,
    SUM(CASE WHEN ms.[b2s_status] = 'RUNNING'        THEN 1 ELSE 0 END) AS b2s_running,
    SUM(CASE WHEN ms.[b2s_status] = 'SUCCESS'        THEN 1 ELSE 0 END) AS b2s_success,
    SUM(CASE WHEN ms.[b2s_status] = 'FAILED'         THEN 1 ELSE 0 END) AS b2s_failed,
    SUM(CASE WHEN ms.[b2s_status] = 'SKIPPED'        THEN 1 ELSE 0 END) AS b2s_skipped,
    SUM(CASE WHEN ms.[s2g_status] = 'NOT_STARTED'    THEN 1 ELSE 0 END) AS s2g_not_started,
    SUM(CASE WHEN ms.[s2g_status] = 'PROCESSING'     THEN 1 ELSE 0 END) AS s2g_processing,
    SUM(CASE WHEN ms.[s2g_status] = 'SUCCESS'        THEN 1 ELSE 0 END) AS s2g_success,
    SUM(CASE WHEN ms.[s2g_status] = 'FAILED'         THEN 1 ELSE 0 END) AS s2g_failed,
    SUM(CASE WHEN ms.[s2g_status] = 'SKIPPED'        THEN 1 ELSE 0 END) AS s2g_skipped,
    SUM(CASE WHEN e.[is_late_arrival] = 1             THEN 1 ELSE 0 END) AS late_arrivals
FROM [dbo].[medallion_sync] ms
INNER JOIN [dbo].[extract] e  ON ms.[extract_id] = e.[extract_id]
INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
WHERE (@domain IS NULL    OR e.[domain_code] = @domain)
  AND (@workspace IS NULL OR ms.[target_workspace_id] = @workspace)
GROUP BY e.[domain_code], ms.[target_workspace_id], tw.[target_workspace_name]
ORDER BY e.[domain_code], tw.[target_workspace_name];


-- ─────────────────────────────────────────────────────────────────────────────
-- Extract Browser: listing with filters
-- Source: streamlit_ui/pages/extracts.py
-- ─────────────────────────────────────────────────────────────────────────────

-- Filter dropdown
SELECT DISTINCT domain_code FROM dbo.extract ORDER BY domain_code;

-- Browse extracts (adjust WHERE clauses as needed)
DECLARE @limit INT = 100;
DECLARE @filter_domain NVARCHAR(20) = NULL;    -- e.g. 'DP' or NULL
DECLARE @filter_status NVARCHAR(30) = NULL;    -- e.g. 'NEW', 'VALIDATED'
DECLARE @late_only BIT = 0;                    -- 1 = only late arrivals

SELECT TOP (@limit)
    e.[extract_id], e.[domain_code], e.[source_code], e.[folder_path],
    e.[period_year], e.[period_month], e.[period_label],
    e.[status], e.[is_latest_for_period], e.[is_late_arrival],
    e.[extraction_date], e.[extraction_def], e.[package_def], e.[cycle_id],
    e.[actual_file_count], e.[total_size_bytes],
    e.[arrived_at], e.[created_at]
FROM [dbo].[extract] e
WHERE (@filter_domain IS NULL OR e.[domain_code] = @filter_domain)
  AND (@filter_status IS NULL OR e.[status] = @filter_status)
  AND (@late_only = 0 OR e.[is_late_arrival] = 1)
ORDER BY e.[arrived_at] DESC, e.[extract_id] DESC;

-- Single extract detail
-- SELECT * FROM dbo.extract WHERE extract_id = @extract_id;

-- Files in an extract
-- SELECT file_name, file_format, row_count, file_size_bytes
-- FROM dbo.extract_file WHERE extract_id = @extract_id;

-- Medallion sync rows for an extract
-- SELECT sync_id, target_workspace_id, bronze_status, b2s_status, s2g_status,
--        b2s_run_id, s2g_run_id
-- FROM dbo.medallion_sync WHERE extract_id = @extract_id;


-- ─────────────────────────────────────────────────────────────────────────────
-- Push Jobs: listing with filters
-- Source: streamlit_ui/pages/push_jobs.py
-- ─────────────────────────────────────────────────────────────────────────────

DECLARE @pj_limit INT = 100;
DECLARE @pj_status NVARCHAR(30) = NULL;           -- e.g. 'RUNNING', 'SUCCESS'
DECLARE @pj_workspace NVARCHAR(100) = NULL;        -- target_workspace_id

SELECT TOP (@pj_limit)
    pj.[push_job_id], pj.[extract_id],
    e.[domain_code],
    pj.[target_workspace_name],
    pj.[status],
    pj.[started_at], pj.[completed_at], pj.[duration_seconds],
    pj.[files_attempted], pj.[files_succeeded], pj.[files_failed],
    pj.[bytes_transferred],
    pj.[error_message],
    pj.[attempt_number], pj.[max_attempts]
FROM [dbo].[push_job] pj
INNER JOIN [dbo].[extract] e ON pj.[extract_id] = e.[extract_id]
WHERE (@pj_status IS NULL    OR pj.[status] = @pj_status)
  AND (@pj_workspace IS NULL OR pj.[target_workspace_id] = @pj_workspace)
ORDER BY pj.[created_at] DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Timeline: pipeline run history (Gantt chart data)
-- Source: streamlit_ui/pages/timeline.py
-- ─────────────────────────────────────────────────────────────────────────────

DECLARE @tl_domain NVARCHAR(20) = NULL;
DECLARE @tl_workspace NVARCHAR(100) = NULL;

SELECT
    ms.[sync_id],
    e.[extract_id],
    e.[domain_code],
    tw.[target_workspace_name],
    ms.[b2s_status],  ms.[b2s_started_at],  ms.[b2s_completed_at],  ms.[b2s_run_id],
    ms.[s2g_status],  ms.[s2g_started_at],  ms.[s2g_completed_at],  ms.[s2g_run_id]
FROM [dbo].[medallion_sync] ms
INNER JOIN [dbo].[extract] e  ON ms.[extract_id] = e.[extract_id]
INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
WHERE (@tl_domain IS NULL    OR e.[domain_code] = @tl_domain)
  AND (@tl_workspace IS NULL OR ms.[target_workspace_id] = @tl_workspace)
  AND (ms.[b2s_started_at] IS NOT NULL OR ms.[s2g_started_at] IS NOT NULL)
ORDER BY ms.[b2s_started_at] DESC, ms.[s2g_started_at] DESC;


-- ─────────────────────────────────────────────────────────────────────────────
-- Late Arrivals: flagged extracts + blocking analysis
-- Source: streamlit_ui/pages/late_arrivals.py
-- ─────────────────────────────────────────────────────────────────────────────

-- All late arrival extracts
SELECT
    e.[extract_id], e.[domain_code], e.[extraction_def], e.[package_def],
    e.[extraction_date], e.[arrived_at], e.[status],
    e.[is_late_arrival]
FROM [dbo].[extract] e
WHERE e.[is_late_arrival] = 1
ORDER BY e.[domain_code], e.[extraction_def], e.[extraction_date];

-- Blocking extracts for late arrivals
SELECT DISTINCT
    blocker.[extract_id]        AS blocker_id,
    blocker.[domain_code],
    blocker.[extraction_def],
    blocker.[extraction_date]   AS blocker_extraction_date,
    ms.[b2s_status],
    late.[extract_id]           AS late_extract_id,
    late.[extraction_date]      AS late_extraction_date
FROM [dbo].[extract] late
INNER JOIN [dbo].[extract] blocker
    ON blocker.[domain_code]     = late.[domain_code]
   AND blocker.[extraction_def]  = late.[extraction_def]
   AND blocker.[extraction_date] > late.[extraction_date]
INNER JOIN [dbo].[medallion_sync] ms
    ON ms.[extract_id] = blocker.[extract_id]
   AND ms.[b2s_status] IN ('RUNNING', 'SUCCESS', 'FAILED')
WHERE late.[is_late_arrival] = 1
ORDER BY blocker.[domain_code], blocker.[extraction_def], blocker.[extraction_date];


-- ─────────────────────────────────────────────────────────────────────────────
-- Poller State: detected files
-- Source: streamlit_ui/pages/poller.py (via API → adls_poller.py)
-- ─────────────────────────────────────────────────────────────────────────────

-- All detected files (most recent first)
SELECT TOP 100
    [id], [file_name], [source_id], [detected_at], [status], [extract_id], [error_message]
FROM [dbo].[poller_state]
ORDER BY [detected_at] DESC;

-- Filter by status
-- SELECT ... WHERE [status] = 'REGISTERED';
-- SELECT ... WHERE [status] = 'FAILED';

-- Filter by source
-- SELECT ... WHERE [source_id] = 'primary';
