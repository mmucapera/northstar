-- =============================================================================
-- INS Orchestrator — Manage Domain Config
-- =============================================================================
-- CRUD operations for dbo.domain_config.
-- Each domain_code represents a data source/feed (e.g. 'DP', 'CUSTOMER0').
-- Edit the values below and run the relevant section.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- List all domains
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    [domain_code],
    [description],
    [enabled],
    [schedule_type],
    [expected_arrival_hour],
    [expected_arrival_day],
    [late_arrival_replay_threshold_hours],
    [extraction_date_cutoff],
    [manifest_filename_pattern],
    [late_arrival_scope_field],
    [on_b2s_failure_policy],
    [max_retry_attempts],
    [retry_delay_minutes],
    [min_expected_files],
    [max_expected_files],
    [alert_email],
    [created_at],
    [updated_at]
FROM [dbo].[domain_config]
ORDER BY [domain_code];


-- ─────────────────────────────────────────────────────────────────────────────
-- Insert a new domain
-- ─────────────────────────────────────────────────────────────────────────────

/*
INSERT INTO [dbo].[domain_config] (
    [domain_code],
    [description],
    [enabled],
    [schedule_type],
    [expected_arrival_hour],
    [expected_arrival_day],
    [late_arrival_replay_threshold_hours],
    [extraction_date_cutoff],
    [manifest_filename_pattern],
    [late_arrival_scope_field],
    [on_b2s_failure_policy],
    [max_retry_attempts],
    [retry_delay_minutes],
    [min_expected_files],
    [max_expected_files],
    [alert_email]
)
VALUES (
    'DP',                             -- domain_code (PK, max 20 chars)
    'DemandPlanning',                 -- description
    1,                                 -- enabled
    'daily',                           -- schedule_type: daily | weekly | manual
    6,                                 -- expected_arrival_hour (0-23 UTC)
    NULL,                              -- expected_arrival_day (for weekly: 'Monday', etc.)
    NULL,                              -- late_arrival_replay_threshold_hours (NULL = use global default)
    NULL,                              -- extraction_date_cutoff (NULL = no cutoff, e.g. '2026-03-01')
    NULL,                              -- manifest_filename_pattern (NULL = default MetaData prefix, e.g. '^MetaData_SP_.*\.tsv$')
    NULL,                              -- late_arrival_scope_field (NULL = 'package_def'; options: 'package_def', 'extraction_def', 'both')
    'BLOCK',                           -- on_b2s_failure_policy: BLOCK | QUEUE | ALERT_AND_CONTINUE
    3,                                 -- max_retry_attempts
    5,                                 -- retry_delay_minutes
    NULL,                              -- min_expected_files (NULL = no validation)
    NULL,                              -- max_expected_files (NULL = no validation)
    NULL                               -- alert_email
);
PRINT 'Inserted domain: DP';




INSERT INTO [dbo].[domain_config] (
    [domain_code],
    [description],
    [enabled],
    [schedule_type],
    [expected_arrival_hour],
    [expected_arrival_day],
    [late_arrival_replay_threshold_hours],
    [extraction_date_cutoff],
    [manifest_filename_pattern],
    [late_arrival_scope_field],
    [on_b2s_failure_policy],
    [max_retry_attempts],
    [retry_delay_minutes],
    [min_expected_files],
    [max_expected_files],
    [alert_email]
)
VALUES (
    'SP',                             -- domain_code (PK, max 20 chars)
    'SupplyPlanning',                 -- description
    1,                                 -- enabled
    'daily',                           -- schedule_type: daily | weekly | manual
    6,                                 -- expected_arrival_hour (0-23 UTC)
    NULL,                              -- expected_arrival_day (for weekly: 'Monday', etc.)
    NULL,                              -- late_arrival_replay_threshold_hours (NULL = use global default)
    NULL,                              -- extraction_date_cutoff (NULL = no cutoff, e.g. '2026-03-01')
    NULL,                              -- manifest_filename_pattern (NULL = default MetaData prefix, e.g. '^MetaData_SP_.*\.tsv$')
    NULL,                              -- late_arrival_scope_field (NULL = 'package_def'; options: 'package_def', 'extraction_def', 'both')
    'BLOCK',                           -- on_b2s_failure_policy: BLOCK | QUEUE | ALERT_AND_CONTINUE
    3,                                 -- max_retry_attempts
    5,                                 -- retry_delay_minutes
    NULL,                              -- min_expected_files (NULL = no validation)
    NULL,                              -- max_expected_files (NULL = no validation)
    NULL                               -- alert_email
);
PRINT 'Inserted domain: SP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Update an existing domain
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[domain_config]
SET [description]           = 'DemandPlanning (Updated)',
    [schedule_type]         = 'daily',
    [expected_arrival_hour] = 8,
    [extraction_date_cutoff] = '2026-03-01',  -- NULL to remove cutoff
    [on_b2s_failure_policy] = 'QUEUE',
    [max_retry_attempts]    = 5,
    [retry_delay_minutes]   = 10,
    [min_expected_files]    = 5,
    [max_expected_files]    = 20,
    [updated_at]            = SYSUTCDATETIME()
WHERE [domain_code] = 'DP';
PRINT 'Updated domain: DP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Disable a domain (stops processing new extracts)
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[domain_config]
SET [enabled]    = 0,
    [updated_at] = SYSUTCDATETIME()
WHERE [domain_code] = 'DP';
PRINT 'Disabled domain: DP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Re-enable a domain
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[domain_config]
SET [enabled]    = 1,
    [updated_at] = SYSUTCDATETIME()
WHERE [domain_code] = 'DP';
PRINT 'Re-enabled domain: DP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Delete a domain (only if no extracts reference it)
-- ─────────────────────────────────────────────────────────────────────────────

/*
-- Check for references first
SELECT COUNT(*) AS extract_count
FROM [dbo].[extract]
WHERE [domain_code] = 'DP';

-- If 0, safe to delete:
-- DELETE FROM [dbo].[domain_config] WHERE [domain_code] = 'DP';
-- PRINT 'Deleted domain: DP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Set extraction_date_cutoff (skip historical data before this date)
-- ─────────────────────────────────────────────────────────────────────────────

/*
-- Set cutoff: B2S/S2G will only process extracts with extraction_date >= this value
UPDATE [dbo].[domain_config]
SET [extraction_date_cutoff] = '2026-03-01',
    [updated_at]             = SYSUTCDATETIME()
WHERE [domain_code] = 'DP';
PRINT 'Set extraction_date_cutoff for domain: DP';
*/

