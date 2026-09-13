-- =============================================================================
-- INS Orchestrator — First-Time Database Setup
-- Run against: Fabric SQL Database (northstar_control)
-- =============================================================================
-- Creates all tables, constraints, indexes, and stored procedures.
-- Safe to re-run: drops tables in correct order to handle FK constraints.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- DROP TABLES IN CORRECT ORDER (child tables first, then parents)
-- ─────────────────────────────────────────────────────────────────────────────
DROP TABLE IF EXISTS [dbo].[job_log];
DROP TABLE IF EXISTS [dbo].[workspace_signal];
DROP TABLE IF EXISTS [dbo].[poller_state];
DROP TABLE IF EXISTS [dbo].[medallion_sync];
DROP TABLE IF EXISTS [dbo].[push_job];
DROP TABLE IF EXISTS [dbo].[extract_file];
DROP TABLE IF EXISTS [dbo].[extract];
DROP TABLE IF EXISTS [dbo].[target_workspace];
DROP TABLE IF EXISTS [dbo].[domain_config];
DROP TABLE IF EXISTS [dbo].[poller_source];
PRINT 'All existing tables dropped (if they existed)';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. domain_config
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.domain_config', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[domain_config] (
        [domain_code]           NVARCHAR(20)   NOT NULL,
        [description]           NVARCHAR(200)  NULL,
        [enabled]               BIT            DEFAULT 1 NOT NULL,
        [schedule_type]         NVARCHAR(20)   DEFAULT 'daily' NOT NULL,
        [expected_arrival_hour] INT            NULL,
        [expected_arrival_day]  NVARCHAR(20)   NULL,
        [on_b2s_failure_policy] NVARCHAR(30)   DEFAULT 'BLOCK' NOT NULL,
        [max_retry_attempts]    INT            DEFAULT 3 NOT NULL,
        [retry_delay_minutes]   INT            DEFAULT 5 NOT NULL,
        [min_expected_files]    INT            NULL,
        [max_expected_files]    INT            NULL,
        [alert_email]           NVARCHAR(200)  NULL,
        [late_arrival_replay_threshold_hours] INT NULL,
        [late_arrival_scope_field]  NVARCHAR(20)   DEFAULT 'package_def' NULL,
        [manifest_filename_pattern]  NVARCHAR(500)  NULL,
        [extraction_date_cutoff] DATETIME2(7)  NULL,
        [created_at]            DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]            DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        CONSTRAINT [pk_domain_config] PRIMARY KEY CLUSTERED ([domain_code]),
        CONSTRAINT [ck_domain_config_arrival_hour]   CHECK ([expected_arrival_hour] >= 0 AND [expected_arrival_hour] <= 23),
        CONSTRAINT [ck_domain_config_failure_policy] CHECK ([on_b2s_failure_policy] IN ('BLOCK', 'QUEUE', 'ALERT_AND_CONTINUE')),
        CONSTRAINT [ck_domain_config_schedule_type]  CHECK ([schedule_type] IN ('daily', 'weekly', 'manual')),
        CONSTRAINT [ck_domain_config_late_arrival_scope] CHECK ([late_arrival_scope_field] IN ('package_def', 'extraction_def', 'both'))
    );
    PRINT 'Created table: dbo.domain_config';
END
ELSE PRINT 'Table dbo.domain_config already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. target_workspace
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.target_workspace', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[target_workspace] (
        [target_workspace_id]   NVARCHAR(100) NOT NULL,
        [target_workspace_name] NVARCHAR(200) NOT NULL,
        [target_lakehouse_id]   NVARCHAR(100) NOT NULL,
        [target_lakehouse_name] NVARCHAR(200) NULL,
        [enabled]               BIT           DEFAULT 1 NOT NULL,
        [domain_filter]         NVARCHAR(20)  NULL,
        [instance_filter]       NVARCHAR(50)  NULL,
        [period_type_filter]    NVARCHAR(20)  NULL,
        [arrived_after]         DATETIME2(7)  NULL,
        [b2s_pipeline_id]       NVARCHAR(100) NULL,
        [s2g_pipeline_id]       NVARCHAR(100) NULL,
        [created_at]            DATETIME2(7)  DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]            DATETIME2(7)  DEFAULT SYSUTCDATETIME() NOT NULL,
        CONSTRAINT [pk_target_workspace] PRIMARY KEY CLUSTERED ([target_workspace_id])
    );
    PRINT 'Created table: dbo.target_workspace';
