"""Generate a DDL notebook from SQL output files.

Scans output/sql/{domain}/bronze|silver|gold/ directories, collects all SQL
DDL/DML statements, resolves inter-table dependencies (topological sort),
and writes a single Fabric .Notebook with one ``%%sql`` cell per table.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from ..utils.logging import get_logger

logger = get_logger(__name__)


def generate_ddl_notebook(
    output_dir: Path,
    lakehouse_name: str,
    customer: str,
) -> Optional[Path]:
    """Generate a DDL notebook from all SQL files under *output_dir*/sql.

    The notebook is written to ``output_dir/notebooks/UTL/DDL/nb_ddl_{customer}.Notebook/``.

    Args:
        output_dir: Root output directory (e.g. ``output/``).
        lakehouse_name: Default lakehouse name for the ``%%configure`` cell.
        customer: Customer identifier used in the notebook filename.

    Returns:
        Path to the generated ``.Notebook`` directory, or *None* if no SQL
        files were found.
    """
    sql_dir = output_dir / "sql"
    if not sql_dir.exists():
        logger.warning(f"SQL output directory not found: {sql_dir}")
        return None

    # Collect SQL statements per layer across all domains
    bronze_stmts: List[Tuple[str, str]] = []   # (table_name, sql)
    silver_stmts: List[Tuple[str, str]] = []
    gold_stmts: List[Tuple[str, str]] = []
    interface_stmts: List[Tuple[str, str]] = []

    # Customers built since the fct/opr domain-folder flattening (e.g. customer0,
    # customer0) emit sql_dir/{layer}/*.sql directly - no domain subfolder. Older
    # customers may still emit sql_dir/{domain}/{layer}/*.sql. Detect which
    # shape this output uses rather than assuming the legacy nested one,
    # otherwise flat output silently yields zero SQL files here.
    _layer_names = {"bronze", "silver", "gold", "interface"}
    if any((sql_dir / layer).is_dir() for layer in _layer_names):
        domain_dirs = [sql_dir]
    else:
        domain_dirs = [d for d in sorted(sql_dir.iterdir()) if d.is_dir()]

    for domain_dir in domain_dirs:
        for layer in ("bronze", "silver", "gold", "interface"):
            layer_dir = domain_dir / layer
            if not layer_dir.exists():
                continue

            for sql_file in sorted(layer_dir.glob("*.sql")):
                name = sql_file.stem  # e.g. "fct_customer"

                # Skip scripts
                if "script" in name.lower():
                    logger.debug(f"Skipping script: {sql_file.name}")
                    continue

                sql_text = sql_file.read_text(encoding="utf-8").strip()
                if not sql_text:
                    continue

                table_fqn = f"{layer}.{name}"

                if layer == "silver":
                    # Wrap bare SELECT in CREATE OR REPLACE TABLE ... AS
                    if not sql_text.upper().startswith("CREATE"):
                        sql_text = f"CREATE OR REPLACE TABLE {table_fqn} AS\n{sql_text}"

                if layer == "bronze":
                    bronze_stmts.append((table_fqn, sql_text))
                elif layer == "silver":
                    silver_stmts.append((table_fqn, sql_text))
                elif layer == "interface":
                    interface_stmts.append((table_fqn, sql_text))
                else:
                    gold_stmts.append((table_fqn, sql_text))

    total = len(bronze_stmts) + len(silver_stmts) + len(gold_stmts) + len(interface_stmts)
    if total == 0:
        logger.warning("No SQL files found for DDL notebook generation")
        return None

    # Topological sort within each layer
    bronze_sorted = _topo_sort(bronze_stmts)
    silver_sorted = _topo_sort(silver_stmts)
    gold_sorted = _topo_sort(gold_stmts)
    interface_sorted = _topo_sort(interface_stmts)

    # Build notebook cells
    cells: List[Dict] = []

    # Cell 1: %%configure
    cells.append({
        "cell_type": "code",
        "metadata": {"tags": ["configure"]},
        "source": [
            "%%configure\n",
            json.dumps({"defaultLakehouse": {"name": lakehouse_name}}, indent=2),
        ],
    })

    # Schema creation cells
    for schema in ("bronze", "silver", "gold", "log","interface"):
        cells.append({
            "cell_type": "code",
            "metadata": {"language": "sql"},
            "source": [
                "%%sql\n",
                f"CREATE SCHEMA IF NOT EXISTS {schema};\n",
            ],
        })

    # DDL cells per layer
    for table_name, sql_text in bronze_sorted + silver_sorted + gold_sorted + interface_sorted:
        # Ensure SQL ends with semicolon
        sql_clean = sql_text.rstrip().rstrip(";") + ";"
        cells.append({
            "cell_type": "code",
            "metadata": {"language": "sql"},
            "source": [
                "%%sql\n",
                sql_clean + "\n",
            ],
        })

    # Write using Fabric .Notebook format
    notebook_name = f"nb_ddl_{customer}"
    dest_dir = output_dir / "notebooks" / "UTL" / "DDL" / f"{notebook_name}.Notebook"
    dest_dir.mkdir(parents=True, exist_ok=True)

    # Build notebook-content.py
    content = _build_fabric_content(cells)
    (dest_dir / "notebook-content.py").write_text(content, encoding="utf-8")

    # Build .platform
    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": "Notebook",
            "displayName": notebook_name,
        },
        "config": {
            "version": "2.0",
            "logicalId": _deterministic_id(notebook_name),
        },
    }
    (dest_dir / ".platform").write_text(
        json.dumps(platform, indent=2), encoding="utf-8"
    )

    logger.info(
        f"Generated DDL notebook at {dest_dir} with {total} table(s) "
        f"(bronze={len(bronze_stmts)}, silver={len(silver_stmts)}, gold={len(gold_stmts)}, "
        f"interface={len(interface_stmts)})"
    )
    return dest_dir


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deterministic_id(name: str) -> str:
    """Create a deterministic UUID-like string from a name."""
    import hashlib
    h = hashlib.md5(name.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"


def _extract_refs(sql: str) -> Set[str]:
    """Extract fully-qualified table references (schema.table) from SQL."""
    refs: Set[str] = set()
    # Match schema.table after FROM or JOIN keywords
    pattern = re.compile(
        r'\b(?:FROM|JOIN)\s+([a-zA-Z_]\w*\.[a-zA-Z_]\w*)',
        re.IGNORECASE,
    )
    for m in pattern.finditer(sql):
        refs.add(m.group(1).lower())
    return refs


def _topo_sort(stmts: List[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """Topologically sort statements by their intra-layer table dependencies."""
    if not stmts:
        return []

    table_map = {name.lower(): (name, sql) for name, sql in stmts}
    deps: Dict[str, Set[str]] = {}

    for name, sql in stmts:
        key = name.lower()
        refs = _extract_refs(sql)
        # Only keep deps that are within our own set
        deps[key] = refs & set(table_map.keys())
        # Remove self-references
        deps[key].discard(key)

    # Kahn's algorithm
    in_degree = {k: len(v) for k, v in deps.items()}
    reverse: Dict[str, List[str]] = {k: [] for k in table_map}
    for k, d in deps.items():
        for dep in d:
            reverse[dep].append(k)

    queue = sorted(k for k, deg in in_degree.items() if deg == 0)
    result: List[Tuple[str, str]] = []

    while queue:
        current = queue.pop(0)
        result.append(table_map[current])
        for dependent in sorted(reverse[current]):
            in_degree[dependent] -= 1
            if in_degree[dependent] == 0:
                queue.append(dependent)

    # Append any remaining (cycles) at the end
    if len(result) < len(stmts):
        done = {r[0].lower() for r in result}
        for name, sql in stmts:
            if name.lower() not in done:
                result.append((name, sql))
                logger.warning(f"Circular dependency detected for {name}")

    return result


def _build_fabric_content(cells: List[Dict]) -> str:
    """Build a notebook-content.py string in Fabric format."""
    lines = [
        "# Fabric notebook source",
        "",
        "# METADATA ********************",
        "",
    ]

    # Notebook-level metadata
    metadata = {
        "kernel_info": {"name": "synapse_pyspark"},
        "dependencies": {},
    }
    for ml in _format_meta(metadata):
        lines.append(ml)
    lines.append("")

    for cell in cells:
        cell_lines = _format_cell(cell)
        lines.extend(cell_lines)
        lines.append("")

    return "\n".join(lines)


def _format_cell(cell: Dict) -> List[str]:
    """Format a single cell into Fabric notebook lines."""
    result: List[str] = []
    source_lines = cell.get("source", [])
    meta = cell.get("metadata", {})

    # Determine if this is a SQL cell (has %%sql or %%configure magic)
    is_magic = False
    if source_lines:
        first = source_lines[0].strip()
        if first.startswith("%%"):
            is_magic = True

    result.append("# CELL ********************")
    result.append("")

    if is_magic:
        for line in source_lines:
            for sub in line.rstrip("\n").split("\n"):
                result.append(f"# MAGIC {sub}")
    else:
        for line in source_lines:
            result.append(line.rstrip("\n"))

    result.append("")
    result.append("# METADATA ********************")
    result.append("")

    # Cell metadata
    if "tags" in meta and "configure" in meta["tags"]:
        cell_meta = {"language": "python", "language_group": "synapse_pyspark"}
    elif meta.get("language") == "sql":
        cell_meta = {"language": "sparksql", "language_group": "synapse_pyspark"}
    else:
        cell_meta = {"language": "python", "language_group": "synapse_pyspark"}

    for ml in _format_meta(cell_meta):
        result.append(ml)

    return result


def _format_meta(data: dict) -> List[str]:
    """Format a dict as # META JSON lines."""
    lines: List[str] = []
    raw = json.dumps(data, indent=2)
    for line in raw.split("\n"):
        lines.append(f"# META {line}")
    return lines
