"""
Fabric Deployment Script
========================
Reusable deployment for any workspace/tenant/customer.

Usage:
    python deploy_fabric_eng.py <target>                  # publish items
    python deploy_fabric_eng.py <target> --unpublish      # also remove orphans
    python deploy_fabric_eng.py --list                    # list available targets

Targets are defined in deploy_targets.yml.
"""

import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

TARGETS_FILE = Path(__file__).parent / "deploy_targets.yml"
WORKSPACE_ROOT = Path(__file__).resolve().parents[2]
LEGACY_TRANSFORM_ROOT = WORKSPACE_ROOT / "northstar-formation"

# Per-workspace deploy-state tracking (stores last deployed git commit SHA)
_DEPLOY_STATE_DIR = Path.home() / ".cache" / "unison-deploy" / "deploy-state"


# ---------------------------------------------------------------------------
# Git-based change detection
# ---------------------------------------------------------------------------

def _git_root(path: str) -> Path | None:
    """Return the git repository root that contains *path*, or None."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=path, check=True,
        )
        return Path(r.stdout.strip())
    except Exception:
        return None


def _current_git_commit(path: str) -> str | None:
    """Return the current HEAD commit SHA for the repo at *path*, or None."""
    try:
        r = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, cwd=path, check=True,
        )
        return r.stdout.strip()
    except Exception:
        return None


def detect_changed_items(repo_dir: str, workspace_id: str) -> list[str] | None:
    """Return Fabric items changed since the last deploy to *workspace_id*.

    Each entry is ``"ItemName.ItemType"`` (e.g. ``"MyNotebook.Notebook"``).

    Returns ``None`` when the baseline is unknown (first run → full deploy).
    Returns ``[]`` when nothing changed.
    """
    state_file = _DEPLOY_STATE_DIR / f"{workspace_id}.txt"
    if not state_file.exists():
        return None  # No baseline — must do full deploy

    last_commit = state_file.read_text(encoding="utf-8").strip()
    if not last_commit:
        return None

    root = _git_root(repo_dir)
    if root is None:
        return None  # Not a git repo

    repo_path = Path(repo_dir).resolve()
    try:
        rel_pathspec = str(repo_path.relative_to(root))
    except ValueError:
        rel_pathspec = str(repo_path)

    try:
        r = subprocess.run(
            ["git", "diff", "--name-only", last_commit, "HEAD", "--", rel_pathspec],
            capture_output=True, text=True, cwd=str(root), check=True,
        )
    except subprocess.CalledProcessError:
        return None  # git error — fall back to full deploy

    changed_files = [f for f in r.stdout.strip().splitlines() if f]
    if not changed_files:
        return []

    items: set[str] = set()
    for file_path in changed_files:
        full = (root / file_path).resolve()
        try:
            rel = full.relative_to(repo_path)
        except ValueError:
            continue
        if not rel.parts:
            continue
        item_folder = rel.parts[0]          # e.g. "MyNotebook.Notebook"
        if "." in item_folder:
            items.add(item_folder)

    return sorted(items)


def save_deploy_state(workspace_id: str, repo_dir: str) -> None:
    """Record the current HEAD commit as the successful deploy baseline."""
    commit = _current_git_commit(repo_dir)
    if commit:
        _DEPLOY_STATE_DIR.mkdir(parents=True, exist_ok=True)
        (_DEPLOY_STATE_DIR / f"{workspace_id}.txt").write_text(commit, encoding="utf-8")


def load_targets() -> dict:
    with open(TARGETS_FILE) as f:
        return yaml.safe_load(f)


def resolve_path(relative_path: str) -> str:
    """Resolve a repo path from workspace root, with northstar-control/ subfolder and northstar-formation fallbacks."""
    # Per-customer northstar-control output folders now live under northstar-control/
    if relative_path.startswith("ORC_output_"):
        orc_candidate = (WORKSPACE_ROOT / "northstar-control" / relative_path).resolve()
        if orc_candidate.exists():
            return str(orc_candidate)

    root_candidate = (WORKSPACE_ROOT / relative_path).resolve()
    if root_candidate.exists():
        return str(root_candidate)

    legacy_candidate = (LEGACY_TRANSFORM_ROOT / relative_path).resolve()
    if legacy_candidate.exists():
        return str(legacy_candidate)

    # Default: ORC_output_* → northstar-control/ subfolder; everything else → workspace root
    if relative_path.startswith("ORC_output_"):
        return str(WORKSPACE_ROOT / "northstar-control" / relative_path)
    return str(root_candidate)


_RESERVED_LOGICAL_ID = "00000000-0000-0000-0000-000000000000"


def _preflight_check_logical_ids(repo_dir: Path) -> None:
    """Refuse to publish when any .platform holds the reserved all-zeros logicalId.

    fabric-cicd's _replace_logical_ids substitutes every occurrence of a logicalId
    with that item's deployed guid — including inside pipeline JSON `workspaceId`
    placeholders, which use the same all-zeros value. That collision silently
    rewrites every activity's workspaceId to point at a random unrelated item.
    """
    import json as _json
    offenders: list[tuple[str, str]] = []
    for platform in Path(repo_dir).rglob(".platform"):
        try:
            data = _json.loads(platform.read_text(encoding="utf-8"))
        except Exception:
            continue
        lid = (data.get("config") or {}).get("logicalId", "")
        if lid == _RESERVED_LOGICAL_ID:
            name = (data.get("metadata") or {}).get("displayName", platform.parent.name)
            offenders.append((name, str(platform.relative_to(repo_dir))))
    if offenders:
        lines = "\n".join(f"    - {n}  ({p})" for n, p in offenders)
        raise RuntimeError(
            "Refusing to publish: the following items have logicalId set to the "
            "reserved workspaceId placeholder (00000000-0000-0000-0000-000000000000), "
            "which collides with fabric-cicd's logicalId replacement pass and rewrites "
            "every DataPipeline activity's workspaceId to point at these items.\n"
            f"{lines}\n"
            "  Fix: replace each .platform's config.logicalId with a fresh UUID."
        )


def _filter_parameter_file(param_path: Path, item_types: list[str]) -> Path:
    """Return a path to a parameter file whose find_replace entries only reference
    item types that are actually in scope.  When all entries survive filtering the
    original file is returned unchanged.  Otherwise a NamedTemporaryFile is written
    and its path is returned; the file is placed in the system temp directory and
    will be cleaned up by the OS on next boot (acceptable for a CLI tool).
    """
    if not param_path.exists():
        return param_path

    with open(param_path, encoding="utf-8") as f:
        payload: dict = yaml.safe_load(f) or {}

    scope = set(item_types)
    original_rules: list = payload.get("find_replace") or []
    filtered_rules = [
        rule for rule in original_rules
        if not rule.get("item_type") or scope.intersection(rule["item_type"])
    ]

    if len(filtered_rules) == len(original_rules):
        return param_path  # nothing was removed — use original file as-is

    filtered_payload = {**payload, "find_replace": filtered_rules}
    tmp = tempfile.NamedTemporaryFile(
        mode="w", suffix=".yml", prefix="parameter_filtered_",
        delete=False, encoding="utf-8",
    )
    yaml.dump(filtered_payload, tmp, default_flow_style=False, sort_keys=False)
    tmp.close()
    return Path(tmp.name)


def deploy(
    target_name: str,
    unpublish: bool = False,
    repository_directory: str | None = None,
    token_credential=None,
    items_to_include: list[str] | None = None,
):
    targets = load_targets()

    if target_name not in targets["targets"]:
        available = list(targets["targets"].keys())
        raise RuntimeError(f"Unknown target '{target_name}'. Available: {available}")

    target = targets["targets"][target_name]
    workspace_id = target["workspace_id"]
    effective_repo_dir = repository_directory or target.get("repository_directory")
    if not effective_repo_dir:
        raise RuntimeError(f"No repository directory configured for target '{target_name}'")
    repo_dir = resolve_path(effective_repo_dir)
    item_types = target.get("item_types", ["Notebook", "DataPipeline", "Environment", "Lakehouse"])
    environment = target.get("environment", target_name)
    parameter_file = target.get("parameter_file")
    tenant_id = target.get("tenant_id")

    import logging
    import os
    if os.environ.get("DEPLOY_DEBUG"):
        logging.basicConfig(level=logging.DEBUG)
        logging.getLogger("fabric_cicd").setLevel(logging.DEBUG)

    print(f"{'='*60}")
    print(f"  Target:      {target_name}")
    print(f"  Workspace:   {workspace_id}")
    if tenant_id:
        print(f"  Tenant:      {tenant_id}")
    print(f"  Repository:  {repo_dir}")
    print(f"  Item types:  {item_types}")
    print(f"  Environment: {environment}")
    if parameter_file:
        print(f"  Parameters:  {parameter_file}")
    print(f"{'='*60}\n")

    _preflight_check_logical_ids(Path(repo_dir))

    try:
        from fabric_cicd import FabricWorkspace, publish_all_items, unpublish_all_orphan_items
    except ModuleNotFoundError as exc:
        missing = getattr(exc, "name", "required package")
        raise RuntimeError(
            f"Missing dependency '{missing}'. Run: uv run python deploy\\deploy_cli.py"
        ) from exc

    # Reuse a credential passed in from the caller (e.g. deploy_cli already authenticated).
    # Fall back to a fresh MSAL credential (silent-first) when called standalone.
    if token_credential is None:
        from runtime_target_builder import MsalCredential
        token_credential = MsalCredential(tenant_id or "organizations")

    # Build kwargs
    kwargs = dict(
        workspace_id=workspace_id,
        repository_directory=repo_dir,
        item_type_in_scope=item_types,
        token_credential=token_credential,
    )
    if parameter_file:
        raw_param_path = (Path(__file__).parent / parameter_file).resolve()
        effective_param_path = _filter_parameter_file(raw_param_path, item_types)
        kwargs["parameter_file_path"] = str(effective_param_path)
        kwargs["environment"] = environment

    target_workspace = FabricWorkspace(**kwargs)

    if items_to_include is not None:
        from fabric_cicd import append_feature_flag
        append_feature_flag("enable_experimental_features")
        append_feature_flag("enable_items_to_include")
        print(f"Publishing {len(items_to_include)} changed item(s)...")
        for item in items_to_include:
            print(f"  • {item}")
        publish_all_items(target_workspace, items_to_include=items_to_include)
    else:
        print("Publishing all items...")
        publish_all_items(target_workspace)
    print("Publish complete")

    save_deploy_state(workspace_id, repo_dir)

    if unpublish:
        if items_to_include is not None:
            # Selective publish + orphan cleanup is destructive: fabric-cicd only
            # publishes the listed items but orphan cleanup scans the whole
            # workspace against the whole local repo. Any item not on disk (e.g.
            # because a customer output was generated with different flags) will
            # be deleted, even though it wasn't in the selective set.
            print(
                "  ⚠ Skipping orphan cleanup because items_to_include is set. "
                "Run a FULL deploy to remove orphans."
            )
        else:
            print("Removing orphan items...")
            try:
                unpublish_all_orphan_items(target_workspace)
                print("✔ Orphan cleanup complete")
            except Exception as exc:
                print(f"  ⚠ Orphan cleanup encountered an error (continuing): {exc}")

    # Deploy SQL schema when the target includes a SQLDatabase item type.
    # fabric-cicd only creates the item shell — stored procedures and tables
    # must be pushed separately.
    if "SQLDatabase" in item_types:
        sql_dir = (Path(repo_dir) / "northstar_control.SQLDatabase").resolve()
        if not sql_dir.exists():
            # Fall back to scanning for any .SQLDatabase folder in repo_dir
            candidates = list(Path(repo_dir).glob("*.SQLDatabase"))
            sql_dir = candidates[0] if candidates else None

        if sql_dir and sql_dir.exists():
            from deploy_sql_schema import deploy_sql_schema
            deploy_sql_schema(
                workspace_id=workspace_id,
                token_credential=token_credential,
                sql_dir=sql_dir,
            )
        else:
            print("\n  ⚠ SQLDatabase schema directory not found — skipping SP deployment.")


def list_targets():
    targets = load_targets()
    print("Available deployment targets:\n")
    for name, cfg in targets["targets"].items():
        desc = cfg.get("description", "")
        print(f"  {name:<20} {desc}")
    print()


if __name__ == "__main__":
    if "--list" in sys.argv:
        list_targets()
        sys.exit(0)

    if len(sys.argv) < 2:
        print("Usage: python deploy_fabric_eng.py <target> [--unpublish]")
        print("       python deploy_fabric_eng.py --list")
        sys.exit(1)

    target_name = sys.argv[1]
    do_unpublish = "--unpublish" in sys.argv

    deploy(target_name, unpublish=do_unpublish)