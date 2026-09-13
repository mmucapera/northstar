#generate_fabric_assets.py

from __future__ import annotations

import argparse
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
import yaml


# ============================================================
# Utilities
# ============================================================

class PipelineGenError(Exception):
    pass


def uuid_from_display_name(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, name.strip().lower()))


def uuid_for_object_id(name: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"object:{name.strip().lower()}"))


def _read_text(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _write_text(p: Path, s: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s, encoding="utf-8")


def _read_yaml(p: Path) -> Dict[str, Any]:
    return yaml.safe_load(_read_text(p)) or {}


def _policy():
    return {
        "timeout": "0.12:00:00",
        "retry": 2,
        "retryIntervalInSeconds": 30,
        "secureOutput": False,
        "secureInput": False,
    }


# ============================================================
# MANIFEST BUILDER
# ============================================================

def build_manifest(notebooks_root: Path, manifest_path: Path) -> Dict[str, str]:
    notebooks: Dict[str, str] = {}

    # Collect layer directories: check both flat (bronze/) and domain-scoped (FCT/bronze/, OPR/bronze/)
    layer_dirs: list[tuple[str, Path]] = []
    for layer in ("bronze", "silver", "gold", "interface"):
        flat = notebooks_root / layer
        if flat.exists():
            layer_dirs.append((layer, flat))
        # Also scan domain subdirectories (FCT, OPR, etc.)
        for domain_dir in notebooks_root.iterdir():
            if domain_dir.is_dir() and domain_dir.name not in ("bronze", "silver", "gold", "interface"):
                nested = domain_dir / layer
                if nested.exists():
                    layer_dirs.append((layer, nested))

    for layer, layer_dir in layer_dirs:
        for platform_path in layer_dir.rglob(".platform"):
            try:
                pj = json.loads(_read_text(platform_path))
                logical_id = pj["config"]["logicalId"]
                display = pj["metadata"]["displayName"].strip().lower()

                if layer == "bronze":
                    key = f"bronze.{display[4:]}" if display.startswith("brz_") else f"bronze.{display}"
                elif layer == "silver":
                    key = f"silver.{display[4:]}" if display.startswith("slv_") else f"silver.{display}"
                elif layer == "interface":
                    # Strip any stale layer prefix from display name (e.g. "gold.d_fct_x" -> "d_fct_x")
                    clean = display
                    for stale in ("bronze.", "silver.", "gold.", "interface."):
                        if display.startswith(stale):
                            clean = display[len(stale):]
                            break
                    key = f"interface.{clean}"
                else:
                    key = f"gold.{display}"

                notebooks[key] = logical_id

            except Exception:
                continue

    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        yaml.safe_dump({"notebooks": notebooks}, sort_keys=True),
        encoding="utf-8",
    )

    print(f"✔ Manifest built with {len(notebooks)} notebooks")
    return notebooks


def load_notebook_ids_from_manifest(manifest_path: Path) -> Dict[str, str]:
    doc = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    return doc.get("notebooks", {})


# ============================================================
# MODEL LOADING
# ============================================================

@dataclass
class ModelInfo:
    name: str
    layer: str
    depends_on_tables: List[str]


def load_models(models_dir: Path) -> Dict[str, ModelInfo]:
    models: Dict[str, ModelInfo] = {}

    for p in models_dir.rglob("*.yaml"):
        doc = _read_yaml(p)
        if not doc or "model" not in doc:
            continue

        m = doc["model"]
        s = doc.get("source", {})

        layer = m.get("layer", "").lower()
        if layer not in ("bronze", "silver", "gold", "interface"):
            continue

        name = m["name"].split(".")[-1]
        deps = s.get("depends_on_tables", []) or []

        key = f"{layer}.{name}"
        models[key] = ModelInfo(name=name, layer=layer, depends_on_tables=deps)

    return models


# ============================================================
# Dependency resolution
# ============================================================

def toposort(nodes: List[str], deps: Dict[str, Set[str]]) -> List[str]:
    result = []
    deps = {k: set(v) for k, v in deps.items()}

    while deps:
        ready = sorted([n for n, d in deps.items() if not d])
        if not ready:
            raise PipelineGenError(f"Dependency cycle detected: {deps}")

        for r in ready:
            result.append(r)
            deps.pop(r)
            for d in deps.values():
                d.discard(r)

    return result


# ============================================================
# Pipeline generation
# ============================================================