END
ELSE PRINT 'Table dbo.target_workspace already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. extract
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.extract', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[extract] (
        [extract_id]           INT            IDENTITY(1,1) NOT NULL,
        [domain_code]          NVARCHAR(20)   NOT NULL,
        [source_code]          NVARCHAR(50)   NULL,
        [folder_path]          NVARCHAR(500)  NOT NULL,
        [folder_name]          NVARCHAR(200)  NULL,
        [period_year]          INT            NOT NULL,
        [period_month]         INT            NOT NULL,
        [period_day]           INT            NULL,
        [period_label]         NVARCHAR(50)   NULL,
        [status]               NVARCHAR(30)   DEFAULT 'NEW' NOT NULL,
        [is_latest_for_period] BIT            DEFAULT 1 NOT NULL,
        [superseded_by_id]     INT            NULL,
        [has_duplicate_period] BIT            DEFAULT 0 NOT NULL,
        [expected_file_count]  INT            NULL,
        [actual_file_count]    INT            NULL,
        [total_size_bytes]     BIGINT         NULL,
        [is_valid]             BIT            NULL,
        [validation_message]   NVARCHAR(500)  NULL,
        [validated_at]         DATETIME2(7)   NULL,
        [arrived_at]           DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [created_at]           DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]           DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [source_file_name]     NVARCHAR(500)  NULL,
        [source_file_format]   NVARCHAR(10)   NULL,
        [instance_code]        NVARCHAR(50)   NULL,
        [report_name]          NVARCHAR(100)  NULL,
        [period_type]          NVARCHAR(20)   NULL,
        [period_week]          INT            NULL,
        [period_raw]           NVARCHAR(50)   NULL,
        [staging_folder_path]  NVARCHAR(500)  NULL,
        [ready_folder_path]    NVARCHAR(500)  NULL,
        [extraction_date]      DATETIME2(7)   NULL,
        [cycle_id]             NVARCHAR(50)   NULL,
        [extraction_def]       NVARCHAR(100)  NULL,
        [package_def]          NVARCHAR(200)  NULL,
        [is_late_arrival]      BIT            DEFAULT 0 NOT NULL,
        [late_arrival_alerted_at] DATETIME2(7) NULL,
        CONSTRAINT [pk_extract] PRIMARY KEY CLUSTERED ([extract_id]),
        CONSTRAINT [ck_extract_period_month] CHECK ([period_month] >= 1 AND [period_month] <= 12),
        CONSTRAINT [ck_extract_status_v3] CHECK ([status] IN ('NEW','TRIGGERED','PROCESSING','VALIDATED','FAILED','ABANDONED','PUSHED','PUSHING','SKIPPED')),
        CONSTRAINT [fk_extract_domain_config] FOREIGN KEY ([domain_code]) REFERENCES [dbo].[domain_config]([domain_code]),
        CONSTRAINT [fk_extract_superseded_by] FOREIGN KEY ([superseded_by_id]) REFERENCES [dbo].[extract]([extract_id])
    );

    CREATE NONCLUSTERED INDEX [ix_extract_arrived]       ON [dbo].[extract]([arrived_at] DESC);
    CREATE NONCLUSTERED INDEX [ix_extract_domain_period]  ON [dbo].[extract]([domain_code], [period_year], [period_month], [is_latest_for_period]);
    CREATE NONCLUSTERED INDEX [ix_extract_instance]       ON [dbo].[extract]([domain_code], [instance_code]);
    CREATE NONCLUSTERED INDEX [ix_extract_period_type]    ON [dbo].[extract]([period_type], [period_year], [period_month]);
    CREATE NONCLUSTERED INDEX [ix_extract_report]         ON [dbo].[extract]([domain_code], [report_name]);
    CREATE NONCLUSTERED INDEX [ix_extract_status]         ON [dbo].[extract]([status]);

    PRINT 'Created table: dbo.extract (with indexes)';
END
ELSE PRINT 'Table dbo.extract already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 3b. Trigger: auto-populate folder_name on extract INSERT
--     Derives folder_name from source_file_name (strips extension) whenever
--     the caller inserts a NULL or empty folder_name.  This is unconditional
--     so it works regardless of SP version or app behaviour.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE OR ALTER TRIGGER [dbo].[tr_extract_set_folder_name]
ON [dbo].[extract]
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE e
    SET    e.[folder_name] = LEFT(
               i.[source_file_name],
               LEN(i.[source_file_name]) - CHARINDEX('.', REVERSE(i.[source_file_name]))
           ),
           e.[updated_at] = SYSUTCDATETIME()
    FROM   [dbo].[extract] e
    INNER JOIN inserted i ON e.[extract_id] = i.[extract_id]
    WHERE  (e.[folder_name] IS NULL OR e.[folder_name] = '')
      AND  i.[source_file_name] IS NOT NULL
      AND  CHARINDEX('.', i.[source_file_name]) > 0;
