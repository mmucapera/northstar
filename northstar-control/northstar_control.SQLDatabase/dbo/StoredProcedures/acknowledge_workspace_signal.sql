CREATE   PROCEDURE [dbo].[acknowledge_workspace_signal]
    @signal_id   INT,
    @new_status  NVARCHAR(20)   -- 'ACKNOWLEDGED' or 'COMPLETED'
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE [dbo].[workspace_signal]
    SET [status]          = @new_status,
        [acknowledged_at] = CASE WHEN @new_status = 'ACKNOWLEDGED' AND [acknowledged_at] IS NULL
                                 THEN SYSUTCDATETIME() ELSE [acknowledged_at] END,
        [completed_at]    = CASE WHEN @new_status = 'COMPLETED'
                                 THEN SYSUTCDATETIME() ELSE [completed_at] END
    WHERE [signal_id] = @signal_id;
END;

GO