def _matches_domain(name: str, domain_prefix: str, layer: str) -> bool:
    """Check if a model name matches the domain prefix.
    
    For gold layer, also matches patterns like:
      - d_[domain]_*  (dimension tables)
      - f_[domain]_*  (fact tables)
    """
    name_lower = name.lower()
    prefix_lower = domain_prefix.lower()
    
    # Direct prefix match (works for all layers)
    if name_lower.startswith(prefix_lower):
        return True
    
    # For gold/interface layer, also match d_[domain]_* and f_[domain]_* patterns
    if layer in ("gold", "interface"):
        if name_lower.startswith(f"d_{prefix_lower}_") or name_lower.startswith(f"f_{prefix_lower}_"):
            return True
    
    return False


def build_layer_pipeline(
    pipeline_name: str,
    layer: str,
    domain_prefix: str,
    models: Dict[str, ModelInfo],
    notebook_ids: Dict[str, str],
    workspace_id: str,
    pass_parameters: Optional[Dict[str, str]] = None,
    notebooks_config: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Build a pipeline from models or explicit notebook configuration.
    
    Args:
        pipeline_name: Name of the pipeline
        layer: Layer (bronze, silver, gold, interface)
        domain_prefix: Domain prefix for auto-discovery
        models: Dictionary of model info
        notebook_ids: Dictionary of notebook logical IDs
        workspace_id: Fabric workspace ID
        pass_parameters: Parameters to pass to notebooks
        notebooks_config: Explicit list of notebooks with dependencies (overrides auto-discovery)
    """
    
    # If explicit notebooks are provided, use them
    if notebooks_config:
        return _build_pipeline_from_config(
            pipeline_name=pipeline_name,
            layer=layer,
            notebooks_config=notebooks_config,
            notebook_ids=notebook_ids,
            workspace_id=workspace_id,
            pass_parameters=pass_parameters,
        )
    
    # Otherwise, auto-discover from models
    selected = {
        k: v
        for k, v in models.items()
        if v.layer == layer and _matches_domain(v.name, domain_prefix, layer)
    }

    if not selected:
        raise PipelineGenError(f"No models found for layer={layer}, domain={domain_prefix}")

    deps: Dict[str, Set[str]] = {k: set() for k in selected.keys()}

    for k, m in selected.items():
        for d in m.depends_on_tables:
            if d in selected:
                deps[k].add(d)

    ordered = toposort(list(deps.keys()), deps)

    activities = []

    for key in ordered:
        model = selected[key]
        nb_key = f"{layer}.{model.name}".lower()

        if nb_key not in notebook_ids:
            raise PipelineGenError(f"Notebook ID not found for {nb_key}")

        activity_name = (
            f"BRZ_{model.name}" if layer == "bronze"
            else f"SLV_{model.name}" if layer == "silver"
            else model.name
        ).upper()

        type_props = {
            "notebookId": notebook_ids[nb_key],
            "workspaceId": "00000000-0000-0000-0000-000000000000",
        }

        if pass_parameters:
            params = {}
            for k, v in pass_parameters.items():
                params[k] = {
                    "value": {"value": v, "type": "Expression"},
                    "type": "string",
                }
            type_props["parameters"] = params

            # Add sessionTag to typeProperties for all notebook activities
            type_props["sessionTag"] = {
                "value": "@replace(concat(pipeline().PipelineName,pipeline().DataFactory),'-','_')",
                "type": "Expression"
            }
        activities.append({
            "name": activity_name,
            "type": "TridentNotebook",
            "dependsOn": [],
            "policy": _policy(),
            "typeProperties": type_props,
        })

    properties = {"activities": activities}

    if pass_parameters:
        properties["parameters"] = {
            k: {"type": "string"} for k in pass_parameters.keys()
        }

    return {
        "name": pipeline_name,
        "objectId": uuid_for_object_id(pipeline_name),
        "properties": properties,
    }


def _build_pipeline_from_config(
    pipeline_name: str,
    layer: str,
    notebooks_config: List[Dict[str, Any]],
    notebook_ids: Dict[str, str],
    workspace_id: str,
    pass_parameters: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a pipeline from explicit notebook configuration with dependencies."""
    
    activities = []
    notebook_to_activity: Dict[str, str] = {}
    
    # First pass: create activity names mapping
    for nb_cfg in notebooks_config:
        nb_name = nb_cfg["name"]
        activity_name = (
            f"BRZ_{nb_name}" if layer == "bronze"
            else f"SLV_{nb_name}" if layer == "silver"
            else nb_name
        ).upper()
        notebook_to_activity[nb_name] = activity_name
    
    # Second pass: build activities with dependencies
    for nb_cfg in notebooks_config:
        nb_name = nb_cfg["name"]
        nb_key = f"{layer}.{nb_name}".lower()
        depends_on = nb_cfg.get("depends_on", [])

        if nb_key not in notebook_ids:
            # Some gold-layer notebooks are classified as "interface" in the
            # model metadata (e.g. customer-specific dim overrides) even
            # though they're wired into a gold pipeline definition.
            fallback_key = f"interface.{nb_name}".lower()
            if layer == "gold" and fallback_key in notebook_ids:
                nb_key = fallback_key
            else:
                raise PipelineGenError(f"Notebook ID not found for {nb_key}")
        
        activity_name = notebook_to_activity[nb_name]
        
        # Build dependsOn array with activity references
        depends_on_activities = []
        for dep in depends_on:
            if dep not in notebook_to_activity:
                raise PipelineGenError(f"Dependency '{dep}' not found in notebooks list for pipeline {pipeline_name}")
            depends_on_activities.append({
                "activity": notebook_to_activity[dep],
                "dependencyConditions": ["Succeeded"]
            })
        
        type_props = {
            "notebookId": notebook_ids[nb_key],
            "workspaceId": "00000000-0000-0000-0000-000000000000",
        }
        
        if pass_parameters:
            params = {}
            for k, v in pass_parameters.items():
                params[k] = {
                    "value": {"value": v, "type": "Expression"},
                    "type": "string",
                }
            type_props["parameters"] = params

        # Add sessionTag to typeProperties for all notebook activities
        type_props["sessionTag"] = {
            "value": "@replace(concat(pipeline().PipelineName,pipeline().DataFactory),'-','_')",
            "type": "Expression"
        }

        activities.append({
            "name": activity_name,
            "type": "TridentNotebook",
            "dependsOn": depends_on_activities,
            "policy": _policy(),
            "typeProperties": type_props,
        })
    
    properties = {"activities": activities}
    
    if pass_parameters:
        properties["parameters"] = {
            k: {"type": "string"} for k in pass_parameters.keys()
        }
    
    return {
        "name": pipeline_name,
        "objectId": uuid_for_object_id(pipeline_name),
        "properties": properties,
    }


# ============================================================
# Main
# ============================================================

def main():
    ap = argparse.ArgumentParser()

    ap.add_argument("--models-dir", required=True)
    ap.add_argument("--notebooks-root", required=True)
    ap.add_argument("--pipelines-yaml-dir", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--workspace-id", required=True)

    args = ap.parse_args()

    models_dir = Path(args.models_dir)
    notebooks_root = Path(args.notebooks_root)
    pipelines_dir = Path(args.pipelines_yaml_dir)
    out_dir = Path(args.out)
    workspace_id = args.workspace_id

    manifest_path = out_dir / "manifest" / "notebooks_manifest.yaml"

    print("Step 1: Building manifest")
    build_manifest(notebooks_root, manifest_path)

    notebook_ids = load_notebook_ids_from_manifest(manifest_path)
    models = load_models(models_dir)

    print("Step 2: Generating pipelines")

    for yaml_file in pipelines_dir.rglob("*.yaml"):
        doc = _read_yaml(yaml_file)
        if "pipeline" not in doc:
            continue

        p = doc["pipeline"]
        name = p["name"]

        afm = p["auto_from_models"]
        layer = afm["layer"]
        domain_prefix = afm["domain_prefix"]
        pass_params = afm.get("pass_parameters")
        
        # Check for explicit notebooks configuration
        notebooks_config = p.get("notebooks")

        pipeline_json = build_layer_pipeline(
            pipeline_name=name,
            layer=layer,
            domain_prefix=domain_prefix,
            models=models,
            notebook_ids=notebook_ids,
            workspace_id=workspace_id,
            pass_parameters=pass_params,
            notebooks_config=notebooks_config,
        )

        dp_dir = out_dir / f"{name}.DataPipeline"
        dp_dir.mkdir(parents=True, exist_ok=True)

        _write_text(
            dp_dir / "pipeline-content.json",
            json.dumps(pipeline_json, indent=2),
        )

        _write_text(
            dp_dir / ".platform",
            json.dumps({
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "DataPipeline", "displayName": name},
                "config": {
                    "version": "2.0",
                    "objectId": uuid_for_object_id(name),
                    "logicalId": uuid_from_display_name(name),
                },
            }, indent=2),
        )

        print(f"✔ Generated {name}")

    print("✔ All pipelines generated successfully")


if __name__ == "__main__":
    main()
