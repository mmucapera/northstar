CREATE TABLE [dbo].[target_workspace] (
    [target_workspace_id]   NVARCHAR (100) NOT NULL,
    [target_workspace_name] NVARCHAR (200) NOT NULL,
    [target_lakehouse_id]   NVARCHAR (100) NOT NULL,
    [target_lakehouse_name] NVARCHAR (200) NULL,
    [enabled]               BIT            DEFAULT ((1)) NOT NULL,
    [domain_filter]         NVARCHAR (20)  NULL,
    [instance_filter]       NVARCHAR (50)  NULL,
    [period_type_filter]    NVARCHAR (20)  NULL,
    [arrived_after]         DATETIME2 (7)  NULL,
    [b2s_pipeline_id]       NVARCHAR (100) NULL,
    [s2g_pipeline_id]       NVARCHAR (100) NULL,
    [created_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_target_workspace] PRIMARY KEY CLUSTERED ([target_workspace_id] ASC)
);


GO

