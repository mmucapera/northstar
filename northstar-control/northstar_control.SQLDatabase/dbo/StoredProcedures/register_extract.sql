

-- =============================================================================
-- STORED PROCEDURES
-- =============================================================================

-- -----------------------------------------------------------------------------
-- register_extract
-- -----------------------------------------------------------------------------
CREATE   PROCEDURE [dbo].[register_extract]
    @folder_path        NVARCHAR(500),
    @domain_code        NVARCHAR(20),
    @source_code        NVARCHAR(50),
    @folder_name        NVARCHAR(200),
    @period_year        INT,
    @period_month       INT,
    @period_day         INT = NULL,
    @period_label       NVARCHAR(50) = NULL,
    @file_count         INT = NULL,
    @total_size_bytes   BIGINT = NULL,
    @source_file_name   NVARCHAR(500) = NULL,
    @source_file_format NVARCHAR(10) = NULL,
    @instance_code      NVARCHAR(50) = NULL,
    @report_name        NVARCHAR(100) = NULL,
    @extract_id         INT OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    BEGIN TRY
        BEGIN TRANSACTION;

        -- Remap alias domain codes to their canonical equivalents
        SET @domain_code = CASE @domain_code
            WHEN 'FCT' THEN 'DP'
            WHEN 'OPR' THEN 'SP'
            ELSE @domain_code
        END;

        -- Derive folder_name from source_file_name when caller passes NULL or empty string
        -- (e.g. files dropped at container root with no subfolder)
        IF (@folder_name IS NULL OR @folder_name = '') AND @source_file_name IS NOT NULL
        BEGIN
            SET @folder_name = CASE
                WHEN CHARINDEX('.', @source_file_name) > 0
                    THEN LEFT(@source_file_name, LEN(@source_file_name) - CHARINDEX('.', REVERSE(@source_file_name)))
                ELSE @source_file_name
            END;
        END

        -- Idempotency: if an extract with this source_file_name already exists, return it
        IF @source_file_name IS NOT NULL
        BEGIN
            SELECT @extract_id = [extract_id]
            FROM [dbo].[extract]
            WHERE [source_file_name] = @source_file_name;

            IF @extract_id IS NOT NULL
            BEGIN
                COMMIT TRANSACTION;
                RETURN;
            END
        END

        -- Find existing latest extract for same period
        DECLARE @old_extract_id INT;
        SELECT TOP 1 @old_extract_id = [extract_id]
        FROM [dbo].[extract]
        WHERE [domain_code] = @domain_code
          AND [period_year] = @period_year
          AND [period_month] = @period_month
          AND [is_latest_for_period] = 1;

        -- Insert new extract
        INSERT INTO [dbo].[extract] (
            [domain_code], [source_code], [folder_path], [folder_name],
            [period_year], [period_month], [period_day], [period_label],
            [actual_file_count], [total_size_bytes],
            [source_file_name], [source_file_format], [instance_code], [report_name],
            [status], [is_latest_for_period], [has_duplicate_period]
        )
        VALUES (
            @domain_code, @source_code, @folder_path, @folder_name,
            @period_year, @period_month, @period_day,
            COALESCE(@period_label, CONCAT(@period_year, '-', RIGHT('0' + CAST(@period_month AS VARCHAR(2)), 2))),
            @file_count, @total_size_bytes,
            @source_file_name, @source_file_format, @instance_code, @report_name,
            'NEW', 1,
            CASE WHEN @old_extract_id IS NOT NULL THEN 1 ELSE 0 END
        );

        SET @extract_id = SCOPE_IDENTITY();

        -- Supersede old extract if exists
        IF @old_extract_id IS NOT NULL
        BEGIN
            UPDATE [dbo].[extract]
            SET [is_latest_for_period] = 0,
                [superseded_by_id] = @extract_id,
                [has_duplicate_period] = 1,
                [updated_at] = SYSUTCDATETIME()
            WHERE [extract_id] = @old_extract_id;
        END

        COMMIT TRANSACTION;
    END TRY
    BEGIN CATCH
        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;
        THROW;
    END CATCH
END;

GO

