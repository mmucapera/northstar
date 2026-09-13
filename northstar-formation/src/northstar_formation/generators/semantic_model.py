"""Dynamic Fabric SemanticModel (TMDL, DirectLake) generation from gold/*.yaml
models - infers tables, columns, and dim<->fact relationships from the same
model metadata the gold-layer notebooks are generated from, so the semantic
layer never drifts from the actual star schema.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .pipelines import _read_yaml, _write_text


class SemanticModelGenError(Exception):
    pass


_DIM_PREFIXES = ("dim_", "d_")
_FACT_PREFIXES = ("fact_", "f_")


def _table_kind(name: str) -> str:
    n = name.lower()
    if n.startswith(_DIM_PREFIXES):
        return "dim"
    if n.startswith(_FACT_PREFIXES):
        return "fact"
    return "other"


def _sql_type_to_tmdl(data_type: str) -> Tuple[str, Optional[str]]:
    """Map a model YAML SQL-style data_type to a (TMDL dataType, formatString)."""
    t = (data_type or "").strip().upper()
    base = t.split("(")[0].strip()
    if base in ("NVARCHAR", "VARCHAR", "NCHAR", "CHAR", "TEXT"):
        return "string", None
    if base in ("INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT"):
        return "int64", None
    if base == "DECIMAL":
        # Every DECIMAL column in the CUSTOMER0 gold models has scale <= 3, which
        # fits Tabular's "Fixed Decimal Number" (max 4 decimal digits) cleanly.
        return "decimal", None
    if base in ("FLOAT", "REAL", "DOUBLE"):
        return "double", None
    if base == "DATE":
        # Explicit pattern, not a named style ("Short Date") - the named
        # styles produced schema-validation warnings on every table using
        # them when actually published to Fabric (dim_period, fact_reconciliation,
        # fact_cash_call_event all flagged; the only unaffected tables had no
        # dateTime columns at all). Verified against a real working TMDL
        # example before switching.
        return "dateTime", "dd mmm yyyy"
    if base in ("TIMESTAMP", "DATETIME", "DATETIME2"):
        return "dateTime", "dd mmm yyyy hh:mm"
    if base in ("BOOLEAN", "BOOL", "BIT"):
        return "boolean", None
    return "string", None


def load_gold_models(gold_dir: Path) -> Dict[str, Dict[str, Any]]:
    """Load every gold/*.yaml model, keyed by table name (e.g. 'dim_partner')."""
    tables: Dict[str, Dict[str, Any]] = {}
    for p in sorted(gold_dir.glob("*.yaml")):
        doc = _read_yaml(p)
        if not doc or "model" not in doc:
            continue
        m = doc["model"]
        name = m["name"].split(".")[-1]
        columns = doc.get("transformations", {}).get("columns", [])
        # Columns with no expression (e.g. Manifest_package/Manifest_file in the
        # CUSTOMER0 facts) are still real physical columns - keep them.
        tables[name] = {"name": name, "columns": columns}
    return tables


def infer_relationships(tables: Dict[str, Dict[str, Any]]) -> List[Tuple[str, str, str]]:
    """Infer many-to-one fact->dim relationships by matching a fact column name
    against a dim table's own natural-key column (its first declared column, by
    convention - e.g. PartnerId is both dim_partner's key and the FK on every
    fact that references it). Returns (fact_table, column, dim_table) tuples."""
    dim_keys: Dict[str, str] = {}
    for name, t in tables.items():
        if _table_kind(name) != "dim":
            continue
        cols = [c["name"] for c in t["columns"]]
        if cols:
            dim_keys[cols[0]] = name

    rels: List[Tuple[str, str, str]] = []
    for name, t in tables.items():
        if _table_kind(name) != "fact":
            continue
        fact_cols = {c["name"] for c in t["columns"]}
        for col, dim_name in dim_keys.items():
            if dim_name == name:
                continue
            if col in fact_cols:
                rels.append((name, col, dim_name))
    return rels


# A small set of hand-picked measures per fact table - not exhaustive, just
# enough that a self-service report (or any user exploring the model) gets
# sensible pre-aggregated values instead of having to build SUM/AVERAGE
# aggregations themselves. (name, DAX expression, formatString)
_MEASURES: Dict[str, List[Tuple[str, str, str]]] = {
    "fact_reconciliation": [
        ("Total Allocated Bbl", "SUM('fact_reconciliation'[AllocatedBbl])", "#,0"),
        ("Total Lifted Bbl", "SUM('fact_reconciliation'[LiftedBbl])", "#,0"),
        ("Avg Variance Pct", "AVERAGE('fact_reconciliation'[VariancePct])", "#,0.00"),
        ("Total Cash Call USD", "SUM('fact_reconciliation'[CashCallUsd])", "$#,0"),
    ],
    "fact_production": [
        ("Total Actual Bopd", "SUM('fact_production'[ActualBopd])", "#,0"),
        ("Total Forecast Bopd", "SUM('fact_production'[ForecastBopd])", "#,0"),
        ("Avg Uptime Pct", "AVERAGE('fact_production'[UptimePct])", "#,0.0"),
    ],
    "fact_downtime": [
        ("Total Downtime Hours", "SUM('fact_downtime'[Hours])", "#,0"),
    ],
    "fact_hse_exposure": [
        ("Total Exposure Hours", "SUM('fact_hse_exposure'[HoursWorked])", "#,0"),
    ],
    "fact_hse_incidents": [
        ("Incident Count", "COUNTROWS('fact_hse_incidents')", "#,0"),
    ],
}


def _tmdl_table_full(name: str, table: Dict[str, Any]) -> str:
    lines = [f"table {name}", f"\tlineageTag: {uuid.uuid4()}", ""]
    for col in table["columns"]:
        col_name = col["name"]
        dtype, fmt = _sql_type_to_tmdl(col.get("data_type", ""))
        lines.append(f"\tcolumn {col_name}")
        lines.append(f"\t\tdataType: {dtype}")
        if fmt:
            lines.append(f'\t\tformatString: {fmt}')
        lines.append(f"\t\tsourceColumn: {col_name}")
        lines.append(f"\t\tlineageTag: {uuid.uuid4()}")
        lines.append("")
    for m_name, m_expr, m_fmt in _MEASURES.get(name, []):
        lines.append(f"\tmeasure '{m_name}' = {m_expr}")
        lines.append(f"\t\tformatString: {m_fmt}")
        lines.append(f"\t\tlineageTag: {uuid.uuid4()}")
        lines.append("")
    lines.append(f"\tpartition {name} = entity")
    lines.append("\t\tmode: directLake")
    lines.append("\t\tsource")
    lines.append(f"\t\t\tentityName: {name}")
    lines.append("\t\t\tschemaName: gold")
    lines.append("\t\t\texpressionSource: DatabaseQuery")
    lines.append("")
    lines.append("\tannotation PBI_ResultType = Table")
    lines.append("")
    return "\n".join(lines)


def _tmdl_relationships(rels: List[Tuple[str, str, str]]) -> str:
    lines: List[str] = []
    for fact, col, dim in rels:
        lines.append(f"relationship {uuid.uuid4()}")
        lines.append(f"\tfromColumn: {fact}.{col}")
        lines.append(f"\ttoColumn: {dim}.{col}")
        lines.append("")
    return "\n".join(lines)


def _tmdl_model(table_names: List[str]) -> str:
    order = ", ".join(f'"{n}"' for n in table_names)
    lines = [
        "model Model",
        "\tculture: en-US",
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US",
        "",
        f"annotation PBI_QueryOrder = [{order}]",
        "",
        "annotation __PBI_TimeIntelligenceEnabled = 0",
        "",
    ]
    for n in table_names:
        lines.append(f"ref table {n}")
    lines.append("")
    return "\n".join(lines)


def _tmdl_database() -> str:
    return "database\n\n\tcompatibilityLevel: 1604\n"


def _tmdl_expressions(sql_endpoint: str, database_id: str) -> str:
    # `let` MUST be on its own line, indented deeper than `expression` - gluing
    # it onto the declaration line ("expression X = let") makes the TMDL
    # parser treat "let" as the whole value and then choke on the next line
    # ("Source = ...") as an unrecognized property keyword. Verified against
    # a real exported Fabric DirectLake expressions.tmdl.
    return (
        "expression DatabaseQuery =\n"
        "\t\tlet\n"
        f'\t\t    database = Sql.Database("{sql_endpoint}", "{database_id}")\n'
        "\t\tin\n"
        "\t\t    database\n"
        f"\tlineageTag: {uuid.uuid4()}\n"
        "\n"
        "\tannotation PBI_IncludeFutureArtifacts = False\n"
    )


def _platform_json(display_name: str, logical_id: str) -> str:
    import json as _json
    return _json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {"type": "SemanticModel", "displayName": display_name},
        "config": {"version": "2.0", "logicalId": logical_id},
    }, indent=2)


def _definition_pbism() -> str:
    import json as _json
    return _json.dumps({"version": "4.0", "settings": {}}, indent=2)


def generate_semantic_model(
    gold_dir: Path,
    output_dir: Path,
    semantic_model_name: str,
    sql_endpoint: str,
    database_id: str,
    logical_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate a DirectLake Fabric SemanticModel (TMDL) item from gold/*.yaml
    models. Relationships are inferred automatically from natural-key column
    name matches between dim and fact tables - no manual wiring needed.
    """
    tables = load_gold_models(gold_dir)
    if not tables:
        raise SemanticModelGenError(f"No gold models found under {gold_dir}")

    rels = infer_relationships(tables)

    sm_dir = output_dir / f"{semantic_model_name}.SemanticModel"
    def_dir = sm_dir / "definition"
    tables_dir = def_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    table_names = sorted(tables.keys())
    for name in table_names:
        _write_text(tables_dir / f"{name}.tmdl", _tmdl_table_full(name, tables[name]))

    _write_text(def_dir / "relationships.tmdl", _tmdl_relationships(rels))
    _write_text(def_dir / "model.tmdl", _tmdl_model(table_names))
    _write_text(def_dir / "database.tmdl", _tmdl_database())
    _write_text(def_dir / "expressions.tmdl", _tmdl_expressions(sql_endpoint, database_id))
    _write_text(sm_dir / "definition.pbism", _definition_pbism())
    _write_text(
        sm_dir / ".platform",
        _platform_json(semantic_model_name, logical_id or str(uuid.uuid5(uuid.NAMESPACE_DNS, semantic_model_name.strip().lower()))),
    )

    return {
        "tables": table_names,
        "relationships": rels,
        "output_dir": str(sm_dir),
    }
