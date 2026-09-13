from pydantic import BaseModel, Field
from typing import Dict, Optional, List
from datetime import datetime


# ---------------------------------------------------------------------------
# Extract models
# ---------------------------------------------------------------------------

class RegisterExtractRequest(BaseModel):
    folder_path: str
    domain_code: str
    source_code: str
    folder_name: str
    period_year: int
    period_month: int = Field(ge=1, le=12)
    period_day: Optional[int] = None
    period_label: Optional[str] = None
    file_count: Optional[int] = None
    total_size_bytes: Optional[int] = None


class RegisterExtractResponse(BaseModel):
    extract_id: int


class ExtractDetail(BaseModel):
    extract_id: int
    domain_code: str
    source_code: Optional[str] = None
    folder_path: str
    folder_name: Optional[str] = None
    period_year: int
    period_month: int
    period_day: Optional[int] = None
    period_label: Optional[str] = None
    status: str
    is_latest_for_period: bool
    superseded_by_id: Optional[int] = None
    has_duplicate_period: bool
    actual_file_count: Optional[int] = None
    total_size_bytes: Optional[int] = None
    is_valid: Optional[bool] = None
    validation_message: Optional[str] = None
    validated_at: Optional[datetime] = None
    arrived_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    extraction_date: Optional[datetime] = None
    cycle_id: Optional[str] = None
    extraction_def: Optional[str] = None
    package_def: Optional[str] = None
    is_late_arrival: Optional[bool] = None


class PendingExtractItem(BaseModel):
    extract_id: int
    domain_code: str
    source_code: Optional[str] = None
    folder_path: str
    folder_name: Optional[str] = None
    period_year: int
    period_month: int
    period_label: Optional[str] = None
    status: str
    is_latest_for_period: bool
    actual_file_count: Optional[int] = None
    total_size_bytes: Optional[int] = None
    arrived_at: Optional[datetime] = None
    on_b2s_failure_policy: Optional[str] = None
    max_retry_attempts: Optional[int] = None


# ---------------------------------------------------------------------------
# Push Job models
# ---------------------------------------------------------------------------

class CreatePushJobRequest(BaseModel):
    extract_id: int
    target_workspace_id: str
    target_workspace_name: str
    target_lakehouse_id: str
    target_lakehouse_name: Optional[str] = None
    bronze_folder_path: str


class CreatePushJobResponse(BaseModel):
    push_job_id: int


class UpdatePushJobStatusRequest(BaseModel):
    status: str = Field(pattern="^(PENDING|RUNNING|SUCCESS|PARTIAL|FAILED|CANCELLED)$")
    files_attempted: Optional[int] = None
    files_succeeded: Optional[int] = None
    files_failed: Optional[int] = None
    bytes_transferred: Optional[int] = None
    error_message: Optional[str] = None
    pipeline_run_id: Optional[str] = None


class PushJobDetail(BaseModel):
    push_job_id: int
    extract_id: int
    target_workspace_id: Optional[str] = None
    target_workspace_name: Optional[str] = None
    target_lakehouse_id: Optional[str] = None
    target_lakehouse_name: Optional[str] = None
    bronze_folder_path: Optional[str] = None
    status: str
    pipeline_run_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[int] = None
    files_attempted: Optional[int] = None
    files_succeeded: Optional[int] = None
    files_failed: Optional[int] = None
    bytes_transferred: Optional[int] = None
    error_message: Optional[str] = None
    attempt_number: int
    max_attempts: int
    next_retry_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Medallion Sync models
# ---------------------------------------------------------------------------

class UpdateMedallionSyncRequest(BaseModel):
    extract_id: int
    target_workspace_id: str
    bronze_status: Optional[str] = None
    bronze_loaded_at: Optional[datetime] = None
    bronze_file_count: Optional[int] = None
    b2s_status: Optional[str] = None
    b2s_run_id: Optional[str] = None
    b2s_started_at: Optional[datetime] = None
    b2s_completed_at: Optional[datetime] = None
    b2s_rows_processed: Optional[int] = None
    b2s_error: Optional[str] = None
    s2g_status: Optional[str] = None
    s2g_run_id: Optional[str] = None
    s2g_started_at: Optional[datetime] = None
    s2g_completed_at: Optional[datetime] = None
    s2g_error: Optional[str] = None


class MedallionSyncDetail(BaseModel):
    sync_id: int
    extract_id: int
    target_workspace_id: Optional[str] = None
    bronze_status: Optional[str] = None
    bronze_loaded_at: Optional[datetime] = None
    bronze_file_count: Optional[int] = None
    b2s_status: Optional[str] = None
    b2s_run_id: Optional[str] = None
    b2s_started_at: Optional[datetime] = None
    b2s_completed_at: Optional[datetime] = None
    b2s_rows_processed: Optional[int] = None
    b2s_error: Optional[str] = None
    s2g_status: Optional[str] = None
    s2g_run_id: Optional[str] = None
    s2g_started_at: Optional[datetime] = None
    s2g_completed_at: Optional[datetime] = None
    s2g_error: Optional[str] = None
    last_synced_at: Optional[datetime] = None
    sync_count: int = 0
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# Notebook Trigger models
# ---------------------------------------------------------------------------

class NotebookTriggerResponse(BaseModel):
    extract_id: int
    job_instance_id: Optional[str] = None
    status_url: Optional[str] = None
    message: str


# ---------------------------------------------------------------------------
# Poller models
# ---------------------------------------------------------------------------

