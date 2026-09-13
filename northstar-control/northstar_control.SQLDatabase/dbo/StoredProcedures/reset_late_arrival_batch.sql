-- -----------------------------------------------------------------------------
-- reset_late_arrival_batch
--
-- Resets a late-arrival batch for replay. Operator-controlled lookback scope.
--
-- @lookback_hours = 0: Skip/discard — clears is_late_arrival, sets b2s_status
--                      to SKIPPED. No replay.
-- @lookback_hours > 0: Replay — clears is_late_arrival on flagged extracts,
--                      resets B2S + S2G to NOT_STARTED for the late arrival
--                      AND all extracts in the same batch with extraction_date
--                      within the lookback window.
--
-- Batch = domain_code + package_def (per target_workspace if specified).
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[reset_late_arrival_batch]
    @domain_code           NVARCHAR(20),
    @lookback_hours        INT,
    @extraction_def        NVARCHAR(100) = NULL,
    @package_def           NVARCHAR(100) = NULL,
    @target_workspace_id   NVARCHAR(100) = NULL,
    @extracts_reset        INT OUTPUT,
    @syncs_reset           INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    SET @extracts_reset = 0;
    SET @syncs_reset = 0;

    BEGIN TRANSACTION;

    IF @lookback_hours = 0
    BEGIN
        -- ── SKIP/DISCARD mode ──
        -- Clear the late arrival flag and mark B2S as SKIPPED (no replay)

        -- Update medallion_sync rows for late arrival extracts
        UPDATE ms
        SET ms.[b2s_status]     = 'SKIPPED',
            ms.[b2s_error]      = 'Late arrival skipped by operator (lookback=0)',
            ms.[s2g_status]     = 'SKIPPED',
            ms.[s2g_error]      = 'Late arrival skipped by operator (lookback=0)',
            ms.[updated_at]     = SYSUTCDATETIME()
        FROM [dbo].[medallion_sync] ms
        INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
        WHERE e.[domain_code] = @domain_code
          AND e.[is_late_arrival] = 1
          AND (@extraction_def IS NULL OR e.[extraction_def] = @extraction_def)
          AND (@package_def IS NULL OR e.[package_def] = @package_def)
          AND (@target_workspace_id IS NULL OR ms.[target_workspace_id] = @target_workspace_id);

        SET @syncs_reset = @@ROWCOUNT;

        -- Clear the flag on extract
        UPDATE [dbo].[extract]
        SET [is_late_arrival] = 0,
            [updated_at]      = SYSUTCDATETIME()
        WHERE [domain_code] = @domain_code
          AND [is_late_arrival] = 1
          AND (@extraction_def IS NULL OR [extraction_def] = @extraction_def)
          AND (@package_def IS NULL OR [package_def] = @package_def);

        SET @extracts_reset = @@ROWCOUNT;
    END
    ELSE
    BEGIN
        -- ── REPLAY mode ──
        -- Find the earliest extraction_date among late arrival extracts
        DECLARE @earliest_late DATETIME2;
        SELECT @earliest_late = MIN(e.[extraction_date])
        FROM [dbo].[extract] e
        WHERE e.[domain_code] = @domain_code
          AND e.[is_late_arrival] = 1
          AND (@extraction_def IS NULL OR e.[extraction_def] = @extraction_def)
          AND (@package_def IS NULL OR e.[package_def] = @package_def);

        -- Calculate the lookback cutoff
        DECLARE @lookback_cutoff DATETIME2;
        SET @lookback_cutoff = DATEADD(HOUR, -@lookback_hours, SYSUTCDATETIME());

        -- Use the earlier of the two as the reset boundary
        -- (always include the late arrival even if older than lookback window)
        DECLARE @reset_from DATETIME2;
        IF @earliest_late IS NOT NULL AND @earliest_late < @lookback_cutoff
            SET @reset_from = @earliest_late;
        ELSE
            SET @reset_from = @lookback_cutoff;

        -- Reset B2S + S2G on medallion_sync for all extracts in the batch
        -- within the reset window
        UPDATE ms
        SET ms.[b2s_status]       = 'NOT_STARTED',
            ms.[b2s_run_id]       = NULL,
            ms.[b2s_started_at]   = NULL,
            ms.[b2s_completed_at] = NULL,
            ms.[b2s_rows_processed] = NULL,
            ms.[b2s_error]        = NULL,
            ms.[s2g_status]       = 'NOT_STARTED',
            ms.[s2g_run_id]       = NULL,
            ms.[s2g_started_at]   = NULL,
            ms.[s2g_completed_at] = NULL,
            ms.[s2g_error]        = NULL,
            ms.[updated_at]       = SYSUTCDATETIME()
        FROM [dbo].[medallion_sync] ms
        INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
        WHERE e.[domain_code] = @domain_code
          AND (@extraction_def IS NULL OR e.[extraction_def] = @extraction_def)
          AND (@package_def IS NULL OR e.[package_def] = @package_def)
          AND (@target_workspace_id IS NULL OR ms.[target_workspace_id] = @target_workspace_id)
          AND e.[extraction_date] >= @reset_from
          AND ms.[b2s_status] != 'NOT_STARTED';  -- only reset rows that actually ran

        SET @syncs_reset = @@ROWCOUNT;

        -- Clear is_late_arrival flag on affected extracts
        UPDATE [dbo].[extract]
        SET [is_late_arrival] = 0,
            [updated_at]      = SYSUTCDATETIME()
        WHERE [domain_code] = @domain_code
          AND [is_late_arrival] = 1
          AND (@extraction_def IS NULL OR [extraction_def] = @extraction_def)
          AND (@package_def IS NULL OR [package_def] = @package_def);

        SET @extracts_reset = @@ROWCOUNT;
    END

    COMMIT TRANSACTION;

    -- Return summary of what was reset
    SELECT
        @extracts_reset AS extracts_reset,
        @syncs_reset    AS syncs_reset,
        @lookback_hours AS lookback_hours,
        @domain_code    AS domain_code,
        @extraction_def AS extraction_def,
        @package_def    AS package_def;

    -- Return the affected extract details
    SELECT
        e.[extract_id],
        e.[domain_code],
        e.[extraction_def],
        e.[extraction_date],
        e.[package_def],
        e.[is_late_arrival]
    FROM [dbo].[extract] e
    WHERE e.[domain_code] = @domain_code
      AND (@extraction_def IS NULL OR e.[extraction_def] = @extraction_def)
      AND (@package_def IS NULL OR e.[package_def] = @package_def)
      AND e.[extraction_date] >= COALESCE(
          (SELECT MIN(e2.[extraction_date])
           FROM [dbo].[extract] e2
           WHERE e2.[domain_code] = @domain_code
             AND (@extraction_def IS NULL OR e2.[extraction_def] = @extraction_def)
             AND (@package_def IS NULL OR e2.[package_def] = @package_def)
             AND e2.[extraction_date] >= DATEADD(HOUR, -@lookback_hours, SYSUTCDATETIME())),
          DATEADD(HOUR, -@lookback_hours, SYSUTCDATETIME())
      )
    ORDER BY e.[extraction_date] ASC;
END;

GO
