CREATE TABLE [dbo].[extract_file] (
    [file_id]            BIGINT         IDENTITY (1, 1) NOT NULL,
    [extract_id]         INT            NOT NULL,
    [file_name]          NVARCHAR (255) NOT NULL,
    [file_path]          NVARCHAR (500) NOT NULL,
    [file_size_bytes]    BIGINT         NULL,
    [file_hash]          NVARCHAR (64)  NULL,
    [status]             NVARCHAR (30)  DEFAULT ('NEW') NOT NULL,
    [pushed_at]          DATETIME2 (7)  NULL,
    [push_error]         NVARCHAR (500) NULL,
    [created_at]         DATETIME2 (7)  DEFAULT (sysutcdatetime()) NOT NULL,
    [original_file_name] NVARCHAR (255) NULL,
    [file_format]        NVARCHAR (10)  NULL,
    [row_count]          BIGINT         NULL,
    CONSTRAINT [pk_extract_file] PRIMARY KEY CLUSTERED ([file_id] ASC),
    CONSTRAINT [ck_extract_file_status] CHECK ([status]='ABANDONED' OR [status]='FAILED' OR [status]='VALIDATED' OR [status]='PROCESSING' OR [status]='TRIGGERED' OR [status]='NEW' OR [status]='PUSHED' OR [status]='PUSHING'),
    CONSTRAINT [fk_extract_file_extract] FOREIGN KEY ([extract_id]) REFERENCES [dbo].[extract] ([extract_id])
);


GO

CREATE NONCLUSTERED INDEX [ix_extract_file_extract]
    ON [dbo].[extract_file]([extract_id] ASC);


GO

