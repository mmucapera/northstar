

-- -----------------------------------------------------------------------------
-- get_pending_extracts
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[get_pending_extracts]
    @domain_code    NVARCHAR(20) = NULL,
    @limit          INT = 10
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@limit)
        e.[extract_id],
        e.[domain_code],
        e.[source_code],
        e.[folder_path],
        e.[folder_name],
        e.[period_year],
        e.[period_month],
        e.[period_label],
        e.[status],
        e.[is_latest_for_period],
        e.[actual_file_count],
        e.[total_size_bytes],
        e.[arrived_at],
        d.[on_b2s_failure_policy],
        d.[max_retry_attempts]
    FROM [dbo].[extract] e
    INNER JOIN [dbo].[domain_config] d ON e.[domain_code] = d.[domain_code]
    WHERE e.[status] IN ('NEW', 'VALIDATED', 'QUEUED')
      AND e.[is_latest_for_period] = 1
      AND d.[enabled] = 1
      AND (@domain_code IS NULL OR e.[domain_code] = @domain_code)
    ORDER BY e.[arrived_at] ASC;
END;

GO

