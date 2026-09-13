"""Interactive deployment launcher for deploy_fabric_eng targets."""

from __future__ import annotations

from collections import OrderedDict
from typing import Dict

from pathlib import Path

from deploy_fabric_eng import deploy, detect_changed_items, resolve_path
from runtime_target_builder import DEFAULT_TENANT, prepare_runtime_targets


GROUP_ORDER = ["INSIGHTS", "ORCH", "INGESTION", "ORCHESTRATION", "CUST"]
ENVIRONMENT_ORDER = {
    "dev": 1,
    "acc": 2,
    "prd": 3,
    "test": 4,
    "uat": 5,
}


def _kind_label(target: dict) -> str:
    if "kind" in target:
        return target["kind"].upper()
    # Infer from environment suffix (e.g. DEV_C0000_ORCH -> ORCH)
    env = target.get("environment", "")
    suffix = env.rsplit("_", 1)[-1].upper() if env else ""
    if suffix in {"ORCH", "INGESTION", "ORCHESTRATION", "CUST"}:
        return suffix
    return "INSIGHTS"


def _environment_rank(target: dict) -> int:
    environment = target.get("environment", "")
    env_code = environment.split("_", 1)[0].lower() if environment else ""
    return ENVIRONMENT_ORDER.get(env_code, 99)


