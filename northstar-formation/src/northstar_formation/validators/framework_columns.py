"""Framework-column contract enforcement.

Reads `models/_base/framework/required_columns.yaml` (the framework contract)
and checks that every merged bronze/silver model exposes the mandatory columns.
Also powers `northstar-formation inspect`, which annotates each column in a resolved
model with its origin (base yaml or customer yaml).

The check runs *after* the base + customer merge, so it validates the effective
schema each customer will build against — not just what's in _base.
"""
from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from ..core.models import BuildContext
from ..core.parser import YAMLParser


DEFAULT_CONTRACT_PATH = Path("models/_base/framework/required_columns.yaml")


@dataclass
class ColumnCheck:
    """One row of the framework-contract check per model."""

    model_name: str
    layer: str
    kind: str = "dim"  # 'dim' | 'fact'
    missing: List[str] = field(default_factory=list)
    type_mismatches: List[Tuple[str, str, str]] = field(default_factory=list)  # (name, expected, actual)

    @property
    def ok(self) -> bool:
        return not self.missing  # type mismatches are warnings, not failures


@dataclass
class InspectRow:
    """One column of a merged model with its origin annotation."""

    name: str
    data_type: str
    expression: Optional[str]
    source: str  # 'base' | 'customer' | 'framework' | 'unknown'


def _load_contract(contract_path: Optional[Path]) -> Dict[str, Any]:
    path = contract_path or DEFAULT_CONTRACT_PATH
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        raise FileNotFoundError(
            f"Framework-column contract not found at {path}. "
            f"Create it or pass --contract."
        )
    with path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _layer_from_qualified_name(name: str) -> str:
    """`bronze.customer` -> `bronze`. Silver SCD kept as 'silver' here."""
    return name.split(".", 1)[0].lower() if "." in name else ""


def _is_scd(name: str) -> bool:
    return name.rsplit(".", 1)[-1].lower().endswith("_scd")


def _table_stem(name: str) -> str:
    """`bronze.customer` -> `customer` (lowercase, no layer prefix)."""
    return name.rsplit(".", 1)[-1].lower()


def _req_applies(req: Dict[str, Any], model_name: str) -> bool:
    """There is no domain concept any more, so every requirement applies to
    every model; `only_domains` (if still present in a contract file) is
    ignored rather than used to filter."""
    return True


def _is_fact(name: str, contract: Dict[str, Any]) -> bool:
    """A model is a fact if its stem (ignoring optional `_scd` suffix) is listed
    under `facts` in the contract."""
    stem = _table_stem(name)
    if stem.endswith("_scd"):
        stem = stem[: -len("_scd")]
    facts = {f.lower() for f in contract.get("facts", []) or []}
    return stem in facts


def _extract_columns(model) -> List[Any]:
    tx = getattr(model, "transformations", None)
    if not tx:
        return []
    cols = getattr(tx, "columns", None) or []
    return list(cols)


def _column_index(model) -> Dict[str, Any]:
    return {c.name.lower(): c for c in _extract_columns(model) if getattr(c, "name", None)}


def check_model(model_name: str, model, contract: Dict[str, Any]) -> ColumnCheck:
    layer = _layer_from_qualified_name(model_name)
    section = contract.get(layer, {}) or {}
    required = list(section.get("required", []) or [])

    # Add dim-only requirements unless this model is a fact.
    is_fact = _is_fact(model_name, contract)
    if not is_fact:
        required.extend(section.get("required_for_dims", []) or [])

    if _is_scd(model_name) and contract.get("silver_scd"):
        scd_required = contract["silver_scd"].get("required", []) or []
        required = list({(r["name"].lower()): r for r in required + scd_required}.values())

    cols = _column_index(model)
    result = ColumnCheck(
        model_name=model_name,
        layer=layer,
        kind=("fact" if is_fact else "dim"),
    )
    for req in required:
        if not _req_applies(req, model_name):
            continue
        req_name = req["name"]
        col = cols.get(req_name.lower())
        if col is None:
            result.missing.append(req_name)
            continue
        expected = (req.get("expected_type") or "").upper()
        actual = (getattr(col, "data_type", "") or "").upper()
        if expected and actual and not actual.startswith(expected):
            result.type_mismatches.append((req_name, expected, actual))
    return result


def check_all_models(
    models: Dict[str, Any],
    contract: Dict[str, Any],
) -> List[ColumnCheck]:
    checks: List[ColumnCheck] = []
    for name in sorted(models.keys()):
        layer = _layer_from_qualified_name(name)
        if layer not in ("bronze", "silver") and not _is_scd(name):
            continue
        checks.append(check_model(name, models[name], contract))
    return checks


# ---------- inspect: per-column source annotation ----------

def _build_source_index(base_dir: Optional[Path], customer_dir: Path, ctx: BuildContext) -> Dict[str, Dict[str, str]]:
    """Return {model_qualified_name: {column_name_lower: 'base'|'customer'}}.

    Columns present in the base model are labelled 'base'. Columns only present
    on the customer side are labelled 'customer'. Later customer overrides of a
    base column also count as 'customer'.
    """
    idx: Dict[str, Dict[str, str]] = {}

    base_columns_per_model: Dict[str, set] = {}
    if base_dir:
        base_parser = YAMLParser(str(base_dir))
        base_models = base_parser.load_all_models(ctx)
        for name, model in base_models.items():
            base_columns_per_model[name] = {c.name.lower() for c in _extract_columns(model) if c.name}

    customer_parser = YAMLParser(str(customer_dir))
    customer_models = customer_parser.load_all_models(ctx)
    for name, model in customer_models.items():
        customer_cols = {c.name.lower() for c in _extract_columns(model) if c.name}
        base_cols = base_columns_per_model.get(name, set())
        origins: Dict[str, str] = {}
        for col_lower in base_cols | customer_cols:
            if col_lower in customer_cols and col_lower not in base_cols:
                origins[col_lower] = "customer"
            elif col_lower in base_cols and col_lower not in customer_cols:
                origins[col_lower] = "base"
            elif col_lower in base_cols and col_lower in customer_cols:
                origins[col_lower] = "customer"  # customer overrides base
            else:
                origins[col_lower] = "unknown"
        idx[name] = origins

    # Also add base-only models (those the customer doesn't override at all)
    for name, base_cols in base_columns_per_model.items():
        if name not in idx:
            idx[name] = {col: "base" for col in base_cols}

    return idx


def inspect_model(
    model_name: str,
    merged_models: Dict[str, Any],
    source_index: Dict[str, Dict[str, str]],
) -> List[InspectRow]:
    """Return one InspectRow per column in the merged model."""
    model = merged_models.get(model_name)
    if model is None:
        raise KeyError(f"Model {model_name!r} not found in merged models")
    origins = source_index.get(model_name, {})
    out: List[InspectRow] = []
    for col in _extract_columns(model):
        out.append(
            InspectRow(
                name=col.name,
                data_type=(col.data_type or "") if getattr(col, "data_type", None) else "",
                expression=getattr(col, "expression", None),
                source=origins.get(col.name.lower(), "unknown"),
            )
        )
    return out


__all__ = [
    "ColumnCheck",
    "InspectRow",
    "DEFAULT_CONTRACT_PATH",
    "check_all_models",
    "check_model",
    "inspect_model",
    "_build_source_index",
    "_load_contract",
]
