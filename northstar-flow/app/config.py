from pydantic_settings import BaseSettings
from pydantic import BaseModel
from typing import Dict, List, Optional
from pathlib import Path
from dotenv import load_dotenv
import json
import os
import re
import yaml
import logging

# Load .env into os.environ so ${VAR} interpolation works for poller sources
load_dotenv()

logger = logging.getLogger(__name__)


class ADLSSourceConfig(BaseModel):
    """Configuration for a single ADLS Gen2 polling source."""
    id: str
    label: str = ""
    storage_account: str
    container: str
    folder_path: str = ""
    sas_token: str
    poll_interval_seconds: int = 10
    enabled: bool = True
    poll_modified_since_days: Optional[int] = None  # Only poll blobs modified in last N days
    # Filename parsing config (formerly in file-naming.yaml)
    filename_extension: str = ".zip"
    filename_must_contain: str = ""
    filename_pattern: Optional[str] = (
        r"^(?P<date>\d{8})_(?P<time>\d{6})_(?P<domain_code>[A-Za-z]+)"
        r"_FinishedZip_(?P<instance_code>[^_]+)_(?P<report_name>[^.]+)\.zip$"
    )
    source_code: str = "ADLS_POLLER"
    source_file_format: str = "zip"
    domain_code_map: Optional[Dict[str, str]] = None  # e.g. {"FCT": "DP", "OPR": "SP"}


def _interpolate_env_vars(value: str) -> str:
    """Replace ${ENV_VAR} references with actual environment variable values."""
    def _replace(match):
        var_name = match.group(1)
        env_val = os.environ.get(var_name)
        if env_val is None:
            logger.warning(f"Environment variable '{var_name}' referenced in config is not set")
            return match.group(0)  # leave placeholder as-is
        return env_val
    return re.sub(r"\$\{([^}]+)\}", _replace, value)


def load_adls_sources_from_db() -> Optional[List[ADLSSourceConfig]]:
    """Try loading ADLS source configs from dbo.poller_source table.

    Returns None if the table doesn't exist or DB is unavailable.
    Returns [] if the table exists but has no rows.
    """
    try:
        from app.database import db
        if not db:
            return None

        rows = db.execute_query(
            "SELECT [source_id], [label], [storage_account], [container], "
            "[folder_path], [sas_token], [poll_interval_seconds], [enabled], "
            "[filename_extension], [filename_must_contain], [filename_pattern], "
            "[source_code], [source_file_format], [domain_code_map] "
            "FROM [dbo].[poller_source]"
        )
        logger.info(f"poller_source query returned {len(rows)} row(s)")

        # Global fallback for poll_modified_since_days from env
        global_modified_since = os.environ.get("INS_ORCH_POLL_MODIFIED_SINCE_DAYS")
        modified_since_days = int(global_modified_since) if global_modified_since else None

        sources = []
        for row in rows:
            # Interpolate env var references in string values
            for key, val in row.items():
                if isinstance(val, str):
                    row[key] = _interpolate_env_vars(val)

            sources.append(ADLSSourceConfig(
                id=row["source_id"],
                label=row.get("label") or "",
                storage_account=row["storage_account"],
                container=row["container"],
                folder_path=row.get("folder_path") or "",
                sas_token=row["sas_token"],
                poll_interval_seconds=row.get("poll_interval_seconds", 10),
                enabled=bool(row.get("enabled", True)),
                poll_modified_since_days=modified_since_days,
                filename_extension=row.get("filename_extension") or ".zip",
                filename_must_contain=row["filename_must_contain"] if row.get("filename_must_contain") is not None else "",
                filename_pattern=row.get("filename_pattern"),  # None is valid (disables regex)
                source_code=row.get("source_code") or "ADLS_POLLER",
                source_file_format=row.get("source_file_format") or "zip",
                domain_code_map=json.loads(row["domain_code_map"]) if row.get("domain_code_map") else None,
            ))

        return sources
    except Exception as e:
        logger.warning(f"Could not load from dbo.poller_source: {e}")
        return None


