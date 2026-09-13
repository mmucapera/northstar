"""
ADLS Gen2 Poller Service

Polls an external ADLS Gen2 container for new .zip files containing
'FinishedZip' in the filename. Detected files are automatically
registered as extracts via the register_extract stored procedure.

Supports multiple sources — each ADLSPollerService instance polls one
ADLS source independently.
"""

import asyncio
import logging
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Set, List, Dict

from azure.storage.blob import BlobServiceClient
from app.config import ADLSSourceConfig, settings
from app.models.schemas import PollerStatusResponse, PollerFileItem

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Deprecation notice for legacy YAML config
# ---------------------------------------------------------------------------
_LEGACY_YAML = Path(__file__).resolve().parents[2] / "file-naming.yaml"
if _LEGACY_YAML.exists():
    logger.info("file-naming.yaml found but no longer used -- config is now per-source in poller_source table")


class ADLSPollerService:
    """Polls a single ADLS Gen2 source for new zip files.

    Each instance manages its own asyncio task, seen-files set, and stats.
    Use PollerRegistry to manage multiple instances.
    """

    def __init__(self, source_config: ADLSSourceConfig):
        self.source_config = source_config
        self._task: Optional[asyncio.Task] = None
        self._running: bool = False
        self._seen_files: Set[str] = set()

        # Compile filename regex from per-source config
        self._filename_re: Optional[re.Pattern] = None
        if source_config.filename_pattern:
            try:
                self._filename_re = re.compile(source_config.filename_pattern)
            except re.error as e:
                logger.error(f"[{source_config.id}] Invalid filename_pattern: {e}")

        # Cached ADLS client (reused across poll cycles)
        self._container_client = None

        # After initial full scan, track whether we found anything new.
        # If not, back off to a slower interval to avoid hammering ADLS.
        self._initial_scan_done: bool = False

        # Stats
        self._poll_cycles: int = 0
        self._new_files_detected: int = 0
        self._errors: int = 0
        self._started_at: Optional[datetime] = None
        self._last_poll_at: Optional[datetime] = None

    @property
    def source_id(self) -> str:
        return self.source_config.id

    async def start(self) -> bool:
        """Start the polling loop. Returns False if already running."""
        if self._running and self._task and not self._task.done():
            return False

        # Load seen files from DB
        await self._load_seen_files()

        self._running = True
        self._poll_cycles = 0
        self._new_files_detected = 0
        self._errors = 0
        self._started_at = datetime.now(timezone.utc)
        self._last_poll_at = None
        self._task = asyncio.create_task(self._poll_loop())
        logger.info(f"[{self.source_id}] ADLS poller started")
        return True

    async def stop(self):
        """Stop the polling loop gracefully."""
        if not self._running:
            return

        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

        logger.info(f"[{self.source_id}] ADLS poller stopped")

    def get_status(self) -> PollerStatusResponse:
        elapsed = 0.0
        if self._started_at and self._running:
            elapsed = (datetime.now(timezone.utc) - self._started_at).total_seconds()

        return PollerStatusResponse(
            source_id=self.source_id,
            label=self.source_config.label,
            is_running=self._running and self._task is not None and not self._task.done(),
            poll_cycles=self._poll_cycles,
            new_files_detected=self._new_files_detected,
            errors=self._errors,
            elapsed_seconds=round(elapsed, 1),
            started_at=self._started_at,
            last_poll_at=self._last_poll_at,
        )

    def get_detected_files(
        self, limit: int = 50, status_filter: Optional[str] = None
    ) -> List[PollerFileItem]:
        from app.database import db

        if not db:
            return []

        query = (
            "SELECT TOP (?) source_id, file_name, detected_at, status, extract_id, "
            "error_message, blob_last_modified "
            "FROM [dbo].[poller_state] WHERE source_id = ?"
        )
        params: list = [limit, self.source_id]

        if status_filter:
            query += " AND status = ?"
            params.append(status_filter)

        query += " ORDER BY detected_at DESC"

        rows = db.execute_query(query, tuple(params))
        return [PollerFileItem(**row) for row in rows]

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get_container_client(self):
        """Return a cached container client (creates on first call)."""
        if self._container_client is None:
            account_url = f"https://{self.source_config.storage_account}.blob.core.windows.net"
            service_client = BlobServiceClient(
                account_url=account_url,
                credential=self.source_config.sas_token,
            )
            self._container_client = service_client.get_container_client(
                container=self.source_config.container
            )
            logger.info(f"[{self.source_id}] Cached ADLS container client")
        return self._container_client

    async def _load_seen_files(self):
        """Load previously seen file names from poller_state table."""
        from app.database import db

        self._seen_files = set()
        if not db:
            return

        try:
            rows = db.execute_query(
                "SELECT file_name FROM [dbo].[poller_state] WHERE status != 'FAILED' AND source_id = ?",
                (self.source_id,),
            )
            self._seen_files = {row["file_name"] for row in rows}
            logger.info(
                f"[{self.source_id}] Loaded {len(self._seen_files)} previously seen files "
                f"(FAILED files eligible for retry)"
            )
        except Exception as e:
            logger.warning(f"[{self.source_id}] Could not load poller state (table may not exist yet): {e}")

    async def _poll_loop(self):
        base_interval = self.source_config.poll_interval_seconds
        # After the initial full scan finds nothing new, back off to 5x interval
        # to reduce ADLS API calls. Revert to base interval when new files appear.
        idle_multiplier = 5
        current_interval = base_interval
        logger.info(f"[{self.source_id}] Polling loop started (base_interval={base_interval}s)")

        while self._running:
            try:
                new_files = await asyncio.to_thread(self._list_new_zips)
                self._poll_cycles += 1
                self._last_poll_at = datetime.now(timezone.utc)

                if new_files:
                    # Sort by actual upload time (last_modified) so files uploaded
                    # earlier are processed first, regardless of filename alphabetical order.
                    new_files.sort(
                        key=lambda x: x[1].last_modified or datetime.min.replace(tzinfo=timezone.utc)
                    )
                    logger.info(
                        f"[{self.source_id}] Detected {len(new_files)} new file(s) "
                        f"(processing in upload-time order: "
                        f"{', '.join(f for f, _ in new_files)})"
                    )

                    # ── Phase 1: pre-register all extracts ────────────────────────────
                    # Create placeholder medallion_sync rows (b2s_status=NOT_STARTED)
                    # for every file in the batch BEFORE any notebook runs.
                    # This keeps the get_s2g_ready guard from firing S2G after the
                    # first B2S completes — it must wait until all pending rows are done.
                    if len(new_files) > 1:
                        logger.info(
                            f"[{self.source_id}] Pre-registering {len(new_files)} extracts "
                            "to block premature S2G"
                        )
                        for file_name, file_props in new_files:
                            await asyncio.to_thread(
                                self._pre_register_placeholder, file_name, file_props
                            )

                    # ── Phase 2: notebook → B2S per domain (parallel across domains, sequential within) ─
                    # Group files by domain_code: different domains start immediately in
                    # parallel, but files within the same domain are processed one at a time.
                    domain_groups: Dict[str, list] = {}
                    for file_name, file_props in new_files:
                        domain_code = self._parse_filename_segments(file_name)["domain_code"]
                        if domain_code not in domain_groups:
                            domain_groups[domain_code] = []
                        domain_groups[domain_code].append((file_name, file_props))

                    if len(domain_groups) > 1:
                        logger.info(
                            f"[{self.source_id}] {len(new_files)} file(s) span "
                            f"{len(domain_groups)} domain(s) — starting domains in parallel: "
                            f"{list(domain_groups.keys())}"
                        )

                    async def _process_domain_files(domain: str, files: list) -> list:
                        """Process all files for one domain sequentially, then trigger S2G for that domain."""
                        domain_ids = []
                        for fn, fp in files:
                            eid = await asyncio.to_thread(self._process_new_zip, fn, fp)
                            self._new_files_detected += 1
                            if eid is not None:
                                domain_ids.append(eid)
                        if domain_ids:
                            logger.info(
                                f"[{self.source_id}] Domain '{domain}': all B2S done "
                                f"— waiting for S2G on {len(domain_ids)} extract(s)"
                            )
                            await asyncio.to_thread(
                                self._wait_for_all_s2g_completion, domain_ids
                            )
                        return domain_ids

                    domain_results = await asyncio.gather(
                        *[
                            _process_domain_files(domain, files)
                            for domain, files in domain_groups.items()
                        ],
                        return_exceptions=True,
                    )

                    # ── Phase 3: S2G already triggered per-domain inside each task ─
                    for domain_res in domain_results:
                        if isinstance(domain_res, Exception):
                            logger.error(
                                f"[{self.source_id}] Domain processing task failed: {domain_res}",
                                exc_info=domain_res,
                            )
                            self._errors += 1
                    # New files found — keep polling at base interval
                    current_interval = base_interval
                else:
                    if self._initial_scan_done:
                        # Already did a full scan before with no new files — back off
                        current_interval = base_interval * idle_multiplier
                    else:
                        # First full scan completed with no new files
                        self._initial_scan_done = True
                        current_interval = base_interval * idle_multiplier
                        logger.info(
                            f"[{self.source_id}] Initial scan complete "
                            f"({len(self._seen_files)} known files). "
                            f"Backing off to {current_interval}s interval."
                        )

                await asyncio.sleep(current_interval)

            except asyncio.CancelledError:
                logger.info(f"[{self.source_id}] Polling loop cancelled")
                break
            except Exception as e:
                self._errors += 1
                logger.error(f"[{self.source_id}] Error in polling loop: {e}", exc_info=True)
                # Keep running — retry on next cycle
                await asyncio.sleep(base_interval)

    def _list_new_zips(self) -> list:
        """List ADLS container and return new zip files matching filters."""
        try:
            container_client = self._get_container_client()

            folder = self.source_config.folder_path or ""
            blobs = container_client.list_blobs(name_starts_with=folder if folder else None)

            # Compute modified-since cutoff (if configured)
            modified_cutoff = None
            if self.source_config.poll_modified_since_days:
                modified_cutoff = datetime.now(timezone.utc) - timedelta(days=self.source_config.poll_modified_since_days)
                if not self._initial_scan_done:
                    logger.info(f"[{self.source_id}] Filtering blobs modified since {modified_cutoff.isoformat()}")

            new_files = []
            total_scanned = 0
            skipped_seen = 0
            for blob in blobs:
                total_scanned += 1
                name = blob.name
                # Extract just the filename from the full path
                file_name = name.rsplit("/", 1)[-1] if "/" in name else name

                # Check seen-set first (cheapest check)
                if file_name in self._seen_files:
                    skipped_seen += 1
                    continue
                if not file_name.endswith(self.source_config.filename_extension):
                    continue
                if self.source_config.filename_must_contain and self.source_config.filename_must_contain not in file_name:
                    continue
                if modified_cutoff and blob.last_modified and blob.last_modified < modified_cutoff:
                    continue

                new_files.append((file_name, blob))

            if self._initial_scan_done:
                logger.debug(
                    f"[{self.source_id}] Scanned {total_scanned} blobs, "
                    f"{skipped_seen} already seen, {len(new_files)} new"
                )
            else:
                logger.info(
                    f"[{self.source_id}] Initial scan: {total_scanned} blobs, "
                    f"{skipped_seen} already seen, {len(new_files)} new"
                )

            return new_files

        except Exception as e:
            # Invalidate cached client on failure so it reconnects next cycle
            self._container_client = None
            logger.error(f"[{self.source_id}] Failed to list ADLS container: {e}")
            raise

    def _process_new_zip(self, file_name: str, file_props) -> None:
        """Register detected file as an extract, trigger notebook, then record in poller_state.

        Order is critical:
        1.  Attempt register_extract SP call
        1b. Trigger Fabric notebook and wait for completion before returning
        2.  Insert into poller_state with REGISTERED or FAILED status
        3.  Add to in-memory seen set regardless of outcome
        """
        from app.database import db

        extract_id = None
        status = "REGISTERED"
        error_message = None

        # Step 1: attempt register_extract
        if db:
            try:
                # Derive folder path and folder name from the blob's full path
                blob_path = file_props.name if hasattr(file_props, "name") else file_name
                if "/" in blob_path:
                    folder_path = blob_path.rsplit("/", 1)[0]
                    folder_name = folder_path.rsplit("/", 1)[-1] if "/" in folder_path else folder_path
                else:
                    folder_path = ""
                    folder_name = ""

                parsed = self._parse_filename_segments(file_name)

                result = db.call_sp(
                    "register_extract",
                    params={
                        "folder_path": folder_path,
                        "domain_code": parsed["domain_code"],
                        "source_code": self.source_config.source_code,
                        "folder_name": folder_name,
                        "period_year": datetime.now(timezone.utc).year,
                        "period_month": datetime.now(timezone.utc).month,
                        "file_count": 1,
                        "total_size_bytes": (
                            file_props.size
                            if hasattr(file_props, "size")
                            else None
                        ),
                        "source_file_name": file_name,
                        "source_file_format": self.source_config.source_file_format,
                        "instance_code": parsed["instance_code"],
                        "report_name": parsed["report_name"],
                    },
                    output_params=["extract_id"],
                )
                # Try to get extract_id from output or result set
                extract_id = (
                    result["output"].get("extract_id")
                    or (result["result"][0].get("extract_id") if result["result"] else None)
                )
                logger.info(f"[{self.source_id}] Registered extract {extract_id} for file: {file_name}")

                # Step 1b: trigger notebook and wait for it to complete before
                # processing the next file (sequential execution).
                if extract_id:
                    try:
                        from app.services.fabric_notebook import trigger_notebook, wait_for_notebook_completion
                        job_info = trigger_notebook(extract_id, file_name)
                        if job_info and job_info.get("job_instance_id"):
                            workspace_id = settings.ins_orch_fabric_workspace_id
                            notebook_id = settings.ins_orch_notebook_id
                            final_status = wait_for_notebook_completion(
                                workspace_id=workspace_id,
                                notebook_id=notebook_id,
                                job_instance_id=job_info["job_instance_id"],
                                extract_id=extract_id,
                                poll_interval_seconds=settings.ins_orch_notebook_poll_interval_seconds,
                            )
                            if final_status not in ("Completed",):
                                logger.warning(
                                    f"[{self.source_id}] Notebook for extract {extract_id} "
                                    f"finished with status={final_status}"
                                )
                            else:
                                # Bronze loaded — wait for B2S pipeline before
                                # triggering the next extract notebook.
                                self._wait_for_b2s_completion(extract_id)
                    except Exception as nb_err:
                        logger.warning(
                            f"[{self.source_id}] Notebook trigger/wait failed for extract {extract_id} (non-fatal): {nb_err}"
                        )

            except Exception as e:
                status = "FAILED"
                error_message = str(e)[:500]
                logger.error(f"[{self.source_id}] Failed to register extract for {file_name}: {e}")

        # Step 2: upsert poller_state (MERGE handles retries of previously FAILED files)
        if db:
            try:
                now = datetime.now(timezone.utc)
                blob_last_modified = (
                    file_props.last_modified
                    if hasattr(file_props, "last_modified") and file_props.last_modified
                    else None
                )
                db.execute_query(
                    """
                    MERGE [dbo].[poller_state] AS tgt
                    USING (SELECT ? AS file_name, ? AS source_id) AS src
                        ON tgt.file_name = src.file_name AND tgt.source_id = src.source_id
                    WHEN MATCHED THEN
                        UPDATE SET detected_at = ?, status = ?, extract_id = ?,
                                   error_message = ?, blob_last_modified = ?
                    WHEN NOT MATCHED THEN
                        INSERT (file_name, source_id, detected_at, status, extract_id,
                                error_message, blob_last_modified)
                        VALUES (?, ?, ?, ?, ?, ?, ?);
                    """,
                    (
                        file_name, self.source_id,
                        now, status, extract_id, error_message, blob_last_modified,
                        file_name, self.source_id, now, status, extract_id,
                        error_message, blob_last_modified,
                    ),
                )
            except Exception as e:
                logger.warning(f"[{self.source_id}] Failed to write poller_state for {file_name}: {e}")

        # Step 3: only add to seen set if registration succeeded
        if status == "REGISTERED":
            self._seen_files.add(file_name)

        return extract_id

    def _pre_register_placeholder(self, file_name: str, file_props) -> None:
        """Register the extract (idempotent) and pre-create a medallion_sync
        placeholder row (bronze_status=PENDING, b2s_status=NOT_STARTED) for every
        applicable target workspace.

        Must be called for ALL files in a batch before any notebook is triggered,
        so that get_s2g_ready always sees at least one NOT_STARTED row while
        earlier extracts are being processed, preventing premature S2G.
        """
        from app.database import db

        if not db:
            return

        try:
            blob_path = file_props.name if hasattr(file_props, "name") else file_name
            if "/" in blob_path:
                folder_path = blob_path.rsplit("/", 1)[0]
                folder_name = folder_path.rsplit("/", 1)[-1] if "/" in folder_path else folder_path
            else:
                folder_path = ""
                folder_name = ""

            parsed = self._parse_filename_segments(file_name)
            domain_code = parsed["domain_code"]

            result = db.call_sp(
                "register_extract",
                params={
                    "folder_path": folder_path,
                    "domain_code": domain_code,
                    "source_code": self.source_config.source_code,
                    "folder_name": folder_name,
                    "period_year": datetime.now(timezone.utc).year,
                    "period_month": datetime.now(timezone.utc).month,
                    "file_count": 1,
                    "total_size_bytes": (
                        file_props.size if hasattr(file_props, "size") else None
                    ),
                    "source_file_name": file_name,
                    "source_file_format": self.source_config.source_file_format,
                    "instance_code": parsed["instance_code"],
                    "report_name": parsed["report_name"],
                },
                output_params=["extract_id"],
            )
            extract_id = (
                result["output"].get("extract_id")
                or (result["result"][0].get("extract_id") if result["result"] else None)
            )
            if not extract_id:
                return

            # SP remaps domain aliases; replicate the same logic here
            canonical = {"FCT": "DP", "OPR": "SP"}.get(domain_code, domain_code)

            ws_rows = db.execute_query(
                """
                SELECT [target_workspace_id]
                FROM [dbo].[target_workspace]
                WHERE [enabled] = 1
                  AND [b2s_pipeline_id] IS NOT NULL
                  AND ([domain_filter] IS NULL OR [domain_filter] = ?)
                """,
                (canonical,),
            )

            for ws_row in ws_rows:
                ws_id = ws_row["target_workspace_id"]
                db.execute_query(
                    "EXEC dbo.update_medallion_sync @extract_id = ?, @target_workspace_id = ?",
                    (extract_id, ws_id),
                )
                logger.info(
                    f"[{self.source_id}] Placeholder medallion_sync created: "
                    f"extract={extract_id} workspace={ws_id}"
                )

        except Exception as e:
            logger.warning(
                f"[{self.source_id}] Failed to pre-register placeholder for {file_name}: {e}"
            )

    def _wait_for_b2s_completion(self, extract_id: int) -> None:
        """Block (in worker thread) until all medallion_sync rows for extract_id
        reach a terminal B2S status (SUCCESS / FAILED / INVALIDATED) or the
        configured timeout elapses.
        """
        import time
        from app.database import db

        if not db:
            logger.warning(
                f"[{self.source_id}] Cannot wait for B2S — no DB connection; "
                "proceeding to next file immediately"
            )
            return

        _TERMINAL = {"SUCCESS", "FAILED", "INVALIDATED"}
        _POLL_INTERVAL = settings.ins_orch_pipeline_poll_interval_seconds
        _TIMEOUT = settings.ins_orch_s2g_wait_timeout_seconds

        elapsed = 0
        logger.info(
            f"[{self.source_id}] Waiting for B2S completion of extract {extract_id} "
            f"(poll every {_POLL_INTERVAL}s, timeout {_TIMEOUT}s)"
        )

        while elapsed < _TIMEOUT:
            time.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            try:
                rows = db.execute_query(
                    "SELECT [b2s_status] FROM [dbo].[medallion_sync] WHERE [extract_id] = ?",
                    (extract_id,),
                )
                if not rows:
                    logger.debug(
                        f"[{self.source_id}] No medallion_sync row for extract {extract_id} yet "
                        f"[{elapsed}s elapsed] — waiting"
                    )
                    continue

                statuses = {r["b2s_status"] for r in rows}
                logger.info(
                    f"[{self.source_id}] Extract {extract_id} B2S statuses: {statuses} "
                    f"[{elapsed}s elapsed]"
                )
                if not (statuses - _TERMINAL):
                    logger.info(
                        f"[{self.source_id}] B2S complete for extract {extract_id}: {statuses}"
                    )
                    return

            except Exception as e:
                logger.warning(
                    f"[{self.source_id}] Error polling B2S status for extract {extract_id}: {e} "
                    f"— retrying in {_POLL_INTERVAL}s"
                )

        logger.warning(
            f"[{self.source_id}] B2S wait timed out after {_TIMEOUT}s for extract {extract_id} "
            "— proceeding to next file"
        )

    def _wait_for_all_s2g_completion(self, extract_ids: list) -> None:
        """Block (in worker thread) until every extract in extract_ids reaches a
        terminal S2G status (SUCCESS / FAILED / SKIPPED) or the configured
        timeout elapses.

        Called once after ALL notebooks for a batch have finished, so that
        S2G runs once for the whole batch rather than once per file.
        """
        import time
        from app.database import db

        if not db:
            logger.warning(
                f"[{self.source_id}] Cannot wait for S2G — no DB connection; "
                "proceeding immediately"
            )
            return

        _TERMINAL = {"SUCCESS", "FAILED", "SKIPPED"}
        _POLL_INTERVAL = settings.ins_orch_pipeline_poll_interval_seconds
        _TIMEOUT = settings.ins_orch_s2g_wait_timeout_seconds

        pending_ids = set(extract_ids)
        elapsed = 0
        placeholders = ",".join("?" * len(extract_ids))
        query = (
            f"SELECT [extract_id], [s2g_status] FROM [dbo].[medallion_sync] "
            f"WHERE [extract_id] IN ({placeholders})"
        )

        logger.info(
            f"[{self.source_id}] Waiting for S2G completion of {len(extract_ids)} extract(s): "
            f"{list(extract_ids)} (poll every {_POLL_INTERVAL}s, timeout {_TIMEOUT}s)"
        )

        while elapsed < _TIMEOUT:
            time.sleep(_POLL_INTERVAL)
            elapsed += _POLL_INTERVAL
            try:
                rows = db.execute_query(query, tuple(extract_ids))

                # Build a map of extract_id → latest s2g_status
                status_map: dict = {}
                for r in rows:
                    eid = r["extract_id"]
                    status_map.setdefault(eid, set()).add(r["s2g_status"])

                # An extract is done when ALL its medallion_sync rows are terminal
                still_pending = {
                    eid for eid in pending_ids
                    if not status_map.get(eid) or (status_map[eid] - _TERMINAL)
                }

                logger.info(
                    f"[{self.source_id}] S2G progress [{elapsed}s]: "
                    f"done={len(pending_ids) - len(still_pending)}/{len(pending_ids)} "
                    f"pending={sorted(still_pending)}"
                )

                if not still_pending:
                    logger.info(
                        f"[{self.source_id}] S2G complete for all {len(extract_ids)} extract(s)"
                    )
                    return

            except Exception as e:
                logger.warning(
                    f"[{self.source_id}] Error polling S2G status: {e} "
                    f"— retrying in {_POLL_INTERVAL}s"
                )

        logger.warning(
            f"[{self.source_id}] S2G wait timed out after {_TIMEOUT}s "
            f"for extracts {list(extract_ids)} — proceeding"
        )

    def _parse_filename_segments(self, file_name: str) -> dict:
        """Parse filename into component segments using the per-source regex.

        Falls back to positional parsing if no regex is configured or
        the regex doesn't match.
        """
        # Try regex from per-source config first
        if self._filename_re:
            m = self._filename_re.match(file_name)
            if m:
                groups = m.groupdict()
                result = {
                    "domain_code": groups.get("domain_code", file_name),
                    "instance_code": groups.get("instance_code"),
                    "report_name": groups.get("report_name"),
                }
                # Apply domain code remapping (e.g. FCT -> DP)
                if self.source_config.domain_code_map:
                    original = result["domain_code"]
                    mapped = self.source_config.domain_code_map.get(original, original)
                    if mapped != original:
                        logger.info(f"[{self.source_id}] Remapped domain_code: {original} -> {mapped}")
                    result["domain_code"] = mapped
                return result

        # Fallback: positional parser
        base = file_name.rsplit(self.source_config.filename_extension, 1)[0]
        parts = base.split("_")

        domain_code = parts[2] if len(parts) >= 3 else (parts[0] if parts else base)
        instance_code = None
        report_name = None

        try:
            fz_idx = parts.index(self.source_config.filename_must_contain) if self.source_config.filename_must_contain else -1
            if fz_idx >= 0:
                remaining = parts[fz_idx + 1:]
                if len(remaining) >= 1:
                    instance_code = remaining[0]
                if len(remaining) >= 2:
                    report_name = remaining[1]
        except ValueError:
            pass

        result = {
            "domain_code": domain_code,
            "instance_code": instance_code,
            "report_name": report_name,
        }

        # Apply domain code remapping if configured
        if self.source_config.domain_code_map:
            original = result["domain_code"]
            mapped = self.source_config.domain_code_map.get(original, original)
            if mapped != original:
                logger.info(f"[{self.source_id}] Remapped domain_code: {original} -> {mapped}")
            result["domain_code"] = mapped

        return result
