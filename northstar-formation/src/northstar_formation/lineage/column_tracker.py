"""Column-level lineage tracking.

This module provides utilities for parsing SQL expressions to extract
column dependencies and track column-level lineage through the data pipeline.
"""

import re
from typing import List, Set, Tuple


class ColumnExpressionParser:
    """Parse SQL expressions to extract column dependencies.

    This parser identifies column references within SQL expressions,
    handling common patterns like CAST, function calls, and table aliases.
    """

    # Common SQL functions that don't represent column references
    SQL_FUNCTIONS: Set[str] = {
        # Type casting and conversion
        "cast",
        "convert",
        "try_cast",
        "try_convert",
        # Null handling
        "coalesce",
        "nullif",
        "ifnull",
        "nvl",
        "nvl2",
        "isnull",
        # String functions
        "concat",
        "concat_ws",
        "substring",
        "substr",
        "trim",
        "ltrim",
        "rtrim",
        "upper",
        "lower",
        "length",
        "len",
        "replace",
        "translate",
        "split",
        "left",
        "right",
        "lpad",
        "rpad",
        "reverse",
        "initcap",
        "instr",
        "locate",
        "position",
        "regexp_replace",
        "regexp_extract",
        # Numeric functions
        "round",
        "floor",
        "ceil",
        "ceiling",
        "abs",
        "mod",
        "power",
        "pow",
        "sqrt",
        "exp",
        "log",
        "log10",
        "log2",
        "sign",
        "rand",
        "random",
        "greatest",
        "least",
        "trunc",
        "truncate",
        # Date/time functions
        "current_date",
        "current_timestamp",
        "current_time",
        "now",
        "date_add",
        "date_sub",
        "datediff",
        "dateadd",
        "date_diff",
        "year",
        "month",
        "day",
        "hour",
        "minute",
        "second",
        "quarter",
        "week",
        "dayofweek",
        "dayofmonth",
        "dayofyear",
        "weekofyear",
        "date_format",
        "to_date",
        "to_timestamp",
        "from_unixtime",
        "unix_timestamp",
        "months_between",
        "add_months",
        "last_day",
        "next_day",
        "date_trunc",
        # Aggregate functions
        "sum",
        "count",
        "avg",
        "min",
        "max",
        "first",
        "last",
        "collect_list",
        "collect_set",
        "count_distinct",
        "approx_count_distinct",
        "stddev",
        "variance",
        "var_pop",
        "var_samp",
        "percentile",
        "percentile_approx",
        # Window functions
        "row_number",
        "rank",
        "dense_rank",
        "ntile",
        "lead",
        "lag",
        "first_value",
        "last_value",
        "nth_value",
        "cume_dist",
        "percent_rank",
        # Hash functions
        "xxhash64",
        "md5",
        "sha1",
        "sha2",
        "hash",
        "crc32",
        "murmur3",
        # Conditional functions
        "if",
        "iff",
        "case",
        "when",
        "decode",
        # Array/Map functions
        "array",
        "map",
        "struct",
        "named_struct",
        "size",
        "explode",
        "posexplode",
        "array_contains",
        "array_distinct",
        "array_sort",
        "array_union",
        "map_keys",
        "map_values",
        "element_at",
        "transform",
        # PySpark specific
        "lit",
        "col",
        "column",
        "expr",
        "otherwise",
        # Type checking
        "typeof",
        "isnan",
        "isnotnull",  # JSON functions
        "get_json_object",
        "json_tuple",
        "from_json",
        "to_json",
        "schema_of_json",
        # Other
        "uuid",
        "monotonically_increasing_id",
        "spark_partition_id",
        "input_file_name",
        "input_file_block_start",
        "input_file_block_length",
    }

    # SQL keywords that should not be treated as columns
    SQL_KEYWORDS: Set[str] = {
        "select",
        "from",
        "where",
        "and",
        "or",
        "not",
        "in",
        "is",
        "null",
        "true",
        "false",
        "as",
        "on",
        "join",
        "left",
        "right",
        "inner",
        "outer",
        "full",
        "cross",
        "case",
        "when",
        "then",
        "else",
        "end",
        "between",
        "like",
        "ilike",
        "rlike",
        "over",
        "partition",
        "by",
        "order",
        "asc",
        "desc",
        "nulls",
        "first",
        "last",
        "distinct",
        "all",
        "union",
        "intersect",
        "except",
        "group",
        "having",
        "limit",
        "offset",
        "with",
        "recursive",
        "exists",
        "any",
        "some",
        "into",
        "values",
        "insert",
        "update",
        "delete",
        "create",
        "drop",
        "alter",
        "table",
        "view",
        "index",
        "using",
        "natural",
        "lateral",
        "rows",
        "range",
        "unbounded",
        "preceding",
        "following",
        "current",
        "row",
        "interval",
        # Data types
        "int",
        "integer",
        "bigint",
        "smallint",
        "tinyint",
        "float",
        "double",
        "decimal",
        "numeric",
        "string",
        "varchar",
        "char",
        "boolean",
        "bool",
        "date",
        "timestamp",
        "binary",
        "array",
        "map",
        "struct",
        "void",
        "nvarchar",
        "text",
        "long",
        "short",
    }

    def __init__(self) -> None:
        """Initialize the parser."""
        # Compile regex patterns for efficiency
        self._identifier_pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\b"
        )
        self._quoted_identifier_pattern = re.compile(r'`([^`]+)`|"([^"]+)"|\[([^\]]+)\]')

    def extract_column_references(self, expression: str) -> List[str]:
        """Extract column references from a SQL expression.

        Args:
            expression: SQL expression (e.g., "CAST(customer_id AS BIGINT)")

        Returns:
            List of column names referenced in the expression.

        Examples:
            >>> parser = ColumnExpressionParser()
            >>> parser.extract_column_references("CAST(customer_id AS BIGINT)")
            ['customer_id']
            >>> parser.extract_column_references("xxhash64(CONCAT(col1, col2))")
            ['col1', 'col2']
            >>> parser.extract_column_references("COALESCE(T.name, J.alt_name)")
            ['T.name', 'J.alt_name']
            >>> parser.extract_column_references("current_timestamp")
            []
        """
        if not expression:
            return []

        # Handle quoted identifiers first
        quoted_columns = self._extract_quoted_identifiers(expression)

        # Find all potential identifiers
        matches = self._identifier_pattern.findall(expression)

        columns: List[str] = []
        seen: Set[str] = set()

        for match in matches:
            # Get the base name (last part after dots)
            parts = match.split(".")
            base_name = parts[-1].lower()

            # Skip if it's a SQL function or keyword
            if base_name in self.SQL_FUNCTIONS:
                continue
            if base_name in self.SQL_KEYWORDS:
                continue

            # Skip pure numbers
            if base_name.isdigit():
                continue

            # Skip literals (strings starting with quote chars are handled separately)
            if self._is_literal_context(expression, match):
                continue

            # Add if not seen
            if match.lower() not in seen:
                seen.add(match.lower())
                columns.append(match)

        # Add quoted identifiers
        for quoted in quoted_columns:
            if quoted.lower() not in seen:
                seen.add(quoted.lower())
                columns.append(quoted)

        return columns

    def _extract_quoted_identifiers(self, expression: str) -> List[str]:
        """Extract quoted column identifiers.

        Args:
            expression: SQL expression.

        Returns:
            List of quoted column names.
        """
        columns: List[str] = []
        matches = self._quoted_identifier_pattern.findall(expression)

        for match in matches:
            # findall returns tuples for multiple groups
            for group in match:
                if group:
                    columns.append(group)

        return columns

    def _is_literal_context(self, expression: str, match: str) -> bool:
        """Check if a match is within a string literal.

        Args:
            expression: Full SQL expression.
            match: Matched identifier.

        Returns:
            True if the match is within a string literal.
        """
        # Simple heuristic: check for common literal patterns
        # This is not exhaustive but covers common cases
        literal_patterns = [
            f"'{match}'",
            f'"{match}"',
            f"CAST('{match}'",
            f'CAST("{match}"',
        ]
        expr_lower = expression.lower()
        match_lower = match.lower()

        for pattern in literal_patterns:
            if pattern.lower() in expr_lower:
                return True

        return False

    def is_simple_reference(self, expression: str, column_name: str) -> bool:
        """Check if expression is just a simple column reference.

        Args:
            expression: SQL expression.
            column_name: Column name to check.

        Returns:
            True if expression is just the column name (possibly with alias prefix).
        """
        if not expression:
            return True

        expr_clean = expression.strip()

        # Direct match
        if expr_clean.lower() == column_name.lower():
            return True

        # Match with alias prefix (e.g., "T.column_name")
        pattern = rf"^[A-Za-z_][A-Za-z0-9_]*\.{re.escape(column_name)}$"
        return bool(re.match(pattern, expr_clean, re.IGNORECASE))

    def extract_source_columns_with_table(self, expression: str) -> List[Tuple[str, str]]:
        """Extract column references with their table aliases.

        Args:
            expression: SQL expression.

        Returns:
            List of (table_alias, column_name) tuples.
            If no table alias, the first element is None.
        """
        if not expression:
            return []

        columns = self.extract_column_references(expression)
        result: List[Tuple[str, str]] = []

        for col in columns:
            parts = col.split(".")
            if len(parts) >= 2:
                # Has table alias: T.column or schema.table.column
                table_alias = ".".join(parts[:-1])
                column_name = parts[-1]
                result.append((table_alias, column_name))
            else:
                # No table alias
                result.append(("", col))

        return result

    def get_transformation_type(self, expression: str, column_name: str) -> str:
        """Determine the type of transformation applied to a column.

        Args:
            expression: SQL expression.
            column_name: Output column name.

        Returns:
            Transformation type: 'direct', 'cast', 'hash', 'aggregation',
            'window', 'computation', or 'unknown'.
        """
        if not expression:
            return "direct"

        expr_lower = expression.lower().strip()
        col_lower = column_name.lower()

        # Check for simple reference to output column
        if self.is_simple_reference(expression, column_name):
            return "direct"

        # Check if expression is just a plain identifier (any column reference)
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", expression.strip()):
            return "direct"

        # Check if expression is a table.column reference
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$", expression.strip()):
            return "direct"

        # Check for common transformation patterns
        if expr_lower.startswith("cast(") or "::(" in expr_lower:
            return "cast"

        hash_functions = {"xxhash64", "md5", "sha1", "sha2", "hash", "murmur3"}
        for func in hash_functions:
            if expr_lower.startswith(f"{func}("):
                return "hash"

        agg_functions = {"sum", "count", "avg", "min", "max", "first", "last"}
        for func in agg_functions:
            if expr_lower.startswith(f"{func}("):
                return "aggregation"

        window_functions = {
            "row_number",
            "rank",
            "dense_rank",
            "lead",
            "lag",
            "first_value",
            "last_value",
            "ntile",
        }
        for func in window_functions:
            if expr_lower.startswith(f"{func}("):
                return "window"

        # If contains operators, it's a computation
        if any(op in expression for op in ["+", "-", "*", "/", "%", "||"]):
            return "computation"

        # Default to unknown for complex expressions
        return "unknown"

    def normalize_column_name(self, column_name: str) -> str:
        """Normalize a column name for comparison.

        Args:
            column_name: Column name to normalize.

        Returns:
            Normalized column name (lowercase, stripped).
        """
        return column_name.strip().lower()

    def columns_match(self, col1: str, col2: str) -> bool:
        """Check if two column names refer to the same column.

        Args:
            col1: First column name.
            col2: Second column name.

        Returns:
            True if they match (case-insensitive).
        """
        return self.normalize_column_name(col1) == self.normalize_column_name(col2)
