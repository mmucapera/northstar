"""
Northstar — Multi-Customer Deploy UI
==========================================
Run with:
    cmd /c "pushd C:\\Users\\MMUCAPER\\Downloads\\00-PRJ\\northstar\\northstar-deploy && uv run streamlit run deploy_ui.py && popd"
"""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import Any

import streamlit as st
import pandas as pd

# Make deploy/ importable
sys.path.insert(0, str(Path(__file__).parent / "deploy"))

# ─────────────────────────────────────────────────────────────────────────────
# Page config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Unison Deploy",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ─────────────────────────────────────────────────────────────────────────────
# Lazy imports (after sys.path setup)
# ─────────────────────────────────────────────────────────────────────────────

from deploy_fabric_eng import deploy, detect_changed_items, resolve_path, save_deploy_state  # noqa: E402
from deploy_cli import (  # noqa: E402
    _discover_items_in_repo,
    _filter_items_by_layer,
    _filter_items_by_path_segment,
    _filter_reports,
    _filter_semantic_models,
)
from generate_seed_sql import (  # noqa: E402
    B2S_PIPELINE_NAME,
    S2G_PIPELINE_NAME,
    DEFAULT_LAKEHOUSE_NAME,
    SQL_DATABASE_ITEM_NAME,
    _list_workspace_items,
    _find_item,
    _get_sql_database_details,
    _initialize_orc_output,
    generate_seed_for_target,
)
from runtime_target_builder import (  # noqa: E402
    DEFAULT_TENANT,
    MsalCredential,
    SCOPE,
    WORKSPACE_ROOT,
    _slugify_customer_name,
    prepare_runtime_targets,
)

# ─────────────────────────────────────────────────────────────────────────────
# Threading: deploy results live in sys.modules so they survive Streamlit
# hot-reloads. Each reload re-imports this module, resetting module-level
# variables — but sys.modules entries persist for the lifetime of the process.
# ─────────────────────────────────────────────────────────────────────────────

_SHARED_KEY = "_unison_deploy_shared"
if _SHARED_KEY not in sys.modules:
    import types as _types
    _shared = _types.ModuleType(_SHARED_KEY)
    _shared.results: dict[str, dict] = {}
    _shared.lock = threading.Lock()
    _shared.output_lines: list[str] = []
    _shared.stop_requested: bool = False
    _shared.paused: bool = False
    _shared.skip_current: bool = False
    sys.modules[_SHARED_KEY] = _shared

# Backfill attributes added in later versions (module survives hot-reloads)
for _bk, _bv in [
    ("output_lines",   []),
    ("stop_requested", False),
    ("paused",         False),
    ("skip_current",   False),
]:
    if not hasattr(sys.modules[_SHARED_KEY], _bk):
        setattr(sys.modules[_SHARED_KEY], _bk, _bv)
del _bk, _bv

_deploy_results: dict[str, dict] = sys.modules[_SHARED_KEY].results
_deploy_lock: threading.Lock = sys.modules[_SHARED_KEY].lock


def _set_result(key: str, **kwargs: Any) -> None:
    with _deploy_lock:
        _deploy_results[key] = {**_deploy_results.get(key, {}), **kwargs}


HISTORY_FILE = Path.home() / ".cache" / "unison-deploy" / "deploy-history.jsonl"
_ACTIVE_DEPLOY_FILE = Path.home() / ".cache" / "unison-deploy" / "active-deploy.json"


def _save_active_deploy(plan: list) -> None:
    import json as _json
    _ACTIVE_DEPLOY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_ACTIVE_DEPLOY_FILE, "w", encoding="utf-8") as f:
        _json.dump({"plan": plan, "saved_at": time.strftime("%Y-%m-%dT%H:%M:%S")}, f)


def _clear_active_deploy() -> None:
    _ACTIVE_DEPLOY_FILE.unlink(missing_ok=True)


def _load_active_deploy() -> list | None:
    import json as _json
    if not _ACTIVE_DEPLOY_FILE.exists():
        return None
    try:
        with open(_ACTIVE_DEPLOY_FILE, "r", encoding="utf-8") as f:
            return _json.load(f).get("plan")
    except Exception:
        return None


def _save_deploy_history(plan: list, snapshot: dict, tenant: str, dry_run: bool) -> None:
    import json as _json
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tenant": tenant,
        "dry_run": dry_run,
        "steps": [],
    }
    for step in plan:
        key = step["key"]
        r = snapshot.get(key, {})
        t = step["target"]
        entry["steps"].append({
            "key": key,
            "customer_name": t.get("customer_name", ""),
            "environment": t.get("environment", ""),
            "kind": t.get("kind", ""),
            "status": r.get("status", "?"),
            "elapsed": round(r["ended"] - r["started"], 1)
                if r.get("started") and r.get("ended") else None,
            "message": r.get("message", ""),
            "dry_run": step.get("dry_run", False),
        })
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")


def _save_interrupted_history(plan: list, tenant: str) -> None:
    """Record a deployment that was stopped mid-way (process killed, Ctrl+C, etc.).
    All steps are marked 'interrupted' since we have no in-memory results.
    """
    import json as _json
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "tenant": tenant,
        "dry_run": False,
        "interrupted": True,
        "steps": [
            {
                "key": step["key"],
                "customer_name": step["target"].get("customer_name", ""),
                "environment": step["target"].get("environment", ""),
                "kind": step["target"].get("kind", ""),
                "status": "interrupted",
                "elapsed": None,
                "message": "Deploy was stopped before completion",
                "dry_run": step.get("dry_run", False),
            }
            for step in plan
        ],
    }
    with open(HISTORY_FILE, "a", encoding="utf-8") as f:
        f.write(_json.dumps(entry) + "\n")


def _load_deploy_history() -> list:
    import json as _json
    if not HISTORY_FILE.exists():
        return []
    entries = []
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(_json.loads(line))
                except Exception:
                    pass
    return list(reversed(entries))  # most recent first


# ─────────────────────────────────────────────────────────────────────────────
# Styling helpers
# ─────────────────────────────────────────────────────────────────────────────

ENV_COLOR  = {"dev": "#1d6fa8", "acc": "#8a6200", "prd": "#2a7d45", "test": "#555"}
KIND_COLOR = {"insights": "#6b3fa0", "orch": "#b84800", "ingestion": "#1a6b5a", "orchestration": "#b84800"}


def _badge(label: str, color: str) -> str:
    return (
        f'<span style="background:{color};color:#fff;padding:2px 8px;border-radius:4px;'
        f'font-size:0.75em;font-weight:600;letter-spacing:.04em">{label.upper()}</span>'
    )


def _env_badge(env: str) -> str:
    return _badge(env, ENV_COLOR.get(env.lower(), "#555"))


def _kind_badge(kind: str) -> str:
    return _badge(kind, KIND_COLOR.get(kind.lower(), "#555"))


def _change_badge(changes: list | None) -> str:
    if changes is None:
        return '<span style="color:#888;font-size:0.82em">— no baseline</span>'
    n = len(changes)
    if n == 0:
        return '<span style="color:#2a7d45;font-size:0.82em">✓ up to date</span>'
    return (
        f'<span style="color:#b84800;font-size:0.82em;font-weight:600">'
        f'🔄 {n} change{"s" if n != 1 else ""}</span>'
    )


# ─────────────────────────────────────────────────────────────────────────────
# Session-state defaults
# ─────────────────────────────────────────────────────────────────────────────