def _format_table(rows: list[list[str] | None], headers: list[str]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        if row is None:
            continue
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    header_line = "  " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator = "  " + "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    lines = [header_line, separator]
    for row in rows:
        if row is None:
            lines.append("")
            continue
        lines.append("  " + " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)))
    return lines


def _render_grouped_targets(targets: Dict[str, dict]) -> list[str]:
    ordered_names: list[str] = []
    grouped: OrderedDict[str, list[tuple[str, dict]]] = OrderedDict((group, []) for group in GROUP_ORDER)
    for name, target in targets.items():
        label = _kind_label(target)
        if label not in grouped:
            grouped[label] = []
        grouped[label].append((name, target))

    print("\nAvailable deployment targets:\n")
    index = 1
    for group_label, entries in grouped.items():
        if not entries:
            continue

        sorted_entries = sorted(
            entries,
            key=lambda item: (
                item[1].get("customer_name", "").lower(),
                _environment_rank(item[1]),
                item[1].get("workspace_name", "").lower(),
            ),
        )

        rows: list[list[str] | None] = []
        previous_customer = ""
        for name, target in sorted_entries:
            if target.get("hidden"):
                continue
            customer = target.get("customer_name", "")
            if previous_customer and customer != previous_customer:
                rows.append(None)
                rows.append(None)

            ordered_names.append(name)
            rows.append(
                [
                    str(index),
                    name,
                    customer,
                    target.get("environment", ""),
                    target.get("workspace_name", ""),
                    target.get("repository_directory") or "(prompt)",
                ]
            )
            previous_customer = customer
            index += 1

        if not rows:
            continue

        print(group_label)
        for line in _format_table(rows, ["#", "Target", "Customer", "Environment", "Workspace", "Repository"]):
            print(line)
        print()

    return ordered_names


def _pick_target(targets: Dict[str, dict]) -> str:
    names = _render_grouped_targets(targets)

    while True:
        raw = input("\nEnter target number (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(names):
                return names[choice - 1]
        print("Invalid selection. Enter a valid number from the list.")


def _prompt_repository_directory() -> str:
    """Let the user choose an output directory for pinned test targets."""
    from deploy_fabric_eng import LEGACY_TRANSFORM_ROOT, WORKSPACE_ROOT

    candidates: list[str] = []
    for root in (WORKSPACE_ROOT, LEGACY_TRANSFORM_ROOT):
        for d in sorted(root.iterdir()):
            if d.is_dir() and d.name.startswith("output_"):
                if d.name not in candidates:
                    candidates.append(d.name)

    if not candidates:
        raw = input("\nEnter repository directory name: ").strip()
        return raw

    print("\nAvailable output directories:\n")
    for idx, name in enumerate(candidates, 1):
        print(f"  {idx}. {name}")

    while True:
        raw = input("\nEnter number (or type a directory name directly): ").strip()
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
        elif raw:
            return raw
        print("Invalid selection.")


# ---------------------------------------------------------------------------
# Scope / layer filtering
# ---------------------------------------------------------------------------

_FABRIC_SUFFIXES = (
    ".Notebook", ".DataPipeline", ".Lakehouse", ".Environment", ".SQLDatabase",
    ".SemanticModel", ".Report",
)

_LAYER_PREFIXES: dict[str, tuple[str, ...]] = {
    "bronze": ("brz_",),
    "silver": ("slv_",),
    "gold":   ("gld_",),
    "utl":    ("nb_",),
}


def _discover_items_in_repo(repo_dir: str) -> dict[str, Path]:
    """Return {folder_name: absolute_path} for every Fabric artifact found recursively."""
    root = Path(repo_dir)
    items: dict[str, Path] = {}
    for p in root.rglob("*"):
        if p.is_dir() and any(p.name.endswith(s) for s in _FABRIC_SUFFIXES):
            items[p.name] = p
    return items


def _filter_items_by_layer(items: dict[str, Path], layer: str) -> list[str]:
    """Return notebook folder names matching the given layer prefix."""
    prefixes = _LAYER_PREFIXES.get(layer, ())
    return sorted(
        name for name in items
        if name.endswith(".Notebook") and name.lower().startswith(prefixes)
    )


def _filter_semantic_models(items: dict[str, Path]) -> list[str]:
    return sorted(name for name in items if name.endswith(".SemanticModel"))


def _filter_reports(items: dict[str, Path]) -> list[str]:
    return sorted(name for name in items if name.endswith(".Report"))


def _filter_items_by_path_segment(items: dict[str, Path], repo_dir: str, segment: str) -> list[str]:
    """Return item names whose path (relative to repo_dir) contains `segment` as a
    directory component - used for the auth/ folder, which isn't identifiable by
    Fabric-type suffix alone (it's a sibling of ENG/, mixing Notebook + DataPipeline)."""
    root = Path(repo_dir)
    out = []
    for name, p in items.items():
        try:
            parts = p.relative_to(root).parts
        except ValueError:
            continue
        if segment in parts:
            out.append(name)
    return sorted(out)


def _pick_scope(
    repo_dir: str, base_item_types: list[str]
) -> tuple[list[str], list[str] | None]:
    """Ask what to deploy (item type + optional notebook layer).

    Returns (item_types_override, items_to_include_or_None).
    items_to_include_or_None=None means no additional name-level filtering.
    """
    print("\nChoose deployment scope:\n")
    print("  1. All items  (default)")
    print("  2. Notebooks only")
    print("  3. Pipelines only")

    while True:
        raw = input("\nEnter scope number (or 'q' to quit): ").strip()
        if raw in {"", "1"}:
            return base_item_types, None
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if raw == "2":
            item_types = [t for t in base_item_types if t == "Notebook"] or ["Notebook"]
            break
        if raw == "3":
            item_types = [t for t in base_item_types if t == "DataPipeline"] or ["DataPipeline"]
            return item_types, None
        print("Invalid selection.")

    # Notebook scope — ask for layer
    print("\nChoose notebook layer:\n")
    print("  1. All layers  (default)")
    print("  2. Bronze only")
    print("  3. Silver only")
    print("  4. Gold only")
    print("  5. UTL only")

    layer_map = {"2": "bronze", "3": "silver", "4": "gold", "5": "utl"}
    while True:
        raw = input("\nEnter layer number (or 'q' to quit): ").strip()
        if raw in {"", "1"}:
            return item_types, None
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if raw in layer_map:
            layer = layer_map[raw]
            break
        print("Invalid selection.")

    all_items = _discover_items_in_repo(repo_dir)
    layer_items = _filter_items_by_layer(all_items, layer)

    if not layer_items:
        print(f"\n  ⚠ No {layer} notebooks found in {repo_dir} — deploying all notebooks.")
        return item_types, None

    print(f"\n  Deploying {len(layer_items)} {layer} notebook(s):")
    for name in layer_items:
        print(f"    • {name}")

    return item_types, layer_items


# ---------------------------------------------------------------------------


def _pick_mode(changed_items: list[str] | None) -> tuple[bool, list[str] | None]:
    """Return (do_unpublish, items_to_include).
    items_to_include=None means full deploy; a list means changed-only deploy.
    """
    has_changes = changed_items is not None and len(changed_items) > 0
    no_changes  = changed_items is not None and len(changed_items) == 0

    print("\nChoose deployment mode:\n")

    if no_changes:
        print("  No changes detected since last deploy to this workspace.")
        print("  1. Skip  (nothing to deploy)")
        print("  2. Full deploy")
        print("  3. Full deploy + remove orphans")
        options = {"1": "skip", "2": (False, None), "3": (True, None)}
    elif has_changes:
        print(f"  1. Deploy changed items only  ({len(changed_items)} item(s))")
        for item in changed_items:
            print(f"       • {item}")
        print("  2. Full deploy")
        print("  3. Full deploy + remove orphans")
        options = {"1": (False, changed_items), "2": (False, None), "3": (True, None)}
    else:
        # No baseline yet (first deploy or git unavailable)
        print("  1. Full deploy")
        print("  2. Full deploy + remove orphans")
        options = {"1": (False, None), "2": (True, None)}

    while True:
        raw = input("\nEnter mode number (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if raw in options:
            choice = options[raw]
            if choice == "skip":
                print("\nNothing to deploy.")
                raise SystemExit(0)
            return choice
        print("Invalid selection. Enter one of the listed numbers.")


def _preview_changes(
    runtime_info: dict,
    target_name: str,
    target: dict,
    do_unpublish: bool,
    items_to_include: list[str] | None = None,
) -> None:
    print("\nDeployment preview\n")

    repo_dir = resolve_path(target["repository_directory"])
    print(f"  Target name:        {target_name}")
    print(f"  Type:               {_kind_label(target)}")
    print(f"  Tenant:             {target['tenant_id']}")
    print(f"  Workspace name:     {target.get('workspace_name', '')}")
    print(f"  Workspace id:       {target['workspace_id']}")
    print(f"  Environment key:    {target['environment']}")
    print(f"  Source repository:  {repo_dir}")
    print(f"  Item types:         {', '.join(target['item_types'])}")
    print(f"  Mode:               {'Publish + orphan cleanup' if do_unpublish else 'Publish only'}")
    if items_to_include is not None:
        print(f"  Items to deploy:    {len(items_to_include)} item(s)")
        for name in items_to_include:
            print(f"                        • {name}")

    print("\nGenerated file changes")
    for file_name, changed in runtime_info["file_changes"].items():
        state = "UPDATED" if changed else "UNCHANGED"
        print(f"  {file_name:<18} {state}")

    created_placeholders = runtime_info.get("created_placeholders", [])
    if created_placeholders:
        print("\nNew placeholder directories")
        for placeholder in created_placeholders:
            print(f"  + {placeholder}")

    print("\nReplacement preview")
    parameter_payload = runtime_info["parameter_payload"]
    for replacement in parameter_payload.get("find_replace", []):
        value = replacement.get("replace_value", {}).get(target["environment"])
        if value is None:
            continue
        items = ", ".join(replacement.get("item_type", []))
        print(f"  {replacement['find_value']} -> {value} [{items}]")


def _confirm_deploy() -> bool:
    while True:
        raw = input("\nProceed with deployment? (y/N): ").strip().lower()
        if raw in {"", "n", "no"}:
            return False
        if raw in {"y", "yes"}:
            return True
        print("Invalid selection. Enter 'y' or 'n'.")


def main() -> None:
    tenant_id = DEFAULT_TENANT
    print(f"Using default tenant: {tenant_id}")
    print("\nSearching tenant workspaces and generating runtime deployment files...")
    runtime_info = prepare_runtime_targets(tenant_id)
    print(
        f"Generated {runtime_info['target_count']} deploy targets from {runtime_info['workspace_count']} accessible workspaces."
    )
    if runtime_info["unmatched"]:
        print(f"Skipped {len(runtime_info['unmatched'])} workspaces that did not match the customer catalog.")

    targets_config = runtime_info["targets"]
    if not targets_config:
        print("No targets configured in deploy_targets.yml")
        raise SystemExit(1)

    target_name = _pick_target(targets_config)
    target = targets_config[target_name]

    # Detect what changed since the last successful deploy to this workspace.
    workspace_id = target["workspace_id"]
    repo_dir_for_diff = resolve_path(target["repository_directory"]) if target.get("repository_directory") else None
    changed_items = detect_changed_items(repo_dir_for_diff, workspace_id) if repo_dir_for_diff else None

    do_unpublish, items_to_include = _pick_mode(changed_items)

    # Pinned test targets have no fixed output folder — prompt the user
    repo_dir_override: str | None = None
    if not target.get("repository_directory"):
        print("\nThis target has no fixed output directory (it is a test workspace).")
        repo_dir_override = _prompt_repository_directory()
        target = dict(target)
        target["repository_directory"] = repo_dir_override

    # Scope / layer filter (notebooks-only, pipelines-only, or by layer)
    effective_repo_dir = repo_dir_for_diff or (resolve_path(repo_dir_override) if repo_dir_override else None)
    if effective_repo_dir:
        base_item_types = list(target.get("item_types", ["Notebook", "DataPipeline", "Environment", "Lakehouse"]))
        scope_item_types, scope_items = _pick_scope(effective_repo_dir, base_item_types)

        # Apply item-type override
        target = dict(target)
        target["item_types"] = scope_item_types

        # Merge layer filter with any changed-only list from mode picker
        if scope_items is not None:
            if items_to_include is None:
                # Full deploy scoped to a layer
                items_to_include = scope_items
            else:
                # Intersect changed items with selected layer
                scope_set = set(scope_items)
                items_to_include = [i for i in items_to_include if i in scope_set]
                if not items_to_include:
                    print("\n  No changed items in the selected layer — nothing to deploy.")
                    raise SystemExit(0)

    _preview_changes(runtime_info, target_name, target, do_unpublish, items_to_include)

    if not _confirm_deploy():
        print("\nDeployment cancelled.")
        raise SystemExit(0)

    print("\nStarting deployment...")
    deploy(
        target_name,
        unpublish=do_unpublish,
        repository_directory=repo_dir_override,
        token_credential=runtime_info.get("credential"),
        items_to_include=items_to_include,
    )


if __name__ == "__main__":
    main()
