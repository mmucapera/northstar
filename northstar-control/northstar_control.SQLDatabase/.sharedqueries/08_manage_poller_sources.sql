-- ============================================================================
-- 08_manage_poller_sources.sql
-- CRUD operations for dbo.poller_source (ADLS polling source config)
-- ============================================================================

-- -------------------------------------------------------------------------
-- List all sources
-- -------------------------------------------------------------------------
SELECT [source_id], [label], [storage_account], [container],
    [folder_path], [sas_token], [poll_interval_seconds], [enabled],
    [filename_extension], [filename_must_contain], [filename_pattern],
    [source_code], [source_file_format], [domain_code_map],
       [created_at], [updated_at]
FROM [dbo].[poller_source]
ORDER BY [source_id];


-- -------------------------------------------------------------------------
-- Get a single source
-- -------------------------------------------------------------------------
-- SELECT * FROM [dbo].[poller_source] WHERE [source_id] = 'my-source';


-- -------------------------------------------------------------------------
-- Insert a new source
-- -------------------------------------------------------------------------
-- INSERT INTO [dbo].[poller_source]
--     ([source_id], [label], [storage_account], [container],
--      [folder_path], [sas_token], [poll_interval_seconds], [enabled],
--      [filename_extension], [filename_must_contain], [filename_pattern],
--      [source_code], [source_file_format], [domain_code_map])
-- VALUES
--     ('my-source',                 -- source_id (unique key)
--      'My ADLS Source',            -- label
--      'mystorageaccount',          -- storage_account
--      'outbound',                  -- container
--      '',                 -- folder_path
--      '${INS_ORCH_ADLS_SAS_TOKEN_01}',           -- sas_token (env var reference)
--      10,                          -- poll_interval_seconds
--      1,                           -- enabled (1=yes, 0=no)
--      '.zip',                      -- filename_extension
--      'FinishedZip',               -- filename_must_contain
--      NULL,                        -- filename_pattern (NULL = positional parser)
--      'ADLS_POLLER',               -- source_code
--      'zip',                       -- source_file_format
--      '{"FCT":"DP","SP":"SP"}'  -- domain_code_map (JSON, e.g. '{"FCT":"DP","OPR":"SP"}')
--    );

-- -------------------------------------------------------------------------
-- Update a source
-- -------------------------------------------------------------------------
-- UPDATE [dbo].[poller_source]
-- SET [label] = 'Updated Label',
--     [poll_interval_seconds] = 30,
--     [updated_at] = SYSUTCDATETIME()
-- WHERE [source_id] = 'my-source';


-- -------------------------------------------------------------------------
-- Disable / Enable a source
-- -------------------------------------------------------------------------
-- UPDATE [dbo].[poller_source]
-- SET [enabled] = 0, [updated_at] = SYSUTCDATETIME()
-- WHERE [source_id] = 'my-source';


-- -------------------------------------------------------------------------
-- Rotate SAS token (update env var reference)
-- -------------------------------------------------------------------------
-- UPDATE [dbo].[poller_source]
-- SET [sas_token] = '${NEW_SAS_TOKEN_ENV_VAR}',
--     [updated_at] = SYSUTCDATETIME()
-- WHERE [source_id] = 'my-source';


-- -------------------------------------------------------------------------
-- Delete a source
-- -------------------------------------------------------------------------
-- NOTE: Stop the poller via the API first, or it will be stopped on next restart.
-- Orphaned rows in poller_state referencing this source_id are harmless.
--
-- DELETE FROM [dbo].[poller_source] WHERE [source_id] = 'my-source';


-- -------------------------------------------------------------------------
-- Summary: sources with poller_state file counts
-- -------------------------------------------------------------------------
SELECT ps.[source_id], ps.[label], ps.[enabled],
       COUNT(pst.[file_name]) AS total_files,
       SUM(CASE WHEN pst.[status] = 'REGISTERED' THEN 1 ELSE 0 END) AS registered,
       SUM(CASE WHEN pst.[status] = 'FAILED' THEN 1 ELSE 0 END) AS failed
FROM [dbo].[poller_source] ps
LEFT JOIN [dbo].[poller_state] pst ON ps.[source_id] = pst.[source_id]
GROUP BY ps.[source_id], ps.[label], ps.[enabled]
ORDER BY ps.[source_id];
