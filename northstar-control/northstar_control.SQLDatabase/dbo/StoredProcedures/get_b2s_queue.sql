-- -----------------------------------------------------------------------------
-- get_b2s_queue
--
-- For a given (domain_code, target_workspace_id), atomically claims and returns
-- the next extract ready for B2S processing.
--
-- Concurrency guard: uses UPDATE ... FROM (SELECT TOP 1 ...) so that two
-- concurrent callers cannot both claim the same row.  The row is immediately
-- marked RUNNING with a provisional run_id ('PROV-<uuid>') before the Fabric
-- pipeline is triggered.  start_medallion_run then replaces the provisional
-- id with the real Fabric job instance id.
--
-- Stale provisional claims (trigger failed / orchestrator crashed) are
-- auto-released after 5 minutes so the row re-enters the queue.
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[get_b2s_queue]
    @domain_code           NVARCHAR(20),
    @target_workspace_id   NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    -- Auto-release stale provisional claims (>5 min old) so they re-enter the queue.
    -- This handles the edge-case where a trigger failed after claiming the row.
    UPDATE [dbo].[medallion_sync]
    SET [b2s_status]     = 'NOT_STARTED',
        [b2s_run_id]     = NULL,
        [b2s_started_at] = NULL,
        [updated_at]     = SYSUTCDATETIME()
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
    WHERE ms.[target_workspace_id] = @target_workspace_id
      AND e.[domain_code]          = @domain_code
      AND ms.[b2s_status]          = 'RUNNING'
      AND ms.[b2s_run_id]          LIKE 'PROV-%'
      AND ms.[b2s_started_at]      < DATEADD(MINUTE, -5, SYSUTCDATETIME());

    -- Atomically find and claim the oldest NOT_STARTED row.
    -- Two concurrent callers cannot both see rows_affected = 1 for the same row.
    DECLARE @provisional_run_id NVARCHAR(100) = 'PROV-' + CAST(NEWID() AS NVARCHAR(36));

    UPDATE ms
    SET ms.[b2s_status]     = 'RUNNING',
        ms.[b2s_run_id]     = @provisional_run_id,
        ms.[b2s_started_at] = SYSUTCDATETIME(),
        ms.[updated_at]     = SYSUTCDATETIME()
    FROM [dbo].[medallion_sync] ms
    INNER JOIN (
        SELECT TOP (1) ms2.[sync_id]
        FROM  [dbo].[medallion_sync]  ms2
        INNER JOIN [dbo].[extract]       e2  ON ms2.[extract_id]  = e2.[extract_id]
        INNER JOIN [dbo].[domain_config] dc  ON e2.[domain_code]  = dc.[domain_code]
        WHERE  e2.[domain_code]           = @domain_code
          AND  ms2.[target_workspace_id]  = @target_workspace_id
          AND  ms2.[bronze_status]        = 'LOADED'
          AND  ms2.[b2s_status]           = 'NOT_STARTED'
          AND  e2.[is_late_arrival]       = 0
          AND (dc.[extraction_date_cutoff] IS NULL
               OR  e2.[extraction_date]  IS NULL
               OR  e2.[extraction_date] >= dc.[extraction_date_cutoff])
          -- No B2S currently RUNNING (including fresh provisional claims) for this domain+workspace
          AND NOT EXISTS (
              SELECT 1
              FROM  [dbo].[medallion_sync] ms3
              INNER JOIN [dbo].[extract]   e3  ON ms3.[extract_id] = e3.[extract_id]
              WHERE ms3.[target_workspace_id] = @target_workspace_id
                AND e3.[domain_code]          = @domain_code
                AND ms3.[b2s_status]          = 'RUNNING'
          )
        ORDER BY e2.[extraction_date] ASC,
                 e2.[package_def]     ASC,
                 e2.[extract_id]      ASC
    ) AS candidate ON ms.[sync_id] = candidate.[sync_id];

    IF @@ROWCOUNT = 0
        RETURN;  -- queue empty or claimed by a concurrent caller

    -- Return the claimed row (same columns as before)
    SELECT TOP 1
        ms.[sync_id],
        ms.[extract_id],
        ms.[target_workspace_id],
        e.[domain_code],
        e.[source_file_name],
        e.[extraction_date],
        e.[cycle_id],
        e.[extraction_def],
        e.[instance_code],
        e.[period_type],
        ms.[bronze_status],
        ms.[b2s_status],
        ms.[bronze_file_count],
        tw.[target_workspace_name],
        tw.[target_lakehouse_id],
        tw.[target_lakehouse_name],
        tw.[b2s_pipeline_id],
        pj.[bronze_folder_path]
    FROM  [dbo].[medallion_sync]    ms
    INNER JOIN [dbo].[extract]          e   ON ms.[extract_id]          = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw  ON ms.[target_workspace_id] = tw.[target_workspace_id]
    LEFT  JOIN [dbo].[push_job]         pj  ON pj.[extract_id]          = e.[extract_id]
                                           AND pj.[target_workspace_id] = ms.[target_workspace_id]
                                           AND pj.[status]              = 'SUCCESS'
    WHERE ms.[b2s_run_id] = @provisional_run_id;
END;

GO
