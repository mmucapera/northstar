"""SQL generator for Spark SQL output using Jinja2 templates — updated for A1 schema logic."""
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from ..core.models import Column, JoinSpec, ModelKind, ResolvedModel
from ..functions.registry import FunctionResolver
from ..utils.logging import get_logger


logger = get_logger(__name__)

SCHEMA_ONLY_SENTINEL = "__SCHEMA_ONLY__"


# ======================================================
# Schema Qualification
# ======================================================


# Layer schemas that can appear as a directory-derived prefix in model names
_LAYER_SCHEMAS: frozenset = frozenset({"bronze", "silver", "gold", "interface"})


def qualify(name: str, layer: Optional[str] = None) -> str:
    """Qualify table name using the model's declared layer."""
    if not name:
        return name

    n = name.strip()

    # If no layer specified, return name unchanged
    if not layer:
        return n

    # Already qualified (contains a dot) - return as-is
    if "." in n:
        return n

    # Qualify with layer as schema
    return f"{layer.lower().strip()}.{n}"


def qualify_model_name(name: str, layer: Optional[str] = None) -> str:
    """Qualify a *model* name using its declared layer.

    Unlike :func:`qualify`, this function strips any stale layer prefix that
    was injected by the file-system discovery logic (e.g. a YAML file living
    under a ``gold/`` directory while declaring ``layer: interface`` in its
    content).  The declared layer always takes precedence.
    """
    if not name or not layer:
        return qualify(name, layer)

    n = name.strip()
    # Strip existing known-layer prefix so the declared layer wins
    if "." in n:
        existing_prefix = n.split(".", 1)[0].lower()
        if existing_prefix in _LAYER_SCHEMAS:
            n = n.split(".", 1)[1]

    return f"{layer.lower().strip()}.{n}"


