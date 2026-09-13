"""
Fabric Pipeline Trigger & Poll Service

Triggers Fabric Data Pipelines (B2S, S2G) via the REST API and polls
for completion. The orchestrator uses this to manage medallion pipeline
execution without callbacks — pure poll-based tracking.
"""

import logging
from typing import Optional, Dict

import httpx
from azure.identity import ClientSecretCredential
from app.config import settings

logger = logging.getLogger(__name__)

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"


def _get_fabric_token() -> str:
    """Get a bearer token for the Fabric REST API using the app's Service Principal."""
    credential = ClientSecretCredential(
        tenant_id=settings.azure_tenant_id,
        client_id=settings.azure_client_id,
        client_secret=settings.azure_client_secret,
    )
    token = credential.get_token("https://api.fabric.microsoft.com/.default")
    return token.token


def trigger_pipeline(
    workspace_id: str,
    pipeline_id: str,
    parameters: Optional[Dict[str, str]] = None,
) -> Dict[str, str]:
    """Trigger a Fabric Data Pipeline via REST API.

    Args:
        workspace_id: The target workspace containing the pipeline.
        pipeline_id: The Fabric item ID of the pipeline.
        parameters: Optional dict of pipeline parameters (string key-value pairs).

    Returns:
        Dict with 'job_instance_id' and 'status_url'.

    Raises:
        RuntimeError: If the Fabric API returns a non-202 response.
    """
    token = _get_fabric_token()

    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/items/{pipeline_id}/jobs/instances?jobType=Pipeline"
    )

    body: Dict = {}
    if parameters:
        body["executionData"] = {"parameters": parameters}

    resp = httpx.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json=body if body else None,
        timeout=30,
    )

    if resp.status_code == 202:
        location = resp.headers.get("Location", "")
        job_instance_id = location.rsplit("/", 1)[-1] if location else None
        logger.info(
            "Pipeline triggered: workspace=%s pipeline=%s job=%s",
            workspace_id, pipeline_id, job_instance_id,
        )
        return {
            "job_instance_id": job_instance_id,
            "status_url": location,
        }
    else:
        error_msg = f"Fabric API returned {resp.status_code}: {resp.text}"
        logger.error(
            "Pipeline trigger failed: workspace=%s pipeline=%s — %s",
            workspace_id, pipeline_id, error_msg,
        )
        raise RuntimeError(error_msg)


def poll_pipeline_status(
    workspace_id: str,
    pipeline_id: str,
    job_instance_id: str,
) -> Dict[str, str]:
    """Poll the status of a running pipeline job.

    Args:
        workspace_id: The workspace containing the pipeline.
        pipeline_id: The pipeline item ID.
        job_instance_id: The job instance ID from trigger_pipeline().

    Returns:
        Dict with 'status' (InProgress, Completed, Failed, Cancelled, etc.)
        and 'start_time', 'end_time' if available.

    Raises:
        RuntimeError: If the Fabric API returns an error.
    """
    token = _get_fabric_token()

    url = (
        f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        f"/items/{pipeline_id}/jobs/instances/{job_instance_id}"
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
        # Include failure details if present
        failure_reason = data.get("failureReason")
        if failure_reason:
            result["failure_reason"] = str(failure_reason)

        logger.debug(
            "Pipeline poll: job=%s status=%s",
            job_instance_id, result["status"],
        )
        return result
    else:
        error_msg = f"Fabric API returned {resp.status_code}: {resp.text}"
        logger.error("Pipeline poll failed for job %s: %s", job_instance_id, error_msg)
        raise RuntimeError(error_msg)