class PollerStatusResponse(BaseModel):
    source_id: Optional[str] = None  # None for aggregate status
    label: Optional[str] = None
    is_running: bool
    poll_cycles: int = 0
    new_files_detected: int = 0
    errors: int = 0
    elapsed_seconds: float = 0.0
    started_at: Optional[datetime] = None
    last_poll_at: Optional[datetime] = None


class PollerFileItem(BaseModel):
    source_id: str = "default"
    file_name: str
    detected_at: Optional[datetime] = None
    status: str  # REGISTERED or FAILED
    extract_id: Optional[int] = None
    error_message: Optional[str] = None
    blob_last_modified: Optional[datetime] = None


class PollerSourceInfo(BaseModel):
    source_id: str
    label: str
    storage_account: str
    container: str
    folder_path: str
    poll_interval_seconds: int
    enabled: bool
    is_running: bool
    filename_extension: str = ".zip"
    filename_must_contain: str = "FinishedZip"
    filename_pattern: Optional[str] = None
    source_code: str = "ADLS_POLLER"
    source_file_format: str = "zip"
    domain_code_map: Optional[Dict[str, str]] = None


class PollerSourceCreate(BaseModel):
    source_id: str = Field(max_length=50)
    label: str = ""
    storage_account: str
    container: str
    folder_path: str = ""
    sas_token: str = Field(description="Env var reference, e.g. ${MY_SAS_TOKEN}")
    poll_interval_seconds: int = 10
    enabled: bool = True
    filename_extension: str = ".zip"
    filename_must_contain: str = "FinishedZip"
    filename_pattern: Optional[str] = (
        r"^(?P<date>\d{8})_(?P<time>\d{6})_(?P<domain_code>[A-Za-z]+)"
        r"_FinishedZip_(?P<instance_code>[^_]+)_(?P<report_name>[^.]+)\.zip$"
    )
    source_code: str = "ADLS_POLLER"
    source_file_format: str = "zip"
    domain_code_map: Optional[Dict[str, str]] = None


class PollerSourceUpdate(BaseModel):
    label: Optional[str] = None
    storage_account: Optional[str] = None
    container: Optional[str] = None
    folder_path: Optional[str] = None
    sas_token: Optional[str] = None
    poll_interval_seconds: Optional[int] = None
    enabled: Optional[bool] = None
    filename_extension: Optional[str] = None
    filename_must_contain: Optional[str] = None
    filename_pattern: Optional[str] = None
    source_code: Optional[str] = None
    source_file_format: Optional[str] = None
    domain_code_map: Optional[Dict[str, str]] = None


# ---------------------------------------------------------------------------
# Medallion Orchestrator models
# ---------------------------------------------------------------------------

class MedallionOrchestratorStatusResponse(BaseModel):
    is_running: bool
    scan_cycles: int = 0
    b2s_triggered: int = 0
    b2s_completed: int = 0
    b2s_failed: int = 0
    s2g_triggered: int = 0
    s2g_completed: int = 0
    s2g_failed: int = 0
    late_arrivals_auto_replayed: int = 0
    late_arrivals_alerted: int = 0
    errors: int = 0
    active_b2s_jobs: int = 0
    active_s2g_jobs: int = 0
    elapsed_seconds: float = 0.0
    started_at: Optional[str] = None
    last_scan_at: Optional[str] = None
    grace_period_minutes: int = 5
    pipeline_poll_interval_seconds: int = 300
    late_arrival_threshold_hours: int = 48


class B2SPendingBatchItem(BaseModel):
    domain_code: str
    target_workspace_id: str
    target_workspace_name: Optional[str] = None
    b2s_pipeline_id: Optional[str] = None
    pending_extract_count: int
    latest_bronze_loaded_at: Optional[datetime] = None
    earliest_extraction_date: Optional[datetime] = None


class S2GReadyItem(BaseModel):
    domain_code: str
    target_workspace_id: str
    target_workspace_name: Optional[str] = None
    s2g_pipeline_id: Optional[str] = None
    target_lakehouse_id: Optional[str] = None
    target_lakehouse_name: Optional[str] = None
    extract_count: int
    total_b2s_rows: Optional[int] = None


class TriggerB2SRequest(BaseModel):
    domain_code: str
    target_workspace_id: str


class TriggerS2GRequest(BaseModel):
    domain_code: str
    target_workspace_id: str


class MedallionDashboardItem(BaseModel):
    domain_code: str
    target_workspace_id: str
    target_workspace_name: Optional[str] = None
    bronze_loaded: int = 0
    b2s_not_started: int = 0
    b2s_running: int = 0
    b2s_success: int = 0
    b2s_failed: int = 0
    b2s_skipped: int = 0
    s2g_not_started: int = 0
    s2g_processing: int = 0
    s2g_success: int = 0
    s2g_failed: int = 0
    s2g_skipped: int = 0
    late_arrivals: int = 0


class BatchRerunRequest(BaseModel):
    domain_code: str
    lookback_hours: int = Field(ge=0, description="0=skip/discard, >0=replay window in hours")
    extraction_def: Optional[str] = None
    package_def: Optional[str] = None
    target_workspace_id: Optional[str] = None


class BatchRerunResponse(BaseModel):
    extracts_reset: int
    syncs_reset: int
    lookback_hours: int
    domain_code: str
    extraction_def: Optional[str] = None
    package_def: Optional[str] = None
    affected_extracts: List[dict] = []