/*
-- Clear cutoff: all extracts become eligible again
UPDATE [dbo].[domain_config]
SET [extraction_date_cutoff] = NULL,
    [updated_at]             = SYSUTCDATETIME()
WHERE [domain_code] = 'DP';
PRINT 'Cleared extraction_date_cutoff for domain: DP';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Quick view: domains with extract counts
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    dc.[domain_code],
    dc.[description],
    dc.[enabled],
    dc.[schedule_type],
    dc.[extraction_date_cutoff],
    dc.[late_arrival_scope_field],
    COUNT(e.[extract_id]) AS total_extracts,
    SUM(CASE WHEN e.[status] = 'NEW'       THEN 1 ELSE 0 END) AS new_count,
    SUM(CASE WHEN e.[status] = 'VALIDATED' THEN 1 ELSE 0 END) AS validated_count,
    SUM(CASE WHEN e.[status] = 'FAILED'    THEN 1 ELSE 0 END) AS failed_count,
    MAX(e.[arrived_at]) AS last_arrival
FROM [dbo].[domain_config] dc
LEFT JOIN [dbo].[extract] e ON dc.[domain_code] = e.[domain_code]
GROUP BY dc.[domain_code], dc.[description], dc.[enabled], dc.[schedule_type], dc.[extraction_date_cutoff], dc.[late_arrival_scope_field]
ORDER BY dc.[domain_code];
