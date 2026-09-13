"""
Fabric Notebook Trigger Service

Triggers a Fabric Python Notebook via the REST API to process a registered extract.
Fire-and-forget — the notebook handles its own status updates in the database.
"""

import logging
import time
from typing import Optional, Dict
import httpx
from azure.identity import ClientSecretCredential
from app.config import settings

logger = logging.getLogger(__name__)

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"

# Terminal job statuses (job will not progress further once in one of these)
_TERMINAL_STATUSES = {"Completed", "Failed", "Cancelled", "Deduped"}


def _get_fabric_token() -> str:
    """Get a bearer token for the Fabric REST API using the app's Service Principal."""
    credential = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    token = credential.get_token("https://api.fabric.microsoft.com/.default")
    return token.token


def trigger_notebook(extract_id: int, file_name: str) -> Optional[Dict[str, str]]:
    """Trigger the extract processor notebook via Fabric REST API.

    Args:
        extract_id: The registered extract ID to process.
        file_name: The source zip filename (passed as notebook parameter).

    Returns:
        Dict with job_instance_id and status_url on success, None if not configured.

    Raises:
        RuntimeError: If the Fabric API returns a non-202 response.
    """
    workspace_id = settings.ins_orch_fabric_workspace_id
    notebook_id = settings.ins_orch_notebook_id

    if not workspace_id or not notebook_id:
        logger.debug("Notebook trigger skipped — workspace_id or notebook_id not configured")
        return None

    token = _get_fabric_token()

    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/items/{notebook_id}/jobs/instances?jobType=RunNotebook"
    )

    params = {
        "EXTRACT_ID": {"value": str(extract_id), "type": "string"},
        "FILE_NAME": {"value": file_name, "type": "string"},
    }
    if settings.ins_orch_sql_endpoint:
        params["SQL_SERVER"] = {"value": settings.ins_orch_sql_endpoint, "type": "string"}
    if settings.ins_orch_database:
        params["SQL_DATABASE"] = {"value": settings.ins_orch_database, "type": "string"}

    body = {
        "executionData": {
            "parameters": params
        }
    }

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=30,
    )

    if resp.status_code == 202:
        location = resp.headers.get("Location", "")
        job_instance_id = location.rsplit("/", 1)[-1] if location else None
        logger.info(
            f"Notebook triggered for extract {extract_id}: job_instance_id={job_instance_id}"
        )
        return {
            "job_instance_id": job_instance_id,
            "status_url": location,
        }
    else:
        error_msg = f"Fabric API returned {resp.status_code}: {resp.text}"
        logger.error(f"Notebook trigger failed for extract {extract_id}: {error_msg}")
        raise RuntimeError(error_msg)


def poll_notebook_status(
    workspace_id: str,
    notebook_id: str,
    job_instance_id: str,
) -> Dict[str, str]:
    """Poll the status of a running notebook job instance.

    Returns:
        Dict with 'status' and optionally 'start_time', 'end_time', 'failure_reason'.

    Raises:
        RuntimeError: If the Fabric API returns an error.
    """
    token = _get_fabric_token()

    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/items/{notebook_id}/jobs/instances/{job_instance_id}"
    )

    resp = httpx.get(
        url,
        headers={"Authorization": f"Bearer {token}"},
        timeout=30,
    )

    if resp.status_code == 200:
        data = resp.json()
        result = {
            "status": data.get("status", "Unknown"),
            "start_time": data.get("startTimeUtc"),
            "end_time": data.get("endTimeUtc"),
        }
        failure_reason = data.get("failureReason")
        if failure_reason:
            result["failure_reason"] = str(failure_reason)
        logger.debug(
            "Notebook poll: job=%s status=%s", job_instance_id, result["status"]
        )
        return result
    else:
        error_msg = f"Fabric API returned {resp.status_code}: {resp.text}"
        logger.error("Notebook poll failed for job %s: %s", job_instance_id, error_msg)
        raise RuntimeError(error_msg)


def wait_for_notebook_completion(
    workspace_id: str,
    notebook_id: str,
    job_instance_id: str,
    extract_id: int,
    poll_interval_seconds: int = 30,
    timeout_seconds: int = 3600,
) -> str:
    """Block (synchronously) until the notebook job reaches a terminal state.

    Intended to be called from a worker thread (asyncio.to_thread) so the
    event loop is not blocked.

    Returns:
        The final status string (e.g. 'Completed', 'Failed').
    """
    elapsed = 0
    logger.info(
        f"Waiting for notebook job {job_instance_id} (extract {extract_id}) — "
        f"poll every {poll_interval_seconds}s, timeout {timeout_seconds}s"
    )
    while elapsed < timeout_seconds:
        time.sleep(poll_interval_seconds)
        elapsed += poll_interval_seconds
        try:
            result = poll_notebook_status(workspace_id, notebook_id, job_instance_id)
            status = result["status"]
            logger.info(
                f"Notebook job {job_instance_id} (extract {extract_id}): status={status} "
                f"[{elapsed}s elapsed]"
            )
            if status in _TERMINAL_STATUSES:
                return status
        except Exception as e:
            logger.warning(
                f"Poll error for notebook job {job_instance_id} (extract {extract_id}): {e} "
                f"— retrying in {poll_interval_seconds}s"
            )

    logger.warning(
        f"Notebook job {job_instance_id} (extract {extract_id}) timed out after "
        f"{timeout_seconds}s — proceeding to next file"
    )
    return "TimedOut"
