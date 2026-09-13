"""Generate a silver-layer data-quality validation notebook.

Reads a customer-specific ``validation.yaml`` (test definitions + per-table
overrides) and the model YAML files (for merge keys, layer, domain), then
produces a single Fabric ``.Notebook`` structured as:

  1. ``%%configure`` cell binding ``defaultLakehouse``.
  2. Markdown header + usage notes.
  3. Shared-state cell (``VALIDATION_RESULTS``, ``TESTS_META``, ``_record``).
  4. Optional YAML-defined ``setups:`` cells (e.g. building temp views).
  5. **Helper functions** cell — generic ``run_check``.
  6. **Toggles** cell — one ``validate_<test_id> = True`` per test.
  7. **One cell per (test × table) check** — SQL inlined at the top,
     ``if validate_<id>: run_check(...)`` at the bottom. Each cell is
     independently freezable and re-runnable.
  8. Summary matrix cell.
  9. Diagnostics cell (auto-shows ``SELECT *`` for failing checks).

The notebook is intended to run before the gold pipelines so that data-quality
regressions are caught early.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

try:
    from ..utils.logging import get_logger
except ImportError:
    import logging as _logging
    def get_logger(name: str):  # type: ignore[misc]
        return _logging.getLogger(name)

logger = get_logger(__name__)


# Search order for the customer's validation.yaml when the caller does not
# pass ``validation_config_path`` explicitly.
_DEFAULT_CONFIG_CANDIDATES = (
    "data_quality/validation.yaml",
    "validation.yaml",
)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

_DEFAULT_DOMAIN_PREFIXES: Dict[str, str] = {}


def _read_yaml(path: Path) -> Dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return data or {}
    except Exception as exc:  # pragma: no cover
        logger.warning(f"Failed to parse {path}: {exc}")
        return {}


def _load_model_keys(
    models_dir: Path,
    base_dir: Optional[Path],
    layer: str,
) -> Dict[str, Dict[str, Any]]:
    """Return ``{layer.name: {merge_keys, delete_keys, non_nulls, base_table, raw_name}}``.

    Customer models are merged on top of base models: any of the three key
    lists that the customer defines wins; otherwise the base value is used.
    """

    layer_norm = layer.lower()

    def _scan(root: Path) -> Dict[str, Dict[str, Any]]:
        out: Dict[str, Dict[str, Any]] = {}
        if not root.exists():
            return out
        for yaml_path in root.rglob("*.yaml"):
            doc = _read_yaml(yaml_path)
            if not doc or not isinstance(doc, dict):
                continue
            model = doc.get("model") or {}
            if not isinstance(model, dict):
                continue
            model_layer = str(model.get("layer") or "").lower()
            if model_layer != layer_norm:
                continue
            name = model.get("name")
            if not name:
                continue

            source = doc.get("source") or {}
            merge_cfg = source.get("merge_keys") or {}
            # merge_keys.merge_keys is the nested list of PK columns
            merge_keys = list(merge_cfg.get("merge_keys") or [])
            delete_keys = list(merge_cfg.get("delete_keys") or [])
            non_nulls = list(merge_cfg.get("non_nulls") or [])

            fqn = f"{model_layer}.{name}"
            out[fqn] = {
                "raw_name": name,
                "layer": model_layer,
                "merge_keys": merge_keys,
                "delete_keys": delete_keys,
                "non_nulls": non_nulls,
                "base_table": source.get("base_table"),
            }
        return out

    result: Dict[str, Dict[str, Any]] = {}

    if base_dir and base_dir.exists():
        result.update(_scan(base_dir))

    # Customer overrides base
    for fqn, info in _scan(models_dir).items():
        if fqn in result:
            merged = dict(result[fqn])
            for k in ("merge_keys", "delete_keys", "non_nulls"):
                if info.get(k):
                    merged[k] = info[k]
            if info.get("base_table"):
                merged["base_table"] = info["base_table"]
            result[fqn] = merged
        else:
            result[fqn] = info

    return result


# ---------------------------------------------------------------------------
# Domain resolution
# ---------------------------------------------------------------------------

def _resolve_domain(name: str, prefixes: Dict[str, str]) -> str:
    """Return the bucket for a bare model name.

    Matches against customer-configured ``prefixes`` (``domain_prefixes`` in
    ``validation.yaml``). There is no built-in domain concept any more — the
    default is empty, so every model falls into ``"other"`` unless a customer
    opts into custom bucketing via its own ``validation.yaml``.
    """
    name_low = name.lower()
    for domain, prefix in prefixes.items():
        if name_low.startswith(prefix.lower()):
            return domain
    return "other"


def _table_sort_key(fqn: str) -> int:
    """Ordering used when emitting per-table check cells within a test.

    The generated notebook lists cells in this deterministic order so the
    reader sees the most important fact tables first:

    * ``saleshistory``  → bucket 0
    * everything else   → bucket 1
    """
    low = fqn.lower()
    if "saleshistory" in low:
        return 0
    return 1


# ---------------------------------------------------------------------------
# SQL rendering
# ---------------------------------------------------------------------------

_PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _render_sql(template: str, variables: Dict[str, str]) -> str:
    """Simple ``{name}`` substitution. Missing keys are left as-is."""
    def _sub(match: "re.Match[str]") -> str:
        key = match.group(1)
        return variables.get(key, match.group(0))

    return _PLACEHOLDER_RE.sub(_sub, template).strip()


def _keys_for_test(
    test_def: Dict[str, Any],
    model_info: Dict[str, Any],
    table_override: Dict[str, Any],
) -> List[str]:
    """Determine which keys apply for a given test/table combination.

    Precedence:
      1. ``tables.<fqn>.custom_keys`` (per-table override in validation.yaml)
      2. ``tests[].custom_keys`` (per-test default)
      3. Model YAML column list picked by ``keys_source``
    """
    if table_override.get("custom_keys"):
        return list(table_override["custom_keys"])

    if test_def.get("custom_keys"):
        return list(test_def["custom_keys"])

    source_field = str(test_def.get("keys_source") or "merge_keys").lower()
    if source_field in ("merge_keys", "delete_keys", "non_nulls"):
        return list(model_info.get(source_field) or [])
    return []


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_validation_notebook(
    models_dir: Path,
    output_dir: Path,
    lakehouse_name: str,
    customer: str,
    base_dir: Optional[Path] = None,
    lakehouse_id: Optional[str] = None,
    lakehouse_workspace_id: Optional[str] = None,
    validation_config_path: Optional[Path] = None,
) -> Optional[Path]:
    """Build the validation notebook. Returns the ``.Notebook`` directory path."""

    models_dir = Path(models_dir)
    output_dir = Path(output_dir)
    base_dir = Path(base_dir) if base_dir else None

    # 1. Locate validation.yaml
    if validation_config_path is None:
        for candidate in _DEFAULT_CONFIG_CANDIDATES:
            probe = models_dir / candidate
            if probe.exists():
                validation_config_path = probe
                break

    if validation_config_path is None or not validation_config_path.exists():
        logger.error(
            "validation.yaml not found under "
            f"{models_dir} "
            f"(searched: {', '.join(_DEFAULT_CONFIG_CANDIDATES)})"
        )
        return None

    cfg = _read_yaml(validation_config_path)
    if not cfg:
        logger.error(f"validation.yaml is empty: {validation_config_path}")
        return None

    config_dir = validation_config_path.parent

    notebook_cfg = cfg.get("notebook") or {}
    layer = str(notebook_cfg.get("layer") or "silver").lower()
    notebook_name = notebook_cfg.get("name") or f"nb_{layer}_validation_{customer}"
    description = notebook_cfg.get("description") or (
        f"{layer.capitalize()} layer data-quality validation for {customer}"
    )

    domain_prefixes = cfg.get("domain_prefixes") or dict(_DEFAULT_DOMAIN_PREFIXES)
    fail_on_error = bool(cfg.get("fail_on_error", False))

    tests: List[Dict[str, Any]] = list(cfg.get("tests") or [])
    if not tests:
        logger.error("No tests defined in validation.yaml")
        return None

    table_overrides: Dict[str, Dict[str, Any]] = cfg.get("tables") or {}

    # Global table exclusion — any fqn or raw_name matching one of these
    # glob patterns is skipped by every templated test. Standalone tests
    # target a specific ``target_table`` and are unaffected on purpose.
    exclude_tables: List[str] = list(cfg.get("exclude_tables") or [])

    # 2. Load model info (merge_keys etc.) from customer + base — only used by
    #    templated tests. Standalone tests do not need it.
    model_info_map = _load_model_keys(models_dir, base_dir, layer)

    # 3. Setup cells
    setup_cells = _build_setup_cells(cfg.get("setups") or [], config_dir)

    # 4. Test cells + summary metadata
    test_cells: List[Dict[str, Any]] = []
    tests_meta: List[Dict[str, str]] = []

    for test_def in tests:
        test_id = test_def.get("id")
        if not test_id:
            logger.warning(f"Skipping test without id: {test_def}")
            continue

        kind = str(test_def.get("kind") or "templated").lower()
        test_name = test_def.get("name") or test_id

        if kind in ("standalone", "python"):
            spec = _build_standalone_spec(test_def)
            if spec is None:
                continue
            tests_meta.append(
                {
                    "id": test_id,
                    "name": test_name,
                    "short_label": str(test_def.get("short_label") or test_name),
                }
            )
            test_cells.append(
                {
                    "kind": spec["kind"],  # "standalone" or "python"
                    "test_id": test_id,
                    "test_name": test_name,
                    "description": test_def.get("description") or "",
                    "markdown": test_def.get("markdown"),
                    "frozen": bool(test_def.get("frozen", False)),
                    "editable": bool(test_def.get("editable", True)),
                    "mode": spec["mode"],
                    "target_table": spec["table"],
                    "domain": spec["domain"],
                    "check_sql": spec.get("check_sql", ""),
                    "diagnostic_sql": spec.get("diagnostic_sql", ""),
                    "python": spec.get("python", ""),
                }
            )
            continue

        # ------------------------------------------------------------------ #
        # Templated test
        # ------------------------------------------------------------------ #
        check_tmpl = test_def.get("check_sql")
        if not check_tmpl:
            logger.warning(f"Test '{test_id}' has no check_sql; skipping")
            continue
        diag_tmpl = test_def.get("diagnostic_sql") or ""

        applies_to_domains = set(
            test_def.get("applies_to_domains")
            or list(domain_prefixes.keys()) + ["other"]
        )
        applies_to_layers = set(test_def.get("applies_to_layers") or [layer])
        applies_to_tables_glob = test_def.get("applies_to_tables") or []
        frozen = bool(test_def.get("frozen", False))
        editable = bool(test_def.get("editable", True))
        mode = str(test_def.get("mode") or "check").lower()

        specs: List[Dict[str, Any]] = []
        for fqn, model_info in sorted(
            model_info_map.items(), key=lambda kv: (_table_sort_key(kv[0]), kv[0])
        ):
            if model_info["layer"] not in applies_to_layers:
                continue

            raw_name = model_info["raw_name"]
            domain = _resolve_domain(raw_name, domain_prefixes)
            if domain not in applies_to_domains:
                continue

            if applies_to_tables_glob and not any(
                fnmatch.fnmatchcase(fqn, pat) or fnmatch.fnmatchcase(raw_name, pat)
                for pat in applies_to_tables_glob
            ):
                continue

            if exclude_tables and any(
                fnmatch.fnmatchcase(fqn, pat) or fnmatch.fnmatchcase(raw_name, pat)
                for pat in exclude_tables
            ):
                continue

            override = table_overrides.get(fqn) or table_overrides.get(raw_name) or {}
            skip_list = override.get("skip") or []
            if test_id in skip_list:
                continue

            frozen_list = override.get("frozen") or []
            spec_frozen = frozen or (test_id in frozen_list)

            keys = _keys_for_test(test_def, model_info, override)

            if keys:
                _where_parts = ", ".join(
                    f"CONCAT('{k} = ', COALESCE(CAST({k} AS STRING), 'NULL'))"
                    for k in keys
                )
                _keys_where_concat = f"CONCAT_WS(' AND ', {_where_parts})"
            else:
                _keys_where_concat = "''"

            variables = {
                "table": fqn,
                "raw_name": raw_name,
                "layer": model_info["layer"],
                "keys_csv": ", ".join(keys) if keys else "",
                "keys_group": ", ".join(keys) if keys else "",
                "keys_qualified_csv": ", ".join(f"t.{k}" for k in keys) if keys else "",
                # SQL expression that builds "col1 = 'v1' AND col2 = 'v2' ..." per row
                "keys_where_concat": _keys_where_concat,
            }

            if "{keys_csv}" in check_tmpl and not keys:
                logger.info(f"Skipping '{test_id}' on {fqn} — no keys resolved")
                continue

            check_sql = _render_sql(check_tmpl, variables)
            diagnostic_sql = _render_sql(diag_tmpl, variables) if diag_tmpl else ""

            specs.append(
                {
                    "table": fqn,
                    "domain": domain,
                    "check_sql": check_sql,
                    "diagnostic_sql": diagnostic_sql,
                    "mode": mode,
                    "frozen": spec_frozen,
                }
            )

        tests_meta.append(
            {
                "id": test_id,
                "name": test_name,
                "short_label": str(test_def.get("short_label") or test_name),
            }
        )

        test_cells.append(
            {
                "kind": "templated",
                "test_id": test_id,
                "test_name": test_name,
                "description": test_def.get("description") or "",
                "markdown": test_def.get("markdown"),
                "frozen": frozen,
                "editable": editable,
                "mode": mode,
                "specs": specs,
            }
        )

    # 5. Build notebook cells
    cells = _build_cells(
        lakehouse_name=lakehouse_name,
        lakehouse_id=lakehouse_id,
        lakehouse_workspace_id=lakehouse_workspace_id,
        customer=customer,
        layer=layer,
        description=description,
        tests_meta=tests_meta,
        setup_cells=setup_cells,
        test_cells=test_cells,
        fail_on_error=fail_on_error,
    )

    # 6. Write .Notebook directory
    dest_dir = output_dir / "notebooks" / "UTL" / "VALIDATION" / f"{notebook_name}.Notebook"
    dest_dir.mkdir(parents=True, exist_ok=True)

    content = _build_fabric_content(
        cells,
        lakehouse_name=lakehouse_name,
        lakehouse_id=lakehouse_id,
        lakehouse_workspace_id=lakehouse_workspace_id,
    )
    (dest_dir / "notebook-content.py").write_text(content, encoding="utf-8")

    platform = {
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
        "metadata": {
            "type": "Notebook",
            "displayName": notebook_name,
            "description": description,
        },
        "config": {
            "version": "2.0",
            # Shared logicalId across customers so the _c000 pipeline template
            # (PL_02_MASTER_S2G_ORCH) can reference this notebook uniformly.
            "logicalId": _deterministic_id("nb_silver_validation"),
        },
    }
    (dest_dir / ".platform").write_text(
        json.dumps(platform, indent=2), encoding="utf-8"
    )

    total_specs = sum(len(c.get("specs", []) or [1]) for c in test_cells)
    logger.info(
        f"Generated validation notebook at {dest_dir} "
        f"({len(setup_cells)} setup(s), {len(test_cells)} test(s), {total_specs} table-checks)"
    )
    return dest_dir


# ---------------------------------------------------------------------------
# Setup cells
# ---------------------------------------------------------------------------

def _build_setup_cells(
    setups: List[Dict[str, Any]],
    config_dir: Path,
) -> List[Dict[str, Any]]:
    """Turn ``setups:`` YAML entries into notebook cells (in order)."""
    out: List[Dict[str, Any]] = []
    for setup in setups:
        setup_id = setup.get("id") or "setup"
        name = setup.get("name") or setup_id
        frozen = bool(setup.get("frozen", False))
        editable = bool(setup.get("editable", True))
        language = str(setup.get("language") or "python").lower()

        source = setup.get("source") or ""
        source_file = setup.get("source_file")
        if source_file:
            src_path = (config_dir / source_file).resolve()
            if not src_path.exists():
                logger.warning(
                    f"Setup '{setup_id}': source_file not found at {src_path}"
                )
            else:
                source = src_path.read_text(encoding="utf-8")

        if not source.strip():
            logger.warning(f"Setup '{setup_id}' has no source; skipping")
            continue

        parameters: Dict[str, Any] = setup.get("parameters") or {}

        header_lines = [
            f"# ── Setup: {name} ──────────────────────────────────────────────────",
        ]
        description = setup.get("description")
        if description:
            header_lines.extend(_comment_lines(description))
        if parameters:
            header_lines.append("# Parameters (from validation.yaml):")
            for k, v in parameters.items():
                header_lines.append(f"{k} = {repr(v)}")

        cell_source = "\n".join(header_lines) + "\n\n" + source.rstrip() + "\n"

        out.append(
            {
                "kind": "python" if language == "python" else "sql",
                "source": cell_source,
                "frozen": frozen,
                "editable": editable,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Standalone test spec extraction
# ---------------------------------------------------------------------------

def _build_standalone_spec(test_def: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract the SQL / Python and metadata for a standalone test.

    Two flavours are supported:

    * SQL standalone (``kind: standalone`` or omitted) — requires ``check_sql``.
    * Python standalone (``kind: python``) — requires ``python`` (raw code
      block). The generated cell wraps the code in a ``try/except`` and
      auto-records a passing result if the user code doesn't call
      ``_record(...)`` itself.

    Returns ``None`` if the definition is invalid.
    """
    test_id = test_def["id"]
    kind = str(test_def.get("kind") or "standalone").lower()

    if kind == "python":
        code = str(test_def.get("python") or "").rstrip()
        if not code:
            logger.warning(f"Python test '{test_id}' has no python body; skipping")
            return None
        return {
            "kind": "python",
            "table": str(test_def.get("target_table") or f"[{test_id}]"),
            "domain": str(test_def.get("domain") or "other"),
            "mode": str(test_def.get("mode") or "check").lower(),
            "python": code,
        }

    check_sql = str(test_def.get("check_sql") or "").strip()
    if not check_sql:
        logger.warning(f"Standalone test '{test_id}' has no check_sql; skipping")
        return None

    return {
        "kind": "standalone",
        "table": str(test_def.get("target_table") or f"[{test_id}]"),
        "domain": str(test_def.get("domain") or "other"),
        "mode": str(test_def.get("mode") or "check").lower(),
        "check_sql": check_sql,
        "diagnostic_sql": str(test_def.get("diagnostic_sql") or ""),
    }


