-- -----------------------------------------------------------------------------
-- get_b2s_pending_batches
--
-- Returns (domain_code, target_workspace_id) combos that have extracts
-- with bronze_status=LOADED and b2s_status=NOT_STARTED.
-- Includes the latest bronze_loaded_at so the orchestrator can evaluate
-- whether the grace period has expired.
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[get_b2s_pending_batches]
AS
BEGIN
    SET NOCOUNT ON;

    -- Release stale provisional claims across all workspaces.
    -- A 'PROV-' prefixed run_id means get_b2s_queue claimed the row but the
    -- pipeline trigger never completed.  After 5 minutes we reset so the row
    -- re-enters the queue on the next scan cycle.
    UPDATE [dbo].[medallion_sync]
    SET [b2s_status]     = 'NOT_STARTED',
        [b2s_run_id]     = NULL,
        [b2s_started_at] = NULL,
        [updated_at]     = SYSUTCDATETIME()
    WHERE [b2s_status]     = 'RUNNING'
      AND [b2s_run_id]     LIKE 'PROV-%'
      AND [b2s_started_at] < DATEADD(MINUTE, -5, SYSUTCDATETIME());

    SELECT
        e.[domain_code],
        ms.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[b2s_pipeline_id],
        COUNT(*)                    AS pending_extract_count,
        MAX(ms.[bronze_loaded_at])  AS latest_bronze_loaded_at,
        MIN(e.[extraction_date])    AS earliest_extraction_date
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e
        ON ms.[extract_id] = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw
        ON ms.[target_workspace_id] = tw.[target_workspace_id]
    INNER JOIN [dbo].[domain_config] dc
        ON e.[domain_code] = dc.[domain_code]
    WHERE ms.[bronze_status] = 'LOADED'
      AND ms.[b2s_status] = 'NOT_STARTED'
      AND tw.[enabled] = 1
      AND tw.[b2s_pipeline_id] IS NOT NULL
      AND e.[is_late_arrival] = 0
      AND (dc.[extraction_date_cutoff] IS NULL
           OR e.[extraction_date] IS NULL
           OR e.[extraction_date] >= dc.[extraction_date_cutoff])
      -- Ensure no B2S is currently running for this domain+workspace
      AND NOT EXISTS (
          SELECT 1
          FROM [dbo].[medallion_sync] ms2
          INNER JOIN [dbo].[extract] e2 ON ms2.[extract_id] = e2.[extract_id]
          WHERE ms2.[target_workspace_id] = ms.[target_workspace_id]
            AND e2.[domain_code] = e.[domain_code]
            AND ms2.[b2s_status] = 'RUNNING'
      )
    GROUP BY
        e.[domain_code],
        ms.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[b2s_pipeline_id]
    ORDER BY
        MIN(e.[extraction_date]) ASC;
END;

GO
