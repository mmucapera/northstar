-- =============================================================================
-- INS Orchestrator — Manage Target Workspaces
-- =============================================================================
-- CRUD operations for dbo.target_workspace.
-- Edit the values below and run the relevant section.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- List all workspaces
-- ─────────────────────────────────────────────────────────────────────────────

SELECT
    [target_workspace_id],
    [target_workspace_name],
    [target_lakehouse_id],
    [target_lakehouse_name],
    [enabled],
    [domain_filter],
    [instance_filter],
    [period_type_filter],
    [arrived_after],
    [b2s_pipeline_id],
    [s2g_pipeline_id],
    [created_at],
    [updated_at]
FROM [dbo].[target_workspace]
ORDER BY [target_workspace_name];


-- ─────────────────────────────────────────────────────────────────────────────
-- Insert a new workspace
-- ─────────────────────────────────────────────────────────────────────────────

/*
INSERT INTO [dbo].[target_workspace] (
    [target_workspace_id],
    [target_workspace_name],
    [target_lakehouse_id],
    [target_lakehouse_name],
    [enabled],
    [domain_filter],
    [instance_filter],
    [period_type_filter],
    [arrived_after],
    [b2s_pipeline_id],
    [s2g_pipeline_id]
)
VALUES (
    '<workspace-guid>',                -- target_workspace_id (from Fabric)
    'CXXX - ENV',                      -- target_workspace_name
    '<lakehouse-guid>',                -- target_lakehouse_id (from Fabric)
    'lkh_001',                         -- target_lakehouse_name
    1,                                 -- enabled
    NULL,                              -- domain_filter (NULL = all domains, e.g. 'DP')
    NULL,                              -- instance_filter (NULL = all instances, e.g. 'CUSTOMER0')
    NULL,                              -- period_type_filter (NULL = all period types, e.g. 'daily')
    NULL,                              -- arrived_after (NULL = no arrival cutoff, e.g. '2026-01-01')
    '<b2s-pipeline-guid>',             -- b2s_pipeline_id (Fabric pipeline)
    '<s2g-pipeline-guid>'              -- s2g_pipeline_id (Fabric pipeline)
);
PRINT 'Inserted workspace: Customer X — Production';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Update an existing workspace
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[target_workspace]
SET [target_workspace_name] = 'Customer X — Production (Updated)',
    [enabled]               = 1,
    [domain_filter]         = 'DP',          -- restrict to DP domain only
    [b2s_pipeline_id]       = '<new-b2s-pipeline-guid>',
    [s2g_pipeline_id]       = '<new-s2g-pipeline-guid>',
    [updated_at]            = SYSUTCDATETIME()
WHERE [target_workspace_id] = '<workspace-guid>';
PRINT 'Updated workspace';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Disable a workspace (stop sending extracts to it)
-- ─────────────────────────────────────────────────────────────────────────────

/*
UPDATE [dbo].[target_workspace]
SET [enabled]    = 0,
    [updated_at] = SYSUTCDATETIME()
WHERE [target_workspace_id] = '<workspace-guid>';
PRINT 'Disabled workspace';
*/


-- ─────────────────────────────────────────────────────────────────────────────
-- Delete a workspace (only if no medallion_sync rows reference it)
-- ─────────────────────────────────────────────────────────────────────────────

/*
-- Check for references first
SELECT COUNT(*) AS sync_rows
FROM [dbo].[medallion_sync]
WHERE [target_workspace_id] = '<workspace-guid>';

-- If 0, safe to delete:
-- DELETE FROM [dbo].[workspace_signal]  WHERE [target_workspace_id] = '<workspace-guid>';
-- DELETE FROM [dbo].[target_workspace]  WHERE [target_workspace_id] = '<workspace-guid>';
*/
