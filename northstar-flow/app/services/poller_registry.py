"""
Poller Registry

Manages multiple ADLSPollerService instances (one per configured ADLS source).
The registry itself is a classmethod singleton, matching the pattern used by
MedallionOrchestratorService.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional

from app.config import ADLSSourceConfig
from app.models.schemas import PollerStatusResponse, PollerFileItem, PollerSourceInfo
from app.services.adls_poller import ADLSPollerService

logger = logging.getLogger(__name__)


class PollerRegistry:
    """Manages N ADLSPollerService instances, one per configured source."""

    _pollers: Dict[str, ADLSPollerService] = {}

    @classmethod
    def initialize(cls, sources: List[ADLSSourceConfig]):
        """Create poller instances for all configured sources."""
        cls._pollers = {}
        for source in sources:
            cls._pollers[source.id] = ADLSPollerService(source)
            logger.info(f"Registered ADLS source: '{source.id}' ({source.label or source.storage_account})")

    @classmethod
    async def start_all(cls) -> Dict[str, bool]:
        """Start all enabled pollers. Returns {source_id: started}."""
        results = {}
        for source_id, poller in cls._pollers.items():
            if not poller.source_config.enabled:
                results[source_id] = False
                logger.info(f"Skipping disabled source: '{source_id}'")
                continue
            try:
                started = await poller.start()
                results[source_id] = started
            except Exception as e:
                results[source_id] = False
                logger.warning(f"Failed to start poller '{source_id}' (non-fatal): {e}")
        return results

    @classmethod
    async def stop_all(cls):
        """Stop all running pollers."""
        for source_id, poller in cls._pollers.items():
            try:
                await poller.stop()
            except Exception as e:
                logger.warning(f"Error stopping poller '{source_id}': {e}")

    @classmethod
    async def start_source(cls, source_id: str) -> bool:
        """Start a specific source's poller. Returns True if started."""
        poller = cls._pollers.get(source_id)
        if poller is None:
            raise KeyError(f"Unknown source: '{source_id}'")
        return await poller.start()

    @classmethod
    async def stop_source(cls, source_id: str):
        """Stop a specific source's poller."""
        poller = cls._pollers.get(source_id)
        if poller is None:
            raise KeyError(f"Unknown source: '{source_id}'")
        await poller.stop()

    @classmethod
    def get_source_status(cls, source_id: str) -> PollerStatusResponse:
        """Get status for a specific source."""
        poller = cls._pollers.get(source_id)
        if poller is None:
            raise KeyError(f"Unknown source: '{source_id}'")
        return poller.get_status()

    @classmethod
    def get_all_statuses(cls) -> Dict[str, PollerStatusResponse]:
        """Get status for every registered source."""
        return {sid: p.get_status() for sid, p in cls._pollers.items()}

    @classmethod
    def get_aggregate_status(cls) -> PollerStatusResponse:
        """Backwards-compatible aggregate: is_running if ANY source running, summed stats."""
        if not cls._pollers:
            return PollerStatusResponse(is_running=False)

        total_cycles = 0
        total_detected = 0
        total_errors = 0
        any_running = False
        earliest_start: Optional[datetime] = None
        latest_poll: Optional[datetime] = None

        for poller in cls._pollers.values():
            status = poller.get_status()
            total_cycles += status.poll_cycles
            total_detected += status.new_files_detected
            total_errors += status.errors
            if status.is_running:
                any_running = True
            if status.started_at:
                if earliest_start is None or status.started_at < earliest_start:
                    earliest_start = status.started_at
            if status.last_poll_at:
                if latest_poll is None or status.last_poll_at > latest_poll:
                    latest_poll = status.last_poll_at

        elapsed = 0.0
        if earliest_start and any_running:
            elapsed = (datetime.now(timezone.utc) - earliest_start).total_seconds()

        return PollerStatusResponse(
            is_running=any_running,
            poll_cycles=total_cycles,
            new_files_detected=total_detected,
            errors=total_errors,
            elapsed_seconds=round(elapsed, 1),
            started_at=earliest_start,
            last_poll_at=latest_poll,
        )

    @classmethod
    def get_source_files(
        cls, source_id: str, limit: int = 50, status_filter: Optional[str] = None
    ) -> List[PollerFileItem]:
        """Get detected files for a specific source."""
        poller = cls._pollers.get(source_id)
        if poller is None:
            raise KeyError(f"Unknown source: '{source_id}'")
        return poller.get_detected_files(limit=limit, status_filter=status_filter)

    @classmethod
    def get_all_files(
        cls, limit: int = 50, status_filter: Optional[str] = None, source_id: Optional[str] = None
    ) -> List[PollerFileItem]:
        """Get detected files across all sources (or filtered to one)."""
        if source_id:
            return cls.get_source_files(source_id, limit=limit, status_filter=status_filter)

        from app.database import db
        if not db:
            return []

        query = (
            "SELECT TOP (?) source_id, file_name, detected_at, status, extract_id, "
            "error_message, blob_last_modified "
            "FROM [dbo].[poller_state]"
        )
        params: list = [limit]

        if status_filter:
            query += " WHERE status = ?"
            params.append(status_filter)

        query += " ORDER BY detected_at DESC"

        rows = db.execute_query(query, tuple(params))
        return [PollerFileItem(**row) for row in rows]

    @classmethod
    def list_sources(cls) -> List[PollerSourceInfo]:
        """List all configured sources with their current run status."""
        result = []
        for sid, poller in cls._pollers.items():
            cfg = poller.source_config
            status = poller.get_status()
            result.append(PollerSourceInfo(
                source_id=cfg.id,
                label=cfg.label,
                storage_account=cfg.storage_account,
                container=cfg.container,
                folder_path=cfg.folder_path,
                poll_interval_seconds=cfg.poll_interval_seconds,
                enabled=cfg.enabled,
                is_running=status.is_running,
                filename_extension=cfg.filename_extension,
                filename_must_contain=cfg.filename_must_contain,
                filename_pattern=cfg.filename_pattern,
                source_code=cfg.source_code,
                source_file_format=cfg.source_file_format,
                domain_code_map=cfg.domain_code_map,
            ))
        return result

    @classmethod
    def get_source(cls, source_id: str) -> Optional[ADLSPollerService]:
        """Get a specific poller instance."""
        return cls._pollers.get(source_id)

    @classmethod
    def has_sources(cls) -> bool:
        """True if any sources are registered."""
        return len(cls._pollers) > 0

    # ── DB-backed source CRUD ────────────────────────────────────────────

    @classmethod
    async def add_source(cls, config: ADLSSourceConfig) -> PollerSourceInfo:
        """Insert a new source into the DB and start its poller."""
        from app.database import db
        if not db:
            raise RuntimeError("Database not available")

        if config.id in cls._pollers:
            raise ValueError(f"Source '{config.id}' already exists")

        import json as _json
        db.execute_query(
            "INSERT INTO [dbo].[poller_source] "
            "([source_id], [label], [storage_account], [container], "
            "[folder_path], [sas_token], [poll_interval_seconds], [enabled], "
            "[filename_extension], [filename_must_contain], [filename_pattern], "
            "[source_code], [source_file_format], [domain_code_map]) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (config.id, config.label, config.storage_account, config.container,
             config.folder_path, config.sas_token, config.poll_interval_seconds,
             1 if config.enabled else 0,
             config.filename_extension, config.filename_must_contain,
             config.filename_pattern, config.source_code, config.source_file_format,
             _json.dumps(config.domain_code_map) if config.domain_code_map else None),
        )

        poller = ADLSPollerService(config)
        cls._pollers[config.id] = poller
        logger.info(f"Added ADLS source: '{config.id}'")

        if config.enabled:
            await poller.start()

        status = poller.get_status()
        return PollerSourceInfo(
            source_id=config.id, label=config.label,
            storage_account=config.storage_account, container=config.container,
            folder_path=config.folder_path,
            poll_interval_seconds=config.poll_interval_seconds,
            enabled=config.enabled, is_running=status.is_running,
            filename_extension=config.filename_extension,
            filename_must_contain=config.filename_must_contain,
            filename_pattern=config.filename_pattern,
            source_code=config.source_code,
            source_file_format=config.source_file_format,
            domain_code_map=config.domain_code_map,
        )

    @classmethod
    async def update_source(cls, source_id: str, updates: dict) -> PollerSourceInfo:
        """Update a source's config in the DB and restart its poller."""
        from app.database import db
        if not db:
            raise RuntimeError("Database not available")

        if source_id not in cls._pollers:
            raise KeyError(f"Unknown source: '{source_id}'")

        # Build SET clause from provided updates
        allowed = {"label", "storage_account", "container", "folder_path",
                    "sas_token", "poll_interval_seconds", "enabled",
                    "filename_extension", "filename_must_contain", "filename_pattern",
                    "source_code", "source_file_format", "domain_code_map"}
        set_parts = []
        values = []
        import json as _json
        for key, val in updates.items():
            if key in allowed:
                col = key if key != "enabled" else "enabled"
                set_parts.append(f"[{col}] = ?")
                if key == "enabled":
                    values.append(1 if val else 0)
                elif key == "domain_code_map":
                    values.append(_json.dumps(val) if val else None)
                else:
                    values.append(val)

        if not set_parts:
            raise ValueError("No valid fields to update")

        set_parts.append("[updated_at] = SYSUTCDATETIME()")
        values.append(source_id)

        db.execute_query(
            f"UPDATE [dbo].[poller_source] SET {', '.join(set_parts)} "
            f"WHERE [source_id] = ?",
            tuple(values),
        )

        # Reload from DB and restart poller
        from app.config import _interpolate_env_vars
        row = db.execute_single(
            "SELECT [source_id], [label], [storage_account], [container], "
            "[folder_path], [sas_token], [poll_interval_seconds], [enabled], "
            "[filename_extension], [filename_must_contain], [filename_pattern], "
            "[source_code], [source_file_format], [domain_code_map] "
            "FROM [dbo].[poller_source] WHERE [source_id] = ?",
            (source_id,),
        )
        if not row:
            raise KeyError(f"Source '{source_id}' not found in DB after update")

        for key, val in row.items():
            if isinstance(val, str):
                row[key] = _interpolate_env_vars(val)

        new_config = ADLSSourceConfig(
            id=row["source_id"],
            label=row.get("label") or "",
            storage_account=row["storage_account"],
            container=row["container"],
            folder_path=row.get("folder_path") or "",
            sas_token=row["sas_token"],
            poll_interval_seconds=row.get("poll_interval_seconds", 10),
            enabled=bool(row.get("enabled", True)),
            filename_extension=row.get("filename_extension") or ".zip",
            filename_must_contain=row.get("filename_must_contain") or "FinishedZip",
            filename_pattern=row.get("filename_pattern"),
            source_code=row.get("source_code") or "ADLS_POLLER",
            source_file_format=row.get("source_file_format") or "zip",
            domain_code_map=_json.loads(row["domain_code_map"]) if row.get("domain_code_map") else None,
        )

        # Stop old, replace, start new
        old_poller = cls._pollers[source_id]
        await old_poller.stop()

        new_poller = ADLSPollerService(new_config)
        cls._pollers[source_id] = new_poller

        if new_config.enabled:
            await new_poller.start()

        logger.info(f"Updated ADLS source: '{source_id}'")
        status = new_poller.get_status()
        return PollerSourceInfo(
            source_id=new_config.id, label=new_config.label,
            storage_account=new_config.storage_account, container=new_config.container,
            folder_path=new_config.folder_path,
            poll_interval_seconds=new_config.poll_interval_seconds,
            enabled=new_config.enabled, is_running=status.is_running,
            filename_extension=new_config.filename_extension,
            filename_must_contain=new_config.filename_must_contain,
            filename_pattern=new_config.filename_pattern,
            source_code=new_config.source_code,
            source_file_format=new_config.source_file_format,
            domain_code_map=new_config.domain_code_map,
        )

    @classmethod
    async def remove_source(cls, source_id: str):
        """Stop poller, remove from registry, delete from DB."""
        from app.database import db
        if not db:
            raise RuntimeError("Database not available")

        poller = cls._pollers.get(source_id)
        if poller is None:
            raise KeyError(f"Unknown source: '{source_id}'")

        await poller.stop()
        del cls._pollers[source_id]

        db.execute_query(
            "DELETE FROM [dbo].[poller_source] WHERE [source_id] = ?",
            (source_id,),
        )
        logger.info(f"Removed ADLS source: '{source_id}'")
