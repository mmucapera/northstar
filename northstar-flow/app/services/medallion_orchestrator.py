"""
Medallion Orchestrator Service

Background service that continuously scans for medallion pipeline work:
1. Checks for B2S-ready batches (grace period expired, no running B2S)
2. Triggers B2S pipelines sequentially per domain+workspace
3. Polls running B2S jobs for completion
4. When all B2S complete for a domain+workspace, triggers S2G
5. Polls running S2G jobs for completion

The orchestrator is the SINGLE BRAIN — pipelines just do data work.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List

from app.config import settings
from app.services.fabric_pipeline import trigger_pipeline, poll_pipeline_status

logger = logging.getLogger(__name__)


class MedallionOrchestratorService:
    """Background service that orchestrates B2S and S2G pipeline execution."""

    _task: Optional[asyncio.Task] = None
    _running: bool = False

    # Active pipeline jobs being polled: {run_id: job_info_dict}
    _active_b2s_jobs: Dict[str, dict] = {}
    _active_s2g_jobs: Dict[str, dict] = {}

    # Stats
    _scan_cycles: int = 0
    _b2s_triggered: int = 0
    _b2s_completed: int = 0
    _b2s_failed: int = 0
    _s2g_triggered: int = 0
    _s2g_completed: int = 0
    _s2g_failed: int = 0
    _late_arrivals_auto_replayed: int = 0
    _late_arrivals_alerted: int = 0
    _errors: int = 0
    _started_at: Optional[datetime] = None
    _last_scan_at: Optional[datetime] = None

    @classmethod
    async def start(cls) -> bool:
        """Start the medallion orchestration loop. Returns False if already running."""
        if cls._running and cls._task and not cls._task.done():
            return False

        cls._running = True
        cls._scan_cycles = 0
        cls._b2s_triggered = 0
        cls._b2s_completed = 0
        cls._b2s_failed = 0
        cls._s2g_triggered = 0
        cls._s2g_completed = 0
        cls._s2g_failed = 0
        cls._late_arrivals_auto_replayed = 0
        cls._late_arrivals_alerted = 0
        cls._errors = 0
        cls._active_b2s_jobs = {}
        cls._active_s2g_jobs = {}
        cls._started_at = datetime.now(timezone.utc)
        cls._last_scan_at = None

        # Recover in-flight jobs from DB before starting the loop
        await cls._recover_in_flight_jobs()

        cls._task = asyncio.create_task(cls._orchestration_loop())
        logger.info("Medallion orchestrator started")
        return True

    @classmethod
    async def stop(cls):
        """Stop the orchestration loop gracefully."""
        if not cls._running:
            return

        cls._running = False
        if cls._task:
            cls._task.cancel()
            try:
                await cls._task
            except asyncio.CancelledError:
                pass

        logger.info("Medallion orchestrator stopped")

    @classmethod
    def get_status(cls) -> dict:
        """Return current orchestrator status."""
        elapsed = 0.0
        if cls._started_at and cls._running:
            elapsed = (datetime.now(timezone.utc) - cls._started_at).total_seconds()

        return {
            "is_running": cls._running and cls._task is not None and not cls._task.done(),
            "scan_cycles": cls._scan_cycles,
            "b2s_triggered": cls._b2s_triggered,
            "b2s_completed": cls._b2s_completed,
            "b2s_failed": cls._b2s_failed,
            "s2g_triggered": cls._s2g_triggered,
            "s2g_completed": cls._s2g_completed,
            "s2g_failed": cls._s2g_failed,
            "late_arrivals_auto_replayed": cls._late_arrivals_auto_replayed,
            "late_arrivals_alerted": cls._late_arrivals_alerted,
            "errors": cls._errors,
            "active_b2s_jobs": len(cls._active_b2s_jobs),
            "active_s2g_jobs": len(cls._active_s2g_jobs),
            "elapsed_seconds": round(elapsed, 1),
            "started_at": cls._started_at.isoformat() if cls._started_at else None,
            "last_scan_at": cls._last_scan_at.isoformat() if cls._last_scan_at else None,
            "grace_period_minutes": settings.ins_orch_b2s_grace_period_minutes,
            "pipeline_poll_interval_seconds": settings.ins_orch_pipeline_poll_interval_seconds,
            "late_arrival_threshold_hours": settings.ins_orch_late_arrival_threshold_hours,
        }

    # ------------------------------------------------------------------
    # Startup recovery — re-populate in-memory dicts from DB
    # ------------------------------------------------------------------

    @classmethod
    async def _recover_in_flight_jobs(cls):
        """
        On startup, query medallion_sync for rows stuck in RUNNING (B2S)
        or PROCESSING (S2G). Re-add them to the in-memory tracking dicts
        so the poll loop can check their actual Fabric status and update
        the DB accordingly.
        """
        from app.database import db

        if not db:
            return

        try:
            # Recover B2S RUNNING jobs
            b2s_rows = db.execute_query("""
                SELECT
                    ms.[sync_id],
                    ms.[extract_id],
                    ms.[b2s_run_id],
                    ms.[target_workspace_id],
                    ms.[b2s_started_at],
                    e.[domain_code],
                    tw.[b2s_pipeline_id]
                FROM [dbo].[medallion_sync] ms
                INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
                INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
                WHERE ms.[b2s_status] = 'RUNNING'
                  AND ms.[b2s_run_id] IS NOT NULL
            """)

            for row in b2s_rows:
                job_id = row["b2s_run_id"]
                cls._active_b2s_jobs[job_id] = {
                    "job_instance_id": job_id,
                    "sync_id": row["sync_id"],
                    "extract_id": row["extract_id"],
                    "domain_code": row["domain_code"],
                    "target_workspace_id": row["target_workspace_id"],
                    "pipeline_id": row["b2s_pipeline_id"],
                    "triggered_at": row.get("b2s_started_at") or datetime.now(timezone.utc),
                }

            logger.info(
                "Recovered %d in-flight B2S job(s) from DB", len(b2s_rows),
            )

            # Recover S2G PROCESSING jobs (grouped by run_id)
            s2g_rows = db.execute_query("""
                SELECT
                    ms.[s2g_run_id],
                    ms.[target_workspace_id],
                    ms.[s2g_started_at],
                    e.[domain_code],
                    tw.[s2g_pipeline_id],
                    COUNT(*) AS rows_claimed
                FROM [dbo].[medallion_sync] ms
                INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
                INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
                WHERE ms.[s2g_status] = 'PROCESSING'
                  AND ms.[s2g_run_id] IS NOT NULL
                GROUP BY ms.[s2g_run_id], ms.[target_workspace_id],
                         ms.[s2g_started_at], e.[domain_code], tw.[s2g_pipeline_id]
            """)

            for row in s2g_rows:
                job_id = row["s2g_run_id"]
                cls._active_s2g_jobs[job_id] = {
                    "job_instance_id": job_id,
                    "domain_code": row["domain_code"],
                    "target_workspace_id": row["target_workspace_id"],
                    "pipeline_id": row["s2g_pipeline_id"],
                    "rows_claimed": row["rows_claimed"],
                    "triggered_at": row.get("s2g_started_at") or datetime.now(timezone.utc),
                }

            logger.info(
                    "Recovered %d in-flight S2G job(s) from DB", len(s2g_rows),
                )

        except Exception as e:
            logger.warning("Failed to recover in-flight jobs (non-fatal): %s", e)

        logger.info(
            "In-flight job recovery complete: %d B2S, %d S2G tracked",
            len(cls._active_b2s_jobs), len(cls._active_s2g_jobs),
        )

    @classmethod
    async def _reconcile_orphaned_jobs(cls):
        """Re-scan the DB for RUNNING/PROCESSING jobs not currently tracked in memory.

        Protects against jobs becoming orphaned after a restart where
        _recover_in_flight_jobs failed, or after any in-memory state loss.
        """
        from app.database import db

        if not db:
            return

        try:
            b2s_rows = db.execute_query("""
                SELECT
                    ms.[sync_id],
                    ms.[extract_id],
                    ms.[b2s_run_id],
                    ms.[target_workspace_id],
                    ms.[b2s_started_at],
                    e.[domain_code],
                    tw.[b2s_pipeline_id]
                FROM [dbo].[medallion_sync] ms
                INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
                INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
                WHERE ms.[b2s_status] = 'RUNNING'
                  AND ms.[b2s_run_id] IS NOT NULL
            """)

            orphaned_b2s = 0
            for row in b2s_rows:
                job_id = row["b2s_run_id"]
                if job_id not in cls._active_b2s_jobs:
                    cls._active_b2s_jobs[job_id] = {
                        "job_instance_id": job_id,
                        "sync_id": row["sync_id"],
                        "extract_id": row["extract_id"],
                        "domain_code": row["domain_code"],
                        "target_workspace_id": row["target_workspace_id"],
                        "pipeline_id": row["b2s_pipeline_id"],
                        "triggered_at": row.get("b2s_started_at") or datetime.now(timezone.utc),
                    }
                    orphaned_b2s += 1
                    logger.warning(
                        "Reconcile: re-added orphaned B2S job %s (extract=%d domain=%s)",
                        job_id, row["extract_id"], row["domain_code"],
                    )

            s2g_rows = db.execute_query("""
                SELECT
                    ms.[s2g_run_id],
                    ms.[target_workspace_id],
                    ms.[s2g_started_at],
                    e.[domain_code],
                    tw.[s2g_pipeline_id],
                    COUNT(*) AS rows_claimed
                FROM [dbo].[medallion_sync] ms
                INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
                INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
                WHERE ms.[s2g_status] = 'PROCESSING'
                  AND ms.[s2g_run_id] IS NOT NULL
                GROUP BY ms.[s2g_run_id], ms.[target_workspace_id],
                         ms.[s2g_started_at], e.[domain_code], tw.[s2g_pipeline_id]
            """)

            orphaned_s2g = 0
            for row in s2g_rows:
                job_id = row["s2g_run_id"]
                if job_id not in cls._active_s2g_jobs:
                    cls._active_s2g_jobs[job_id] = {
                        "job_instance_id": job_id,
                        "domain_code": row["domain_code"],
                        "target_workspace_id": row["target_workspace_id"],
                        "pipeline_id": row["s2g_pipeline_id"],
                        "rows_claimed": row["rows_claimed"],
                        "triggered_at": row.get("s2g_started_at") or datetime.now(timezone.utc),
                    }
                    orphaned_s2g += 1
                    logger.warning(
                        "Reconcile: re-added orphaned S2G job %s (domain=%s)",
                        job_id, row["domain_code"],
                    )

        except Exception as e:
            logger.warning("Reconcile orphaned jobs failed (non-fatal): %s", e)

    # ------------------------------------------------------------------
    # Main orchestration loop
    # ------------------------------------------------------------------

    @classmethod
    async def _orchestration_loop(cls):
        scan_interval = settings.ins_orch_medallion_scan_interval_seconds
        poll_interval = settings.ins_orch_pipeline_poll_interval_seconds
        late_arrival_interval = settings.ins_orch_late_arrival_check_interval_seconds
        logger.info(
            "Orchestration loop started (scan=%ds, poll=%ds, grace=%dm, late_arrival_check=%ds)",
            scan_interval, poll_interval,
            settings.ins_orch_b2s_grace_period_minutes,
            late_arrival_interval,
        )

        last_poll_time = datetime.min.replace(tzinfo=timezone.utc)
        last_late_arrival_check = datetime.min.replace(tzinfo=timezone.utc)
        last_reconcile_time = datetime.min.replace(tzinfo=timezone.utc)
        reconcile_interval = max(poll_interval, 300)  # at most every 5 min

        while cls._running:
            try:
                now = datetime.now(timezone.utc)
                cls._scan_cycles += 1
                cls._last_scan_at = now

                # ── 0. Reconcile orphaned jobs (DB says RUNNING but not tracked in-memory) ──
                if (now - last_reconcile_time).total_seconds() >= reconcile_interval:
                    await cls._reconcile_orphaned_jobs()
                    last_reconcile_time = now

                # ── 1. Poll active pipeline jobs (at poll_interval) ──
                if (now - last_poll_time).total_seconds() >= poll_interval:
                    await cls._poll_active_jobs()
                    last_poll_time = now

                # ── 2. Check for B2S-ready batches ──
                await cls._check_b2s_ready()

                # ── 3. Check for S2G-ready domains ──
                await cls._check_s2g_ready()

                # ── 4. Check for late arrivals eligible for auto-replay ──
                if (now - last_late_arrival_check).total_seconds() >= late_arrival_interval:
                    await cls._check_late_arrivals()
                    last_late_arrival_check = now

                await asyncio.sleep(scan_interval)

            except asyncio.CancelledError:
                logger.info("Orchestration loop cancelled")
                break
            except Exception as e:
                cls._errors += 1
                logger.error("Error in orchestration loop: %s", e, exc_info=True)
                await asyncio.sleep(scan_interval)

    # ------------------------------------------------------------------
    # B2S batch detection and triggering
    # ------------------------------------------------------------------

    @classmethod
    async def _check_b2s_ready(cls):
        """Query for B2S-ready batches and trigger pipelines."""
        from app.database import db

        if not db:
            return

        try:
            result = db.call_sp("get_b2s_pending_batches", params={})
            batches = result.get("result", [])

            if not batches:
                return

            grace_minutes = settings.ins_orch_b2s_grace_period_minutes
            now = datetime.now(timezone.utc)

            for batch in batches:
                domain = batch["domain_code"]
                ws_id = batch["target_workspace_id"]
                ws_name = batch.get("target_workspace_name", ws_id)
                pipeline_id = batch.get("b2s_pipeline_id")
                latest_push = batch.get("latest_bronze_loaded_at")
                pending_count = batch.get("pending_extract_count", 0)

                # Skip if no pipeline configured
                if not pipeline_id:
                    continue

                # Skip if already have an active B2S job for this domain+workspace
                active_key = f"{domain}:{ws_id}"
                if any(
                    j.get("domain_code") == domain
                    and j.get("target_workspace_id") == ws_id
                    for j in cls._active_b2s_jobs.values()
                ):
                    continue

                # Check grace period
                if latest_push:
                    if hasattr(latest_push, "tzinfo") and latest_push.tzinfo is None:
                        latest_push = latest_push.replace(tzinfo=timezone.utc)
                    elapsed = (now - latest_push).total_seconds() / 60
                    if elapsed < grace_minutes:
                        logger.debug(
                            "B2S grace period not expired for %s/%s (%.1f/%.0f min)",
                            domain, ws_name, elapsed, grace_minutes,
                        )
                        continue

                # Grace period expired — get the next extract to process
                logger.info(
                    "B2S ready: domain=%s workspace=%s pending=%d — fetching queue",
                    domain, ws_name, pending_count,
                )
                await cls._trigger_next_b2s(domain, ws_id, pipeline_id)

        except Exception as e:
            cls._errors += 1
            logger.error("Error checking B2S readiness: %s", e, exc_info=True)

    @classmethod
    async def _trigger_next_b2s(cls, domain: str, ws_id: str, pipeline_id: str):
        """Get the next extract from the B2S queue and trigger the pipeline."""
        from app.database import db

        if not db:
            return

        try:
            result = db.call_sp(
                "get_b2s_queue",
                params={
                    "domain_code": domain,
                    "target_workspace_id": ws_id,
                },
            )
            queue = result.get("result", [])

            if not queue:
                logger.debug("B2S queue empty for %s/%s", domain, ws_id)
                return

            item = queue[0]
            sync_id = item["sync_id"]
            extract_id = item["extract_id"]
            bronze_path = item.get("bronze_folder_path", "")
            extraction_date = item.get("extraction_date")
            source_file_name = item.get("source_file_name", "")
            if source_file_name and source_file_name.endswith(".zip"):
                source_file_name = source_file_name[:-4]

            # Trigger the pipeline
            pipeline_params = {
                "extract_id": str(extract_id),
                "domain_code": domain,
                "bronze_folder_path": bronze_path,
                "extraction_date": extraction_date.isoformat() if extraction_date else "",
                "source_file_name": source_file_name,
            }

            trigger_result = await asyncio.to_thread(
                trigger_pipeline, ws_id, pipeline_id, pipeline_params
            )

            job_id = trigger_result.get("job_instance_id")
            if not job_id:
                logger.error("Pipeline trigger returned no job_instance_id")
                return

            # Atomically claim the sync row
            claim_result = db.call_sp(
                "start_medallion_run",
                params={
                    "run_type": "B2S",
                    "run_id": job_id,
                    "sync_id": sync_id,
                },
                output_params=["rows_affected"],
            )

            rows_claimed = claim_result["output"].get("rows_affected", 0)
            if rows_claimed == 0:
                logger.warning(
                    "B2S claim failed for sync_id=%d (already claimed?)", sync_id,
                )
                return

            # Track the active job
            cls._active_b2s_jobs[job_id] = {
                "job_instance_id": job_id,
                "sync_id": sync_id,
                "extract_id": extract_id,
                "domain_code": domain,
                "target_workspace_id": ws_id,
                "pipeline_id": pipeline_id,
                "triggered_at": datetime.now(timezone.utc),
            }
            cls._b2s_triggered += 1

            logger.info(
                "B2S triggered: extract=%d domain=%s workspace=%s job=%s",
                extract_id, domain, ws_id, job_id,
            )

        except Exception as e:
            cls._errors += 1
            logger.error("Error triggering B2S for %s/%s: %s", domain, ws_id, e, exc_info=True)

    # ------------------------------------------------------------------
    # S2G detection and triggering
    # ------------------------------------------------------------------

    @classmethod
    async def _check_s2g_ready(cls):
        """Query for domains where all B2S are done and trigger S2G."""
        from app.database import db

        if not db:
            return

        try:
            result = db.call_sp("get_s2g_ready", params={})
            ready = result.get("result", [])

            if not ready:
                return

            for item in ready:
                domain = item["domain_code"]
                ws_id = item["target_workspace_id"]
                ws_name = item.get("target_workspace_name", ws_id)
                pipeline_id = item.get("s2g_pipeline_id")

                if not pipeline_id:
                    continue

                # Skip if already have an active S2G job for this domain+workspace
                if any(
                    j.get("domain_code") == domain
                    and j.get("target_workspace_id") == ws_id
                    for j in cls._active_s2g_jobs.values()
                ):
                    continue

                logger.info(
                    "S2G ready: domain=%s workspace=%s extracts=%d — triggering",
                    domain, ws_name, item.get("extract_count", 0),
                )
                await cls._trigger_s2g(domain, ws_id, pipeline_id)

        except Exception as e:
            cls._errors += 1
            logger.error("Error checking S2G readiness: %s", e, exc_info=True)

    @classmethod
    async def _trigger_s2g(cls, domain: str, ws_id: str, pipeline_id: str):
        """Trigger an S2G pipeline for a domain+workspace."""
        from app.database import db

        if not db:
            return

        try:
            pipeline_params = {"domain_code": domain}

            trigger_result = await asyncio.to_thread(
                trigger_pipeline, ws_id, pipeline_id, pipeline_params
            )

            job_id = trigger_result.get("job_instance_id")
            if not job_id:
                logger.error("S2G pipeline trigger returned no job_instance_id")
                return

            # Atomically claim all sync rows for this domain+workspace
            claim_result = db.call_sp(
                "start_medallion_run",
                params={
                    "run_type": "S2G",
                    "run_id": job_id,
                    "domain_code": domain,
                    "target_workspace_id": ws_id,
                },
                output_params=["rows_affected"],
            )

            rows_claimed = claim_result["output"].get("rows_affected", 0)
            if rows_claimed == 0:
                logger.warning(
                    "S2G claim failed for %s/%s (already claimed?)", domain, ws_id,
                )
                return

            # Track the active job
            cls._active_s2g_jobs[job_id] = {
                "job_instance_id": job_id,
                "domain_code": domain,
                "target_workspace_id": ws_id,
                "pipeline_id": pipeline_id,
                "rows_claimed": rows_claimed,
                "triggered_at": datetime.now(timezone.utc),
            }
            cls._s2g_triggered += 1

            logger.info(
                "S2G triggered: domain=%s workspace=%s job=%s rows=%d",
                domain, ws_id, job_id, rows_claimed,
            )

        except Exception as e:
            cls._errors += 1
            logger.error("Error triggering S2G for %s/%s: %s", domain, ws_id, e, exc_info=True)

    # ------------------------------------------------------------------
    # Late arrival auto-replay
    # ------------------------------------------------------------------

    @classmethod
    async def _check_late_arrivals(cls):
        """
        Scan for extracts flagged as late arrivals and either:
        - Auto-replay (if within threshold) via reset_late_arrival_batch SP
        - Log alert (if beyond threshold and not yet alerted)
        """
        from app.database import db

        if not db:
            return

        try:
            result = db.call_sp(
                "get_late_arrivals_pending",
                params={
                    "default_threshold_hours": settings.ins_orch_late_arrival_threshold_hours,
                },
            )
            rows = result.get("result", [])

            if not rows:
                return

            # Group by scope-aware key for batch-level decisions
            batches: Dict[tuple, List[dict]] = {}
            for row in rows:
                scope = row.get("late_arrival_scope_field", "package_def")
                if scope == "extraction_def":
                    key = (row["domain_code"], row.get("extraction_def") or "", "", scope)
                elif scope == "both":
                    key = (row["domain_code"], row.get("extraction_def") or "", row.get("package_def") or "", scope)
                else:  # "package_def" (default)
                    key = (row["domain_code"], "", row.get("package_def") or "", scope)
                batches.setdefault(key, []).append(row)

            for (domain_code, extraction_def_val, package_def_val, scope), group in batches.items():
                # Check if any in the group are eligible for auto-replay
                eligible = [r for r in group if r.get("eligible_for_auto_replay") == 1]
                beyond_threshold = [
                    r for r in group
                    if r.get("eligible_for_auto_replay") == 0
                    and r.get("late_arrival_alerted_at") is None
                ]

                if eligible:
                    # Auto-replay: call reset_late_arrival_batch with the threshold as lookback
                    threshold = eligible[0].get("threshold_hours", settings.ins_orch_late_arrival_threshold_hours)
                    try:
                        replay_result = db.call_sp(
                            "reset_late_arrival_batch",
                            params={
                                "domain_code": domain_code,
                                "lookback_hours": threshold,
                                "extraction_def": extraction_def_val or None,
                                "package_def": package_def_val or None,
                            },
                            output_params=["extracts_reset", "syncs_reset"],
                        )
                        extracts_reset = replay_result["output"].get("extracts_reset", 0)
                        syncs_reset = replay_result["output"].get("syncs_reset", 0)
                        cls._late_arrivals_auto_replayed += extracts_reset

                        logger.info(
                            "Late arrival auto-replay: domain=%s scope=%s "
                            "extraction_def=%s package_def=%s extracts_reset=%d syncs_reset=%d lookback=%dh",
                            domain_code, scope,
                            extraction_def_val or "(all)", package_def_val or "(all)",
                            extracts_reset, syncs_reset, threshold,
                        )
                    except Exception as e:
                        cls._errors += 1
                        logger.error(
                            "Failed auto-replay for %s/%s/%s: %s",
                            domain_code, extraction_def_val, package_def_val, e,
                        )

                if beyond_threshold:
                    # Alert: log warning and mark alerted_at to prevent repeat alerts
                    extract_ids = [r["extract_id"] for r in beyond_threshold]
                    logger.warning(
                        "Late arrival BEYOND threshold: domain=%s scope=%s "
                        "extraction_def=%s package_def=%s extract_ids=%s — requires manual intervention",
                        domain_code, scope, extraction_def_val or "(all)", package_def_val or "(all)", extract_ids,
                    )

                    # Mark as alerted
                    placeholders = ",".join("?" for _ in extract_ids)
                    db.execute_query(
                        f"UPDATE [dbo].[extract] "
                        f"SET [late_arrival_alerted_at] = SYSUTCDATETIME() "
                        f"WHERE [extract_id] IN ({placeholders})",
                        tuple(extract_ids),
                    )
                    cls._late_arrivals_alerted += len(extract_ids)

        except Exception as e:
            cls._errors += 1
            logger.error("Error checking late arrivals: %s", e, exc_info=True)

    # ------------------------------------------------------------------
    # Poll active pipeline jobs
    # ------------------------------------------------------------------

    @classmethod
    async def _poll_active_jobs(cls):
        """Poll all active B2S and S2G jobs for completion."""
        # Poll B2S jobs
        completed_b2s = []
        for job_id, job_info in list(cls._active_b2s_jobs.items()):
            try:
                status = await asyncio.to_thread(
                    poll_pipeline_status,
                    job_info["target_workspace_id"],
                    job_info["pipeline_id"],
                    job_id,
                )
                pipeline_status = status.get("status", "Unknown")

                if pipeline_status == "Completed":
                    await cls._complete_b2s(job_id, job_info, "SUCCESS")
                    completed_b2s.append(job_id)
                elif pipeline_status in ("Failed", "Cancelled"):
                    error = status.get("failure_reason", f"Pipeline {pipeline_status}")
                    await cls._complete_b2s(job_id, job_info, "FAILED", error)
                    completed_b2s.append(job_id)
                # else: still InProgress — keep polling

            except Exception as e:
                logger.error("Error polling B2S job %s: %s", job_id, e)

        for job_id in completed_b2s:
            cls._active_b2s_jobs.pop(job_id, None)

        # Poll S2G jobs
        completed_s2g = []
        for job_id, job_info in list(cls._active_s2g_jobs.items()):
            try:
                status = await asyncio.to_thread(
                    poll_pipeline_status,
                    job_info["target_workspace_id"],
                    job_info["pipeline_id"],
                    job_id,
                )
                pipeline_status = status.get("status", "Unknown")

                if pipeline_status == "Completed":
                    await cls._complete_s2g(job_id, job_info, "SUCCESS")
                    completed_s2g.append(job_id)
                elif pipeline_status in ("Failed", "Cancelled"):
                    error = status.get("failure_reason", f"Pipeline {pipeline_status}")
                    await cls._complete_s2g(job_id, job_info, "FAILED", error)
                    completed_s2g.append(job_id)

            except Exception as e:
                logger.error("Error polling S2G job %s: %s", job_id, e)

        for job_id in completed_s2g:
            cls._active_s2g_jobs.pop(job_id, None)

    @classmethod
    async def _complete_b2s(
        cls, job_id: str, job_info: dict, status: str, error: Optional[str] = None
    ):
        """Mark a B2S run as complete in the database."""
        from app.database import db

        if not db:
            return

        try:
            db.call_sp(
                "complete_medallion_run",
                params={
                    "run_type": "B2S",
                    "run_id": job_id,
                    "status": status,
                    "sync_id": job_info["sync_id"],
                    "error_message": error,
                },
                output_params=["rows_affected"],
            )

            if status == "SUCCESS":
                cls._b2s_completed += 1
                logger.info(
                    "B2S completed: extract=%d domain=%s workspace=%s",
                    job_info["extract_id"],
                    job_info["domain_code"],
                    job_info["target_workspace_id"],
                )

                # Immediately check if there's another B2S to process
                await cls._trigger_next_b2s(
                    job_info["domain_code"],
                    job_info["target_workspace_id"],
                    job_info["pipeline_id"],
                )
            else:
                cls._b2s_failed += 1
                logger.error(
                    "B2S failed: extract=%d domain=%s workspace=%s error=%s",
                    job_info["extract_id"],
                    job_info["domain_code"],
                    job_info["target_workspace_id"],
                    error,
                )

        except Exception as e:
            cls._errors += 1
            logger.error("Error completing B2S %s: %s", job_id, e, exc_info=True)

    @classmethod
    async def _complete_s2g(
        cls, job_id: str, job_info: dict, status: str, error: Optional[str] = None
    ):
        """Mark an S2G run as complete in the database."""
        from app.database import db

        if not db:
            return

        try:
            db.call_sp(
                "complete_medallion_run",
                params={
                    "run_type": "S2G",
                    "run_id": job_id,
                    "status": status,
                    "error_message": error,
                },
                output_params=["rows_affected"],
            )

            if status == "SUCCESS":
                cls._s2g_completed += 1
                logger.info(
                    "S2G completed: domain=%s workspace=%s",
                    job_info["domain_code"],
                    job_info["target_workspace_id"],
                )
            else:
                cls._s2g_failed += 1
                logger.error(
                    "S2G failed: domain=%s workspace=%s error=%s",
                    job_info["domain_code"],
                    job_info["target_workspace_id"],
                    error,
                )

        except Exception as e:
            cls._errors += 1
            logger.error("Error completing S2G %s: %s", job_id, e, exc_info=True)
