import os
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx
import streamlit as st
from dotenv import load_dotenv

# Load .env from streamlit_ui root
_env_file = Path(__file__).resolve().parent.parent / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


def _get_env(key: str, default: Optional[str] = None) -> Optional[str]:
    try:
        return st.secrets[key]
    except Exception:
        return os.getenv(key, default)


def _base_url() -> str:
    return _get_env("INS_ORCH_API_URL", "http://localhost:8001")


def _headers() -> Dict[str, str]:
    api_key = _get_env("INS_ORCH_API_KEY", "")
    return {"X-API-Key": api_key, "Content-Type": "application/json"}


def _get(path: str, params: Optional[Dict] = None) -> Dict[str, Any]:
    r = httpx.get(f"{_base_url()}{path}", headers=_headers(), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _post(path: str, json: Optional[Dict] = None, params: Optional[Dict] = None) -> Dict[str, Any]:
    r = httpx.post(f"{_base_url()}{path}", headers=_headers(), json=json, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _put(path: str, json: Optional[Dict] = None) -> Dict[str, Any]:
    r = httpx.put(f"{_base_url()}{path}", headers=_headers(), json=json, timeout=30)
    r.raise_for_status()
    return r.json()


def _delete(path: str) -> None:
    r = httpx.delete(f"{_base_url()}{path}", headers=_headers(), timeout=30)
    r.raise_for_status()


# ---------------------------------------------------------------------------
# Poller (aggregate — backwards compatible)
# ---------------------------------------------------------------------------

def start_poller() -> Dict[str, Any]:
    return _post("/poller/start")


def stop_poller() -> Dict[str, Any]:
    return _post("/poller/stop")


def get_poller_status() -> Dict[str, Any]:
    return _get("/poller/status")


def get_poller_files(status: Optional[str] = None, limit: int = 50, source_id: Optional[str] = None) -> List[Dict]:
    params: Dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    if source_id:
        params["source_id"] = source_id
    return _get("/poller/files", params=params)


# ---------------------------------------------------------------------------
# Poller (per-source)
# ---------------------------------------------------------------------------

def get_poller_sources() -> List[Dict]:
    return _get("/poller/sources")


def start_poller_source(source_id: str) -> Dict[str, Any]:
    return _post(f"/poller/sources/{source_id}/start")


def stop_poller_source(source_id: str) -> Dict[str, Any]:
    return _post(f"/poller/sources/{source_id}/stop")


def get_poller_source_status(source_id: str) -> Dict[str, Any]:
    return _get(f"/poller/sources/{source_id}/status")


def get_poller_source_files(source_id: str, status: Optional[str] = None, limit: int = 50) -> List[Dict]:
    params: Dict[str, Any] = {"limit": limit}
    if status:
        params["status"] = status
    return _get(f"/poller/sources/{source_id}/files", params=params)


def create_poller_source(body: Dict[str, Any]) -> Dict[str, Any]:
    return _post("/poller/sources", json=body)


def update_poller_source(source_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
    return _put(f"/poller/sources/{source_id}", json=body)


def delete_poller_source(source_id: str) -> None:
    _delete(f"/poller/sources/{source_id}")


# ---------------------------------------------------------------------------
# Medallion Orchestrator
# ---------------------------------------------------------------------------

def start_orchestrator() -> Dict[str, Any]:
    return _post("/medallion-sync/orchestrator/start")


def stop_orchestrator() -> Dict[str, Any]:
    return _post("/medallion-sync/orchestrator/stop")


def get_orchestrator_status() -> Dict[str, Any]:
    return _get("/medallion-sync/orchestrator/status")


# ---------------------------------------------------------------------------
# B2S / S2G triggers
# ---------------------------------------------------------------------------

def trigger_b2s(domain_code: str, target_workspace_id: str) -> Dict[str, Any]:
    return _post("/medallion-sync/b2s/trigger", json={
        "domain_code": domain_code,
        "target_workspace_id": target_workspace_id,
    })


def trigger_s2g(domain_code: str, target_workspace_id: str) -> Dict[str, Any]:
    return _post("/medallion-sync/s2g/trigger", json={
        "domain_code": domain_code,
        "target_workspace_id": target_workspace_id,
    })


# ---------------------------------------------------------------------------
# Batch Rerun (late arrival recovery)
# ---------------------------------------------------------------------------

def batch_rerun(
    domain_code: str,
    lookback_hours: int,
    package_def: Optional[str] = None,
    extraction_def: Optional[str] = None,
    target_workspace_id: Optional[str] = None,
) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "domain_code": domain_code,
        "lookback_hours": lookback_hours,
    }
    if package_def:
        body["package_def"] = package_def
    if extraction_def:
        body["extraction_def"] = extraction_def
    if target_workspace_id:
        body["target_workspace_id"] = target_workspace_id
    return _post("/medallion-sync/batch/rerun", json=body)


# ---------------------------------------------------------------------------
# Extracts
# ---------------------------------------------------------------------------

def process_extract(extract_id: int, force: bool = False) -> Dict[str, Any]:
    return _post(f"/extracts/{extract_id}/process", params={"force": str(force).lower()})
