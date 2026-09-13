CREATE TABLE [dbo].[job_log] (
    [log_id]          BIGINT         IDENTITY (1, 1) NOT NULL,
    [push_job_id]     INT            NULL,
    [extract_id]      INT            NULL,
    [log_level]       NVARCHAR (20)  DEFAULT ('INFO') NOT NULL,
    [log_category]    NVARCHAR (50)  NULL,
    [message]         NVARCHAR (MAX) NOT NULL,
    [details]         NVARCHAR (MAX) NULL,
    [function_name]   NVARCHAR (100) NULL,
    [pipeline_run_id] NVARCHAR (100) NULL,
    [created_at]      DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_job_log] PRIMARY KEY CLUSTERED ([log_id] ASC),
    CONSTRAINT [ck_job_log_level] CHECK ([log_level]='ERROR' OR [log_level]='WARNING' OR [log_level]='INFO' OR [log_level]='DEBUG'),
    CONSTRAINT [fk_job_log_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract] ([extract_id]),
    CONSTRAINT [fk_job_log_push_job] FOREIGN KEY ([push_job_id]) REFERENCES [dbo].[push_job] ([push_job_id])
);


GO

CREATE NONCLUSTERED INDEX [ix_job_log_created]
    ON [dbo].[job_log]([created_at] DESC);


GO

CREATE NONCLUSTERED INDEX [ix_job_log_extract]
    ON [dbo].[job_log]([extract_id] ASC);


GO

