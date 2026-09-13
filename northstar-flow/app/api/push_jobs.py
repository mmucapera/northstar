from fastapi import APIRouter, Depends, HTTPException
from app.auth.api_key import verify_api_key
from app.database import db
from app.models.schemas import (
    CreatePushJobRequest,
    CreatePushJobResponse,
    UpdatePushJobStatusRequest,
    PushJobDetail,
)

router = APIRouter(
    prefix="/push-jobs",
    tags=["Push Jobs"],
    dependencies=[Depends(verify_api_key)],
)


def _require_db():
    if not db:
        raise HTTPException(status_code=503, detail="Orchestrator database not configured")


@router.post("", response_model=CreatePushJobResponse)
async def create_push_job(request: CreatePushJobRequest):
    """Create a push job by calling the create_push_job stored procedure."""
    _require_db()
    try:
        result = db.call_sp(
            "create_push_job",
            params={
                "extract_id": request.extract_id,
                "target_workspace_id": request.target_workspace_id,
                "target_workspace_name": request.target_workspace_name,
                "target_lakehouse_id": request.target_lakehouse_id,
                "target_lakehouse_name": request.target_lakehouse_name,
                "bronze_folder_path": request.bronze_folder_path,
            },
            output_params=["push_job_id"],
        )

        push_job_id = (
            result["output"].get("push_job_id")
            or (result["result"][0].get("push_job_id") if result["result"] else None)
        )

        if push_job_id is None:
            raise HTTPException(status_code=500, detail="Failed to retrieve push_job_id from stored procedure")

        return CreatePushJobResponse(push_job_id=push_job_id)

    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "not eligible" in error_msg.lower():
            raise HTTPException(status_code=409, detail=error_msg)
        raise HTTPException(status_code=500, detail=error_msg)


@router.put("/{push_job_id}/status")
async def update_push_job_status(push_job_id: int, request: UpdatePushJobStatusRequest):
    """Update push job status by calling the update_push_job_status stored procedure."""
    _require_db()
    try:
        db.call_sp(
            "update_push_job_status",
            params={
                "push_job_id": push_job_id,
                "status": request.status,
                "files_attempted": request.files_attempted,
                "files_succeeded": request.files_succeeded,
                "files_failed": request.files_failed,
                "bytes_transferred": request.bytes_transferred,
                "error_message": request.error_message,
                "pipeline_run_id": request.pipeline_run_id,
            },
        )
        return {"message": f"Push job {push_job_id} status updated to {request.status}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{push_job_id}", response_model=PushJobDetail)
async def get_push_job(push_job_id: int):
    """Get details of a specific push job."""
    _require_db()
    try:
        row = db.execute_single(
            "SELECT * FROM [dbo].[push_job] WHERE push_job_id = ?",
            (push_job_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Push job {push_job_id} not found")

        return PushJobDetail(**row)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