END;
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. extract_file
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.extract_file', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[extract_file] (
        [file_id]            BIGINT         IDENTITY(1,1) NOT NULL,
        [extract_id]         INT            NOT NULL,
        [file_name]          NVARCHAR(255)  NOT NULL,
        [file_path]          NVARCHAR(500)  NOT NULL,
        [file_size_bytes]    BIGINT         NULL,
        [file_hash]          NVARCHAR(64)   NULL,
        [status]             NVARCHAR(30)   DEFAULT 'NEW' NOT NULL,
        [pushed_at]          DATETIME2(7)   NULL,
        [push_error]         NVARCHAR(500)  NULL,
        [created_at]         DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [original_file_name] NVARCHAR(255)  NULL,
        [file_format]        NVARCHAR(10)   NULL,
        [row_count]          BIGINT         NULL,
        CONSTRAINT [pk_extract_file] PRIMARY KEY CLUSTERED ([file_id]),
        CONSTRAINT [ck_extract_file_status] CHECK ([status] IN ('NEW','TRIGGERED','PROCESSING','VALIDATED','FAILED','ABANDONED','PUSHED','PUSHING')),
        CONSTRAINT [fk_extract_file_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract]([extract_id])
    );

    CREATE NONCLUSTERED INDEX [ix_extract_file_extract] ON [dbo].[extract_file]([extract_id]);

    PRINT 'Created table: dbo.extract_file (with indexes)';
END
ELSE PRINT 'Table dbo.extract_file already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. push_job
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.push_job', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[push_job] (
        [push_job_id]           INT            IDENTITY(1,1) NOT NULL,
        [extract_id]            INT            NOT NULL,
        [target_workspace_id]   NVARCHAR(100)  NULL,
        [target_workspace_name] NVARCHAR(200)  NULL,
        [target_lakehouse_id]   NVARCHAR(100)  NULL,
        [target_lakehouse_name] NVARCHAR(200)  NULL,
        [bronze_folder_path]    NVARCHAR(500)  NULL,
        [status]                NVARCHAR(30)   DEFAULT 'PENDING' NOT NULL,
        [pipeline_run_id]       NVARCHAR(100)  NULL,
        [started_at]            DATETIME2(7)   NULL,
        [completed_at]          DATETIME2(7)   NULL,
        [duration_seconds]      INT            NULL,
        [files_attempted]       INT            NULL,
        [files_succeeded]       INT            NULL,
        [files_failed]          INT            NULL,
        [bytes_transferred]     BIGINT         NULL,
        [error_message]         NVARCHAR(MAX)  NULL,
        [attempt_number]        INT            DEFAULT 1 NOT NULL,
        [max_attempts]          INT            DEFAULT 3 NOT NULL,
        [next_retry_at]         DATETIME2(7)   NULL,
        [created_at]            DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]            DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        CONSTRAINT [pk_push_job] PRIMARY KEY CLUSTERED ([push_job_id]),
        CONSTRAINT [ck_push_job_status] CHECK ([status] IN ('PENDING','RUNNING','SUCCESS','PARTIAL','FAILED','CANCELLED','RECALLED')),
        CONSTRAINT [fk_push_job_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract]([extract_id])
    );

    CREATE NONCLUSTERED INDEX [ix_push_job_extract] ON [dbo].[push_job]([extract_id]);
    CREATE NONCLUSTERED INDEX [ix_push_job_status]  ON [dbo].[push_job]([status]);

    PRINT 'Created table: dbo.push_job (with indexes)';
END
ELSE PRINT 'Table dbo.push_job already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 6. medallion_sync
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.medallion_sync', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[medallion_sync] (
        [sync_id]             INT            IDENTITY(1,1) NOT NULL,
        [extract_id]          INT            NOT NULL,
        [target_workspace_id] NVARCHAR(100)  NULL,
        [bronze_status]       NVARCHAR(30)   DEFAULT 'PENDING' NULL,
        [bronze_loaded_at]    DATETIME2(7)   NULL,
        [bronze_file_count]   INT            NULL,
        [b2s_status]          NVARCHAR(30)   DEFAULT 'NOT_STARTED' NULL,
        [b2s_run_id]          NVARCHAR(100)  NULL,
        [b2s_started_at]      DATETIME2(7)   NULL,
        [b2s_completed_at]    DATETIME2(7)   NULL,
        [b2s_rows_processed]  BIGINT         NULL,
        [b2s_error]           NVARCHAR(MAX)  NULL,
        [s2g_status]          NVARCHAR(30)   DEFAULT 'NOT_STARTED' NULL,
        [s2g_run_id]          NVARCHAR(100)  NULL,
        [s2g_started_at]      DATETIME2(7)   NULL,
        [s2g_completed_at]    DATETIME2(7)   NULL,
        [s2g_error]           NVARCHAR(MAX)  NULL,
        [last_synced_at]      DATETIME2(7)   NULL,
        [sync_count]          INT            DEFAULT 0 NOT NULL,
        [created_at]          DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]          DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        CONSTRAINT [pk_medallion_sync] PRIMARY KEY CLUSTERED ([sync_id]),
        CONSTRAINT [ck_medallion_sync_bronze_status] CHECK ([bronze_status] IN ('PENDING','LOADED','FAILED')),
        CONSTRAINT [ck_medallion_sync_b2s_status]    CHECK ([b2s_status] IN ('NOT_STARTED','RUNNING','SUCCESS','FAILED','INVALIDATED')),
        CONSTRAINT [ck_medallion_sync_s2g_status]    CHECK ([s2g_status] IN ('NOT_STARTED','PENDING','PROCESSING','SUCCESS','FAILED')),
        CONSTRAINT [fk_medallion_sync_extract]       FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract]([extract_id])
    );

    CREATE NONCLUSTERED INDEX [ix_medallion_sync_extract] ON [dbo].[medallion_sync]([extract_id]);
    CREATE NONCLUSTERED INDEX [ix_medallion_sync_status]  ON [dbo].[medallion_sync]([b2s_status]);

    PRINT 'Created table: dbo.medallion_sync (with indexes)';