class SparkSQLGenerator:
    """Generate Spark SQL from resolved models using Jinja2 templates (updated)."""

    def __init__(
        self,
        function_resolver: Optional[FunctionResolver] = None,
        template_dir: Optional[str] = None,
    ):
        self.function_resolver = function_resolver
        self.generated_sql: Dict[str, str] = {}

        if template_dir is None:
            template_dir = Path(__file__).parent / "templates" / "spark"

        self.env = Environment(
            loader=FileSystemLoader(str(template_dir)),
            trim_blocks=True,
            lstrip_blocks=True,
            keep_trailing_newline=True,
        )

        self.env.filters["indent"] = lambda s, n: "\n".join(
            " " * n + line for line in s.split("\n")
        )
        self.env.filters["prefix_columns"] = self._prefix_columns_filter

    # ======================================================
    # Helper: build FROM ... JOIN ...
    # ======================================================
    @staticmethod
    def _from_with_joins(
        base_table: str,
        base_alias: str,
        joins: List[JoinSpec],
        layer: Optional[str] = None,
    ) -> str:
        sql = f"FROM {qualify(base_table, layer)} {base_alias}"
        for j in joins:
            on_clause = re.sub(r'["`$begin:math:display$$end:math:display$\']', "", j.on_clause)
            join_layer = getattr(j, "layer", None) or layer
            sql += (
                f"\n{j.join_type.value} JOIN {qualify(j.ref_table, join_layer)} {j.ref_alias} "
                f"ON {on_clause}"
            )
        return sql

    # ======================================================
    # Type normalization
    # ======================================================
    @staticmethod
    def _spark_type(t: str) -> str:
        if not t:
            return "STRING"
        s = t.strip().upper()

        if s.startswith(("CHAR", "NCHAR", "VARCHAR", "NVARCHAR", "STRING", "TEXT")):
            return "STRING"
        if s in {"INT", "INTEGER"}:
            return "INT"
        if s in {"BIGINT"}:
            return "BIGINT"
        if s in {"SMALLINT", "TINYINT", "BYTEINT"}:
            return "SMALLINT"
        if s.startswith("NUMERIC"):
            s = "DECIMAL" + s[len("NUMERIC") :]
        if s.startswith("DECIMAL"):
            return s
        if s in {"FLOAT", "REAL", "DOUBLE PRECISION"}:
            return "DECIMAL"
        if s == "DOUBLE":
            return "DECIMAL"
        if s == "DATE":
            return "DATE"
        if s in {"DATETIME", "TIMESTAMPTZ", "DATETIME2", "DATETIME2(6)"}:
            return "DATE"
        if s == "TIMESTAMP":
            return "TIMESTAMP"
        if s in {"BOOL", "BOOLEAN"}:
            return "BOOLEAN"

        return s

    # ======================================================
    # detect schema-only bronze
    # ======================================================
    @staticmethod
    def _is_schema_only_table(model: "ResolvedModel") -> bool:
        base = (getattr(model, "source_table", None) or "").strip()
        layer = (getattr(model, "layer", None) or "").strip().lower()
        return layer == "bronze" and (not base or base.upper() == SCHEMA_ONLY_SENTINEL.upper())

    @staticmethod
    def _infer_source_layer(source_table: str, model_layer: Optional[str]) -> Optional[str]:
        """Infer the layer for a source table."""
        if not source_table:
            return None

        if "." in source_table:
            return None

        if model_layer:
            layer_lower = model_layer.lower()
            if layer_lower == "silver":
                return "bronze"
            elif layer_lower in ("gold", "interface"):
                return "silver"

        return model_layer

    def _build_schema_columns_definition(self, columns: List[Column]) -> str:
        """Build '(col1 TYPE, col2 TYPE, ...)' for CREATE TABLE."""
        if not columns:
            return "(\n    id STRING\n)"

        defs = []
        for c in columns:
            name = re.sub(r'["`]', "", c.name)
            dtype = self._spark_type(getattr(c, "data_type", None) or "")
            defs.append(f"    {name} {dtype}")
        return "(\n" + ",\n".join(defs) + "\n)"

    # ======================================================
    # Helper: qualify simple SELECT identifiers with base alias
    # ======================================================
    @staticmethod
    def _qualify_simple_select_identifiers(sql: str, base_alias: str = "T") -> str:
        m_select = re.search(r"\bSELECT\b", sql, flags=re.IGNORECASE)
        if not m_select:
            return sql

        m_from = re.search(r"\bFROM\b", sql[m_select.end() :], flags=re.IGNORECASE)
        if not m_from:
            return sql

        start = m_select.end()
        end = m_select.end() + m_from.start()

        before = sql[:start]
        select_block = sql[start:end]
        after = sql[end:]

        lines = select_block.splitlines()
        new_lines: List[str] = []

        simple_col_pattern = re.compile(
            r"^(?P(indent)\s*)"
            r"(?:(?P<distinct>DISTINCT)\s+)?"
            r"(?P<col>[A-Za-z_][A-Za-z0-9_]*)"
            r"\s*(?P<trail>,?)\s*$",
            flags=re.IGNORECASE,
        )

        sql_keywords = {
            "distinct",
            "case",
            "when",
            "then",
            "else",
            "end",
            "as",
            "and",
            "or",
            "not",
            "null",
            "true",
            "false",
            "select",
        }

        for line in lines:
            stripped = line.strip()

            if not stripped or stripped.upper().startswith("--"):
                new_lines.append(line)
                continue

            if "." in stripped or "(" in stripped or ")" in stripped or " AS " in stripped.upper():
                new_lines.append(line)
                continue

            m = simple_col_pattern.match(line)
            if not m:
                new_lines.append(line)
                continue

            col_name = m.group("col")
            if col_name.lower() in sql_keywords:
                new_lines.append(line)
                continue

            indent = m.group("indent") or ""
            distinct = m.group("distinct")
            trail = m.group("trail") or ""

            if distinct:
                new_line = f"{indent}{distinct} {base_alias}.{col_name}{trail}"
            else:
                new_line = f"{indent}{base_alias}.{col_name}{trail}"

            new_lines.append(new_line)

        new_block = "\n".join(new_lines)
        return before + new_block + after

    @staticmethod
    def _strip_ctas_wrapper(sql: str) -> str:
        """
        Remove leading:
          CREATE OR REPLACE TABLE <x> [USING delta] AS
        and return only the SELECT/WITH...SELECT body.
        """
        if not sql:
            return sql

        s = sql.strip().rstrip().rstrip(";").strip()

        m = re.match(
            r"(?is)^\s*CREATE\s+OR\s+REPLACE\s+TABLE\s+\S+\s+(?:USING\s+DELTA\s+)?AS\s+",
            s,
        )
        if m:
            return s[m.end():].lstrip()

        m2 = re.match(
            r"(?is)^\s*CREATE\s+TABLE\s+\S+\s+(?:USING\s+DELTA\s+)?AS\s+",
            s,
        )
        if m2:
            return s[m2.end():].lstrip()

        return s

    def _format_sql_by_layer(self, sql: str, model: ResolvedModel, model_name_q: str) -> str:
        """
        Final output rules:
          - bronze: (preferred) CREATE TABLE with typed schema USING delta
                   (fallback) legacy select-derived schema (no types)
          - silver: only <select> (no CTAS)
          - gold:  CREATE OR REPLACE TABLE <name> AS <select>
        """
        layer = (getattr(model, "layer", None) or "").strip().lower()

        # Schema-only bronze tables remain exactly as created (already typed)
        if self._is_schema_only_table(model):
            return sql

        body = self._strip_ctas_wrapper(sql).strip().rstrip(";").strip()

        if layer == "silver":
            return body + "\n"

        if layer in ("gold", "interface"):
            return f"CREATE OR REPLACE TABLE {model_name_q} AS\n{body}\n"

        if layer == "bronze":
            # ✅ FIX: if model has declared columns with any data_type, emit typed schema DDL.
            cols = getattr(model, "columns", None) or []
            has_any_type = any(getattr(c, "data_type", None) for c in cols)

            if cols and has_any_type:
                col_defs = self._build_schema_columns_definition(cols)
                return f"CREATE OR REPLACE TABLE {model_name_q}\n{col_defs}\nUSING delta;\n"

            # Fallback: preserve your existing legacy behaviour (may be used when no types exist)
            legacy = body
            legacy = legacy.replace("T.", "")
            legacy = legacy.replace("SELECT DISTINCT\n", "")
            legacy = legacy.replace("FROM bronze.__SCHEMA_ONLY__ T", ")USING delta")
            return f"CREATE OR REPLACE TABLE {model_name_q} (\n{legacy}\n"

        return sql

    # ======================================================
    # Main SQL generation
    # ======================================================
    def generate(self, model: ResolvedModel, context: Optional[Dict[str, Any]] = None) -> str:
        """Generate SQL for a resolved model."""
        logger.info(f"Generating SQL for {model.name}")

        if self.function_resolver:
            model = self._expand_functions(model, context)

        if getattr(model, "joins", None):
            for j in model.joins:
                if getattr(j, "on_clause", None):
                    j.on_clause = re.sub(
                        r'(?:"([A-Za-z_][A-Za-z0-9_]*)"|'
                        r"([A-Za-z_][A-Za-z0-9_]*)|"
                        r"\$begin:math:display\$([A-Za-z_][A-Za-z0-9_]*)\$end:math:display\$)",
                        lambda m: next(g for g in m.groups() if g),
                        j.on_clause,
                    )

        layer = getattr(model, "layer", None)

        model_name_q = qualify_model_name(model.name, layer)
        if getattr(model, "source_table", None):
            src_layer = self._infer_source_layer(model.source_table, layer)
            model.source_table = qualify(model.source_table, src_layer)

        if hasattr(model, "joins") and model.joins:
            for j in model.joins:
                join_layer = getattr(j, "layer", None) or layer
                j.ref_table = qualify(j.ref_table, join_layer)

        # ====================================================
        # BRONZE SCHEMA ONLY
        # ====================================================
        if self._is_schema_only_table(model):
            col_defs = self._build_schema_columns_definition(model.columns)
            sql = f"CREATE OR REPLACE TABLE {model_name_q}\n{col_defs}\nUSING delta;"
            self.generated_sql[model.name] = sql
            return sql

        return self._generate_sql(model, model_name_q)

    # ======================================================
    # Internal SQL generation logic
    # ======================================================
    def _generate_sql(self, model: ResolvedModel, model_name_q: str) -> str:
        """Template-based generation + derived SQL override"""
        derived = model.derived_sql

        if not derived:
            try:
                derived = getattr(model.metadata, "derived_sql", None)
            except Exception:
                derived = None

        if derived is not None and str(derived).strip():
            logger.info(f"[DERIVED_SQL] Using derived_sql for {model.name}")

            sql = str(derived).strip()

            sql = re.sub(
                r"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+\S+",
                f"CREATE OR REPLACE TABLE {model_name_q}",
                sql,
            )

            sql = self._apply_where_filters(sql, model)
            sql = self._format_sql_by_layer(sql, model, model_name_q)

            self.generated_sql[model.name] = sql
            return sql

        try:
            if model.kind == ModelKind.CTE:
                sql = self._generate_with_template("cte.sql.j2", model)

            elif model.kind == ModelKind.VIEW:
                sql = self._generate_with_template("view.sql.j2", model)

            elif model.kind == ModelKind.TABLE:
                sql = self._generate_with_template("table.sql.j2", model)
                sql = re.sub(
                    rf"(?i)\bCREATE\s+(?:OR\s+REPLACE\s+)?TABLE\s+{re.escape(model.name)}\b",
                    f"CREATE OR REPLACE TABLE {model_name_q}",
                    sql,
                )
            else:
                sql = self._generate_fallback(model)

            # enforce alias T
            try:
                if getattr(model, "source_table", None):
                    base_q = model.source_table
                    sql = re.sub(
                        rf"FROM\s+{re.escape(base_q)}(?!\s+T\b)",
                        f"FROM {base_q} T",
                        sql,
                        flags=re.IGNORECASE,
                    )
            except Exception:
                pass

            try:
                sql = self._qualify_simple_select_identifiers(sql, base_alias="T")
            except Exception:
                pass

            sql = self._apply_where_filters(sql, model)
            sql = self._format_sql_by_layer(sql, model, model_name_q)

            self.generated_sql[model.name] = sql
            return sql

        except TemplateNotFound:
            return self._generate_fallback(model)

    # ======================================================
    # fallback
    # ======================================================
    def _generate_fallback(self, model: ResolvedModel) -> str:
        layer = getattr(model, "layer", None)
        name_q = qualify_model_name(model.name, layer)

        src_layer = self._infer_source_layer(model.source_table, layer)
        src_q = qualify(model.source_table, src_layer)

        if not model.columns:
            cols_sql = "    *"
        else:
            cols_sql = self._build_columns_clause(model.columns, "T")

        if hasattr(model, "joins") and model.joins:
            from_sql = self._from_with_joins(model.source_table, "T", model.joins, layer)
        else:
            from_sql = f"FROM {src_q} T"

        sql = "\n".join(
            [
                f"CREATE OR REPLACE TABLE {name_q} USING delta AS",
                "SELECT",
                cols_sql,
                from_sql,
            ]
        )
        return sql

    # ======================================================
    # generate_all
    # ======================================================
    def generate_all(
        self,
        models: Dict[str, ResolvedModel],
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, str]:
        results: Dict[str, str] = {}
        for name, model in models.items():
            try:
                sql = self.generate(model, context)
                results[name] = sql
            except Exception as e:
                logger.error(f"Failed to generate SQL for {name}: {e}")
        return results

    # ======================================================
    # Columns
    # ======================================================
    def _build_columns_clause(self, columns: List[Column], source_alias: str = None) -> str:
        if not columns:
            return "    *"

        column_parts = []
        needs_alias = source_alias and "." not in source_alias
        table_prefix = f"{source_alias}." if needs_alias else ""

        for col in columns:
            expr = col.expression or col.name
            expr = re.sub(r'["`$begin:math:display$$end:math:display$]', "", expr)
            name = re.sub(r'["`]', "", col.name)

            if col.expression and col.expression != col.name:
                if (
                    "." in expr
                    or "(" in expr
                    or expr.upper().startswith(
                        ("CURRENT_TIMESTAMP", "CURRENT_DATE", "CURRENT_TIME")
                    )
                ):
                    col_sql = f"{expr} AS {name}"
                else:
                    col_sql = f"{table_prefix}{expr} AS {name}"
            else:
                col_sql = f"{table_prefix}{name}"

            column_parts.append(f"    {col_sql}")

        return ",\n".join(column_parts)

    # ======================================================
    # Template render
    # ======================================================
    def _generate_with_template(self, tmpl: str, model: ResolvedModel) -> str:
        layer = getattr(model, "layer", None)
        src_layer = self._infer_source_layer(model.source_table, layer)

        template = self.env.get_template(tmpl)
        return template.render(
            model=model,
            columns=model.columns,
            source_table=qualify(model.source_table, src_layer),
            cte_definitions=model.cte_definitions or {},
            joins=getattr(model, "joins", []) or [],
            base_alias="T",
        )

    # ======================================================
    # Dynamic functions
    # ======================================================
    def _expand_functions(
        self, model: ResolvedModel, context: Optional[Dict[str, Any]]
    ) -> ResolvedModel:
        for c in model.columns:
            if c.expression and "@" in c.expression:
                c.expression = self.function_resolver.resolve_expression(c.expression, context)
        if getattr(model, "where_clause", None) and "@" in model.where_clause:
            model.where_clause = self.function_resolver.resolve_expression(
                model.where_clause, context
            )
        if getattr(model, "having_clause", None):
            new = []
            for clause in model.having_clause:
                if "@" in clause:
                    new.append(self.function_resolver.resolve_expression(clause, context))
                else:
                    new.append(clause)
            model.having_clause = new
        return model

    def _prefix_columns_filter(
        self, expression: str, table_prefix: str, columns: List[Column]
    ) -> str:
        return expression

    # ======================================================
    # Inject filters.where_conditions as WHERE clause
    # ======================================================
    def _apply_where_filters(self, sql: str, model: ResolvedModel) -> str:
        where_clause = getattr(model, "where_clause", None)
        if not where_clause:
            return sql

        upper = sql.upper()

        where_pattern = re.compile(
            r"(WHERE\s+)(.+?)(\s*(GROUP BY|ORDER BY|HAVING|LIMIT|;|$))",
            re.IGNORECASE | re.DOTALL,
        )

        if "WHERE" in upper:

            def _append_and(m):
                return f"{m.group(1)}{m.group(2)} AND ({where_clause}){m.group(3)}"

            new_sql, n = where_pattern.subn(_append_and, sql, count=1)
            if n > 0:
                return new_sql
            return sql + f"\nAND ({where_clause})"

        insert_pattern = re.compile(r"\s*(GROUP BY|ORDER BY|HAVING|LIMIT|;)", re.IGNORECASE)
        m = insert_pattern.search(sql)
        if not m:
            return sql.rstrip(";\n ") + f"\nWHERE {where_clause}\n"

        return sql[: m.start()] + f"\nWHERE {where_clause}\n" + sql[m.start() :]