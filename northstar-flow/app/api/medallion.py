from fastapi import APIRouter, Depends, HTTPException, Query
from typing import List, Optional
from app.auth.api_key import verify_api_key
from app.database import db
from app.services.medallion_orchestrator import MedallionOrchestratorService
from app.models.schemas import (
    UpdateMedallionSyncRequest,
    MedallionSyncDetail,
    MedallionOrchestratorStatusResponse,
    B2SPendingBatchItem,
    S2GReadyItem,
    TriggerB2SRequest,
    TriggerS2GRequest,
    MedallionDashboardItem,
    BatchRerunRequest,
    BatchRerunResponse,
)

router = APIRouter(
    prefix="/medallion-sync",
    tags=["Medallion Sync"],
    dependencies=[Depends(verify_api_key)],
)


def _require_db():
    if not db:
        raise HTTPException(status_code=503, detail="Orchestrator database not configured")


@router.put("")
async def update_medallion_sync(request: UpdateMedallionSyncRequest):
    """Update medallion sync status by calling the update_medallion_sync stored procedure."""
    _require_db()
    try:
        db.call_sp(
            "update_medallion_sync",
            params={
                "extract_id": request.extract_id,
                "target_workspace_id": request.target_workspace_id,
                "bronze_status": request.bronze_status,
                "bronze_loaded_at": request.bronze_loaded_at,
                "bronze_file_count": request.bronze_file_count,
                "b2s_status": request.b2s_status,
                "b2s_run_id": request.b2s_run_id,
                "b2s_started_at": request.b2s_started_at,
                "b2s_completed_at": request.b2s_completed_at,
                "b2s_rows_processed": request.b2s_rows_processed,
                "b2s_error": request.b2s_error,
                "s2g_status": request.s2g_status,
                "s2g_run_id": request.s2g_run_id,
                "s2g_started_at": request.s2g_started_at,
                "s2g_completed_at": request.s2g_completed_at,
                "s2g_error": request.s2g_error,
            },
        )
        return {"message": f"Medallion sync updated for extract {request.extract_id}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Medallion Orchestrator endpoints
# ---------------------------------------------------------------------------

@router.post("/orchestrator/start")
async def start_medallion_orchestrator():
    """Start the medallion orchestration background loop."""
    _require_db()
    started = await MedallionOrchestratorService.start()
    if not started:
        raise HTTPException(status_code=409, detail="Medallion orchestrator is already running")
    return {"message": "Medallion orchestrator started", "status": MedallionOrchestratorService.get_status()}


@router.post("/orchestrator/stop")
async def stop_medallion_orchestrator():
    """Stop the medallion orchestration background loop."""
    await MedallionOrchestratorService.stop()
    return {"message": "Medallion orchestrator stopped", "status": MedallionOrchestratorService.get_status()}


@router.get("/orchestrator/status", response_model=MedallionOrchestratorStatusResponse)
async def get_medallion_orchestrator_status():
    """Get current medallion orchestrator status and stats."""
    return MedallionOrchestratorService.get_status()


@router.get("/b2s/pending", response_model=List[B2SPendingBatchItem])
async def get_b2s_pending_batches():
    """Get domain+workspace batches pending B2S processing."""
    _require_db()
    try:
        result = db.call_sp("get_b2s_pending_batches", params={})
        return [B2SPendingBatchItem(**row) for row in result.get("result", [])]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/s2g/ready", response_model=List[S2GReadyItem])
async def get_s2g_ready():
    """Get domain+workspace combos where all B2S are done, ready for S2G."""
    _require_db()
    try:
        result = db.call_sp("get_s2g_ready", params={})
        return [S2GReadyItem(**row) for row in result.get("result", [])]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/b2s/trigger")
async def trigger_b2s_manual(request: TriggerB2SRequest):
    """Manually trigger B2S for a specific domain+workspace (bypasses grace period)."""
    _require_db()

    # Get the pipeline ID for this workspace
    ws = db.execute_single(
        "SELECT [b2s_pipeline_id] FROM [dbo].[target_workspace] WHERE [target_workspace_id] = ?",
        (request.target_workspace_id,),
    )
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace {request.target_workspace_id} not found")
    if not ws.get("b2s_pipeline_id"):
        raise HTTPException(status_code=422, detail="No B2S pipeline configured for this workspace")

    try:
        await MedallionOrchestratorService._trigger_next_b2s(
            request.domain_code,
            request.target_workspace_id,
            ws["b2s_pipeline_id"],
        )
        return {"message": f"B2S triggered for {request.domain_code}/{request.target_workspace_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/s2g/trigger")
async def trigger_s2g_manual(request: TriggerS2GRequest):
    """Manually trigger S2G for a specific domain+workspace."""
    _require_db()

    ws = db.execute_single(
        "SELECT [s2g_pipeline_id] FROM [dbo].[target_workspace] WHERE [target_workspace_id] = ?",
        (request.target_workspace_id,),
    )
    if not ws:
        raise HTTPException(status_code=404, detail=f"Workspace {request.target_workspace_id} not found")
    if not ws.get("s2g_pipeline_id"):
        raise HTTPException(status_code=422, detail="No S2G pipeline configured for this workspace")

    try:
        await MedallionOrchestratorService._trigger_s2g(
            request.domain_code,
            request.target_workspace_id,
            ws["s2g_pipeline_id"],
        )
        return {"message": f"S2G triggered for {request.domain_code}/{request.target_workspace_id}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dashboard", response_model=List[MedallionDashboardItem])
async def get_medallion_dashboard(
    domain_code: Optional[str] = Query(None),
    target_workspace_id: Optional[str] = Query(None),
):
    """Aggregated medallion status dashboard per domain+workspace."""
    _require_db()
    try:
        query = """
            SELECT
                e.[domain_code],
                ms.[target_workspace_id],
                tw.[target_workspace_name],
                SUM(CASE WHEN ms.[bronze_status] = 'LOADED' THEN 1 ELSE 0 END) AS bronze_loaded,
                SUM(CASE WHEN ms.[b2s_status] = 'NOT_STARTED' THEN 1 ELSE 0 END) AS b2s_not_started,
                SUM(CASE WHEN ms.[b2s_status] = 'RUNNING' THEN 1 ELSE 0 END) AS b2s_running,
                SUM(CASE WHEN ms.[b2s_status] = 'SUCCESS' THEN 1 ELSE 0 END) AS b2s_success,
                SUM(CASE WHEN ms.[b2s_status] = 'FAILED' THEN 1 ELSE 0 END) AS b2s_failed,
                SUM(CASE WHEN ms.[b2s_status] = 'SKIPPED' THEN 1 ELSE 0 END) AS b2s_skipped,
                SUM(CASE WHEN ms.[s2g_status] = 'NOT_STARTED' THEN 1 ELSE 0 END) AS s2g_not_started,
                SUM(CASE WHEN ms.[s2g_status] = 'PROCESSING' THEN 1 ELSE 0 END) AS s2g_processing,
                SUM(CASE WHEN ms.[s2g_status] = 'SUCCESS' THEN 1 ELSE 0 END) AS s2g_success,
                SUM(CASE WHEN ms.[s2g_status] = 'FAILED' THEN 1 ELSE 0 END) AS s2g_failed,
                SUM(CASE WHEN ms.[s2g_status] = 'SKIPPED' THEN 1 ELSE 0 END) AS s2g_skipped,
                SUM(CASE WHEN e.[is_late_arrival] = 1 THEN 1 ELSE 0 END) AS late_arrivals
            FROM [dbo].[medallion_sync] ms
            INNER JOIN [dbo].[extract] e ON ms.[extract_id] = e.[extract_id]
            INNER JOIN [dbo].[target_workspace] tw ON ms.[target_workspace_id] = tw.[target_workspace_id]
            WHERE (? IS NULL OR e.[domain_code] = ?)
              AND (? IS NULL OR ms.[target_workspace_id] = ?)
            GROUP BY e.[domain_code], ms.[target_workspace_id], tw.[target_workspace_name]
            ORDER BY e.[domain_code], tw.[target_workspace_name]
        """
        rows = db.execute_query(
            query,
            (domain_code, domain_code, target_workspace_id, target_workspace_id),
        )
        return [MedallionDashboardItem(**row) for row in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Batch Rerun (late arrival recovery)
# ---------------------------------------------------------------------------

@router.post("/batch/rerun", response_model=BatchRerunResponse)
async def batch_rerun(request: BatchRerunRequest):
    """Reset a late-arrival batch for replay or skip.

    lookback_hours=0: Skip/discard — mark late arrivals as SKIPPED.
    lookback_hours>0: Replay — reset B2S/S2G for late arrivals and all
                      extracts within the lookback window.
    """
    _require_db()
    try:
        result = db.call_sp(
            "reset_late_arrival_batch",
            params={
                "domain_code": request.domain_code,
                "lookback_hours": request.lookback_hours,
                "extraction_def": request.extraction_def,
                "package_def": request.package_def,
                "target_workspace_id": request.target_workspace_id,
            },
            output_params=["extracts_reset", "syncs_reset"],
        )

        summary = result["result"][0] if result["result"] else {}
        # Get affected extracts from second result set (if DB driver supports it)
        affected = result["result"][1:] if len(result["result"]) > 1 else []

        return BatchRerunResponse(
            extracts_reset=result["output"].get("extracts_reset", 0),
            syncs_reset=result["output"].get("syncs_reset", 0),
            lookback_hours=request.lookback_hours,
            domain_code=request.domain_code,
            extraction_def=request.extraction_def,
            package_def=request.package_def,
            affected_extracts=affected,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Parameterized route LAST to avoid shadowing fixed paths
# ---------------------------------------------------------------------------

@router.get("/{extract_id}", response_model=List[MedallionSyncDetail])
async def get_medallion_sync(extract_id: int):
    """Get medallion sync status for a specific extract."""
    _require_db()
    try:
        rows = db.execute_query(
            "SELECT * FROM [dbo].[medallion_sync] WHERE extract_id = ?",
            (extract_id,),
        )
        if not rows:
            raise HTTPException(status_code=404, detail=f"No medallion sync found for extract {extract_id}")

        return [MedallionSyncDetail(**row) for row in rows]

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