END
ELSE PRINT 'Table dbo.medallion_sync already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 7. poller_state
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.poller_state', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[poller_state] (
        [id]                 INT            IDENTITY(1,1) NOT NULL,
        [file_name]          NVARCHAR(500)  NOT NULL,
        [detected_at]        DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [status]             NVARCHAR(30)   NOT NULL,
        [extract_id]         INT            NULL,
        [error_message]      NVARCHAR(500)  NULL,
        [source_id]          NVARCHAR(50)   NOT NULL DEFAULT 'default',
        [blob_last_modified] DATETIME2(7)   NULL,
        CONSTRAINT [pk_poller_state] PRIMARY KEY CLUSTERED ([id]),
        CONSTRAINT [uq_poller_state_file_source] UNIQUE ([file_name], [source_id])
    );

    CREATE NONCLUSTERED INDEX [ix_poller_state_detected] ON [dbo].[poller_state]([detected_at] DESC);
    CREATE NONCLUSTERED INDEX [ix_poller_state_status]   ON [dbo].[poller_state]([status]);

    PRINT 'Created table: dbo.poller_state (with indexes)';
END
ELSE PRINT 'Table dbo.poller_state already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 8. job_log
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.job_log', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[job_log] (
        [log_id]          BIGINT         IDENTITY(1,1) NOT NULL,
        [push_job_id]     INT            NULL,
        [extract_id]      INT            NULL,
        [log_level]       NVARCHAR(20)   DEFAULT 'INFO' NOT NULL,
        [log_category]    NVARCHAR(50)   NULL,
        [message]         NVARCHAR(MAX)  NOT NULL,
        [details]         NVARCHAR(MAX)  NULL,
        [function_name]   NVARCHAR(100)  NULL,
        [pipeline_run_id] NVARCHAR(100)  NULL,
        [created_at]      DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        CONSTRAINT [pk_job_log] PRIMARY KEY CLUSTERED ([log_id]),
        CONSTRAINT [ck_job_log_level] CHECK ([log_level] IN ('DEBUG','INFO','WARNING','ERROR')),
        CONSTRAINT [fk_job_log_extract]  FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract]([extract_id]),
        CONSTRAINT [fk_job_log_push_job] FOREIGN KEY ([push_job_id]) REFERENCES [dbo].[push_job]([push_job_id])
    );

    CREATE NONCLUSTERED INDEX [ix_job_log_created] ON [dbo].[job_log]([created_at] DESC);
    CREATE NONCLUSTERED INDEX [ix_job_log_extract] ON [dbo].[job_log]([extract_id]);

    PRINT 'Created table: dbo.job_log (with indexes)';
END
ELSE PRINT 'Table dbo.job_log already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 9. workspace_signal
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.workspace_signal', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[workspace_signal] (
        [signal_id]           INT            IDENTITY(1,1) NOT NULL,
        [target_workspace_id] NVARCHAR(100)  NOT NULL,
        [signal_type]         NVARCHAR(20)   NOT NULL,
        [scope_domain]        NVARCHAR(20)   NULL,
        [scope_instance]      NVARCHAR(50)   NULL,
        [scope_period_type]   NVARCHAR(20)   NULL,
        [scope_from_date]     DATETIME2(7)   NULL,
        [scope_to_date]       DATETIME2(7)   NULL,
        [reason]              NVARCHAR(500)  NULL,
        [status]              NVARCHAR(20)   DEFAULT 'PENDING' NOT NULL,
        [created_by]          NVARCHAR(100)  NULL,
        [created_at]          DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [acknowledged_at]     DATETIME2(7)   NULL,
        [completed_at]        DATETIME2(7)   NULL,
        CONSTRAINT [pk_workspace_signal] PRIMARY KEY CLUSTERED ([signal_id]),
        CONSTRAINT [ck_signal_status] CHECK ([status] IN ('PENDING','ACKNOWLEDGED','COMPLETED')),
        CONSTRAINT [ck_signal_type]   CHECK ([signal_type] IN ('RECALL','REFILL','FILTER_CHANGED','FULL_RESET')),
        CONSTRAINT [fk_workspace_signal_target] FOREIGN KEY ([target_workspace_id]) REFERENCES [dbo].[target_workspace]([target_workspace_id])
    );

    PRINT 'Created table: dbo.workspace_signal';