_defaults = {
    "auth_done": False,
    "auto_auth_attempted": False,
    "credential": None,
    "targets": {},
    "workspace_count": 0,
    "changed_only": False,
    "remove_orphans": False,
    "show_summary": True,
    "dry_run": False,
    "hidden_customers": set(),
    "selected": set(),
    "changed_cache": {},       # workspace_id → list[str] | None
    "deploy_phase": None,      # None | "summary" | "recovery_confirm" | "deploying"
    "deploy_plan": [],         # list of plan dicts
    "deploy_scope": "all",     # "all" | "notebooks" | "pipelines"
    "deploy_layers": ["bronze", "silver", "gold", "utl"],  # active layers (notebooks scope only)
    "seed_params": {},         # target_key → {customer_prefix, customer_label, storage_account}
    "deploy_thread": None,
    "last_deploy": None,       # {timestamp, plan, snapshot} shown as banner
    "seed_preview_cache": {}, # step_key → dict of fetched Fabric IDs
    "keep_open": set(),        # customer names whose expanders stay open regardless of selection
    "collapse_all": False,     # one-shot: force-collapses all expanders on next render
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ─────────────────────────────────────────────────────────────────────────────
# Customer defaults
# ─────────────────────────────────────────────────────────────────────────────

# Default blob storage accounts keyed by customer slug → environment → account name.
# Fill in "" when the account is not yet known.
_STORAGE_ACCOUNT_DEFAULTS: dict[str, dict[str, str]] = {
    "customer0": {
        "dev": "",
        "acc": "",
        "prd": "",
    },
}


# ─────────────────────────────────────────────────────────────────────────────
# Helper: derive seed params from target
# ─────────────────────────────────────────────────────────────────────────────

def _default_seed_params(target: dict) -> dict:
    customer_name = target.get("customer_name", "")
    slug = _slugify_customer_name(customer_name) if customer_name else ""
    prefix = slug[:4] if len(slug) > 4 else slug
    # "DEV_C0040_ORCH" → "dev"
    env_raw = target.get("environment", "").split("_")[0].lower()
    storage = (
        target.get("storage_account")
        or _STORAGE_ACCOUNT_DEFAULTS.get(slug, {}).get(env_raw, "")
    )
    return {
        "customer_prefix": target.get("customer_prefix", prefix),
        "customer_label": target.get("customer_label", customer_name.title()),
        "storage_account": storage,
    }


def _seed_preview_rows(params: dict, target: dict, fetched: dict | None = None) -> list[tuple[str, str]]:
    """Return (field, value) rows summarising what generate_seed will write."""
    prefix  = params.get("customer_prefix", "")
    label   = params.get("customer_label", "")
    storage = params.get("storage_account", "")
    code    = target.get("customer_code", "").upper()

    def _fv(key: str) -> str:
        if fetched is None:
            return "⟳ click Fetch"
        if "error" in fetched:
            return f"⚠ {fetched['error'][:80]}"
        return fetched.get(key) or "—"

    rows = [
        ("customer_prefix",   prefix),
        ("customer_label",    label),
        ("storage_account",   storage or "⚠️ not set"),
        ("source_id",         f"{prefix}-adls"),
        ("poller_label",      f"{label} ADLS"),
        ("container",         "outbound"),
        ("sas_token",         "${INS_ORCH_ADLS_SAS_TOKEN_01}"),
        ("workspace_id",      _fv("workspace_id")),
        ("workspace_name",    _fv("workspace_name")),
        ("lakehouse_id",      _fv("lakehouse_id")),
        ("lakehouse_name",    _fv("lakehouse_name")),
        ("b2s_pipeline_id",   _fv("b2s_pipeline_id")),
        ("s2g_pipeline_id",   _fv("s2g_pipeline_id")),
        ("sql_server",        _fv("sql_server")),
        ("sql_database",      _fv("sql_database")),
    ]
    return rows


def _fetch_seed_preview(
    step_key: str,
    insights_target: dict,
    orch_target: dict | None,
    credential,
) -> dict:
    """Fetch live Fabric IDs for summary preview. Results cached in session state."""
    cache = st.session_state.seed_preview_cache
    if step_key in cache:
        return cache[step_key]
    try:
        token = credential.get_token(SCOPE).token

        ins_items = _list_workspace_items(token, insights_target["workspace_id"])
        lh = _find_item(ins_items, DEFAULT_LAKEHOUSE_NAME, "Lakehouse")
        if not lh:
            lh = next((i for i in ins_items if i.get("type") == "Lakehouse"), None)
        b2s = _find_item(ins_items, B2S_PIPELINE_NAME, "DataPipeline")
        s2g = _find_item(ins_items, S2G_PIPELINE_NAME, "DataPipeline")

        result: dict = {
            "workspace_id":    insights_target["workspace_id"],
            "workspace_name":  insights_target.get("workspace_name", ""),
            "lakehouse_id":    lh["id"] if lh else "— not found",
            "lakehouse_name":  lh.get("displayName", "") if lh else "",
            "b2s_pipeline_id": b2s["id"] if b2s else "— not found",
            "s2g_pipeline_id": s2g["id"] if s2g else "— not found",
            "sql_server":      "—",
            "sql_database":    "—",
        }

        if orch_target:
            orch_items = _list_workspace_items(token, orch_target["workspace_id"])
            sql_item = _find_item(orch_items, SQL_DATABASE_ITEM_NAME, "SQLDatabase")
            if not sql_item:
                sql_item = next((i for i in orch_items if i.get("type") == "SQLDatabase"), None)
            if sql_item:
                try:
                    props = _get_sql_database_details(
                        token, orch_target["workspace_id"], sql_item["id"]
                    ).get("properties", {})
                    result["sql_server"]   = props.get("serverFqdn") or props.get("connectionString") or "—"
                    result["sql_database"] = props.get("databaseName") or "—"
                except Exception:
                    pass

        cache[step_key] = result
        return result
    except Exception as exc:
        err = {"error": str(exc)}
        cache[step_key] = err
        return err


# ─────────────────────────────────────────────────────────────────────────────
# Helper: find the matching ORCH target for an INSIGHTS target
# ─────────────────────────────────────────────────────────────────────────────

def _find_insights_peer(orch_target: dict, all_targets: dict) -> tuple[str, dict] | tuple[None, None]:
    """Return (name, target) of the INSIGHTS target matching this ORCH target's env prefix."""
    env_prefix = orch_target.get("environment", "").rsplit("_", 1)[0]  # e.g. DEV_C0040
    for name, t in all_targets.items():
        if t.get("environment", "").startswith(env_prefix) and t.get("kind") == "insights":
            return name, t
    return None, None


# ─────────────────────────────────────────────────────────────────────────────
# Background deployment runner
# ─────────────────────────────────────────────────────────────────────────────

class _StdoutTee:
    """Wraps a file-like stdout to simultaneously append lines to output_lines.
    Used around deploy() calls so fabric-cicd output is also captured.
    """
    def __init__(self, real_stdout, lines: list) -> None:
        self._real = real_stdout
        self._lines = lines
        self._buf = ""

    def write(self, text: str) -> int:
        try:
            self._real.write(text)
        except Exception:
            pass
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self._lines.append(line)
        return len(text)

    def flush(self) -> None:
        if self._buf:
            self._lines.append(self._buf)
            self._buf = ""
        try:
            self._real.flush()
        except Exception:
            pass

    def fileno(self) -> int:
        return self._real.fileno()

    def isatty(self) -> bool:
        return False


def _oprint(*args, sep: str = " ", end: str = "\n", flush: bool = False) -> None:
    """Print to the real terminal AND the UI output buffer.
    Uses sys.__stdout__ (Python's original fd, unaffected by Streamlit's stdout
    wrapping) so terminal output is always correct from the deploy thread.
    """
    text = sep.join(str(a) for a in args) + end
    _real = sys.__stdout__ or sys.stdout
    try:
        _real.write(text)
        if flush:
            _real.flush()
    except Exception:
        pass
    line = text.rstrip("\n")
    sys.modules[_SHARED_KEY].output_lines.append(line)


def _run_deploy_plan(plan: list[dict], credential) -> None:
    """Runs in a background thread. Updates _deploy_results."""
    import importlib
    import generate_seed_sql as _gsql
    importlib.reload(_gsql)            # always use the on-disk version
    _tlog = Path.home() / ".cache" / "unison-deploy" / "thread.log"
    try:
        _tlog.parent.mkdir(parents=True, exist_ok=True)
        with open(_tlog, "a", encoding="utf-8") as _tf:
            _tf.write(f"[{time.strftime('%H:%M:%S')}] thread entered, {len(plan)} steps, "
                      f"keys={[s['key'] for s in plan]}\n")
        _oprint(f"{'='*60}", flush=True)
        _oprint(f"[{time.strftime('%H:%M:%S')}] Deploy started \u2014 {len(plan)} step(s)", flush=True)
        _oprint(f"{'='*60}", flush=True)
        _run_deploy_plan_inner(plan, credential)
        with open(_tlog, "a", encoding="utf-8") as _tf:
            _tf.write(f"[{time.strftime('%H:%M:%S')}] thread completed normally\n")
    except BaseException as _exc:  # catches SystemExit, KeyboardInterrupt, etc.
        import traceback as _traceback
        msg = f"Fatal error in deploy thread: {_exc}\n{_traceback.format_exc()}"
        # mark all still-queued steps as failed so the UI unblocks
        with _deploy_lock:
            for _k in list(_deploy_results.keys()):
                if _deploy_results[_k].get("status") == "queued":
                    _deploy_results[_k] = {"status": "failed", "ended": time.time(), "message": str(_exc)}
        try:
            with open(_tlog, "a", encoding="utf-8") as _tf:
                _tf.write(f"[{time.strftime('%H:%M:%S')}] EXCEPTION: {msg}\n")
        except Exception:
            pass
        try:
            _err_log = Path.home() / ".cache" / "unison-deploy" / "deploy-error.log"
            with open(_err_log, "a", encoding="utf-8") as _f:
                _f.write(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] {msg}\n")
        except Exception:
            pass


def _run_deploy_plan_inner(plan: list[dict], credential) -> None:
    """Actual deploy logic — called from _run_deploy_plan inside a BaseException guard."""
    _sh = sys.modules[_SHARED_KEY]
    # Reset control flags at the start of each fresh deploy run
    _sh.stop_requested = False
    _sh.paused = False
    _sh.skip_current = False

    total = len(plan)
    for idx, step in enumerate(plan, 1):
        # ── Pause gate ────────────────────────────────────────────────────────
        while getattr(_sh, "paused", False):
            if getattr(_sh, "stop_requested", False):
                break
            time.sleep(0.5)

        # ── Stop gate ─────────────────────────────────────────────────────────
        if getattr(_sh, "stop_requested", False):
            with _deploy_lock:
                for _rem in plan[idx - 1:]:
                    if _deploy_results.get(_rem["key"], {}).get("status") == "queued":
                        _deploy_results[_rem["key"]] = {
                            "status": "cancelled", "ended": time.time(),
                            "message": "Stopped by user",
                        }
            _oprint(f"[{time.strftime('%H:%M:%S')}] Deploy stopped by user — remaining steps cancelled", flush=True)
            return
        key = step["key"]
        t   = step["target"]
        env  = t.get("environment", "").split("_")[0].upper()
        kind = t.get("kind", "").upper()
        cust = t.get("customer_name", key)
        tag  = f"{cust} {env} {kind}"
        _set_result(key, status="running", started=time.time())
        _oprint(f"[{time.strftime('%H:%M:%S')}] ({idx}/{total}) ▶ {tag}", flush=True)

        try:
            # --- Generate seed SQL ---
            if step.get("generate_seed"):
                params = step["seed_params"]
                _oprint(f"[{time.strftime('%H:%M:%S')}]   generating seed SQL "
                      f"(prefix={params.get('customer_prefix')}, "
                      f"storage={params.get('storage_account')})", flush=True)
                _set_result(key, status="running", message="Generating seed SQL…")
                generate_seed_for_target(
                    step["insights_target"],
                    step["target"],
                    credential,
                    customer_prefix=params["customer_prefix"],
                    customer_label=params["customer_label"],
                    storage_account=params["storage_account"],
                )
                _oprint(f"[{time.strftime('%H:%M:%S')}]   seed SQL done", flush=True)

            # --- Deploy (skipped in dry-run mode) ---
            if step.get("dry_run"):
                _oprint(f"[{time.strftime('%H:%M:%S')}]   dry-run — skipping Fabric deploy", flush=True)
                _set_result(key, status="done", ended=time.time(),
                            message="dry-run — northstar-control folder generated, no items deployed")
                _oprint(f"[{time.strftime('%H:%M:%S')}]   ✓ {tag} done (dry-run)", flush=True)
                continue

            target_name    = step["target_name"]
            items_to_include = step.get("items_to_include")
            scope_label = f"{len(items_to_include)} items" if items_to_include else "full"
            _oprint(f"[{time.strftime('%H:%M:%S')}]   deploying to Fabric ({scope_label})…", flush=True)
            _set_result(key, message="Deploying…")
            # Wrap deploy() with _StdoutTee so fabric-cicd output also appears in the UI
            _tee_lines = sys.modules[_SHARED_KEY].output_lines
            _tee_real  = sys.__stdout__ or sys.stdout
            _old_stdout = sys.stdout
            sys.stdout  = _StdoutTee(_tee_real, _tee_lines)
            try:
                deploy(
                    target_name,
                    unpublish=step.get("remove_orphans", False),
                    repository_directory=step.get("repo_dir_override"),
                    token_credential=credential,
                    items_to_include=items_to_include,
                )
            finally:
                sys.stdout.flush()
                sys.stdout = _old_stdout
            elapsed = time.time() - _deploy_results.get(key, {}).get("started", time.time())
            _set_result(key, status="done", ended=time.time(), message="")
            _oprint(f"[{time.strftime('%H:%M:%S')}]   ✓ {tag} done ({elapsed:.0f}s)", flush=True)

        except Exception as exc:
            _set_result(key, status="failed", ended=time.time(), message=str(exc))
            _oprint(f"[{time.strftime('%H:%M:%S')}]   ✗ {tag} FAILED: {exc}", flush=True)

        # ── Skip-current override (applied after step completes, regardless of outcome) ──
        if getattr(_sh, "skip_current", False):
            _sh.skip_current = False
            _set_result(key, status="skipped", ended=time.time(), message="Skipped by user")
            _oprint(f"[{time.strftime('%H:%M:%S')}]   ⏭ {tag} marked as skipped by user", flush=True)

    n_ok   = sum(1 for r in _deploy_results.values() if r.get("status") == "done")
    n_fail = sum(1 for r in _deploy_results.values() if r.get("status") == "failed")
    n_skip = sum(1 for r in _deploy_results.values() if r.get("status") in ("skipped", "cancelled"))
    _oprint(f"[{time.strftime('%H:%M:%S')}] Deploy finished — {n_ok} ok / {n_fail} failed / {n_skip} skipped", flush=True)
    _oprint(f"{'='*60}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
# Auth + workspace loading
# ─────────────────────────────────────────────────────────────────────────────

def _do_load(tenant_id: str) -> None:
    st.session_state.auto_auth_attempted = True
    with st.spinner("Authenticating and discovering workspaces…"):
        try:
            credential = MsalCredential(tenant_id)
            runtime_info = prepare_runtime_targets(tenant_id)
            st.session_state.credential = runtime_info.get("credential") or credential
            st.session_state.targets = runtime_info["targets"]
            st.session_state.workspace_count = runtime_info["workspace_count"]
            st.session_state.auth_done = True
            # Pre-select targets that have changes
            changed_cache: dict = {}
            for tname, t in runtime_info["targets"].items():
                repo = t.get("repository_directory")
                wid = t.get("workspace_id", tname)
                if repo:
                    changed = detect_changed_items(resolve_path(repo), wid)
                    changed_cache[wid] = changed
                    if changed and len(changed) > 0:
                        st.session_state.selected.add(tname)
            st.session_state.changed_cache = changed_cache
        except SystemExit:
            st.error("Authentication cancelled or failed.")
        except Exception as e:
            st.error(f"Failed to load workspaces: {e}")


# Auto-authenticate on first load (bypasses the Connect button)
if not st.session_state.auth_done and not st.session_state.auto_auth_attempted:
    _do_load(DEFAULT_TENANT)
    st.rerun()

# ── also in the "Deploy N" button when show_summary is off
# (handled via deploy_phase set below)

# Recovery: restore in-progress deployment after a hot-reload (sys.modules survives)
# OR after a full restart (active-deploy.json survives on disk).
if st.session_state.auth_done and not st.session_state.deploy_phase:
    with _deploy_lock:
        # Only consider a deploy "active in memory" if there are genuinely
        # running/queued steps — completed results don't count.
        _has_active_mem = any(
            r.get("status") in ("queued", "running")
            for r in _deploy_results.values()
        )
    _saved_plan = _load_active_deploy()           # full-restart case
    if _has_active_mem or _saved_plan:
        if _saved_plan and not _has_active_mem:
            # Full restart — saved plan found but nothing running in memory.
            # Record the interrupted deploy in history, then ask user to confirm resume.
            print(f"[{time.strftime('%H:%M:%S')}] Recovering active deployment (plan loaded from disk)")
            try:
                _tenant_now = st.session_state.get("_tenant", "")
                _save_interrupted_history(_saved_plan, _tenant_now)
            except Exception:
                pass
            st.session_state.deploy_plan = _saved_plan
            st.session_state.deploy_phase = "recovery_confirm"
            st.rerun()
        elif _saved_plan:
            # Hot-reload with both disk plan and live in-memory state
            print(f"[{time.strftime('%H:%M:%S')}] Recovering active deployment (plan loaded from disk)")
            try:
                _tenant_now = st.session_state.get("_tenant", "")
                _save_interrupted_history(_saved_plan, _tenant_now)
            except Exception:
                pass
            st.session_state.deploy_plan = _saved_plan
        st.session_state.deploy_phase = "deploying"
        st.session_state.deploy_thread = None  # let thread-start block run
        st.rerun()

# ─────────────────────────────────────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## ⚙️ Options")

    tenant = st.selectbox(
        "Tenant",
        ["unisonfabric.onmicrosoft.com"],
        disabled=st.session_state.auth_done,
    )
    # Store selected tenant for history logging
    st.session_state["_tenant"] = tenant

    if not st.session_state.auth_done:
        st.info("Connecting…", icon="🔌")
    else:
        st.success(
            f"{st.session_state.workspace_count} workspaces loaded",
            icon="✅",
        )
        if st.button("🔄 Refresh Workspaces", width='stretch'):
            for k in ("auth_done", "targets", "credential", "selected", "changed_cache", "deploy_phase",
                      "deploy_plan", "seed_params", "deploy_thread"):
                st.session_state[k] = _defaults[k]
            _deploy_results.clear()
            st.rerun()

    st.divider()

    st.session_state.changed_only = st.toggle(
        "Changed items only",
        value=st.session_state.changed_only,
        help="Only deploy items that changed since the last successful deploy.",
    )
    st.session_state.remove_orphans = st.toggle(
        "Remove orphan items",
        value=st.session_state.remove_orphans,
        help="Delete workspace items that no longer exist in the repo after deploying.",
    )
    st.session_state.dry_run = st.toggle(
        "🧪 Dry run",
        value=st.session_state.dry_run,
        help="Generate northstar-control output folders and seed SQL without actually deploying anything to Fabric.",
    )
    st.session_state.show_summary = st.toggle(
        "Deployment summary before deploying",
        value=st.session_state.show_summary,
        help="Show a review panel before starting the deployment.",
    )

    st.divider()
    st.markdown("#### Scope")

    _scope_options = ["all", "notebooks", "pipelines", "semantic_models", "auth", "reports"]
    _scope_labels  = {
        "all": "All items", "notebooks": "Notebooks only", "pipelines": "Pipelines only",
        "semantic_models": "Semantic models only", "auth": "Auth only",
        "reports": "Reports only (deploys semantic models first)",
    }
    st.session_state.deploy_scope = st.radio(
        "Deploy scope",
        _scope_options,
        index=_scope_options.index(st.session_state.deploy_scope),
        format_func=_scope_labels.get,
        horizontal=True,
        label_visibility="collapsed",
    )

    if st.session_state.deploy_scope == "notebooks":
        _all_layers = ["bronze", "silver", "gold", "utl"]
        selected_layers = st.multiselect(
            "Notebook layers",
            options=_all_layers,
            default=st.session_state.deploy_layers,
            format_func=str.capitalize,
            placeholder="Select layers…",
        )
        if selected_layers != st.session_state.deploy_layers:
            st.session_state.deploy_layers = selected_layers
        if not selected_layers:
            st.caption("⚠️ No layers selected — all notebooks will be deployed.")

    if st.session_state.auth_done and st.session_state.deploy_phase is None:
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("Select all", width='stretch'):
                st.session_state.selected = set(st.session_state.targets.keys())
                for n in st.session_state.targets:
                    st.session_state["cb_" + n] = True
                st.rerun()
        with col_b:
            if st.button("Clear all", width='stretch'):
                st.session_state.selected = set()
                for n in st.session_state.targets:
                    st.session_state["cb_" + n] = False
                # keep all currently-visible expanders open
                st.session_state.keep_open = {
                    t.get("customer_name", "Unknown")
                    for t in st.session_state.targets.values()
                    if not t.get("hidden")
                    and t.get("customer_name") not in st.session_state.hidden_customers
                }
                st.rerun()

        st.markdown("#### Quick filter")

        def _apply(cond):
            st.session_state.selected = {
                n for n, t in st.session_state.targets.items()
                if cond(t)
                and not t.get("hidden")
                and t.get("customer_name", "Unknown") not in st.session_state.hidden_customers
            }
            for n in st.session_state.targets:
                st.session_state["cb_" + n] = n in st.session_state.selected
            st.session_state.keep_open = set()
            st.rerun()

        # ── By kind ──────────────────────────────────────────────────────────
        _c1, _c2 = st.columns(2)
        with _c1:
            if st.button("All Insights", key="flt_insights", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() == "insights")
        with _c2:
            if st.button("All Orch", key="flt_orch", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() in {"orch", "orchestration"})

        # ── Insights by env ──────────────────────────────────────────────────
        st.caption("Insights")
        _c1, _c2, _c3 = st.columns(3)
        with _c1:
            if st.button("ACC", key="flt_ins_acc", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() == "insights"
                       and t.get("environment", "").lower().startswith("acc"))
        with _c2:
            if st.button("DEV", key="flt_ins_dev", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() == "insights"
                       and t.get("environment", "").lower().startswith("dev"))
        with _c3:
            if st.button("PRD", key="flt_ins_prd", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() == "insights"
                       and t.get("environment", "").lower().startswith("prd"))

        # ── Orch by env ──────────────────────────────────────────────────────
        st.caption("Orch")
        _c1, _c2, _c3 = st.columns(3)
        with _c1:
            if st.button("ACC", key="flt_orch_acc", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() in {"orch", "orchestration"}
                       and t.get("environment", "").lower().startswith("acc"))
        with _c2:
            if st.button("DEV", key="flt_orch_dev", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() in {"orch", "orchestration"}
                       and t.get("environment", "").lower().startswith("dev"))
        with _c3:
            if st.button("PRD", key="flt_orch_prd", width='stretch'):
                _apply(lambda t: t.get("kind", "").lower() in {"orch", "orchestration"}
                       and t.get("environment", "").lower().startswith("prd"))

        # ── All kinds by env ─────────────────────────────────────────────────
        st.caption("All")
        _c1, _c2, _c3 = st.columns(3)
        with _c1:
            if st.button("ACC", key="flt_acc", width='stretch'):
                _apply(lambda t: t.get("environment", "").lower().startswith("acc"))
        with _c2:
            if st.button("DEV", key="flt_dev", width='stretch'):
                _apply(lambda t: t.get("environment", "").lower().startswith("dev"))
        with _c3:
            if st.button("PRD", key="flt_prd", width='stretch'):
                _apply(lambda t: t.get("environment", "").lower().startswith("prd"))

        st.markdown("#### View")
        if st.button("Collapse all", width='stretch'):
            st.session_state.collapse_all = True
            st.session_state.keep_open = set()
            st.rerun()

        st.divider()
        st.markdown("#### 🙈 Hidden customers")
        all_customer_names = sorted({
            t.get("customer_name", "Unknown")
            for t in st.session_state.targets.values()
            if not t.get("hidden")
        })
        valid_hidden = sorted(st.session_state.hidden_customers & set(all_customer_names))
        stale_hidden = st.session_state.hidden_customers - set(all_customer_names)
        if stale_hidden:
            st.warning(f"Some hidden customers are not currently visible (PIM?): {', '.join(sorted(stale_hidden))}", icon="⚠️")
        new_hidden = set(st.multiselect(
            "Hide from view",
            options=all_customer_names,
            default=valid_hidden,
            label_visibility="collapsed",
            placeholder="Select customers to hide…",
        ))
        if new_hidden != st.session_state.hidden_customers:
            st.session_state.hidden_customers = new_hidden
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
# Main content
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("## 🚀 Northstar — Multi-Customer Deploy")

if not st.session_state.auth_done:
    st.info("Connecting… please wait.", icon="🔌")
    st.stop()

targets = st.session_state.targets
changed_cache = st.session_state.changed_cache

tab_deploy, tab_output, tab_history = st.tabs(["🚀 Deploy", "📺 Output", "📋 History"])

# ── Deploy tab ─────────────────────────────────────────────────────────────────
with tab_deploy:

    # Last deploy results banner
    if st.session_state.last_deploy:
        ldr = st.session_state.last_deploy
        snap = ldr["snapshot"]
        n_ok   = sum(1 for r in snap.values() if r.get("status") == "done")
        n_fail = sum(1 for r in snap.values() if r.get("status") == "failed")
        b_icon = "✅" if n_fail == 0 else "⚠️"
        dry_label = " (dry run)" if ldr.get("dry_run") else ""
        with st.expander(
            f"{b_icon} Last deploy {ldr['timestamp']}{dry_label}  ·  {n_ok} ok / {n_fail} failed",
            expanded=(n_fail > 0),
        ):
            STATUS_ICON_B = {"queued": "⏳", "running": "🔄", "done": "✅", "failed": "❌"}
            for step in ldr["plan"]:
                key = step["key"]
                r = snap.get(key, {})
                t = step["target"]
                status = r.get("status", "?")
                elapsed = f"  {r['ended'] - r['started']:.0f}s" if r.get("started") and r.get("ended") else ""
                msg = r.get("message", "")
                env = t.get("environment", "").split("_")[0].lower()
                kind = t.get("kind", "")
                s_col, n_col, i_col = st.columns([0.05, 0.55, 0.40])
                s_col.markdown(STATUS_ICON_B.get(status, "?"))
                n_col.markdown(
                    f"**{t.get('customer_name')}** &nbsp;" + _env_badge(env) + "&nbsp;" + _kind_badge(kind),
                    unsafe_allow_html=True,
                )
                i_col.markdown(
                    f"<span style='color:#aaa;font-size:0.85em'>{status}{elapsed}"
                    f"{' — ' + msg if msg else ''}</span>",
                    unsafe_allow_html=True,
                )
            if st.button("✕ Dismiss", key="dismiss_last"):
                st.session_state.last_deploy = None
                st.rerun()

    # ── Recovery confirmation ──────────────────────────────────────────────────
    if st.session_state.deploy_phase == "recovery_confirm":
        plan = st.session_state.deploy_plan
        step_labels = [s.get("label", s.get("key", "?")) for s in plan]
        st.warning(
            f"**A deployment plan was found from a previous session** "
            f"({len(plan)} step{'s' if len(plan) != 1 else ''}: "
            f"{', '.join(step_labels)}).\n\nResume this deployment?",
            icon="⚠️",
        )
        col_yes, col_no, _ = st.columns([1, 1, 6])
        if col_yes.button("▶ Resume", type="primary", key="recovery_resume"):
            st.session_state.deploy_phase = "deploying"
            st.session_state.deploy_thread = None
            st.rerun()
        if col_no.button("✕ Discard", key="recovery_discard"):
            _clear_active_deploy()
            st.session_state.deploy_phase = None
            st.session_state.deploy_plan = []
            st.rerun()

    # ── Active deployment progress ─────────────────────────────────────────────
    if st.session_state.deploy_phase == "deploying":
        plan = st.session_state.deploy_plan

        # Determine whether a new thread needs to start.
        # Read snapshot first so we can check completion state.
        plan_keys = {s["key"] for s in plan}
        current_thread = st.session_state.deploy_thread

        with _deploy_lock:
            snapshot_now = dict(_deploy_results)

        _TERMINAL_ST = ("done", "failed", "cancelled", "skipped")
        all_terminal_now = all(
            snapshot_now.get(k, {}).get("status") in _TERMINAL_ST
            for k in plan_keys
        )

        thread_is_live = (
            current_thread == "recovered"
            or (isinstance(current_thread, threading.Thread) and current_thread.is_alive())
        )

        needs_start = (
            not thread_is_live          # thread stopped or never created
            and not all_terminal_now    # AND results are not already complete
        )

        if needs_start:
            # Check whether a running step exists (genuine mid-deploy page refresh)
            with _deploy_lock:
                is_recovery = any(
                    _deploy_results.get(k, {}).get("status") == "running"
                    for k in plan_keys
                )
            if is_recovery:
                print(f"[{time.strftime('%H:%M:%S')}] Recovered deploy state after page refresh", flush=True)
                st.session_state.deploy_thread = "recovered"
            else:
                _deploy_results.clear()
                for step in plan:
                    _set_result(step["key"], status="queued", message="")
                print(f"[{time.strftime('%H:%M:%S')}] Starting deploy thread — {len(plan)} step(s)", flush=True)
                thread = threading.Thread(
                    target=_run_deploy_plan,
                    args=(plan, st.session_state.credential),
                    daemon=True,
                )
                thread.start()
                st.session_state.deploy_thread = thread

        is_dry = any(s.get("dry_run") for s in plan)
        st.markdown(f"### {'🧪 Dry Run' if is_dry else '🔄 Deploying'}…")

        STATUS_ICON = {"queued": "⏳", "running": "🔄", "done": "✅", "failed": "❌", "cancelled": "🚫", "skipped": "⏭"}
        all_done = True
        with _deploy_lock:
            snapshot = dict(_deploy_results)

        # ── Progress bar ──────────────────────────────────────────────────────
        n_total = len(plan)
        n_done_f = sum(
            1 for s in plan
            if snapshot.get(s["key"], {}).get("status") in ("done", "failed", "cancelled", "skipped")
        )
        prog_pct = n_done_f / n_total if n_total else 0
        st.progress(
            prog_pct,
            text=f"{n_done_f} / {n_total} steps  ({int(prog_pct * 100)}%)",
        )

        # ── Deploy controls (Stop / Pause / Skip) ─────────────────────────────
        _has_running = any(
            snapshot.get(s["key"], {}).get("status") in ("queued", "running") for s in plan
        )
        if _has_running:
            _sh = sys.modules[_SHARED_KEY]
            _is_stopping = getattr(_sh, "stop_requested", False)
            _is_paused   = getattr(_sh, "paused", False)
            _is_skipping = getattr(_sh, "skip_current", False)
            _cc1, _cc2, _cc3, _ = st.columns([0.16, 0.16, 0.2, 0.48])
            if _cc1.button(
                "⏹ Stopping…" if _is_stopping else "⏹ Stop",
                disabled=_is_stopping, width='stretch', key="ctrl_stop",
            ):
                _sh.stop_requested = True
                st.rerun()
            if _cc2.button(
                "▶ Resume" if _is_paused else "⏸ Pause",
                width='stretch', key="ctrl_pause",
            ):
                _sh.paused = not _is_paused
                st.rerun()
            if _cc3.button(
                "⏭ Skipping…" if _is_skipping else "⏭ Skip step",
                disabled=_is_skipping, width='stretch', key="ctrl_skip",
                help="Marks the currently running step as skipped once it finishes.",
            ):
                _sh.skip_current = True
                st.rerun()
            if _is_paused:
                st.warning("⏸ Paused — current step finishes, then waits for Resume.", icon="⏸")
            elif _is_stopping:
                st.warning("⏹ Stopping after current step — remaining steps will be cancelled.", icon="⏹")
        st.write("")

        for step in plan:
            key = step["key"]
            r = snapshot.get(key, {"status": "queued", "message": ""})
            status = r.get("status", "queued")
            if status not in ("done", "failed", "cancelled", "skipped"):
                all_done = False
            t = step["target"]
            env = t.get("environment", "").split("_")[0].lower()
            kind = t.get("kind", "")
            customer = t.get("customer_name", "")
            icon = STATUS_ICON.get(status, "⏳")
            msg = r.get("message", "")
            elapsed = ""
            if r.get("started"):
                end = r.get("ended", time.time())
                elapsed = f"  {end - r['started']:.0f}s"
            s_col, n_col, i_col = st.columns([0.05, 0.60, 0.35])
            s_col.markdown(icon)
            n_col.markdown(
                f"**{customer}** &nbsp;" + _env_badge(env) + "&nbsp;" + _kind_badge(kind),
                unsafe_allow_html=True,
            )
            i_col.markdown(
                f"<span style='color:#aaa;font-size:0.85em'>{status.capitalize()}{elapsed}"
                f"{' — ' + msg if msg else ''}</span>",
                unsafe_allow_html=True,
            )
            if status == "failed":
                st.error(r.get("message", "Unknown error"), icon="❌")

        if not all_done:
            time.sleep(1)
            st.rerun()
        else:
            with _deploy_lock:
                final_snapshot = dict(_deploy_results)
            # Clear the active-deploy marker FIRST so a reload/recovery
            # can never restart this deploy even if the code below raises.
            _clear_active_deploy()
            # Also clear in-memory results so the recovery block doesn't
            # mistake them for an in-progress deploy on the next rerun.
            with _deploy_lock:
                _deploy_results.clear()
            st.session_state.deploy_phase = None
            st.session_state.deploy_thread = None
            st.session_state.last_deploy = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "plan": plan,
                "snapshot": final_snapshot,
                "dry_run": is_dry,
            }
            try:
                _save_deploy_history(
                    plan, final_snapshot,
                    st.session_state.get("_tenant", DEFAULT_TENANT),
                    is_dry,
                )
            except Exception:
                pass
            try:
                for tname, t in targets.items():
                    repo = t.get("repository_directory")
                    wid = t.get("workspace_id", tname)
                    if repo:
                        st.session_state.changed_cache[wid] = detect_changed_items(resolve_path(repo), wid)
            except Exception:
                pass
            st.rerun()

    else:
        # ── Target list ────────────────────────────────────────────────────────
        st.caption(
            f"Tenant: **{tenant}**  ·  {len(targets)} targets  ·  "
            f"{st.session_state.workspace_count} workspaces discovered"
        )
        st.divider()

        customers: dict[str, list[tuple[str, dict]]] = {}
        for tname, t in targets.items():
            if t.get("hidden"):
                continue
            cname = t.get("customer_name", "Unknown")
            if cname in st.session_state.hidden_customers:
                continue
            customers.setdefault(cname, []).append((tname, t))

        for customer_name, entries in sorted(customers.items()):
            n_sel_grp = sum(1 for n, _ in entries if n in st.session_state.selected)
            total_changes = sum(
                len(v) for _, t in entries
                if isinstance((v := changed_cache.get(t.get("workspace_id"))), list) and v
            )

            hdr_parts = [f"**{customer_name}**"]
            if n_sel_grp:
                hdr_parts.append(f"{n_sel_grp}/{len(entries)} selected")
            if total_changes:
                hdr_parts.append(f"🔄 {total_changes} change{'s' if total_changes != 1 else ''}")
            hdr = "  ·  ".join(hdr_parts)

            auto_open = not st.session_state.collapse_all and (
                n_sel_grp > 0 or total_changes > 0 or customer_name in st.session_state.keep_open
            )
            with st.expander(hdr, expanded=auto_open):
                # ✓ All / ✗ None buttons replace checkbox (avoids Streamlit state bugs)
                btn_a, btn_b, _ = st.columns([0.12, 0.12, 0.76])
                if btn_a.button("✓ All", key=f"sel_{customer_name}", width='stretch'):
                    for n, _ in entries:
                        st.session_state.selected.add(n)
                        st.session_state["cb_" + n] = True
                    st.rerun()
                if btn_b.button("✗ None", key=f"desel_{customer_name}", width='stretch'):
                    for n, _ in entries:
                        st.session_state.selected.discard(n)
                        st.session_state["cb_" + n] = False
                    st.session_state.keep_open.add(customer_name)  # stay open after deselect
                    st.rerun()

                hcols = st.columns([0.04, 0.08, 0.10, 0.36, 0.24, 0.18])
                for col, lbl in zip(hcols[1:], ["Env", "Kind", "Workspace", "Changes", "Items"]):
                    col.markdown(f"<span style='color:#666;font-size:0.78em'>{lbl}</span>",
                                 unsafe_allow_html=True)

                _KIND_RANK = {"insights": 0, "orch": 1, "orchestration": 1}
                _ENV_ORDER = {"dev": 0, "acc": 1, "prd": 2}
                for tname, t in sorted(entries,
                        key=lambda x: (
                            _KIND_RANK.get(x[1].get("kind", "").lower(), 9),
                            _ENV_ORDER.get(x[1].get("environment", "").split("_")[0].lower(), 9),
                        )):
                    checked = tname in st.session_state.selected
                    cols = st.columns([0.04, 0.08, 0.10, 0.36, 0.24, 0.18])

                    cb_key = "cb_" + tname
                    if cb_key not in st.session_state:
                        st.session_state[cb_key] = checked
                    new_val = cols[0].checkbox(
                        "##" + tname, key=cb_key,
                        label_visibility="collapsed",
                    )
                    if new_val != checked:
                        if new_val:
                            st.session_state.selected.add(tname)
                        else:
                            st.session_state.selected.discard(tname)
                        st.rerun()

                    env = t.get("environment", "").split("_")[0].lower()
                    kind = t.get("kind", t.get("environment", "").rsplit("_", 1)[-1].lower())
                    wid = t.get("workspace_id", "")
                    changes = changed_cache.get(wid)
                    items_scope = t.get("item_types", [])

                    cols[1].markdown(_env_badge(env), unsafe_allow_html=True)
                    cols[2].markdown(_kind_badge(kind), unsafe_allow_html=True)
                    cols[3].markdown(
                        f"<code style='font-size:0.82em'>{t.get('workspace_name', '')}</code>",
                        unsafe_allow_html=True)
                    cols[4].markdown(_change_badge(changes), unsafe_allow_html=True)
                    cols[5].markdown(
                        f"<span style='color:#888;font-size:0.78em'>"
                        f"{', '.join(items_scope[:2])}{'…' if len(items_scope) > 2 else ''}</span>",
                        unsafe_allow_html=True,
                    )

        # Reset collapse_all after rendering (one-shot flag)
        st.session_state.collapse_all = False

        # ── Deploy bar (hidden while summary or deploying is active) ─────────
        selected_targets = [(n, targets[n]) for n in st.session_state.selected if n in targets]
        n_sel = len(selected_targets)

        if st.session_state.deploy_phase is None:
            dry_run = st.session_state.dry_run
            st.divider()
            if dry_run:
                st.warning(
                    "**🧪 Dry run mode** — northstar-control folders will be generated but nothing will be deployed.",
                    icon="🧪",
                )
            info_col, btn_col = st.columns([0.7, 0.3])
            with info_col:
                if n_sel == 0:
                    st.info("No targets selected.", icon="ℹ️")
                else:
                    cc = st.session_state.changed_cache
                    changed_only = st.session_state.changed_only
                    n_changed = sum(
                        1 for _, t in selected_targets
                        if changed_only and (cc.get(t.get("workspace_id")) or [])
                    )
                    n_full = n_sel - n_changed
                    parts: list[str] = []
                    if n_changed:
                        parts.append(f"{n_changed} changed-only")
                    if n_full:
                        parts.append(f"{n_full} full deploy{'s' if n_full > 1 else ''}")
                    st.success(
                        f"**{n_sel}** target{'s' if n_sel != 1 else ''} selected — {' + '.join(parts)}",
                        icon="✅",
                    )
            with btn_col:
                if st.button(
                    f"🚀  Deploy {n_sel} target{'s' if n_sel != 1 else ''}",
                    disabled=n_sel == 0,
                    width='stretch',
                    type="primary",
                ):
                    plan: list[dict] = []
                    all_tgts = targets
                    _scope  = st.session_state.deploy_scope
                    _layers = st.session_state.deploy_layers
                    for tname, t in selected_targets:
                        kind = t.get("kind", "").lower()
                        wid = t.get("workspace_id", "")
                        cc = st.session_state.changed_cache
                        changed = cc.get(wid)
                        items_to_include = (
                            sorted(changed)
                            if (st.session_state.changed_only and changed) else None
                        )

                        # ── Scope / layer filter ───────────────────────────────────
                        _pending_semantic_model_step: dict | None = None
                        if _scope != "all":
                            repo = t.get("repository_directory")
                            _scope_items: list[str] | None = None
                            if repo:
                                _repo_dir = resolve_path(repo)
                                _all_repo_items = _discover_items_in_repo(_repo_dir)
                                if _scope == "notebooks":
                                    if _layers and len(_layers) < 4:
                                        _layer_names: list[str] = []
                                        for _lyr in _layers:
                                            _layer_names.extend(_filter_items_by_layer(_all_repo_items, _lyr))
                                        _scope_items = sorted(set(_layer_names)) or None
                                    else:
                                        # all notebook layers
                                        _scope_items = sorted(
                                            n for n in _all_repo_items if n.endswith(".Notebook")
                                        ) or None
                                elif _scope == "pipelines":
                                    _scope_items = sorted(
                                        n for n in _all_repo_items if n.endswith(".DataPipeline")
                                    ) or None
                                elif _scope == "semantic_models":
                                    _scope_items = _filter_semantic_models(_all_repo_items) or None
                                elif _scope == "auth":
                                    _scope_items = _filter_items_by_path_segment(
                                        _all_repo_items, _repo_dir, "auth"
                                    ) or None
                                elif _scope == "reports":
                                    _scope_items = _filter_reports(_all_repo_items) or None
                                    # Reports bind to a SemanticModel by id - deploy semantic
                                    # models for this target first, as a separate preceding
                                    # step, so the reference always resolves.
                                    _sm_items = _filter_semantic_models(_all_repo_items)
                                    if _sm_items:
                                        _pending_semantic_model_step = {
                                            "key": f"{tname}__semantic_models",
                                            "target_name": tname,
                                            "target": t,
                                            "items_to_include": _sm_items,
                                            "remove_orphans": False,
                                            "generate_seed": False,
                                            "dry_run": st.session_state.dry_run,
                                            "label": f"{tname} (semantic models)",
                                        }
                            if _scope_items is not None:
                                if items_to_include is None:
                                    items_to_include = _scope_items
                                else:
                                    _scope_set = set(_scope_items)
                                    items_to_include = [
                                        i for i in items_to_include if i in _scope_set
                                    ] or _scope_items
                        if _pending_semantic_model_step is not None:
                            plan.append(_pending_semantic_model_step)
                        step: dict = {
                            "key": tname,
                            "target_name": tname,
                            "target": t,
                            "items_to_include": items_to_include,
                            "remove_orphans": st.session_state.remove_orphans,
                            "generate_seed": False,
                            "dry_run": st.session_state.dry_run,
                        }
                        if kind in {"orch", "orchestration"}:
                            peer_name, insights_peer = _find_insights_peer(t, all_tgts)
                            # Always refresh the seed SQL from live Fabric data so the
                            # ORC_output folder gets correct pipeline/lakehouse IDs even
                            # when the insights peer is not being deployed in this run.
                            step["generate_seed"] = insights_peer is not None
                            step["insights_target"] = insights_peer or t
                            if tname not in st.session_state.seed_params:
                                st.session_state.seed_params[tname] = _default_seed_params(t)
                            step["seed_params"] = st.session_state.seed_params[tname]
                        plan.append(step)

                    _ENV_RANK = {"dev": 0, "acc": 1, "prd": 2, "test": 3, "uat": 4}
                    plan.sort(key=lambda s: (
                        0 if s["target"].get("kind") == "insights" else 1,
                        _ENV_RANK.get(s["target"].get("environment", "").split("_")[0].lower(), 99),
                    ))
                    st.session_state.deploy_plan = plan
                    st.session_state.deploy_phase = (
                        "summary" if st.session_state.show_summary else "deploying"
                    )
                    if st.session_state.deploy_phase == "deploying":
                        st.session_state.deploy_thread = None  # always start fresh
                        _save_active_deploy(plan)
                    dry_tag = " [DRY RUN]" if st.session_state.dry_run else ""
                    print(f"[{time.strftime('%H:%M:%S')}] Deploy button clicked{dry_tag} — "
                          f"{len(plan)} step(s) — phase={st.session_state.deploy_phase}", flush=True)
                    st.rerun()

        # ── Summary panel ────────────────────────────────────────────────────────────
        if st.session_state.deploy_phase == "summary":
            st.divider()
            st.markdown("### 📋 Deployment Summary")
            st.caption("Review before deploying. For ORCH targets, fetch live Fabric IDs to verify resolved values.")

            # ── Confirm / Cancel at the TOP ───────────────────────────────────
            _top_is_dry = any(s.get("dry_run") for s in st.session_state.deploy_plan)
            _top_label = "🧪  Dry Run" if _top_is_dry else "✅  Confirm & Deploy"
            _tc1, _tc2 = st.columns([0.25, 0.75])
            with _tc1:
                if st.button(_top_label, type="primary", width='stretch', key="confirm_top"):
                    _save_active_deploy(st.session_state.deploy_plan)
                    st.session_state.keep_open = set()
                    sys.modules[_SHARED_KEY].output_lines.clear()
                    st.session_state.deploy_phase = "deploying"
                    st.session_state.deploy_thread = None
                    st.rerun()
            with _tc2:
                if st.button("✖  Cancel", width='stretch', key="cancel_top"):
                    _clear_active_deploy()
                    st.session_state.deploy_phase = None
                    st.rerun()
            st.divider()

            for step in st.session_state.deploy_plan:
                t = step["target"]
                env = t.get("environment", "").split("_")[0].lower()
                kind = t.get("kind", "").lower()
                customer = t.get("customer_name", "")
                workspace = t.get("workspace_name", "")
                step_key = step["key"]
                is_orch = kind in {"orch", "orchestration"}

                with st.expander(
                    f"{customer}  ·  {env.upper()}  ·  {kind.upper()}  ·  {workspace}",
                    expanded=is_orch,
                ):
                    items = step.get("items_to_include")
                    if items:
                        st.markdown(f"**Items to deploy ({len(items)}):**")
                        for item in items:
                            st.markdown(f"  - `{item}`")
                    else:
                        st.markdown("**Full deploy** (all item types)")

                    if is_orch:
                        if step.get("generate_seed"):
                            st.markdown("⚙️ **Seed SQL** will be generated before deploying.")
                        else:
                            st.caption("ℹ️ Seed SQL skipped — INSIGHTS target not in this deploy.")

                        # Ensure seed_params exist
                        if step_key not in st.session_state.seed_params:
                            st.session_state.seed_params[step_key] = _default_seed_params(t)
                        params = step.get("seed_params") or st.session_state.seed_params[step_key]

                        c1, c2, c3 = st.columns(3)
                        params["customer_prefix"] = c1.text_input(
                            "Prefix", value=params["customer_prefix"], key=f"pfx_{step_key}"
                        )
                        params["customer_label"] = c2.text_input(
                            "Label", value=params["customer_label"], key=f"lbl_{step_key}"
                        )
                        params["storage_account"] = c3.text_input(
                            "Storage account", value=params["storage_account"], key=f"sa_{step_key}"
                        )
                        if step.get("generate_seed"):
                            step["seed_params"] = params

                        fetched = st.session_state.seed_preview_cache.get(step_key)
                        if fetched is None:
                            with st.spinner("Fetching IDs from Fabric…"):
                                insights_t = step.get("insights_target") or t
                                fetched = _fetch_seed_preview(
                                    step_key, insights_t, t, st.session_state.credential
                                )

                        st.dataframe(
                            pd.DataFrame(
                                _seed_preview_rows(params, t, fetched),
                                columns=["Field", "Value"],
                            ),
                            width='stretch',
                            hide_index=True,
                        )

            st.divider()
            confirm_col, cancel_col = st.columns([0.2, 0.8])
            with confirm_col:
                btn_label = (
                    "🧪  Dry Run"
                    if any(s.get("dry_run") for s in st.session_state.deploy_plan)
                    else "✅  Confirm & Deploy"
                )
                if st.button(btn_label, type="primary", width='stretch', key="confirm_bottom"):
                    _save_active_deploy(st.session_state.deploy_plan)
                    print(f"[{time.strftime('%H:%M:%S')}] Confirm & Deploy clicked — "
                          f"{len(st.session_state.deploy_plan)} step(s)", flush=True)
                    st.session_state.keep_open = set()
                    sys.modules[_SHARED_KEY].output_lines.clear()
                    st.session_state.deploy_phase = "deploying"
                    st.session_state.deploy_thread = None  # always start fresh
                    st.rerun()
            with cancel_col:
                if st.button("✖  Cancel", width='stretch', key="cancel_bottom"):
                    _clear_active_deploy()
                    st.session_state.deploy_phase = None
                    st.rerun()


# ── Output tab ─────────────────────────────────────────────────────────────────
with tab_output:
    st.markdown("### 📺 Deployment Output")
    _out_lines = sys.modules[_SHARED_KEY].output_lines
    if _out_lines:
        col_clr, _ = st.columns([0.15, 0.85])
        if col_clr.button("🗑 Clear", key="clear_output"):
            sys.modules[_SHARED_KEY].output_lines.clear()
            st.rerun()
        st.code("\n".join(_out_lines), language="text")
    else:
        st.info("No output yet. Run a deployment to see output here.", icon="📺")

# ── History tab ─────────────────────────────────────────────────────────────────
with tab_history:
    st.markdown("### 📋 Deployment History")
    st.caption(f"History file: `{HISTORY_FILE}`")
    history = _load_deploy_history()
    if not history:
        st.info("No deployments recorded yet. Run a deployment to see results here.", icon="📭")
    else:
        for entry in history:
            ts    = entry.get("timestamp", "")
            dry   = entry.get("dry_run", False)
            tn    = entry.get("tenant", "")
            steps = entry.get("steps", [])
            interrupted = entry.get("interrupted", False)
            n_ok   = sum(1 for s in steps if s.get("status") == "done")
            n_fail = sum(1 for s in steps if s.get("status") == "failed")
            n_int  = sum(1 for s in steps if s.get("status") == "interrupted")
            if interrupted:
                e_icon = "⚠️"
                summary = f"{len(steps)} steps interrupted (process was stopped)"
            elif dry:
                e_icon = "🧪"
                summary = f"{n_ok} ok / {n_fail} failed  (dry run)"
            else:
                e_icon = "✅" if n_fail == 0 else "⚠️"
                summary = f"{n_ok} ok / {n_fail} failed"
            label = f"{e_icon} {ts}  ·  {tn}  ·  {summary}"
            with st.expander(label, expanded=False):
                if interrupted:
                    st.warning(
                        "This deployment was stopped mid-way. "
                        "Steps below were **planned** but their outcome is unknown. "
                        "Re-deploying will re-run all steps.",
                        icon="⚠️",
                    )
                for s in steps:
                    st_status = s.get("status", "?")
                    s_icon = (
                        "✅" if st_status == "done"
                        else "⚠️" if st_status == "interrupted"
                        else "❌"
                    )
                    elapsed_str = f"  {s['elapsed']:.0f}s" if s.get("elapsed") else ""
                    msg = s.get("message", "")
                    env_str = s.get("environment", "").split("_")[0]
                    st.markdown(
                        f"{s_icon} **{s.get('customer_name')}**"
                        f" {env_str} · {s.get('kind', '')} — {st_status}"
                        f"{elapsed_str}{' — ' + msg if msg else ''}"
                    )
