CREATE TABLE [dbo].[extract] (
    [extract_id]           INT            IDENTITY (1, 1) NOT NULL,
    [domain_code]          NVARCHAR (20)  NOT NULL,
    [source_code]          NVARCHAR (50)  NULL,
    [folder_path]          NVARCHAR (500) NOT NULL,
    [folder_name]          NVARCHAR (200) NULL,
    [period_year]          INT            NOT NULL,
    [period_month]         INT            NOT NULL,
    [period_day]           INT            NULL,
    [period_label]         NVARCHAR (50)  NULL,
    [status]               NVARCHAR (30)  DEFAULT ('NEW') NOT NULL,
    [is_latest_for_period] BIT            DEFAULT ((1)) NOT NULL,
    [superseded_by_id]     INT            NULL,
    [has_duplicate_period] BIT            DEFAULT ((0)) NOT NULL,
    [expected_file_count]  INT            NULL,
    [actual_file_count]    INT            NULL,
    [total_size_bytes]     BIGINT         NULL,
    [is_valid]             BIT            NULL,
    [validation_message]   NVARCHAR (500) NULL,
    [validated_at]         DATETIME2 (7)  NULL,
    [arrived_at]           DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [created_at]           DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]           DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [source_file_name]     NVARCHAR (500) NULL,
    [source_file_format]   NVARCHAR (10)  NULL,
    [instance_code]        NVARCHAR (50)  NULL,
    [report_name]          NVARCHAR (100) NULL,
    [period_type]          NVARCHAR (20)  NULL,
    [period_week]          INT            NULL,
    [period_raw]           NVARCHAR (50)  NULL,
    [staging_folder_path]  NVARCHAR (500) NULL,
    [ready_folder_path]    NVARCHAR (500) NULL,
    [extraction_date]      DATETIME2 (7)  NULL,
    [cycle_id]             NVARCHAR (50)  NULL,
    [extraction_def]       NVARCHAR (100) NULL,
    [package_def]          NVARCHAR (200) NULL,
    [is_late_arrival]      BIT            DEFAULT ((0)) NOT NULL,
    [late_arrival_alerted_at] DATETIME2 (7) NULL,
    CONSTRAINT [pk_extract] PRIMARY KEY CLUSTERED ([extract_id] ASC),
    CONSTRAINT [ck_extract_period_month] CHECK ([period_month]>=(1) AND [period_month]<=(12)),
    CONSTRAINT [ck_extract_status_v3] CHECK ([status] IN ('NEW','TRIGGERED','PROCESSING','VALIDATED','PUSHED','PUSHING','FAILED','ABANDONED','SKIPPED')),
    CONSTRAINT [fk_extract_domain_config] FOREIGN KEY ([domain_code]) REFERENCES [dbo].[domain_config] ([domain_code]),
    CONSTRAINT [fk_extract_superseded_by] FOREIGN KEY ([superseded_by_id]) REFERENCES [dbo].[extract] ([extract_id])
);


GO

CREATE NONCLUSTERED INDEX [ix_extract_arrived]
    ON [dbo].[extract]([arrived_at] DESC);


GO

CREATE NONCLUSTERED INDEX [ix_extract_domain_period]
    ON [dbo].[extract]([domain_code] ASC, [period_year] ASC, [period_month] ASC, [is_latest_for_period] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_extract_instance]
    ON [dbo].[extract]([domain_code] ASC, [instance_code] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_extract_period_type]
    ON [dbo].[extract]([period_type] ASC, [period_year] ASC, [period_month] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_extract_report]
    ON [dbo].[extract]([domain_code] ASC, [report_name] ASC);


GO

CREATE NONCLUSTERED INDEX [ix_extract_status]
    ON [dbo].[extract]([status] ASC);


GO

