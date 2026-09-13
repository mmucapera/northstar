from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from app.auth.api_key import verify_api_key
from app.config import ADLSSourceConfig, _interpolate_env_vars
from app.services.poller_registry import PollerRegistry
from app.models.schemas import (
    PollerStatusResponse, PollerFileItem, PollerSourceInfo,
    PollerSourceCreate, PollerSourceUpdate,
)

router = APIRouter(
    prefix="/poller",
    tags=["Poller"],
    dependencies=[Depends(verify_api_key)],
)


def _require_sources():
    if not PollerRegistry.has_sources():
        raise HTTPException(
            status_code=503,
            detail="No ADLS poller sources configured",
        )


# ------------------------------------------------------------------
# Backwards-compatible aggregate endpoints
# ------------------------------------------------------------------


@router.post("/start")
async def start_all_pollers():
    """Start all enabled ADLS polling sources."""
    _require_sources()

    results = await PollerRegistry.start_all()
    started = [sid for sid, ok in results.items() if ok]
    skipped = [sid for sid, ok in results.items() if not ok]

    if not started and skipped:
        raise HTTPException(status_code=409, detail="All pollers already running or disabled")

    return {
        "message": f"Started {len(started)} poller(s)",
        "started": started,
        "skipped": skipped,
        "status": PollerRegistry.get_aggregate_status().model_dump(),
    }


@router.post("/stop")
async def stop_all_pollers():
    """Stop all ADLS polling sources."""
    await PollerRegistry.stop_all()
    return {
        "message": "All pollers stopped",
        "status": PollerRegistry.get_aggregate_status().model_dump(),
    }


@router.get("/status", response_model=PollerStatusResponse)
async def get_poller_status():
    """Get aggregate poller status across all sources."""
    return PollerRegistry.get_aggregate_status()


@router.get("/files", response_model=List[PollerFileItem])
async def get_detected_files(
    source_id: Optional[str] = Query(None, description="Filter by source ID"),
    status: Optional[str] = Query(None, description="Filter by status (REGISTERED or FAILED)"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query files detected by the poller (all sources or filtered)."""
    try:
        return PollerRegistry.get_all_files(limit=limit, status_filter=status, source_id=source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# Source-scoped endpoints
# ------------------------------------------------------------------


@router.get("/sources", response_model=List[PollerSourceInfo])
async def list_sources():
    """List all configured ADLS polling sources with their status."""
    return PollerRegistry.list_sources()


@router.get("/sources/{source_id}/status", response_model=PollerStatusResponse)
async def get_source_status(source_id: str):
    """Get status for a specific ADLS source."""
    try:
        return PollerRegistry.get_source_status(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sources/{source_id}/start")
async def start_source(source_id: str):
    """Start polling for a specific ADLS source."""
    try:
        started = await PollerRegistry.start_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not started:
        raise HTTPException(status_code=409, detail=f"Poller '{source_id}' is already running")

    return {
        "message": f"Poller '{source_id}' started",
        "status": PollerRegistry.get_source_status(source_id).model_dump(),
    }


@router.post("/sources/{source_id}/stop")
async def stop_source(source_id: str):
    """Stop polling for a specific ADLS source."""
    try:
        await PollerRegistry.stop_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "message": f"Poller '{source_id}' stopped",
        "status": PollerRegistry.get_source_status(source_id).model_dump(),
    }


@router.get("/sources/{source_id}/files", response_model=List[PollerFileItem])
async def get_source_files(
    source_id: str,
    status: Optional[str] = Query(None, description="Filter by status (REGISTERED or FAILED)"),
    limit: int = Query(50, ge=1, le=500),
):
    """Query files detected by a specific source."""
    try:
        return PollerRegistry.get_source_files(source_id, limit=limit, status_filter=status)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ------------------------------------------------------------------
# Source management (DB-backed CRUD)
# ------------------------------------------------------------------


@router.post("/sources", response_model=PollerSourceInfo, status_code=201)
async def create_source(body: PollerSourceCreate):
    """Add a new ADLS polling source (persisted to database)."""
    config = ADLSSourceConfig(
        id=body.source_id,
        label=body.label,
        storage_account=body.storage_account,
        container=body.container,
        folder_path=body.folder_path,
        sas_token=body.sas_token,
        poll_interval_seconds=body.poll_interval_seconds,
        enabled=body.enabled,
        filename_extension=body.filename_extension,
        filename_must_contain=body.filename_must_contain,
        filename_pattern=body.filename_pattern,
        source_code=body.source_code,
        source_file_format=body.source_file_format,
        domain_code_map=body.domain_code_map,
    )
    try:
        return await PollerRegistry.add_source(config)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.put("/sources/{source_id}", response_model=PollerSourceInfo)
async def update_source(source_id: str, body: PollerSourceUpdate):
    """Update an existing ADLS polling source config."""
    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        return await PollerRegistry.update_source(source_id, updates)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.delete("/sources/{source_id}", status_code=204)
async def delete_source(source_id: str):
    """Remove an ADLS polling source (stops poller, deletes from database)."""
    try:
        await PollerRegistry.remove_source(source_id)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