# ---------------------------------------------------------------------------
# Cell builders
# ---------------------------------------------------------------------------

def _build_cells(
    lakehouse_name: str,
    lakehouse_id: Optional[str],
    lakehouse_workspace_id: Optional[str],
    customer: str,
    layer: str,
    description: str,
    tests_meta: List[Dict[str, str]],
    setup_cells: List[Dict[str, Any]],
    test_cells: List[Dict[str, Any]],
    fail_on_error: bool,
) -> List[Dict[str, Any]]:
    cells: List[Dict[str, Any]] = []

    # 1. --- Configure cell --------------------------------------------------
    configure_body: Dict[str, Any] = {"defaultLakehouse": {"name": lakehouse_name}}
    if lakehouse_id:
        configure_body["defaultLakehouse"]["id"] = lakehouse_id
    if lakehouse_workspace_id:
        configure_body["defaultLakehouse"]["workspaceId"] = lakehouse_workspace_id

    cells.append(
        {
            "kind": "configure",
            "source": "%%configure\n" + json.dumps(configure_body, indent=2),
        }
    )

    # 2. --- Header markdown -------------------------------------------------
    header_md = [
        f"# {layer.capitalize()} Data-Quality Validation — {customer}",
        "",
        description,
    ]
    cells.append({"kind": "markdown", "source": "\n".join(header_md)})

    # 3. --- Shared state cell (frozen — internal machinery, not for end users)
    # `TESTS_META` is emitted as a compact single-line assignment to keep the
    # cell short. The state-init `print(...)` is intentionally omitted so the
    # notebook doesn't clutter the output area with framework noise.
    shared_state_lines = [
        "# ── Shared validation state (internal — do not edit) ──────────────",
        "from pyspark.sql import SparkSession",
        "",
        "spark = SparkSession.builder.getOrCreate()",
        "",
        "# {table_fqn: {test_id: {passed, failing_rows, test_name, domain,",
        "#                        diagnostic_sql, error, mode}}}",
        "VALIDATION_RESULTS = {}",
        "",
        "# Ordered list of tests (drives the summary matrix).",
        "TESTS_META = " + json.dumps(tests_meta, separators=(", ", ": ")),
        "",
        "def _record(table, test_id, test_name, domain, passed, failing_rows,",
        "            diagnostic_sql, error=None, mode='check'):",
        "    VALIDATION_RESULTS.setdefault(table, {})[test_id] = {",
        "        'passed': passed,",
        "        'failing_rows': failing_rows,",
        "        'test_name': test_name,",
        "        'domain': domain,",
        "        'diagnostic_sql': diagnostic_sql,",
        "        'error': error,",
        "        'mode': mode,",
        "    }",
    ]
    cells.append({
        "kind": "python",
        "source": "\n".join(shared_state_lines),
        "frozen": True,
    })

    # 4. --- YAML-defined setup cells ---------------------------------------
    for sc in setup_cells:
        cells.append(sc)

    # 5. --- Helper functions cell (frozen — internal machinery) -----------
    cells.append({
        "kind": "python",
        "source": _build_helpers_cell_source(),
        "frozen": True,
    })

    # 6. --- Toggles cell (first user-facing cell after the setup) ----------
    cells.append({"kind": "python", "source": _build_toggles_cell_source(test_cells)})

    # 7. --- One cell per (test × table) check ------------------------------
    for tc in test_cells:
        # H1 heading so the notebook outline shows each test group as a
        # top-level section, with the per-(table) H2 headings nested
        # underneath. Tests may provide a custom `markdown:` block in the
        # YAML — if set, it replaces the default `# <test_name>` heading
        # verbatim (so authors can add subtitles, bullet lists, links, etc.).
        _custom_md = tc.get("markdown")
        _heading_source = (
            str(_custom_md).rstrip() if _custom_md else f"# {tc['test_name']}"
        )
        cells.append({
            "kind": "markdown",
            "source": _heading_source,
        })
        cells.extend(_build_test_check_cells(tc))

    # 8. --- Summary cell ---------------------------------------------------
    cells.append({"kind": "markdown", "source": "# Summary"})
    cells.append({"kind": "python", "source": _build_summary_cell_source()})

    # 9. --- Diagnostics cell -----------------------------------------------
    cells.append({"kind": "markdown", "source": "# Diagnostics"})
    cells.append({"kind": "python", "source": _build_diagnostics_cell_source(fail_on_error)})

    return cells


