-- =============================================================================
-- INS Orchestrator — Clean / Reset Transactional Data
-- =============================================================================
-- Empties all transactional data while preserving configuration tables
-- (domain_config, target_workspace).
--
-- USE WITH CAUTION — this deletes all extract, push, sync, and poller data.
-- =============================================================================

-- ─────────────────────────────────────────────────────────────────────────────
-- Delete in FK-safe order (children first, parents last)
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Job logs (references push_job + extract)
DELETE FROM [dbo].[job_log];
PRINT 'Cleared: dbo.job_log';

-- 2. Workspace signals (references target_workspace — keep workspace config)
DELETE FROM [dbo].[workspace_signal];
PRINT 'Cleared: dbo.workspace_signal';

-- 3. Medallion sync (references extract)
DELETE FROM [dbo].[medallion_sync];
PRINT 'Cleared: dbo.medallion_sync';

-- 4. Push jobs (references extract)
DELETE FROM [dbo].[push_job];
PRINT 'Cleared: dbo.push_job';

-- 5. Extract files (references extract)
DELETE FROM [dbo].[extract_file];
PRINT 'Cleared: dbo.extract_file';

-- 6. Extracts (references domain_config — keep domain config)
-- Must clear self-referencing FK (superseded_by_id) first
UPDATE [dbo].[extract] SET [superseded_by_id] = NULL WHERE [superseded_by_id] IS NOT NULL;
DELETE FROM [dbo].[extract];
PRINT 'Cleared: dbo.extract';

-- 7. Poller state (no FK dependencies)
-- DELETE FROM [dbo].[poller_state];
-- PRINT 'Cleared: dbo.poller_state';

-- ─────────────────────────────────────────────────────────────────────────────
-- Reset identity seeds
-- ─────────────────────────────────────────────────────────────────────────────
-- Fabric SQL may not support DBCC CHECKIDENT. If these fail, just skip.
BEGIN TRY DBCC CHECKIDENT ('dbo.extract',      RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for extract'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.extract_file',  RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for extract_file'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.push_job',      RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for push_job'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.medallion_sync', RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for medallion_sync'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.job_log',       RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for job_log'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.poller_state',  RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for poller_state'; END CATCH;
BEGIN TRY DBCC CHECKIDENT ('dbo.workspace_signal', RESEED, 0); END TRY BEGIN CATCH PRINT 'RESEED skipped for workspace_signal'; END CATCH;

PRINT '';
PRINT '============================================================';
PRINT '  All transactional data cleared.';
PRINT '  Preserved: dbo.domain_config, dbo.target_workspace';
PRINT '============================================================';
