-- -----------------------------------------------------------------------------
-- get_s2g_ready
--
-- Returns (domain_code, target_workspace_id) combos where:
--   - ALL B2S runs are complete (no NOT_STARTED or RUNNING)
--   - At least one B2S has SUCCESS status
--   - S2G is NOT_STARTED for those rows
-- These are ready to trigger S2G pipeline.
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[get_s2g_ready]
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        e.[domain_code],
        ms.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[s2g_pipeline_id],
        tw.[target_lakehouse_id],
        tw.[target_lakehouse_name],
        COUNT(*)                        AS extract_count,
        SUM(ms.[b2s_rows_processed])    AS total_b2s_rows
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e
        ON ms.[extract_id] = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw
        ON ms.[target_workspace_id] = tw.[target_workspace_id]
    INNER JOIN [dbo].[domain_config] dc
        ON e.[domain_code] = dc.[domain_code]
    WHERE ms.[b2s_status] = 'SUCCESS'
      AND ms.[s2g_status] = 'NOT_STARTED'
      AND tw.[enabled] = 1
      AND tw.[s2g_pipeline_id] IS NOT NULL
      AND (dc.[extraction_date_cutoff] IS NULL
           OR e.[extraction_date] IS NULL
           OR e.[extraction_date] >= dc.[extraction_date_cutoff])
      -- Ensure no B2S is still pending or running for this domain+workspace
      -- (scoped to above-cutoff extracts so below-cutoff NOT_STARTED rows don't block)
      AND NOT EXISTS (
          SELECT 1
          FROM [dbo].[medallion_sync] ms2
          INNER JOIN [dbo].[extract] e2 ON ms2.[extract_id] = e2.[extract_id]
          INNER JOIN [dbo].[domain_config] dc2 ON e2.[domain_code] = dc2.[domain_code]
          WHERE ms2.[target_workspace_id] = ms.[target_workspace_id]
            AND e2.[domain_code] = e.[domain_code]
            AND ms2.[b2s_status] IN ('NOT_STARTED', 'RUNNING')
            AND (dc2.[extraction_date_cutoff] IS NULL
                 OR e2.[extraction_date] IS NULL
                 OR e2.[extraction_date] >= dc2.[extraction_date_cutoff])
      )
      -- Ensure S2G is not already running for this domain+workspace
      AND NOT EXISTS (
          SELECT 1
          FROM [dbo].[medallion_sync] ms3
          INNER JOIN [dbo].[extract] e3 ON ms3.[extract_id] = e3.[extract_id]
          WHERE ms3.[target_workspace_id] = ms.[target_workspace_id]
            AND e3.[domain_code] = e.[domain_code]
            AND ms3.[s2g_status] = 'PROCESSING'
      )
      -- Block S2G if any extract in this domain scope is a late arrival
      AND NOT EXISTS (
          SELECT 1
          FROM [dbo].[extract] e4
          INNER JOIN [dbo].[medallion_sync] ms4 ON ms4.[extract_id] = e4.[extract_id]
          WHERE ms4.[target_workspace_id] = ms.[target_workspace_id]
            AND e4.[domain_code] = e.[domain_code]
            AND e4.[is_late_arrival] = 1
            AND (
                (COALESCE(dc.[late_arrival_scope_field], 'package_def') = 'extraction_def'
                 AND (e4.[extraction_def] = e.[extraction_def] OR (e4.[extraction_def] IS NULL AND e.[extraction_def] IS NULL)))
                OR
                (COALESCE(dc.[late_arrival_scope_field], 'package_def') = 'package_def'
                 AND (e4.[package_def] = e.[package_def] OR (e4.[package_def] IS NULL AND e.[package_def] IS NULL)))
                OR
                (COALESCE(dc.[late_arrival_scope_field], 'package_def') = 'both'
                 AND (e4.[extraction_def] = e.[extraction_def] OR (e4.[extraction_def] IS NULL AND e.[extraction_def] IS NULL))
                 AND (e4.[package_def] = e.[package_def] OR (e4.[package_def] IS NULL AND e.[package_def] IS NULL)))
            )
      )
    GROUP BY
        e.[domain_code],
        ms.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[s2g_pipeline_id],
        tw.[target_lakehouse_id],
        tw.[target_lakehouse_name]
    ORDER BY
        e.[domain_code] ASC;
END;

GO
