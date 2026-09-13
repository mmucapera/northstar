CREATE TABLE [dbo].[push_job] (
    [push_job_id]           INT            IDENTITY (1, 1) NOT NULL,
    [extract_id]            INT            NOT NULL,
    [target_workspace_id]   NVARCHAR (100) NULL,
    [target_workspace_name] NVARCHAR (200) NULL,
    [target_lakehouse_id]   NVARCHAR (100) NULL,
    [target_lakehouse_name] NVARCHAR (200) NULL,
    [bronze_folder_path]    NVARCHAR (500) NULL,
    [status]                NVARCHAR (30)  DEFAULT ('PENDING') NOT NULL,
    [pipeline_run_id]       NVARCHAR (100) NULL,
    [started_at]            DATETIME2 (7)  NULL,
    [completed_at]          DATETIME2 (7)  NULL,
    [duration_seconds]      INT            NULL,
    [files_attempted]       INT            NULL,
    [files_succeeded]       INT            NULL,
    [files_failed]          INT            NULL,
    [bytes_transferred]     BIGINT         NULL,
    [error_message]         NVARCHAR (MAX) NULL,
    [attempt_number]        INT            DEFAULT ((1)) NOT NULL,
    [max_attempts]          INT            DEFAULT ((3)) NOT NULL,
    [next_retry_at]         DATETIME2 (7)  NULL,
    [created_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_push_job] PRIMARY KEY CLUSTERED ([push_job_id] ASC),
    CONSTRAINT [ck_push_job_status] CHECK ([status]='RECALLED' OR [status]='CANCELLED' OR [status]='FAILED' OR [status]='PARTIAL' OR [status]='SUCCESS' OR [status]='RUNNING' OR [status]='PENDING'),
    CONSTRAINT [fk_push_job_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract] ([extract_id])
);


GO

CREATE NONCLUSTERED INDEX [ix_push_job_extract]
    ON [dbo].[push_job]([extract_id] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_push_job_status]
    ON [dbo].[push_job]([status] ASC);


GO