def load_adls_sources() -> List[ADLSSourceConfig]:
    """Load ADLS source configurations.

    Priority:
    1. Database dbo.poller_source table (if rows exist)
    2. poller-sources.yaml (if exists) — supports N sources
    3. Legacy env vars (INS_ORCH_ADLS_*) — single source with id='default'
    4. Empty list — no pollers start
    """
    # Priority 1: Database
    db_sources = load_adls_sources_from_db()
    if db_sources is not None and len(db_sources) > 0:
        logger.info(f"Loaded {len(db_sources)} ADLS source(s) from database")
        return db_sources

    # Priority 2: YAML file
    yaml_path = Path(__file__).resolve().parents[1] / "poller-sources.yaml"

    # Priority 2: YAML file — Try YAML
    if yaml_path.exists():
        try:
            with open(yaml_path) as f:
                raw = yaml.safe_load(f)

            sources = []
            for entry in raw.get("sources", []):
                # Interpolate env vars in string values
                for key, val in entry.items():
                    if isinstance(val, str):
                        entry[key] = _interpolate_env_vars(val)
                sources.append(ADLSSourceConfig(**entry))

            logger.info(f"Loaded {len(sources)} ADLS source(s) from {yaml_path}")
            return sources
        except Exception as e:
            logger.error(f"Failed to load poller-sources.yaml: {e} — falling back to env vars")

    # Priority 3: Legacy env vars
    from app.config import settings
    if all([
        settings.ins_orch_adls_storage_account,
        settings.ins_orch_adls_container,
        settings.ins_orch_adls_sas_token,
    ]):
        source = ADLSSourceConfig(
            id="default",
            label="Default ADLS Source",
            storage_account=settings.ins_orch_adls_storage_account,
            container=settings.ins_orch_adls_container,
            folder_path=settings.ins_orch_adls_folder_path or "",
            sas_token=settings.ins_orch_adls_sas_token,
            poll_interval_seconds=settings.ins_orch_poll_interval_seconds,
            poll_modified_since_days=settings.ins_orch_poll_modified_since_days,
        )
        logger.info("No poller-sources.yaml found — using legacy env vars (single source: 'default')")
        return [source]

    return []


class Settings(BaseSettings):
    # Azure Service Principal Authentication
    azure_tenant_id: str
    azure_client_id: str
    azure_client_secret: str

    # API Settings
    api_title: str = "INS Orchestrator API"
    api_version: str = "1.0.0"
    cors_origins: str = '["http://localhost:3000"]'

    # Pipeline Database (Fabric SQL endpoint)
    ins_orch_sql_endpoint: Optional[str] = None
    ins_orch_database: Optional[str] = None

    # ADLS Gen2 Poller
    ins_orch_adls_storage_account: Optional[str] = None
    ins_orch_adls_container: Optional[str] = None
    ins_orch_adls_folder_path: Optional[str] = None
    ins_orch_adls_sas_token: Optional[str] = None
    ins_orch_poll_interval_seconds: int = 10
    ins_orch_poll_modified_since_days: Optional[int] = None  # Only poll blobs modified in last N days

    # Fabric Notebook Trigger
    ins_orch_fabric_workspace_id: Optional[str] = None
    ins_orch_notebook_id: Optional[str] = None
    ins_orch_notebook_poll_interval_seconds: int = 30   # How often to poll a running notebook job
    ins_orch_s2g_wait_timeout_seconds: int = 14400      # Max seconds to wait for S2G completion per file (4h)

    # Medallion Pipeline Orchestration
    ins_orch_b2s_grace_period_minutes: int = 1
    ins_orch_pipeline_poll_interval_seconds: int = 300
    ins_orch_medallion_scan_interval_seconds: int = 60

    # Late Arrival Auto-Replay
    ins_orch_late_arrival_threshold_hours: int = 48
    ins_orch_late_arrival_check_interval_seconds: int = 300

    # API Key
    ins_orch_api_key: Optional[str] = None

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.cors_origins)

    class Config:
        env_file = ".env"
        case_sensitive = False
        extra = "ignore"


settings = Settings()
