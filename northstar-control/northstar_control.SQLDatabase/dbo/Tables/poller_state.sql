CREATE TABLE [dbo].[poller_state] (
    [id]                 INT            IDENTITY (1, 1) NOT NULL,
    [file_name]          NVARCHAR (500) NOT NULL,
    [detected_at]        DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [status]             NVARCHAR (30)  NOT NULL,
    [extract_id]         INT            NULL,
    [error_message]      NVARCHAR (500) NULL,
    [source_id]          NVARCHAR (50)  DEFAULT ('default') NOT NULL,
    [blob_last_modified] DATETIME2 (7)  NULL,
    CONSTRAINT [pk_poller_state] PRIMARY KEY CLUSTERED ([id] ASC),
    CONSTRAINT [uq_poller_state_file_source] UNIQUE NONCLUSTERED ([file_name] ASC, [source_id] ASC)
);


GO

CREATE NONCLUSTERED INDEX [ix_poller_state_detected]
    ON [dbo].[poller_state]([detected_at] DESC);


GO

CREATE NONCLUSTERED INDEX [ix_poller_state_status]
    ON [dbo].[poller_state]([status] ASC);


GO