END
ELSE PRINT 'Table dbo.workspace_signal already exists — skipped';
GO

-- ─────────────────────────────────────────────────────────────────────────────
-- 10. poller_source
-- ─────────────────────────────────────────────────────────────────────────────
IF OBJECT_ID('dbo.poller_source', 'U') IS NULL
BEGIN
    CREATE TABLE [dbo].[poller_source] (
        [source_id]              NVARCHAR(50)   NOT NULL,
        [label]                  NVARCHAR(200)  NULL,
        [storage_account]        NVARCHAR(200)  NOT NULL,
        [container]              NVARCHAR(200)  NOT NULL,
        [folder_path]            NVARCHAR(500)  DEFAULT '' NOT NULL,
        [sas_token]              NVARCHAR(MAX)  NOT NULL,
        [poll_interval_seconds]  INT            DEFAULT 10 NOT NULL,
        [enabled]                BIT            DEFAULT 1 NOT NULL,
        [created_at]             DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [updated_at]             DATETIME2(7)   DEFAULT SYSUTCDATETIME() NOT NULL,
        [filename_extension]     NVARCHAR(20)   DEFAULT '.zip' NOT NULL,
        [filename_must_contain]  NVARCHAR(200)  DEFAULT '' NOT NULL,
        [filename_pattern]       NVARCHAR(500)  NULL,
        [source_code]            NVARCHAR(50)   DEFAULT 'ADLS_POLLER' NOT NULL,
        [source_file_format]     NVARCHAR(20)   DEFAULT 'zip' NOT NULL,
        [domain_code_map]        NVARCHAR(500)  NULL,
        CONSTRAINT [pk_poller_source] PRIMARY KEY CLUSTERED ([source_id])
    );

    PRINT 'Created table: dbo.poller_source';
END
ELSE PRINT 'Table dbo.poller_source already exists — skipped';
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- 11. stored procedures
-- ─────────────────────────────────────────────────────────────────────────────

-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/acknowledge_workspace_signal.sql
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[acknowledge_workspace_signal]
    @signal_id   INT,
    @new_status  NVARCHAR(20)   -- 'ACKNOWLEDGED' or 'COMPLETED'
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [dbo].[workspace_signal]
    SET [status]          = @new_status,
        [acknowledged_at] = CASE WHEN @new_status = 'ACKNOWLEDGED' AND [acknowledged_at] IS NULL
                                 THEN SYSUTCDATETIME() ELSE [acknowledged_at] END,
        [completed_at]    = CASE WHEN @new_status = 'COMPLETED'
                                 THEN SYSUTCDATETIME() ELSE [completed_at] END
    WHERE [signal_id] = @signal_id;
END;

GO



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/complete_medallion_run.sql
-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- complete_medallion_run
--
-- Marks a B2S or S2G run as SUCCESS or FAILED.
-- For B2S: updates a single sync_id.
-- For S2G: updates all rows with the matching run_id.
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[complete_medallion_run]
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


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/create_push_job.sql
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[create_push_job]
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



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/create_workspace_signal.sql
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[create_workspace_signal]
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



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_b2s_pending_batches.sql
-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- get_b2s_pending_batches
--
-- Returns (domain_code, target_workspace_id) combos that have extracts
-- with bronze_status=LOADED and b2s_status=NOT_STARTED.
-- Includes the latest bronze_loaded_at so the orchestrator can evaluate
-- whether the grace period has expired.
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_b2s_pending_batches]
AS
BEGIN
    SET NOCOUNT ON;

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


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_b2s_queue.sql
-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- get_b2s_queue
--
-- For a given (domain_code, target_workspace_id), return the next extract
-- ready for B2S processing, ordered by extraction_date ASC.
-- Returns only the FIRST extract (sequential processing).
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_b2s_queue]
    @domain_code           NVARCHAR(20),
    @target_workspace_id   NVARCHAR(100)
