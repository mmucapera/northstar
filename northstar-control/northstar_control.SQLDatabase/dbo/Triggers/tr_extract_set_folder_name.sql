CREATE OR ALTER TRIGGER [dbo].[tr_extract_set_folder_name]
ON [dbo].[extract]
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;
    -- Derive folder_name from source_file_name (strip extension) whenever
    -- the caller inserts a NULL or empty folder_name.
    -- Handles files at container root (no subfolder) where the app cannot
    -- determine a folder_name from the blob path.
    UPDATE e
    SET    e.[folder_name] = LEFT(
               i.[source_file_name],
               LEN(i.[source_file_name]) - CHARINDEX('.', REVERSE(i.[source_file_name]))
           ),
           e.[updated_at] = SYSUTCDATETIME()
    FROM   [dbo].[extract] e
    INNER JOIN inserted i ON e.[extract_id] = i.[extract_id]
    WHERE  (e.[folder_name] IS NULL OR e.[folder_name] = '')
      AND  i.[source_file_name] IS NOT NULL
      AND  CHARINDEX('.', i.[source_file_name]) > 0;
END;
