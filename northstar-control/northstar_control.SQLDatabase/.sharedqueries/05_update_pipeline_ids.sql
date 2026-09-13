-- =============================================================================
-- INS Orchestrator — Update Pipeline IDs in Medallion Sync
-- =============================================================================
-- Use this to set or update the B2S / S2G pipeline IDs for target workspaces.
-- Pipeline IDs are Fabric pipeline GUIDs used by the orchestrator to trigger
-- Bronze-to-Silver and Silver-to-Gold transformations.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- View current pipeline assignments
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    [target_workspace_id],
    [target_workspace_name],
    [domain_filter],
    [b2s_pipeline_id],
    [s2g_pipeline_id],
    [enabled]
FROM [dbo].[target_workspace]
ORDER BY [target_workspace_name];


-- ─────────────────────────────────────────────────────────────────────────────
-- Update pipeline IDs for a workspace
-- ─────────────────────────────────────────────────────────────────────────────
-- Replace the GUIDs below with the actual Fabric pipeline IDs.
-- You can find these in the Fabric portal under the pipeline's URL.

/*
-- Example: workspace w_002 (DP only)
UPDATE [dbo].[target_workspace]
SET [b2s_pipeline_id] = '84317693-9647-4a59-9606-099e26e88c2e',
    [s2g_pipeline_id] = '58cb920d-48a9-450d-8ef2-76196c9a8198',
    [updated_at]       = SYSUTCDATETIME()
WHERE [target_workspace_id] = 'f74ebd65-bd5a-4426-a71a-38f84d44df95';
PRINT 'Updated pipeline IDs for w_002';

-- Example: workspace w_001 (no domain filter)
UPDATE [dbo].[target_workspace]
SET [b2s_pipeline_id] = '291fc63f-aac9-46f3-acc4-088aeecbd578',
    [s2g_pipeline_id] = '91926c09-fc2b-4f6b-b3da-fa1c57f9bc76',
    [updated_at]       = SYSUTCDATETIME()
WHERE [target_workspace_id] = 'fea48c31-63da-453f-85e0-2eedc2889315';
PRINT 'Updated pipeline IDs for w_001';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Bulk update: set same pipeline IDs for all workspaces
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[target_workspace]
SET [b2s_pipeline_id] = '<b2s-pipeline-guid>',
    [s2g_pipeline_id] = '<s2g-pipeline-guid>',
    [updated_at]       = SYSUTCDATETIME()
WHERE [enabled] = 1;
PRINT 'Updated pipeline IDs for all enabled workspaces';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Check medallion sync status for a workspace
-- ─────────────────────────────────────────────────────────────────────────────

/*
DECLARE @ws_id NVARCHAR(100) = '<workspace-guid>';

SELECT
    ms.[sync_id],
    e.[domain_code],
    e.[extract_id],
    ms.[bronze_status],
    ms.[b2s_status],  ms.[b2s_run_id],  ms.[b2s_started_at],  ms.[b2s_completed_at],
    ms.[s2g_status],  ms.[s2g_run_id],  ms.[s2g_started_at],  ms.[s2g_completed_at],
    ms.[b2s_error],
    ms.[s2g_error]
FROM [dbo].[medallion_sync] ms
INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
WHERE ms.[target_workspace_id] = @ws_id
ORDER BY ms.[created_at] DESC;
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Reset failed B2S runs for a workspace (allow re-trigger)
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[medallion_sync]
SET [b2s_status]       = 'NOT_STARTED',
    [b2s_run_id]       = NULL,
    [b2s_started_at]   = NULL,
    [b2s_completed_at] = NULL,
    [b2s_error]        = NULL,
    [updated_at]       = SYSUTCDATETIME()
WHERE [target_workspace_id] = '<workspace-guid>'
  AND [b2s_status] = 'FAILED';
PRINT 'Reset failed B2S runs';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Reset failed S2G runs for a workspace (allow re-trigger)
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[medallion_sync]
SET [s2g_status]       = 'NOT_STARTED',
    [s2g_run_id]       = NULL,
    [s2g_started_at]   = NULL,
    [s2g_completed_at] = NULL,
    [s2g_error]        = NULL,
    [updated_at]       = SYSUTCDATETIME()
WHERE [target_workspace_id] = '<workspace-guid>'
  AND [s2g_status] = 'FAILED';
PRINT 'Reset failed S2G runs';
*/