AS
BEGIN
    SET NOCOUNT ON;

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
    FROM [dbo].[medallion_sync] ms
    INNER JOIN [dbo].[extract] e
        ON ms.[extract_id] = e.[extract_id]
    INNER JOIN [dbo].[target_workspace] tw
        ON ms.[target_workspace_id] = tw.[target_workspace_id]
    INNER JOIN [dbo].[domain_config] dc
        ON e.[domain_code] = dc.[domain_code]
    LEFT JOIN [dbo].[push_job] pj
        ON pj.[extract_id] = e.[extract_id]
       AND pj.[target_workspace_id] = ms.[target_workspace_id]
       AND pj.[status] = 'SUCCESS'
    WHERE e.[domain_code] = @domain_code
      AND ms.[target_workspace_id] = @target_workspace_id
      AND ms.[bronze_status] = 'LOADED'
      AND ms.[b2s_status] = 'NOT_STARTED'
      AND e.[is_late_arrival] = 0
      AND (dc.[extraction_date_cutoff] IS NULL
           OR e.[extraction_date] IS NULL
           OR e.[extraction_date] >= dc.[extraction_date_cutoff])
    ORDER BY
        e.[extraction_date] ASC,
        e.[package_def] ASC,
        e.[extract_id] ASC;
END;

GO


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_late_arrivals_pending.sql
-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- get_late_arrivals_pending
--
-- Returns all extracts flagged as late arrivals (is_late_arrival = 1),
-- along with eligibility info for automatic replay.
--
-- Used by the orchestrator's _check_late_arrivals() step to decide:
--   eligible_for_auto_replay = 1  → auto-replay via reset_late_arrival_batch
--   eligible_for_auto_replay = 0  → log alert (if not already alerted)
--
-- @default_threshold_hours: global fallback when domain_config has no override
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_late_arrivals_pending]
    @default_threshold_hours INT = 48
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        e.[extract_id],
        e.[domain_code],
        e.[extraction_def],
        e.[extraction_date],
        e.[package_def],
        e.[arrived_at],
        e.[late_arrival_alerted_at],
        DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME()) AS hours_since_arrival,
        COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours) AS threshold_hours,
        CASE
            WHEN DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME())
                 <= COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours)
            THEN 1 ELSE 0
        END AS eligible_for_auto_replay,
        COALESCE(dc.[late_arrival_scope_field], 'package_def') AS late_arrival_scope_field
    FROM [dbo].[extract] e
    INNER JOIN [dbo].[domain_config] dc ON e.[domain_code] = dc.[domain_code]
    WHERE e.[is_late_arrival] = 1
    ORDER BY e.[domain_code], e.[extraction_def], e.[package_def], e.[extraction_date];
END;

GO


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_pending_extracts.sql
-- -----------------------------------------------------------------------------


-- -----------------------------------------------------------------------------
-- get_pending_extracts
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_pending_extracts]
    @domain_code    NVARCHAR(20) = NULL,
    @limit          INT = 10
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@limit)
        e.[extract_id],
        e.[domain_code],
        e.[source_code],
        e.[folder_path],
        e.[folder_name],
        e.[period_year],
        e.[period_month],
        e.[period_label],
        e.[status],
        e.[is_latest_for_period],
        e.[actual_file_count],
        e.[total_size_bytes],
        e.[arrived_at],
        d.[on_b2s_failure_policy],
        d.[max_retry_attempts]
    FROM [dbo].[extract] e
    INNER JOIN [dbo].[domain_config] d ON e.[domain_code] = d.[domain_code]
    WHERE e.[status] IN ('NEW', 'VALIDATED', 'QUEUED')
      AND e.[is_latest_for_period] = 1
      AND d.[enabled] = 1
      AND (@domain_code IS NULL OR e.[domain_code] = @domain_code)
    ORDER BY e.[arrived_at] ASC;
END;

