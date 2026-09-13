CREATE TABLE [dbo].[medallion_sync] (
    [sync_id]             INT            IDENTITY (1, 1) NOT NULL,
    [extract_id]          INT            NOT NULL,
    [target_workspace_id] NVARCHAR (100) NULL,
    [bronze_status]       NVARCHAR (30)  DEFAULT ('PENDING') NULL,
    [bronze_loaded_at]    DATETIME2 (7)  NULL,
    [bronze_file_count]   INT            NULL,
    [b2s_status]          NVARCHAR (30)  DEFAULT ('NOT_STARTED') NULL,
    [b2s_run_id]          NVARCHAR (100) NULL,
    [b2s_started_at]      DATETIME2 (7)  NULL,
    [b2s_completed_at]    DATETIME2 (7)  NULL,
    [b2s_rows_processed]  BIGINT         NULL,
    [b2s_error]           NVARCHAR (MAX) NULL,
    [s2g_status]          NVARCHAR (30)  DEFAULT ('NOT_STARTED') NULL,
    [s2g_run_id]          NVARCHAR (100) NULL,
    [s2g_started_at]      DATETIME2 (7)  NULL,
    [s2g_completed_at]    DATETIME2 (7)  NULL,
    [s2g_error]           NVARCHAR (MAX) NULL,
    [last_synced_at]      DATETIME2 (7)  NULL,
    [sync_count]          INT            DEFAULT ((0)) NOT NULL,
    [created_at]          DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]          DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_medallion_sync] PRIMARY KEY CLUSTERED ([sync_id] ASC),
    CONSTRAINT [ck_medallion_sync_b2s_status] CHECK ([b2s_status]='INVALIDATED' OR [b2s_status]='FAILED' OR [b2s_status]='SUCCESS' OR [b2s_status]='RUNNING' OR [b2s_status]='NOT_STARTED'),
    CONSTRAINT [ck_medallion_sync_bronze_status] CHECK ([bronze_status]='FAILED' OR [bronze_status]='LOADED' OR [bronze_status]='PENDING'),
    CONSTRAINT [ck_medallion_sync_s2g_status] CHECK ([s2g_status]='FAILED' OR [s2g_status]='SUCCESS' OR [s2g_status]='PROCESSING' OR [s2g_status]='PENDING' OR [s2g_status]='NOT_STARTED'),
    CONSTRAINT [fk_medallion_sync_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract] ([extract_id])
);


GO

CREATE NONCLUSTERED INDEX [ix_medallion_sync_extract]
    ON [dbo].[medallion_sync]([extract_id] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_medallion_sync_status]
    ON [dbo].[medallion_sync]([b2s_status] ASC);


GO

