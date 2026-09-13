-- -----------------------------------------------------------------------------
-- get_late_arrivals_pending
--
-- Returns all extracts flagged as late arrivals (is_late_arrival = 1),
-- along with eligibility info for automatic replay.
--
-- Used by the orchestrator's _check_late_arrivals() step to decide:
--   eligible_for_auto_replay = 1  → auto-replay via reset_late_arrival_batch
--   eligible_for_auto_replay = 0  → log alert (if not already alerted)
--
-- @default_threshold_hours: global fallback when domain_config has no override
-- -----------------------------------------------------------------------------
CREATE PROCEDURE [dbo].[get_late_arrivals_pending]
    @default_threshold_hours INT = 48
AS
BEGIN
    SET NOCOUNT ON;

    SELECT
        e.[extract_id],
        e.[domain_code],
        e.[extraction_def],
        e.[extraction_date],
        e.[package_def],
        e.[arrived_at],
        e.[late_arrival_alerted_at],
        DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME()) AS hours_since_arrival,
        COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours) AS threshold_hours,
        CASE
            WHEN DATEDIFF(HOUR, e.[arrived_at], SYSUTCDATETIME())
                 <= COALESCE(dc.[late_arrival_replay_threshold_hours], @default_threshold_hours)
            THEN 1 ELSE 0
        END AS eligible_for_auto_replay,
        COALESCE(dc.[late_arrival_scope_field], 'package_def') AS late_arrival_scope_field
    FROM [dbo].[extract] e
    INNER JOIN [dbo].[domain_config] dc ON e.[domain_code] = dc.[domain_code]
    WHERE e.[is_late_arrival] = 1
    ORDER BY e.[domain_code], e.[extraction_def], e.[package_def], e.[extraction_date];
END;

GO