GO



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_pending_pushes.sql
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_pending_pushes]
    @domain_code    NVARCHAR(20) = NULL,
    @limit          INT = 50
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@limit)
        e.[extract_id],
        e.[domain_code],
        e.[instance_code],
        e.[period_type],
        e.[period_label],
        e.[source_file_name],
        e.[actual_file_count],
        e.[total_size_bytes],
        e.[ready_folder_path],
        e.[arrived_at],
        tw.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[target_lakehouse_id],
        tw.[target_lakehouse_name]
    FROM [dbo].[extract] e
    CROSS JOIN [dbo].[target_workspace] tw
    WHERE e.[status] = 'VALIDATED'
      AND e.[is_latest_for_period] = 1
      AND tw.[enabled] = 1
      -- ── Four filter dimensions (AND-combined, NULL = no restriction) ──
      AND (tw.[domain_filter]      IS NULL OR tw.[domain_filter]      = e.[domain_code])
      AND (tw.[instance_filter]    IS NULL OR tw.[instance_filter]    = e.[instance_code])
      AND (tw.[period_type_filter] IS NULL OR tw.[period_type_filter] = e.[period_type])
      AND (tw.[arrived_after]      IS NULL OR e.[arrived_at]         >= tw.[arrived_after])
      -- ── Optional caller filter ──
      AND (@domain_code IS NULL OR e.[domain_code] = @domain_code)
      -- ── No existing active push_job for this extract + workspace ──
      AND NOT EXISTS (
          SELECT 1 FROM [dbo].[push_job] pj
          WHERE pj.[extract_id] = e.[extract_id]
            AND pj.[target_workspace_id] = tw.[target_workspace_id]
            AND pj.[status] IN ('PENDING', 'RUNNING', 'SUCCESS')
      )
    ORDER BY e.[arrived_at] ASC;
END;

GO



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/get_s2g_ready.sql
-- -----------------------------------------------------------------------------
-- -----------------------------------------------------------------------------
-- get_s2g_ready
--
-- Returns (domain_code, target_workspace_id) combos where:
--   - ALL B2S runs are complete (no NOT_STARTED or RUNNING)
--   - At least one B2S has SUCCESS status
--   - S2G is NOT_STARTED for those rows
-- These are ready to trigger S2G pipeline.
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[get_s2g_ready]
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


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/register_extract.sql
-- -----------------------------------------------------------------------------


-- =============================================================================
-- STORED PROCEDURES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- register_extract
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[register_extract]
    @folder_path        NVARCHAR(500),
    @domain_code        NVARCHAR(20),
    @source_code        NVARCHAR(50),
    @folder_name        NVARCHAR(200),
    @period_year        INT,
    @period_month       INT,
    @period_day         INT = NULL,
    @period_label       NVARCHAR(50) = NULL,
    @file_count         INT = NULL,
    @total_size_bytes   BIGINT = NULL,
    @source_file_name   NVARCHAR(500) = NULL,
    @source_file_format NVARCHAR(10) = NULL,
    @instance_code      NVARCHAR(50) = NULL,
    @report_name        NVARCHAR(100) = NULL,
    @extract_id         INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Remap alias domain codes to their canonical equivalents
        -- (mirrors domain_code_map in poller_source; keeps DB consistent
        --  even if the poller sends the raw filename token)
        SET @domain_code = CASE @domain_code
            WHEN 'FCT' THEN 'DP'
            WHEN 'OPR' THEN 'SP'
            ELSE @domain_code
        END;

        -- Derive folder_name from source_file_name when caller passes NULL or empty
        -- (e.g. files dropped at container root with no subfolder)
        IF (@folder_name IS NULL OR @folder_name = '') AND @source_file_name IS NOT NULL
        BEGIN
            SET @folder_name = CASE
                WHEN CHARINDEX('.', @source_file_name) > 0
                    THEN LEFT(@source_file_name, LEN(@source_file_name) - CHARINDEX('.', REVERSE(@source_file_name)))
                ELSE @source_file_name
            END;
        END

        -- Idempotency: if an extract with this source_file_name already exists, return it
        IF @source_file_name IS NOT NULL
        BEGIN
            SELECT @extract_id = [extract_id]
            FROM [dbo].[extract]
            WHERE [source_file_name] = @source_file_name;

            IF @extract_id IS NOT NULL
            BEGIN
                COMMIT TRANSACTION;
                RETURN;
            END
        END

        -- Find existing latest extract for same period
        DECLARE @old_extract_id INT;
        SELECT TOP 1 @old_extract_id = [extract_id]
        FROM [dbo].[extract]
        WHERE [domain_code] = @domain_code
          AND [period_year] = @period_year
          AND [period_month] = @period_month
          AND [is_latest_for_period] = 1;

        -- Insert new extract
        INSERT INTO [dbo].[extract] (
            [domain_code], [source_code], [folder_path], [folder_name],
            [period_year], [period_month], [period_day], [period_label],
            [actual_file_count], [total_size_bytes],
            [source_file_name], [source_file_format], [instance_code], [report_name],
            [status], [is_latest_for_period], [has_duplicate_period]
        )
        VALUES (
            @domain_code, @source_code, @folder_path, @folder_name,
            @period_year, @period_month, @period_day,
            COALESCE(@period_label, CONCAT(@period_year, '-', RIGHT('0' + CAST(@period_month AS VARCHAR(2)), 2))),
            @file_count, @total_size_bytes,
            @source_file_name, @source_file_format, @instance_code, @report_name,
            'NEW', 1,
            CASE WHEN @old_extract_id IS NOT NULL THEN 1 ELSE 0 END
        );

        SET @extract_id = SCOPE_IDENTITY();

        -- Supersede old extract if exists
        IF @old_extract_id IS NOT NULL
        BEGIN
            UPDATE [dbo].[extract]
            SET [is_latest_for_period] = 0,
                [superseded_by_id] = @extract_id,
                [has_duplicate_period] = 1,
                [updated_at] = SYSUTCDATETIME()
            WHERE [extract_id] = @old_extract_id;
        END

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;

