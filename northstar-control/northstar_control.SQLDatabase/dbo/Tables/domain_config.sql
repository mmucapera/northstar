CREATE TABLE [dbo].[domain_config] (
    [domain_code]           NVARCHAR (20)  NOT NULL,
    [description]           NVARCHAR (200) NULL,
    [enabled]               BIT            DEFAULT ((1)) NOT NULL,
    [schedule_type]         NVARCHAR (20)  DEFAULT ('daily') NOT NULL,
    [expected_arrival_hour] INT            NULL,
    [expected_arrival_day]  NVARCHAR (20)  NULL,
    [on_b2s_failure_policy] NVARCHAR (30)  DEFAULT ('BLOCK') NOT NULL,
    [max_retry_attempts]    INT            DEFAULT ((3)) NOT NULL,
    [retry_delay_minutes]   INT            DEFAULT ((5)) NOT NULL,
    [min_expected_files]    INT            NULL,
    [max_expected_files]    INT            NULL,
    [alert_email]           NVARCHAR (200) NULL,
    [late_arrival_replay_threshold_hours] INT NULL,
    [late_arrival_scope_field]  NVARCHAR(20)   DEFAULT ('package_def') NULL,
    [manifest_filename_pattern]  NVARCHAR(500)  NULL,
    [extraction_date_cutoff]     DATETIME2(7)   NULL,
    [created_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [updated_at]            DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    CONSTRAINT [pk_domain_config] PRIMARY KEY CLUSTERED ([domain_code] ASC),
    CONSTRAINT [ck_domain_config_arrival_hour] CHECK ([expected_arrival_hour]>=(0) AND [expected_arrival_hour]<=(23)),
    CONSTRAINT [ck_domain_config_failure_policy] CHECK ([on_b2s_failure_policy]='ALERT_AND_CONTINUE' OR [on_b2s_failure_policy]='QUEUE' OR [on_b2s_failure_policy]='BLOCK'),
    CONSTRAINT [ck_domain_config_schedule_type] CHECK ([schedule_type]='manual' OR [schedule_type]='weekly' OR [schedule_type]='daily'),
    CONSTRAINT [ck_domain_config_late_arrival_scope] CHECK ([late_arrival_scope_field] IN ('package_def', 'extraction_def', 'both'))
);


GO

