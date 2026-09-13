

-- -----------------------------------------------------------------------------
-- update_medallion_sync
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[update_medallion_sync]
    @extract_id             INT,
    @target_workspace_id    NVARCHAR(100),
    @bronze_status          NVARCHAR(30) = NULL,
    @bronze_loaded_at       DATETIME2 = NULL,
    @bronze_file_count      INT = NULL,
    @b2s_status             NVARCHAR(30) = NULL,
    @b2s_run_id             NVARCHAR(100) = NULL,
    @b2s_started_at         DATETIME2 = NULL,
    @b2s_completed_at       DATETIME2 = NULL,
    @b2s_rows_processed     BIGINT = NULL,
    @b2s_error              NVARCHAR(MAX) = NULL,
    @s2g_status             NVARCHAR(30) = NULL,
    @s2g_run_id             NVARCHAR(100) = NULL,
    @s2g_started_at         DATETIME2 = NULL,
    @s2g_completed_at       DATETIME2 = NULL,
    @s2g_error              NVARCHAR(MAX) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE @sync_id INT;

    SELECT @sync_id = [sync_id]
    FROM [dbo].[medallion_sync]
    WHERE [extract_id] = @extract_id
      AND [target_workspace_id] = @target_workspace_id;

    IF @sync_id IS NULL
    BEGIN
        INSERT INTO [dbo].[medallion_sync] (
            [extract_id], [target_workspace_id],
            [bronze_status], [bronze_loaded_at], [bronze_file_count],
            [b2s_status], [b2s_run_id], [b2s_started_at], [b2s_completed_at],
            [b2s_rows_processed], [b2s_error],
            [s2g_status], [s2g_run_id], [s2g_started_at], [s2g_completed_at], [s2g_error],
            [last_synced_at], [sync_count]
        )
        VALUES (
            @extract_id, @target_workspace_id,
            COALESCE(@bronze_status, 'PENDING'), @bronze_loaded_at, @bronze_file_count,
            COALESCE(@b2s_status, 'NOT_STARTED'), @b2s_run_id, @b2s_started_at, @b2s_completed_at,
            @b2s_rows_processed, @b2s_error,
            COALESCE(@s2g_status, 'NOT_STARTED'), @s2g_run_id, @s2g_started_at, @s2g_completed_at, @s2g_error,
            SYSUTCDATETIME(), 1
        );
    END
    ELSE
    BEGIN
        UPDATE [dbo].[medallion_sync]
        SET [bronze_status]      = COALESCE(@bronze_status, [bronze_status]),
            [bronze_loaded_at]   = COALESCE(@bronze_loaded_at, [bronze_loaded_at]),
            [bronze_file_count]  = COALESCE(@bronze_file_count, [bronze_file_count]),
            [b2s_status]         = COALESCE(@b2s_status, [b2s_status]),
            [b2s_run_id]         = COALESCE(@b2s_run_id, [b2s_run_id]),
            [b2s_started_at]     = COALESCE(@b2s_started_at, [b2s_started_at]),
            [b2s_completed_at]   = COALESCE(@b2s_completed_at, [b2s_completed_at]),
            [b2s_rows_processed] = COALESCE(@b2s_rows_processed, [b2s_rows_processed]),
            [b2s_error]          = @b2s_error,
            [s2g_status]         = COALESCE(@s2g_status, [s2g_status]),
            [s2g_run_id]         = COALESCE(@s2g_run_id, [s2g_run_id]),
            [s2g_started_at]     = COALESCE(@s2g_started_at, [s2g_started_at]),
            [s2g_completed_at]   = COALESCE(@s2g_completed_at, [s2g_completed_at]),
            [s2g_error]          = @s2g_error,
            [last_synced_at]     = SYSUTCDATETIME(),
            [sync_count]         = [sync_count] + 1,
            [updated_at]         = SYSUTCDATETIME()
        WHERE [sync_id] = @sync_id;
    END
END;

GO