GO



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/reset_late_arrival_batch.sql
-- -----------------------------------------------------------------------------
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
CREATE OR ALTER PROCEDURE [dbo].[reset_late_arrival_batch]
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


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/start_medallion_run.sql
-- -----------------------------------------------------------------------------
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
CREATE OR ALTER PROCEDURE [dbo].[start_medallion_run]
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
            [b2s_started_at] = SYSUTCDATETIME(),
            [updated_at]     = SYSUTCDATETIME()
        WHERE [sync_id] = @sync_id
          AND [b2s_status] = 'NOT_STARTED'
          AND [bronze_status] = 'LOADED';

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


-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/update_medallion_sync.sql
-- -----------------------------------------------------------------------------


-- -----------------------------------------------------------------------------
-- update_medallion_sync
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[update_medallion_sync]
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



-- -----------------------------------------------------------------------------
-- Source: dbo/StoredProcedures/update_push_job_status.sql
-- -----------------------------------------------------------------------------
CREATE OR ALTER PROCEDURE [dbo].[update_push_job_status]
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



PRINT 'Stored procedures created/updated';
GO


-- -----------------------------------------------------------------------------
-- Seed: target_workspace
-- -----------------------------------------------------------------------------

INSERT INTO [dbo].[target_workspace] (
    [target_workspace_id],
    [target_workspace_name],
    [target_lakehouse_id],
    [target_lakehouse_name],
    [enabled],
    [domain_filter],
    [instance_filter],
    [period_type_filter],
    [arrived_after],
    [b2s_pipeline_id],
    [s2g_pipeline_id]
)
VALUES (
    '3c6bac21-087c-4529-b7cd-939a39925cf2',                  -- target_workspace_id (from Fabric)
    'C0040',                  -- target_workspace_name
    '090c7b72-6fa4-4134-aa0d-e56087aa60fb',                -- target_lakehouse_id (from Fabric)
    'lkh_001',                         -- target_lakehouse_name
    1,                                 -- enabled
    NULL,                              -- domain_filter (NULL = all domains, e.g. 'DP')
    NULL,                              -- instance_filter (NULL = all instances, e.g. 'CUSTOMER0')
    NULL,                              -- period_type_filter (NULL = all period types, e.g. 'daily')
    NULL,                              -- arrived_after (NULL = no arrival cutoff, e.g. '2026-01-01')
    'd14c7036-4b23-420a-95fa-56929cf4f39e',             -- b2s_pipeline_id (Fabric pipeline)
    'd0029504-b1a0-40b0-8d19-6fcc9f7771ff'              -- s2g_pipeline_id (Fabric pipeline)
);


GO


-- -----------------------------------------------------------------------------
-- Seed: domain_config
-- -----------------------------------------------------------------------------
INSERT INTO [dbo].[domain_config] (
    [domain_code],
    [description],
    [enabled],
    [schedule_type],
    [expected_arrival_hour],
    [expected_arrival_day],
    [late_arrival_replay_threshold_hours],
    [extraction_date_cutoff],
    [manifest_filename_pattern],
    [late_arrival_scope_field],
    [on_b2s_failure_policy],
    [max_retry_attempts],
    [retry_delay_minutes],
    [min_expected_files],
    [max_expected_files],
    [alert_email]
)
VALUES
    ('DP',  'DemandPlanning',                                      1, 'daily',  6,    NULL, NULL, NULL, NULL, NULL, 'BLOCK', 3, 5, NULL, NULL, NULL),
    ('SP',  'SupplyPlanning',                                      1, 'daily',  6,    NULL, NULL, NULL, NULL, NULL, 'BLOCK', 3, 5, NULL, NULL, NULL),
    ('FCT', 'Forecast (maps to DP)',                               1, 'daily',  6,    NULL, NULL, NULL, NULL, NULL, 'BLOCK', 3, 5, NULL, NULL, NULL),
    ('OPR', 'Operational (maps to SP)',                            1, 'daily',  6,    NULL, NULL, NULL, NULL, NULL, 'BLOCK', 3, 5, NULL, NULL, NULL);
GO


PRINT '';
PRINT '============================================================';
PRINT '  First-time setup complete — all tables created.';
PRINT '  Next: seed domain_config, target_workspace,';
PRINT '        and poller_source rows.';
PRINT '============================================================';