# ---------------------------------------------------------------------------
# Individual section builders
# ---------------------------------------------------------------------------

def _toggle_name(test_id: str) -> str:
    """Return the ``validate_<id>`` toggle variable name for *test_id*."""
    return "validate_" + re.sub(r"[^A-Za-z0-9_]", "_", test_id).lower()


def _build_helpers_cell_source() -> str:
    return "\n".join(
        [
            "# ── Helper functions ────────────────────────────────────────────",
            "# `run_check` — run one SQL against one table, record the result.",
            "# `mode` is either 'check' (fail on rows > 0) or 'monitoring'",
            "# (always passes, displays the result).",
            "",
            "def run_check(test_id, test_name, table, domain, check_sql,",
            "              diagnostic_sql='', mode='check'):",
            "    try:",
            "        _df = spark.sql(check_sql)",
            "        _n = _df.count()",
            "        _err = None",
            "    except Exception as _exc:",
            "        _msg = str(_exc)",
            "        # Table absent in this environment — skip silently.",
            "        if 'TABLE_OR_VIEW_NOT_FOUND' in _msg or 'table or view not found' in _msg.lower():",
            "            _record(table, test_id, test_name, domain, True, 0, '', None, mode)",
            "            if SHOW_PASS:",
            "                print(f'SKIP     {table:<50s} {test_name}  (table does not exist)')",
            "            return",
            "        # Stale catalog cache — REFRESH and retry once.",
            "        if 'underlying files have been updated' in _msg or 'SparkFileNotFoundException' in _msg:",
            "            try:",
            "                spark.sql(f'REFRESH TABLE {table}')",
            "                _df = spark.sql(check_sql)",
            "                _n = _df.count()",
            "                _err = None",
            "            except Exception as _exc2:",
            "                _df = None",
            "                _n = -1",
            "                _err = str(_exc2)",
            "        else:",
            "            _df = None",
            "            _n = -1",
            "            _err = _msg",
            "    _passed = True if mode == 'monitoring' else (_n == 0 and _err is None)",
            "    _record(table, test_id, test_name, domain, _passed, _n,",
            "            diagnostic_sql, _err, mode)",
            "    if _err is not None:",
            "        print(f'ERROR    {table:<50s} {test_name}: {_err}')",
            "    elif mode == 'monitoring':",
            "        print(f'MONITOR  {table:<50s} {test_name}  ({_n} row(s))')",
            "        if _df is not None:",
            "            try:",
            "                display(_df)",
            "            except Exception:",
            "                try:",
            "                    _df.show(20, truncate=False)",
            "                except Exception:",
            "                    pass",
            "    elif _passed:",
            "        if SHOW_PASS:",
            "            print(f'PASS     {table:<50s} {test_name}  (no violations found)')",
            "    else:",
            "        print(f'FAIL     {table:<50s} {test_name}  ({_n} violation(s) found)')",
        ]
    )


