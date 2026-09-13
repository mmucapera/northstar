-- =============================================================================
-- INS Orchestrator — Add source_id to poller_state (multi-source migration)
-- =============================================================================
-- Run this to upgrade poller_state for multi-source ADLS polling.
-- Existing rows get source_id = 'default'. The unique constraint changes
-- from (file_name) to (file_name, source_id) so the same file from
-- different sources creates separate rows.
-- =============================================================================

-- Step 1: Add the column (if not exists)
IF NOT EXISTS (
    SELECT 1 FROM sys.columns
    WHERE object_id = OBJECT_ID('dbo.poller_state')
      AND name = 'source_id'
)
BEGIN
    ALTER TABLE [dbo].[poller_state]
    ADD [source_id] NVARCHAR(50) NOT NULL DEFAULT 'default';

    PRINT 'Added column: poller_state.source_id';
END
ELSE
    PRINT 'Column poller_state.source_id already exists — skipped';
GO

-- Step 2: Drop old unique constraint on file_name alone
IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID('dbo.poller_state')
      AND name = 'uq_poller_state_file_name'
)
BEGIN
    ALTER TABLE [dbo].[poller_state]
    DROP CONSTRAINT [uq_poller_state_file_name];

    PRINT 'Dropped old constraint: uq_poller_state_file_name';
END
ELSE
    PRINT 'Old constraint uq_poller_state_file_name not found — skipped';
GO

-- Step 3: Add new composite unique constraint
IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID('dbo.poller_state')
      AND name = 'uq_poller_state_file_source'
)
BEGIN
    ALTER TABLE [dbo].[poller_state]
    ADD CONSTRAINT [uq_poller_state_file_source]
    UNIQUE ([file_name], [source_id]);

    PRINT 'Added constraint: uq_poller_state_file_source (file_name, source_id)';
END
ELSE
    PRINT 'Constraint uq_poller_state_file_source already exists — skipped';
GO

PRINT '';
PRINT '============================================================';
PRINT '  Migration complete: poller_state supports multi-source.';
PRINT '  Existing rows have source_id = ''default''.';
PRINT '============================================================';
