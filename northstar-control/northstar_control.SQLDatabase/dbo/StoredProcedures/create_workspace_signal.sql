CREATE   PROCEDURE [dbo].[create_workspace_signal]
    @target_workspace_id    NVARCHAR(100),
    @signal_type            NVARCHAR(20),
    @scope_domain           NVARCHAR(20)   = NULL,
    @scope_instance         NVARCHAR(50)   = NULL,
    @scope_period_type      NVARCHAR(20)   = NULL,
    @scope_from_date        DATETIME2      = NULL,
    @scope_to_date          DATETIME2      = NULL,
    @reason                 NVARCHAR(500)  = NULL,
    @created_by             NVARCHAR(100)  = NULL,
    @signal_id              INT OUTPUT,
    @push_jobs_recalled     INT OUTPUT,
    @syncs_invalidated      INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET XACT_ABORT ON;

    BEGIN TRANSACTION;

    -- ── 1. Insert the signal ──
    INSERT INTO [dbo].[workspace_signal] (
        [target_workspace_id], [signal_type],
        [scope_domain], [scope_instance], [scope_period_type],
        [scope_from_date], [scope_to_date],
        [reason], [created_by]
    )
    VALUES (
        @target_workspace_id, @signal_type,
        @scope_domain, @scope_instance, @scope_period_type,
        @scope_from_date, @scope_to_date,
        @reason, @created_by
    );

    SET @signal_id = SCOPE_IDENTITY();
    SET @push_jobs_recalled = 0;
    SET @syncs_invalidated = 0;

    -- ── 2. For RECALL, REFILL, FULL_RESET: mark affected push_jobs and syncs ──
    IF @signal_type IN ('RECALL', 'REFILL', 'FULL_RESET')
    BEGIN
        -- Find affected push_jobs by joining to extract and applying scope filters
        UPDATE pj
        SET pj.[status]     = 'RECALLED',
            pj.[error_message] = CONCAT('Recalled by signal_id=', @signal_id, ': ', @reason),
            pj.[completed_at]  = SYSUTCDATETIME(),
            pj.[updated_at]    = SYSUTCDATETIME()
        FROM [dbo].[push_job] pj
        INNER JOIN [dbo].[extract] e ON pj.[extract_id] = e.[extract_id]
        WHERE pj.[target_workspace_id] = @target_workspace_id
          AND pj.[status] = 'SUCCESS'   -- only recall successful pushes
          AND (@scope_domain      IS NULL OR e.[domain_code]   = @scope_domain)
          AND (@scope_instance    IS NULL OR e.[instance_code]  = @scope_instance)
          AND (@scope_period_type IS NULL OR e.[period_type]    = @scope_period_type)
          AND (@scope_from_date   IS NULL OR e.[arrived_at]    >= @scope_from_date)
          AND (@scope_to_date     IS NULL OR e.[arrived_at]    <= @scope_to_date);

        SET @push_jobs_recalled = @@ROWCOUNT;

        -- Mark corresponding medallion_sync rows as INVALIDATED
        UPDATE ms
        SET ms.[b2s_status]  = 'INVALIDATED',
            ms.[updated_at]  = SYSUTCDATETIME()
        FROM [dbo].[medallion_sync] ms
        INNER JOIN [dbo].[push_job] pj ON ms.[extract_id] = pj.[extract_id]
            AND ms.[target_workspace_id] = pj.[target_workspace_id]
        WHERE pj.[target_workspace_id] = @target_workspace_id
          AND pj.[status] = 'RECALLED'
          AND ms.[b2s_status] IN ('NOT_STARTED', 'RUNNING', 'SUCCESS');

        SET @syncs_invalidated = @@ROWCOUNT;
    END

    COMMIT TRANSACTION;

    -- ── 3. Return summary ──
    SELECT @signal_id         AS signal_id,
           @signal_type       AS signal_type,
           @push_jobs_recalled AS push_jobs_recalled,
           @syncs_invalidated  AS syncs_invalidated;
END;

GO

