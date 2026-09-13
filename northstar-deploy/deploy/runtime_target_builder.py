"""Generate deployment targets and parameter replacements from live Fabric workspaces."""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Tuple

import requests
import yaml

# File-backed MSAL token cache — persists across processes and sessions.
_MSAL_CACHE_FILE = Path.home() / ".cache" / "unison-deploy" / "msal_token_cache.json"
# azure-identity's default public-client app ID (used by InteractiveBrowserCredential too)
_AZURE_SDK_CLIENT_ID = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"


class _AccessToken(NamedTuple):
    """Minimal azure-identity-compatible token container."""
    token: str
    expires_on: int


class MsalCredential:
    """MSAL-backed credential compatible with the azure-identity TokenCredential protocol.

    Attempts silent token acquisition from a file cache first.
    Opens the browser only when no valid cached token exists.
    The cache is shared across processes via a JSON file in the user's home directory.
    """

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id
        self._app = None
        self._cache = None

    def _ensure_app(self) -> None:
        if self._app is not None:
            return
        try:
            import msal
        except ModuleNotFoundError:
            raise RuntimeError("msal is not installed. Run: uv run python deploy\\deploy_cli.py")

        self._cache = msal.SerializableTokenCache()
        if _MSAL_CACHE_FILE.exists():
            try:
                self._cache.deserialize(_MSAL_CACHE_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass  # corrupt cache — start fresh

        self._app = msal.PublicClientApplication(
            _AZURE_SDK_CLIENT_ID,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
            token_cache=self._cache,
        )

    def _save_cache(self) -> None:
        if self._cache and self._cache.has_state_changed:
            _MSAL_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
            _MSAL_CACHE_FILE.write_text(self._cache.serialize(), encoding="utf-8")

    def get_token(self, *scopes, **_kwargs) -> _AccessToken:
        """Return a valid access token, using silent auth when possible."""
        self._ensure_app()
        scope = scopes[0] if scopes else SCOPE

        # --- silent path: reuse cached token / refresh token ---
        accounts = self._app.get_accounts()
        result = None
        if accounts:
            result = self._app.acquire_token_silent([scope], account=accounts[0])

        # --- interactive fallback: open browser once ---
        if not result or "access_token" not in result:
            result = self._app.acquire_token_interactive([scope])

        self._save_cache()

        if "access_token" not in result:
            raise RuntimeError(
                f"Authentication failed: {result.get('error_description', 'unknown error')}"
            )

        expires_on = int(time.time()) + result.get("expires_in", 3600)
        return _AccessToken(token=result["access_token"], expires_on=expires_on)

WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
INS_TRANSFORM_ROOT = WORKSPACE_ROOT / "northstar-formation"
DEPLOY_DIR = Path(__file__).parent
TARGETS_FILE = DEPLOY_DIR / "deploy_targets.yml"
PARAMETERS_FILE = DEPLOY_DIR / "parameter.yml"
DEPLOY_CONFIG_FILE = DEPLOY_DIR / "deploy_config.yml"

SCOPE = "https://api.fabric.microsoft.com/.default"
BASE_URL = "https://api.fabric.microsoft.com/v1"
DEFAULT_TENANT = "unisonfabric.onmicrosoft.com"
WORKSPACE_NAME_PLACEHOLDER = "FEATURE_WS_MMUCAPERA_EU"
PIPELINE_CONNECTION_OLD_ID = "e6971e5f-7b70-4407-8afb-19607abaa274"
PIPELINE_CONNECTION_NEW_ID = "3531b974-b2ad-4161-ae3e-208383cfed31"
# DataPipeline JSON uses "00000000-..." as a self-reference workspace placeholder.
# fabric-cicd resolves it to the authenticated developer's workspace at publish time
# instead of the target workspace ID, producing broken cross-workspace references.
# We substitute it with the correct target workspace ID via parameter.yml.
# Two rules are needed:
#   1. PIPELINE_WORKSPACE_SELF_REF catches the placeholder before fabric-cicd runs
#      (covers future fabric-cicd versions that apply parameter.yml first).
#   2. PIPELINE_WORKSPACE_DEV_ID catches the already-resolved developer workspace ID
#      that fabric-cicd substitutes at publish time (current observed behaviour).
PIPELINE_WORKSPACE_SELF_REF = "00000000-0000-0000-0000-000000000000"
PIPELINE_WORKSPACE_DEV_ID = "71e3043c-7a11-46a6-a654-afd539ec6dc4"  # FEATURE_WS_MMUCAPERA_EU
INSIGHTS_ITEM_TYPES = ["Notebook", "DataPipeline", "Environment", "Lakehouse"]
ORCH_ITEM_TYPES = ["Notebook", "Lakehouse", "SQLDatabase"]
REPO_SLUG_OVERRIDES: Dict[str, str] = {}
CUSTOMERS = [
    {
        "customerCode": "customer0",
        "oldCustomerCode": "customer0",
        "customerName": "CUSTOMER0",
        "location": "EU",
        "customerZone": "z1",
    },
]


def _slugify_customer_name(customer_name: str) -> str:
    override = REPO_SLUG_OVERRIDES.get(customer_name)
    if override:
        return override
    return re.sub(r"[^a-z0-9]+", "", customer_name.lower())


def _match_customer(workspace_name: str) -> dict | None:
    workspace_lower = workspace_name.lower()
    for customer in CUSTOMERS:
        name_slug = _slugify_customer_name(customer["customerName"])
        candidates = {
            customer["customerCode"].lower(),
            customer["oldCustomerCode"].lower(),
            name_slug,
        }
        if any(candidate and candidate in workspace_lower for candidate in candidates):
            return customer
    return None


ENVIRONMENT_ALIASES = {
    "dev": "dev",
    "test": "test",
    "tst": "test",
    "acc": "acc",
    "uat": "uat",
    "prd": "prd",
    "prod": "prd",
}


def _detect_environment(workspace_name: str) -> str | None:
    # Match common workspace suffixes: -dev, -test, -acc, -uat, -prd/-prod
    match = re.search(r"-(dev|test|tst|acc|uat|prd|prod)(?:$|\b)", workspace_name.lower())
    if match:
        return ENVIRONMENT_ALIASES[match.group(1)]
    return None


def _workspace_kind(workspace_name: str) -> str:
    workspace_lower = workspace_name.lower()
    if "orchestration" in workspace_lower:
        return "orchestration"
    if "ws-orch" in workspace_lower or "-orch-" in workspace_lower or re.search(r"\borch\b", workspace_lower):
        return "orch"
    if "ingestion" in workspace_lower or "ingest" in workspace_lower:
        return "ingestion"
    if "cust" in workspace_lower or "customer" in workspace_lower:
        return "cust"
    return "insights"


def _tenant_alias(tenant_id: str) -> str:
    return "unisonfabric"


def _environment_name(environment: str, customer_code: str, kind: str) -> str:
    suffix = kind.upper()
    return f"{environment.upper()}_{customer_code.upper()}_{suffix}"


def _target_name(environment: str, repo_slug: str, kind: str, tenant_id: str) -> str:
    parts = [environment, repo_slug]
    if kind != "insights":
        parts.append(kind)
    parts.append(_tenant_alias(tenant_id))
    return "_".join(parts)


def _target_description(environment: str, kind: str, customer_name: str, workspace_name: str) -> str:
    label_map = {
        "insights": "Insights",
        "orch": "northstar-control",
        "ingestion": "Ingestion",
        "orchestration": "Orchestration",
        "cust": "Customer",
    }
    label = label_map.get(kind, kind.title())
    return f"{environment.title()} workspace {label} ({customer_name}) - {workspace_name}"


def _repository_directory(kind: str, repo_slug: str, env_code: str = "") -> str:
    if kind in {"orch", "orchestration"}:
        suffix = f"_{env_code}" if env_code else ""
        return f"ORC_output_{repo_slug}{suffix}"
    return f"output_{repo_slug}"


def _placeholder_path(repository_directory: str) -> Path:
    # Per-customer northstar-control output folders live inside northstar-control/
    if repository_directory == "northstar-control":
        return WORKSPACE_ROOT / "northstar-control"
    if repository_directory.startswith("ORC_output_"):
        return WORKSPACE_ROOT / "northstar-control" / repository_directory
    return INS_TRANSFORM_ROOT / repository_directory


def _ensure_placeholder(repository_directory: str) -> bool:
    target_dir = _placeholder_path(repository_directory)
    if target_dir.exists():
        return False

    target_dir.mkdir(parents=True, exist_ok=True)
    placeholder = target_dir / "README.md"
    placeholder.write_text(
        "# Placeholder\n\nThis directory was created automatically for deployment target discovery.\n",
        encoding="utf-8",
    )
    return True


def _workspace_name(workspace: dict) -> str:
    return workspace.get("displayName") or workspace.get("name") or ""


def _workspace_id(workspace: dict) -> str:
    return workspace.get("id") or workspace.get("workspaceId") or ""


def _build_targets(workspaces: Iterable[dict], tenant_id: str) -> Tuple[OrderedDict, List[str]]:
    targets: OrderedDict[str, dict] = OrderedDict()
    unmatched: List[str] = []

    sorted_workspaces = sorted(workspaces, key=lambda item: _workspace_name(item).lower())
    for workspace in sorted_workspaces:
        workspace_name = _workspace_name(workspace)
        workspace_id = _workspace_id(workspace)
        if not workspace_name or not workspace_id:
            continue

        customer = _match_customer(workspace_name)
        environment = _detect_environment(workspace_name)
        if customer is None or environment is None:
            unmatched.append(workspace_name)
            continue

        kind = _workspace_kind(workspace_name)
        repo_slug = _slugify_customer_name(customer["customerName"])
        target_name = _target_name(environment, repo_slug, kind, tenant_id)
        if target_name in targets:
            target_name = f"{target_name}_{customer['customerCode']}"

        repository_directory = _repository_directory(kind, repo_slug, environment)
        item_types = ORCH_ITEM_TYPES if kind in {"orch", "orchestration"} else INSIGHTS_ITEM_TYPES

        targets[target_name] = {
            "description": _target_description(environment, kind, customer["customerName"], workspace_name),
            "workspace_id": workspace_id,
            "tenant_id": tenant_id,
            "environment": _environment_name(environment, customer["customerCode"], kind),
            "repository_directory": repository_directory,
            "parameter_file": "parameter.yml",
            "item_types": item_types,
            "workspace_name": workspace_name,
            "customer_name": customer["customerName"],
            "customer_code": customer["customerCode"],
            "kind": kind,
        }

    return targets, unmatched


def _build_parameter_file(targets: OrderedDict[str, dict]) -> dict:
    notebook_replacements: Dict[str, str] = OrderedDict()
    pipeline_name_replacements: Dict[str, str] = OrderedDict()
    pipeline_connection_replacements: Dict[str, str] = OrderedDict()
    pipeline_workspace_id_replacements: Dict[str, str] = OrderedDict()

    for target in targets.values():
        environment = target["environment"]
        workspace_name = target["workspace_name"]
        workspace_id = target["workspace_id"]
        notebook_replacements[environment] = workspace_name
        if "DataPipeline" in target["item_types"]:
            pipeline_name_replacements[environment] = workspace_name
            pipeline_connection_replacements[environment] = PIPELINE_CONNECTION_NEW_ID
            pipeline_workspace_id_replacements[environment] = workspace_id

    find_replace: list[dict] = [
        {
            "find_value": WORKSPACE_NAME_PLACEHOLDER,
            "replace_value": dict(notebook_replacements),
            "item_type": ["Notebook"],
        },
    ]
    if pipeline_name_replacements:
        find_replace += [
            {
                "find_value": WORKSPACE_NAME_PLACEHOLDER,
                "replace_value": dict(pipeline_name_replacements),
                "item_type": ["DataPipeline"],
            },
            {
                "find_value": PIPELINE_CONNECTION_OLD_ID,
                "replace_value": dict(pipeline_connection_replacements),
                "item_type": ["DataPipeline"],
            },
            {
                "find_value": PIPELINE_WORKSPACE_SELF_REF,
                "replace_value": dict(pipeline_workspace_id_replacements),
                "item_type": ["DataPipeline"],
            },
            {
                # fabric-cicd resolves 00000000-... to the developer's workspace at
                # publish time; this rule replaces that resolved ID with the correct
                # target workspace ID so notebook activities point to the right workspace.
                "find_value": PIPELINE_WORKSPACE_DEV_ID,
                "replace_value": dict(pipeline_workspace_id_replacements),
                "item_type": ["DataPipeline"],
            },
        ]

    return {
        "find_replace": find_replace,
        "spark_pool": [],
        "spark_pool_replace_value": [],
        "key_value_replace": [],
        "gateway_binding": [],
        "semantic_model_binding": [],
    }


def _load_deploy_config() -> dict:
    """Load deploy_config.yml (versioned config for pinned entries and hidden names)."""
    if not DEPLOY_CONFIG_FILE.exists():
        return {}
    with open(DEPLOY_CONFIG_FILE, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _load_pinned_targets() -> Dict[str, dict]:
    """Return pinned entries from deploy_config.yml."""
    config = _load_deploy_config()
    return {
        name: dict(target)
        for name, target in (config.get("pinned") or {}).items()
    }


def _load_hidden_target_names() -> set:
    """Return target names to hide from the CLI picker (from deploy_config.yml)."""
    config = _load_deploy_config()
    return set(config.get("hidden") or [])


def _serialize_targets(targets: OrderedDict[str, dict]) -> Dict[str, dict]:
    serializable_targets: Dict[str, dict] = {}
    for target_name, target in targets.items():
        serializable_targets[target_name] = {
            "description": target["description"],
            "workspace_id": target["workspace_id"],
            "tenant_id": target["tenant_id"],
            "environment": target["environment"],
            "repository_directory": target.get("repository_directory"),
            "parameter_file": target["parameter_file"],
            "item_types": target["item_types"],
        }
    return serializable_targets


def _render_yaml(payload: dict) -> str:
    return yaml.safe_dump(payload, sort_keys=False)


def _write_targets_file(targets_content: str) -> None:
    TARGETS_FILE.write_text(targets_content, encoding="utf-8")


def _write_parameter_file(parameters_content: str) -> None:
    PARAMETERS_FILE.write_text(parameters_content, encoding="utf-8")


def _list_workspaces(token: str) -> List[dict]:
    workspaces: List[dict] = []
    url = f"{BASE_URL}/workspaces"
    headers = {"Authorization": f"Bearer {token}"}

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        workspaces.extend(data.get("value", []))
        url = data.get("continuationUri")

    return workspaces


def _get_credential(tenant_id: str) -> MsalCredential:
    """Return an MSAL-backed credential that silently reuses cached tokens."""
    return MsalCredential(tenant_id)


def _get_token(tenant_id: str) -> str:
    try:
        return _get_credential(tenant_id).get_token(SCOPE).token
    except Exception as exc:
        print("\nAuthentication failed:", exc)
        raise SystemExit(1) from exc


def prepare_runtime_targets(tenant_id: str) -> dict:
    # Preserve pinned entries from the existing file before API discovery overwrites it
    pinned_targets = _load_pinned_targets()
    # Preserve hidden flags so they survive the file rewrite
    hidden_names = _load_hidden_target_names()

    try:
        credential = _get_credential(tenant_id)
        token = credential.get_token(SCOPE).token
    except Exception as exc:
        print("\nBrowser authentication failed.")
        raise SystemExit(1) from exc
    workspaces = _list_workspaces(token)
    targets, unmatched = _build_targets(workspaces, tenant_id)

    # Merge pinned targets from deploy_config.yml — always override API-discovered
    # entries so that field overrides (e.g. repository_directory: null) are respected
    for name, pinned in pinned_targets.items():
        targets[name] = pinned

    # Apply hidden flags to matching API-discovered entries
    for name in hidden_names:
        if name in targets:
            targets[name]["hidden"] = True

    if not targets:
        print("No deployable workspaces matched the customer catalog for this tenant.")
        if unmatched:
            print("Accessible workspaces found, but none matched expected patterns:")
            for name in unmatched[:20]:
                print(f"  - {name}")
        raise SystemExit(1)

    created_placeholders: List[str] = []
    for target in targets.values():
        repository_directory = target.get("repository_directory")
        if not repository_directory:
            continue
        if _ensure_placeholder(repository_directory):
            created_placeholders.append(str(_placeholder_path(repository_directory)))

    serialized_targets = _serialize_targets(targets)
    parameter_payload = _build_parameter_file(targets)
    targets_content = _render_yaml({"targets": serialized_targets})
    parameters_content = _render_yaml(parameter_payload)

    previous_targets_content = TARGETS_FILE.read_text(encoding="utf-8") if TARGETS_FILE.exists() else ""
    previous_parameters_content = PARAMETERS_FILE.read_text(encoding="utf-8") if PARAMETERS_FILE.exists() else ""

    _write_targets_file(targets_content)
    _write_parameter_file(parameters_content)

    return {
        "workspace_count": len(workspaces),
        "target_count": len(targets),
        "unmatched": unmatched,
        "targets": targets,
        "parameter_payload": parameter_payload,
        "created_placeholders": created_placeholders,
        "credential": credential,
        "file_changes": {
            "deploy_targets.yml": previous_targets_content != targets_content,
            "parameter.yml": previous_parameters_content != parameters_content,
        },
    }
