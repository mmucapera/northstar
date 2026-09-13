CREATE TABLE [dbo].[poller_source] (
    [source_id]             NVARCHAR (50)  NOT NULL,
    [label]                 NVARCHAR (200) NULL,
    [storage_account]       NVARCHAR (200) NOT NULL,
    [container]             NVARCHAR (200) NOT NULL,
    [folder_path]           NVARCHAR (500) DEFAULT ('') NOT NULL,
    [sas_token]             NVARCHAR (MAX) NOT NULL,
    [poll_interval_seconds] INT            DEFAULT ((10)) NOT NULL,
    [enabled]               BIT            DEFAULT ((1)) NOT NULL,
    [created_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [filename_extension]    NVARCHAR (20)  DEFAULT ('.zip') NOT NULL,
    [filename_must_contain] NVARCHAR (200) DEFAULT ('FinishedZip') NOT NULL,
    [filename_pattern]      NVARCHAR (500) NULL,
    [source_code]           NVARCHAR (50)  DEFAULT ('ADLS_POLLER') NOT NULL,
    [source_file_format]    NVARCHAR (20)  DEFAULT ('zip') NOT NULL,
    [domain_code_map]       NVARCHAR (500) NULL,
    CONSTRAINT [pk_poller_source] PRIMARY KEY CLUSTERED ([source_id] ASC)
);


GO
