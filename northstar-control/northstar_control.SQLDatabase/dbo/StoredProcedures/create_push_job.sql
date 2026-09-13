CREATE   PROCEDURE [dbo].[create_push_job]
    @extract_id             INT,
    @target_workspace_id    NVARCHAR(100),
    @target_workspace_name  NVARCHAR(200),
    @target_lakehouse_id    NVARCHAR(100),
    @target_lakehouse_name  NVARCHAR(200) = NULL,
    @bronze_folder_path     NVARCHAR(500),
    @push_job_id            INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    -- ── Idempotency: check for existing push_job for this extract + workspace ──
    SELECT TOP 1 @push_job_id = [push_job_id]
    FROM [dbo].[push_job]
    WHERE [extract_id] = @extract_id
      AND [target_workspace_id] = @target_workspace_id
      AND [status] IN ('PENDING', 'RUNNING', 'SUCCESS');

    IF @push_job_id IS NOT NULL
    BEGIN
        -- Already exists for this workspace — return it (idempotent)
        SELECT @push_job_id AS push_job_id;
        RETURN;
    END

    -- ── Verify extract is in a pushable state ──
    IF NOT EXISTS (
        SELECT 1 FROM [dbo].[extract]
        WHERE [extract_id] = @extract_id
          AND [status] = 'VALIDATED'
    )
    BEGIN
        RAISERROR('Extract %d is not in VALIDATED state — cannot push.', 16, 1, @extract_id);
        RETURN;
    END

    -- ── Insert new push_job ──
    INSERT INTO [dbo].[push_job] (
        [extract_id],
        [target_workspace_id],
        [target_workspace_name],
        [target_lakehouse_id],
        [target_lakehouse_name],
        [bronze_folder_path]
    )
    VALUES (
        @extract_id,
        @target_workspace_id,
        @target_workspace_name,
        @target_lakehouse_id,
        @target_lakehouse_name,
        @bronze_folder_path
    );

    SET @push_job_id = SCOPE_IDENTITY();

    SELECT @push_job_id AS push_job_id;
END;

GO