def _build_toggles_cell_source(test_cells: List[Dict[str, Any]]) -> str:
    lines: List[str] = [
        "# ── Display options ─────────────────────────────────────────────",
        "# Set SHOW_PASS = True to include passing / skipped checks in the summary.",
        "SHOW_PASS = False",
        "",
        "# ── Enable / disable tests ──────────────────────────────────────",
        "# Flip any of these to False to skip every cell belonging to that",
        "# test at run time. Re-run the affected cells (or the whole",
        "# notebook) after changing a toggle.",
        "",
    ]
    for tc in test_cells:
        toggle = _toggle_name(tc["test_id"])
        lines.append(f"{toggle} = True  # {tc['test_name']}")
    lines.append("")
    lines.append(
        "_enabled = sum(1 for _n, _v in list(globals().items())"
        " if _n.startswith('validate_') and _v)"
    )
    lines.append("print(f'{_enabled} test(s) enabled.')"
    )
    return "\n".join(lines)


def _render_check_cell(
    test_id: str,
    test_name: str,
    table: str,
    domain: str,
    mode: str,
    check_sql: str,
    diagnostic_sql: str,
    description: str,
    frozen: bool,
    editable: bool,
) -> Dict[str, Any]:
    """Emit a single Python cell that runs one SQL check for one table."""
    toggle = _toggle_name(test_id)

    header_lines = [f"# ── {table} :: {test_name}"]
    if mode == "monitoring":
        header_lines.append("# mode: monitoring (always passes, informational)")
    if description:
        header_lines.extend(_comment_lines(description))

    body = header_lines + [
        f"if {toggle}:",
        "    run_check(",
        f"        test_id={json.dumps(test_id)},",
        f"        test_name={json.dumps(test_name)},",
        f"        table={json.dumps(table)},",
        f"        domain={json.dumps(domain)},",
        f"        mode={json.dumps(mode)},",
        "        check_sql=" + _py_triple_quoted("\n" + check_sql.strip() + "\n") + ",",
        "        diagnostic_sql="
        + _py_triple_quoted("\n" + diagnostic_sql.strip() + "\n" if diagnostic_sql.strip() else "")
        + ",",
        "    )",
        "else:",
        f"    print({json.dumps(f'SKIP     {table} :: {test_name}')})",
    ]

    return {
        "kind": "python",
        "source": "\n".join(body),
        "frozen": frozen,
        "editable": editable,
    }


