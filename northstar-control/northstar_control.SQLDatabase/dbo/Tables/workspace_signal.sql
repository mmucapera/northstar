CREATE TABLE [dbo].[workspace_signal] (
    [signal_id]           INT            IDENTITY (1, 1) NOT NULL,
    [target_workspace_id] NVARCHAR (100) NOT NULL,
    [signal_type]         NVARCHAR (20)  NOT NULL,
    [scope_domain]        NVARCHAR (20)  NULL,
    [scope_instance]      NVARCHAR (50)  NULL,
    [scope_period_type]   NVARCHAR (20)  NULL,
    [scope_from_date]     DATETIME2 (7)  NULL,
    [scope_to_date]       DATETIME2 (7)  NULL,
    [reason]              NVARCHAR (500) NULL,
    [status]              NVARCHAR (20)  DEFAULT ('PENDING') NOT NULL,
    [created_by]          NVARCHAR (100) NULL,
    [created_at]          DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [acknowledged_at]     DATETIME2 (7)  NULL,
    [completed_at]        DATETIME2 (7)  NULL,
    CONSTRAINT [pk_workspace_signal] PRIMARY KEY CLUSTERED ([signal_id] ASC),
    CONSTRAINT [ck_signal_status] CHECK ([status]='COMPLETED' OR [status]='ACKNOWLEDGED' OR [status]='PENDING'),
    CONSTRAINT [ck_signal_type] CHECK ([signal_type]='FULL_RESET' OR [signal_type]='FILTER_CHANGED' OR [signal_type]='REFILL' OR [signal_type]='RECALL'),
    CONSTRAINT [fk_workspace_signal_target] FOREIGN KEY ([target_workspace_id]) REFERENCES [dbo].[target_workspace] ([target_workspace_id])
);


GO

