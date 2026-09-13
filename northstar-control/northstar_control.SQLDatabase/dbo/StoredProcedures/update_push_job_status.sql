CREATE   PROCEDURE [dbo].[update_push_job_status]
    @push_job_id        INT,
    @status             NVARCHAR(30),
    @files_attempted    INT = NULL,
    @files_succeeded    INT = NULL,
    @files_failed       INT = NULL,
    @bytes_transferred  BIGINT = NULL,
    @error_message      NVARCHAR(MAX) = NULL,
    @pipeline_run_id    NVARCHAR(100) = NULL
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [dbo].[push_job]
    SET [status]            = @status,
        [files_attempted]   = COALESCE(@files_attempted, [files_attempted]),
        [files_succeeded]   = COALESCE(@files_succeeded, [files_succeeded]),
        [files_failed]      = COALESCE(@files_failed, [files_failed]),
        [bytes_transferred] = COALESCE(@bytes_transferred, [bytes_transferred]),
        [error_message]     = COALESCE(@error_message, [error_message]),
        [pipeline_run_id]   = COALESCE(@pipeline_run_id, [pipeline_run_id]),
        [started_at]        = CASE WHEN @status = 'RUNNING' AND [started_at] IS NULL
                                   THEN SYSUTCDATETIME() ELSE [started_at] END,
        [completed_at]      = CASE WHEN @status IN ('SUCCESS', 'PARTIAL', 'FAILED', 'CANCELLED', 'RECALLED')
                                   THEN SYSUTCDATETIME() ELSE [completed_at] END,
        [duration_seconds]  = CASE WHEN @status IN ('SUCCESS', 'PARTIAL', 'FAILED', 'CANCELLED', 'RECALLED')
                                        AND [started_at] IS NOT NULL
                                   THEN DATEDIFF(SECOND, [started_at], SYSUTCDATETIME())
                                   ELSE [duration_seconds] END,
        [updated_at]        = SYSUTCDATETIME()
    WHERE [push_job_id] = @push_job_id;

    -- ══════════════════════════════════════════════════════════════════
    -- REMOVED: No longer cascades to extract.status
    -- Push status is per-workspace; extract status stays at VALIDATED
    -- ══════════════════════════════════════════════════════════════════
END;

GO