def _build_test_check_cells(tc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Emit a markdown H2 heading + one runnable Python cell per (test × table).

    Standalone tests → exactly one heading + one cell.
    Templated tests  → one heading + one cell per matched table.
    Per-table ``frozen`` overrides (``tables.<fqn>.frozen: [test_ids]``)
    override the test-level ``frozen`` flag for the matching cell.
    """
    test_id = tc["test_id"]
    test_name = tc["test_name"]
    description = tc.get("description") or ""
    frozen = tc.get("frozen", False)
    editable = tc.get("editable", True)
    mode = tc.get("mode", "check")

    if tc["kind"] == "standalone":
        return _heading_and_check(
            test_id=test_id,
            test_name=test_name,
            table=tc["target_table"],
            domain=tc["domain"],
            mode=mode,
            check_sql=tc["check_sql"],
            diagnostic_sql=tc.get("diagnostic_sql") or "",
            description=description,
            frozen=frozen,
            editable=editable,
        )

    if tc["kind"] == "python":
        return _heading_and_python(
            test_id=test_id,
            test_name=test_name,
            table=tc["target_table"],
            domain=tc["domain"],
            mode=mode,
            python_body=tc["python"],
            description=description,
            frozen=frozen,
            editable=editable,
        )

    specs = tc.get("specs") or []
    if not specs:
        toggle = _toggle_name(test_id)
        return [
            {
                "kind": "markdown",
                "source": f"## (no tables matched) — {test_name}",
                "frozen": frozen,
                "editable": editable,
            },
            {
                "kind": "python",
                "source": (
                    f"if {toggle}:\n"
                    f"    print('[{test_id}] no applicable tables')\n"
                ),
                "frozen": frozen,
                "editable": editable,
            },
        ]

    out: List[Dict[str, Any]] = []
    for s in specs:
        out.extend(
            _heading_and_check(
                test_id=test_id,
                test_name=test_name,
                table=s["table"],
                domain=s["domain"],
                mode=mode,
                check_sql=s["check_sql"],
                diagnostic_sql=s.get("diagnostic_sql") or "",
                description=description,
                frozen=bool(s.get("frozen") or frozen),
                editable=editable,
            )
        )
    return out


def _heading_and_check(
    test_id: str,
    test_name: str,
    table: str,
    domain: str,
    mode: str,
    check_sql: str,
    diagnostic_sql: str,
    description: str,
    frozen: bool,
    editable: bool,
) -> List[Dict[str, Any]]:
    """Return ``[markdown_heading_cell, python_check_cell]`` for a single check."""
    heading_lines = [f"## {table} — {test_name}"]
    if mode == "monitoring":
        heading_lines.append("")
        heading_lines.append("_mode: monitoring (always passes, informational)_")
    if description:
        heading_lines.append("")
        heading_lines.append(description.rstrip())

    heading_cell = {
        "kind": "markdown",
        "source": "\n".join(heading_lines),
        "frozen": frozen,
        "editable": editable,
    }
    check_cell = _render_check_cell(
        test_id=test_id,
        test_name=test_name,
        table=table,
        domain=domain,
        mode=mode,
        check_sql=check_sql,
        diagnostic_sql=diagnostic_sql,
        description="",
        frozen=frozen,
        editable=editable,
    )
    return [heading_cell, check_cell]


def _heading_and_python(
    test_id: str,
    test_name: str,
    table: str,
    domain: str,
    mode: str,
    python_body: str,
    description: str,
    frozen: bool,
    editable: bool,
) -> List[Dict[str, Any]]:
    """Return ``[markdown_heading_cell, python_check_cell]`` for a python-kind test.

    The user's ``python:`` YAML block is wrapped in a ``try/except`` and
    guarded by the ``validate_<id>`` toggle. If the code raises, the error
    is recorded via ``_record(...)``. If the code completes but doesn't
    call ``_record`` itself, a default passing record is written so the
    test still shows up in the Summary matrix.
    """
    toggle = _toggle_name(test_id)

    heading_lines = [f"## {table} — {test_name}"]
    if mode == "monitoring":
        heading_lines.append("")
        heading_lines.append("_mode: monitoring (always passes, informational)_")
    if description:
        heading_lines.append("")
        heading_lines.append(description.rstrip())

    heading_cell = {
        "kind": "markdown",
        "source": "\n".join(heading_lines),
        "frozen": frozen,
        "editable": editable,
    }

    # Preamble: expose _table / _test_id / _test_name / _domain / _mode so
    # the user code (and the auto-record fallback) can use them.
    preamble = [
        f"# ── {table} :: {test_name}",
    ]
    if mode == "monitoring":
        preamble.append("# mode: monitoring (always passes, informational)")
    preamble.extend([
        f"if {toggle}:",
        f"    _table = {json.dumps(table)}",
        f"    _test_id = {json.dumps(test_id)}",
        f"    _test_name = {json.dumps(test_name)}",
        f"    _domain = {json.dumps(domain)}",
        f"    _mode = {json.dumps(mode)}",
        "    try:",
    ])

    # Indent the user's python body by 8 spaces (inside try:).
    indented = "\n".join(("        " + ln) if ln.strip() else "" for ln in python_body.splitlines())

    tail = [
        "        # If the user code didn't record its own result, default to PASS.",
        "        if _table not in VALIDATION_RESULTS or _test_id not in VALIDATION_RESULTS[_table]:",
        "            _record(_table, _test_id, _test_name, _domain, True, 0, '', None, _mode)",
        "    except Exception as _exc:",
        "        _record(_table, _test_id, _test_name, _domain, False, -1, '', str(_exc), _mode)",
        f"        print({json.dumps(f'ERROR    {table} :: {test_name}: ')} + str(_exc))",
        "else:",
        f"    print({json.dumps(f'SKIP     {table} :: {test_name}')})",
    ]

    body = "\n".join(preamble + [indented] + tail)

    check_cell = {
        "kind": "python",
        "source": body,
        "frozen": frozen,
        "editable": editable,
    }
    return [heading_cell, check_cell]


def _build_summary_cell_source() -> str:
    return "\n".join(
        [
            "# ── Summary ──────────────────────────────────────────────────────",
            "from pyspark.sql import Row",
            "",
            "# Build one flat row per (table x test).",
            "_flat = []",
            "for _tbl in sorted(VALIDATION_RESULTS.keys()):",
            "    _results = VALIDATION_RESULTS[_tbl]",
            "    _dom = next(iter(_results.values())).get('domain', 'other') if _results else 'other'",
            "    for _t in TESTS_META:",
            "        _r = _results.get(_t['id'])",
            "        if _r is None:",
            "            continue",
            "        if _r.get('error'):",
            "            _status, _detail = 'ERROR', str(_r['error'])[:300]",
            "        elif _r.get('mode') == 'monitoring':",
            "            _status, _detail = 'MONITOR', '{} row(s) observed'.format(_r['failing_rows'])",
            "        elif _r['passed']:",
            "            _status, _detail = 'PASS', 'no violations found'",
            "        else:",
            "            _status, _detail = 'FAIL', '{:,} violation(s) found'.format(_r['failing_rows'])",
            "        _flat.append(Row(status=_status, domain=_dom, table=_tbl,",
            "                        test=_r['test_name'], details=_detail))",
            "",
            "_fails  = [r for r in _flat if r.status in ('FAIL', 'ERROR')]",
            "_passes = [r for r in _flat if r.status not in ('FAIL', 'ERROR')]",
            "",
            "# FAILs / ERRORs first",
            "print('{} FAIL(s) / ERROR(s)'.format(len(_fails)) if _fails else 'No failures')",
            "if _fails:",
            "    display(spark.createDataFrame(_fails).orderBy('domain', 'table', 'test'))",
            "",
            "# PASSes / MONITORs last",
            "if SHOW_PASS:",
            "    print('{} PASS / MONITOR / SKIP'.format(len(_passes)))",
            "    if _passes:",
            "        display(spark.createDataFrame(_passes).orderBy('domain', 'table', 'test'))",
            "else:",
            "    print('{} PASS / MONITOR / SKIP (hidden — set SHOW_PASS = True to display)'.format(len(_passes)))",
            "",
            "_total   = len(_flat)",
            "_failed  = len(_fails)",
            "_errors  = sum(1 for r in _flat if r.status == 'ERROR')",
            "_monitor = sum(1 for r in _flat if r.status == 'MONITOR')",
            "print('Total: {}   Failed: {}   Errors: {}   Monitor-only: {}'.format(_total, _failed, _errors, _monitor))",
            "",
            "# Render a download link for the summary CSV directly in the notebook output.",
            "def save_summary(filename='validation_summary.csv'):",
            "    if not _flat:",
            "        print('No summary data to save.')",
            "        return",
            "    import io, base64",
            "    from IPython.display import display as _ipy_display, HTML",
            "    _buf = io.StringIO()",
            "    spark.createDataFrame(_flat).orderBy('status', 'domain', 'table', 'test').toPandas().to_csv(_buf, index=False)",
            "    _b64 = base64.b64encode(_buf.getvalue().encode()).decode()",
            "    _ipy_display(HTML(f'<a href=\"data:text/csv;base64,{_b64}\" download=\"{filename}\">&#11015; Download {filename}</a>'))",
            "",
            "save_summary()",
        ]
    )


def _build_diagnostics_cell_source(fail_on_error: bool) -> str:
    # Terminal behaviour: raise (breaks pipeline) or print-only (warn) per
    # validation.yaml `fail_on_error`.
    if fail_on_error:
        _fail_block = [
            "    raise Exception(",
            "        f'Silver validation failed: {_fail_count} check(s) failed'",
            "    )",
        ]
    else:
        _fail_block = [
            "    print(",
            "        f'⚠ Silver validation: {_fail_count} check(s) failed — '",
            "        'continuing (fail_on_error=false in validation.yaml).'",
            "    )",
        ]
    return "\n".join(
        [
            "# ── Diagnostics ──────────────────────────────────────────────────",
            "# For every failing (non-monitoring) check, display the diagnostic",
            "# query result. Terminal behaviour driven by validation.yaml fail_on_error.",
            "",
            "_any_failed = False",
            "_fail_count = 0",
            "for _tbl in sorted(VALIDATION_RESULTS.keys()):",
            "    _results = VALIDATION_RESULTS[_tbl]",
            "    for _test_id, _r in _results.items():",
            "        # skip monitoring cells — they always 'pass'",
            "        if _r.get('mode') == 'monitoring':",
            "            continue",
            "        if _r['passed'] and _r.get('error') is None:",
            "            continue",
            "        _any_failed = True",
            "        _fail_count += 1",
            "        print(f'\\n▶ {_tbl} :: {_r[\"test_name\"]}')",
            "        if _r.get('error'):",
            "            print(f'  ERROR: {_r[\"error\"]}')",
            "            continue",
            "        print(f'  failing rows: {_r[\"failing_rows\"]}')",
            "        _diag = (_r.get('diagnostic_sql') or '').strip()",
            "        if not _diag:",
            "            print('  (no diagnostic_sql defined for this test)')",
            "            continue",
            "        try:",
            "            display(spark.sql(_diag))",
            "        except Exception as _exc:",
            "            print(f'  ⚠ diagnostic query failed: {_exc}')",
            "",
            "if not _any_failed:",
            "    print('All validation checks passed.')",
            "else:",
            *_fail_block,
        ]
    )


# ---------------------------------------------------------------------------
# Python source helpers
# ---------------------------------------------------------------------------

def _py_triple_quoted(text: str) -> str:
    """Return *text* wrapped in a triple-quoted Python literal.

    Escapes any embedded triple-quotes and backslashes.
    """
    safe = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""' + safe + '"""'


def _comment_lines(text: str) -> List[str]:
    """Turn a (possibly multi-line) string into a list of ``# ...`` lines."""
    return [
        f"# {line}" if line else "#"
        for line in str(text).rstrip("\n").split("\n")
    ]


# ---------------------------------------------------------------------------
# Fabric notebook-content.py builder
# ---------------------------------------------------------------------------

def _build_fabric_content(
    cells: List[Dict[str, Any]],
    lakehouse_name: str,
    lakehouse_id: Optional[str],
    lakehouse_workspace_id: Optional[str],
) -> str:
    lines: List[str] = [
        "# Fabric notebook source",
        "",
        "# METADATA ********************",
        "",
    ]

    metadata: Dict[str, Any] = {
        "kernel_info": {"name": "synapse_pyspark"},
        "dependencies": {},
    }
    if lakehouse_id or lakehouse_name:
        lh: Dict[str, Any] = {}
        if lakehouse_id:
            lh["default_lakehouse"] = lakehouse_id
        if lakehouse_name:
            lh["default_lakehouse_name"] = lakehouse_name
        if lakehouse_workspace_id:
            lh["default_lakehouse_workspace_id"] = lakehouse_workspace_id
        if lakehouse_id:
            lh["known_lakehouses"] = [{"id": lakehouse_id}]
        metadata["dependencies"]["lakehouse"] = lh

    for ml in _format_meta(metadata):
        lines.append(ml)
    lines.append("")

    for cell in cells:
        lines.extend(_format_cell(cell))
        lines.append("")

    return "\n".join(lines)


def _format_cell(cell: Dict[str, Any]) -> List[str]:
    kind = cell.get("kind", "python")
    source = cell.get("source", "")

    # Markdown cells use Fabric's `# MARKDOWN ********************` block form.
    # These are pure content — no trailing METADATA block — so they render as
    # first-class markdown in the notebook outline.
    if kind == "markdown":
        result: List[str] = ["# MARKDOWN ********************", ""]
        for line in source.split("\n"):
            result.append(f"# {line}" if line else "#")
        return result

    # Everything else is a code cell (python / configure magic / sql magic).
    result = ["# CELL ********************", ""]

    if kind == "configure":
        for line in source.split("\n"):
            result.append(f"# MAGIC {line}" if line.strip() else "# MAGIC")
    elif kind == "sql":
        # source is raw SQL (no magic prefix)
        result.append("# MAGIC %%sql")
        for line in source.split("\n"):
            result.append(f"# MAGIC {line}" if line.strip() else "# MAGIC")
    else:  # python
        for line in source.split("\n"):
            result.append(line)

    result.append("")
    result.append("# METADATA ********************")
    result.append("")

    if kind == "sql":
        cell_meta: Dict[str, Any] = {"language": "sparksql", "language_group": "synapse_pyspark"}
    else:
        cell_meta = {"language": "python", "language_group": "synapse_pyspark"}

    if "frozen" in cell:
        cell_meta["frozen"] = bool(cell["frozen"])
    if "editable" in cell:
        cell_meta["editable"] = bool(cell["editable"])

    for ml in _format_meta(cell_meta):
        result.append(ml)

    return result


def _format_meta(data: Dict[str, Any]) -> List[str]:
    return [f"# META {line}" for line in json.dumps(data, indent=2).split("\n")]


def _deterministic_id(name: str) -> str:
    h = hashlib.md5(name.encode()).hexdigest()
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:32]}"
