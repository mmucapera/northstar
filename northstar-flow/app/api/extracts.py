from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.auth.api_key import verify_api_key
from app.database import db
from app.services.fabric_notebook import trigger_notebook
from app.models.schemas import (
    RegisterExtractRequest,
    RegisterExtractResponse,
    ExtractDetail,
    PendingExtractItem,
    NotebookTriggerResponse,
)

router = APIRouter(
    prefix="/extracts",
    tags=["Extracts"],
    dependencies=[Depends(verify_api_key)],
)


def _require_db():
    if not db:
        raise HTTPException(status_code=503, detail="Orchestrator database not configured")


@router.post("", response_model=RegisterExtractResponse)
async def register_extract(request: RegisterExtractRequest):
    """Register a new extract by calling the register_extract stored procedure."""
    _require_db()
    try:
        result = db.call_sp(
            "register_extract",
            params={
                "folder_path": request.folder_path,
                "domain_code": request.domain_code,
                "source_code": request.source_code,
                "folder_name": request.folder_name,
                "period_year": request.period_year,
                "period_month": request.period_month,
                "period_day": request.period_day,
                "period_label": request.period_label,
                "file_count": request.file_count,
                "total_size_bytes": request.total_size_bytes,
            },
            output_params=["extract_id"],
        )

        extract_id = (
            result["output"].get("extract_id")
            or (result["result"][0].get("extract_id") if result["result"] else None)
        )

        if extract_id is None:
            raise HTTPException(status_code=500, detail="Failed to retrieve extract_id from stored procedure")

        return RegisterExtractResponse(extract_id=extract_id)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending", response_model=List[PendingExtractItem])
async def get_pending_extracts(
    domain_code: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
):
    """Get pending extracts by calling the get_pending_extracts stored procedure."""
    _require_db()
    try:
        result = db.call_sp(
            "get_pending_extracts",
            params={
                "domain_code": domain_code,
                "limit": limit,
            },
        )
        return [PendingExtractItem(**row) for row in result.get("result", [])]

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{extract_id}", response_model=ExtractDetail)
async def get_extract(extract_id: int):
    """Get details of a specific extract."""
    _require_db()
    try:
        row = db.execute_single(
            "SELECT * FROM [dbo].[extract] WHERE extract_id = ?",
            (extract_id,),
        )
        if not row:
            raise HTTPException(status_code=404, detail=f"Extract {extract_id} not found")

        return ExtractDetail(**row)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{extract_id}/process", response_model=NotebookTriggerResponse)
async def process_extract(
    extract_id: int,
    force: bool = Query(False, description="Force re-trigger even if already processing/pushed"),
):
    """Trigger the Fabric notebook to process a registered extract."""
    _require_db()

    row = db.execute_single(
        "SELECT source_file_name, folder_path, status FROM [dbo].[extract] WHERE extract_id = ?",
        (extract_id,),
    )
    if not row:
        raise HTTPException(status_code=404, detail=f"Extract {extract_id} not found")

    # E4: Status guard — only allow trigger for eligible states unless force=True
    extract_status = row.get("status", "")
    allowed_statuses = {"NEW", "TRIGGERED", "FAILED"}
    if not force and extract_status not in allowed_statuses:
        raise HTTPException(
            status_code=409,
            detail=f"Extract {extract_id} is in '{extract_status}' state. Use ?force=true to re-trigger.",
        )

    # Reset status to TRIGGERED so the notebook's atomic claim succeeds
    if force and extract_status not in allowed_statuses:
        db.execute_query(
            "UPDATE [dbo].[extract] SET [status] = 'TRIGGERED', [updated_at] = SYSUTCDATETIME() "
            "WHERE [extract_id] = ?",
            (extract_id,),
        )

    # E3: Fall back to folder_path if source_file_name is missing
    file_name = row.get("source_file_name") or row.get("folder_path") or ""
    if not file_name:
        raise HTTPException(
            status_code=422,
            detail=f"Extract {extract_id} has no source_file_name or folder_path — cannot determine file to process",
        )

    try:
        result = trigger_notebook(extract_id, file_name)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Fabric API error: {e}")

    if result is None:
        raise HTTPException(
            status_code=503,
            detail="Notebook trigger not configured (INS_ORCH_FABRIC_WORKSPACE_ID / INS_ORCH_NOTEBOOK_ID missing)",
        )

    return NotebookTriggerResponse(
        extract_id=extract_id,
        job_instance_id=result.get("job_instance_id"),
        status_url=result.get("status_url"),
        message=f"Notebook triggered for extract {extract_id} (status was '{extract_status}')",
    )
