-- -----------------------------------------------------------------------------
-- start_medallion_run
--
-- Atomically claims a medallion_sync row (or set of rows) for B2S or S2G
-- processing. Sets status to RUNNING/PROCESSING, records the run_id and
-- start time. Returns the claimed row(s).
--
-- For B2S: claims a single sync_id (one extract at a time).
-- For S2G: claims ALL rows for a domain+workspace where b2s_status=SUCCESS
--          and s2g_status=NOT_STARTED.
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[start_medallion_run]
    @run_type              NVARCHAR(10),    -- 'B2S' or 'S2G'
    @run_id                NVARCHAR(100),   -- Pipeline job instance ID
    @sync_id               INT = NULL,      -- Required for B2S (specific row)
    @domain_code           NVARCHAR(20) = NULL,    -- Required for S2G
    @target_workspace_id   NVARCHAR(100) = NULL,   -- Required for S2G
    @rows_affected         INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @rows_affected = 0;

    IF @run_type = 'B2S'
    BEGIN
        -- Atomically claim: only if still NOT_STARTED
        UPDATE [dbo].[medallion_sync]
        SET [b2s_status]     = 'RUNNING',
            [b2s_run_id]     = @run_id,
            -- Preserve existing b2s_started_at when row was pre-claimed by get_b2s_queue
            [b2s_started_at] = CASE
                                   WHEN [b2s_status] = 'NOT_STARTED' THEN SYSUTCDATETIME()
                                   ELSE [b2s_started_at]
                               END,
            [updated_at]     = SYSUTCDATETIME()
        WHERE [sync_id] = @sync_id
          AND [bronze_status] = 'LOADED'
          AND (
              -- Traditional path: row not yet touched
              [b2s_status] = 'NOT_STARTED'
              OR
              -- Pre-claimed by get_b2s_queue: just swap provisional id for real job id
              ([b2s_status] = 'RUNNING' AND [b2s_run_id] LIKE 'PROV-%')
          );

        SET @rows_affected = @@ROWCOUNT;

        -- Return the claimed row
        SELECT
            ms.[sync_id],
            ms.[extract_id],
            ms.[target_workspace_id],
            ms.[b2s_status],
            ms.[b2s_run_id],
            ms.[b2s_started_at]
        FROM [dbo].[medallion_sync] ms
        WHERE ms.[sync_id] = @sync_id;
    END
    ELSE IF @run_type = 'S2G'
    BEGIN
        -- Claim ALL rows for this domain + workspace
        UPDATE ms
        SET ms.[s2g_status]     = 'PROCESSING',
            ms.[s2g_run_id]     = @run_id,
            ms.[s2g_started_at] = SYSUTCDATETIME(),
            ms.[updated_at]     = SYSUTCDATETIME()
        FROM [dbo].[medallion_sync] ms
        INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
        WHERE e.[domain_code] = @domain_code
          AND ms.[target_workspace_id] = @target_workspace_id
          AND ms.[b2s_status] = 'SUCCESS'
          AND ms.[s2g_status] = 'NOT_STARTED';

        SET @rows_affected = @@ROWCOUNT;

        -- Return claimed rows
        SELECT
            ms.[sync_id],
            ms.[extract_id],
            ms.[target_workspace_id],
            ms.[s2g_status],
            ms.[s2g_run_id],
            ms.[s2g_started_at]
        FROM [dbo].[medallion_sync] ms
        INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
        WHERE e.[domain_code] = @domain_code
          AND ms.[target_workspace_id] = @target_workspace_id
          AND ms.[s2g_run_id] = @run_id;
    END
END;

GO
