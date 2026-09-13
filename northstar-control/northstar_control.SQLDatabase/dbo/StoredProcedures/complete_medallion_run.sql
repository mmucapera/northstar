-- -----------------------------------------------------------------------------
-- complete_medallion_run
--
-- Marks a B2S or S2G run as SUCCESS or FAILED.
-- For B2S: updates a single sync_id.
-- For S2G: updates all rows with the matching run_id.
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[complete_medallion_run]
    @run_type              NVARCHAR(10),    -- 'B2S' or 'S2G'
    @run_id                NVARCHAR(100),   -- Pipeline job instance ID
    @status                NVARCHAR(30),    -- 'SUCCESS' or 'FAILED'
    @sync_id               INT = NULL,      -- For B2S (specific row)
    @rows_processed        BIGINT = NULL,   -- For B2S
    @error_message         NVARCHAR(MAX) = NULL,
    @rows_affected         INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    SET @rows_affected = 0;

    IF @run_type = 'B2S'
    BEGIN
        UPDATE [dbo].[medallion_sync]
        SET [b2s_status]         = @status,
            [b2s_completed_at]   = SYSUTCDATETIME(),
            [b2s_rows_processed] = @rows_processed,
            [b2s_error]          = @error_message,
            [last_synced_at]     = SYSUTCDATETIME(),
            [sync_count]         = [sync_count] + 1,
            [updated_at]         = SYSUTCDATETIME()
        WHERE [sync_id] = @sync_id
          AND [b2s_run_id] = @run_id
          AND [b2s_status] = 'RUNNING';

        SET @rows_affected = @@ROWCOUNT;
    END
    ELSE IF @run_type = 'S2G'
    BEGIN
        UPDATE [dbo].[medallion_sync]
        SET [s2g_status]       = @status,
            [s2g_completed_at] = SYSUTCDATETIME(),
            [s2g_error]        = @error_message,
            [last_synced_at]   = SYSUTCDATETIME(),
            [sync_count]       = [sync_count] + 1,
            [updated_at]       = SYSUTCDATETIME()
        WHERE [s2g_run_id] = @run_id
          AND [s2g_status] = 'PROCESSING';

        SET @rows_affected = @@ROWCOUNT;
    END

    -- Return summary
    SELECT @rows_affected AS rows_affected, @status AS final_status;
END;

GO
