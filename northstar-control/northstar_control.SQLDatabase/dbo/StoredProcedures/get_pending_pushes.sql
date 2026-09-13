CREATE   PROCEDURE [dbo].[get_pending_pushes]
    @domain_code    NVARCHAR(20) = NULL,
    @limit          INT = 50
AS
BEGIN
    SET NOCOUNT ON;

    SELECT TOP (@limit)
        e.[extract_id],
        e.[domain_code],
        e.[instance_code],
        e.[period_type],
        e.[period_label],
        e.[source_file_name],
        e.[actual_file_count],
        e.[total_size_bytes],
        e.[ready_folder_path],
        e.[arrived_at],
        tw.[target_workspace_id],
        tw.[target_workspace_name],
        tw.[target_lakehouse_id],
        tw.[target_lakehouse_name]
    FROM [dbo].[extract] e
    CROSS JOIN [dbo].[target_workspace] tw
    WHERE e.[status] = 'VALIDATED'
      AND e.[is_latest_for_period] = 1
      AND tw.[enabled] = 1
      -- ── Four filter dimensions (AND-combined, NULL = no restriction) ──
      AND (tw.[domain_filter]      IS NULL OR tw.[domain_filter]      = e.[domain_code])
      AND (tw.[instance_filter]    IS NULL OR tw.[instance_filter]    = e.[instance_code])
      AND (tw.[period_type_filter] IS NULL OR tw.[period_type_filter] = e.[period_type])
      AND (tw.[arrived_after]      IS NULL OR e.[arrived_at]         >= tw.[arrived_after])
      -- ── Optional caller filter ──
      AND (@domain_code IS NULL OR e.[domain_code] = @domain_code)
      -- ── No existing active push_job for this extract + workspace ──
      AND NOT EXISTS (
          SELECT 1 FROM [dbo].[push_job] pj
          WHERE pj.[extract_id] = e.[extract_id]
            AND pj.[target_workspace_id] = tw.[target_workspace_id]
            AND pj.[status] IN ('PENDING', 'RUNNING', 'SUCCESS')
      )
    ORDER BY e.[arrived_at] ASC;
END;

GO

