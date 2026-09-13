# src/northstar_formation/utils/helpers.py
"""Helper utilities for Northstar Formation.

This module provides common utility functions used throughout the Northstar Formation
system. All functions are designed to be pure and customer-agnostic.
"""

import json
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Union

import yaml


def read_yaml(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Read YAML file and return parsed content."""
    with open(file_path) as f:
        return yaml.safe_load(f) or {}


def write_yaml(data: Dict[str, Any], file_path: Union[str, Path]) -> None:
    """Write data to YAML file."""
    with open(file_path, "w") as f:
        yaml.dump(data, f, default_flow_style=False, sort_keys=False)


def read_json(file_path: Union[str, Path]) -> Dict[str, Any]:
    """Read JSON file and return parsed content."""
    with open(file_path) as f:
        return json.load(f)


def write_json(data: Dict[str, Any], file_path: Union[str, Path], indent: int = 2) -> None:
    """Write data to JSON file."""
    with open(file_path, "w") as f:
        json.dump(data, f, indent=indent)


def ensure_directory(path: Union[str, Path]) -> Path:
    """Ensure directory exists, create if not."""
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    return path


def find_files(directory: Union[str, Path], pattern: str) -> List[Path]:
    """Find all files matching pattern in directory."""
    directory = Path(directory)
    return list(directory.rglob(pattern))


def merge_dicts(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries."""
    result = base.copy()

    for key, value in overlay.items():
        if key in result:
            if isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = merge_dicts(result[key], value)
            elif isinstance(result[key], list) and isinstance(value, list):
                result[key] = result[key] + value
            else:
                result[key] = value
        else:
            result[key] = value

    return result


def format_sql(sql: str, indent_size: int = 2) -> str:
    """Format SQL string for better readability."""
    # Simple SQL formatting - could be enhanced with sqlparse library
    keywords = [
        "SELECT",
        "FROM",
        "WHERE",
        "GROUP BY",
        "HAVING",
        "ORDER BY",
        "JOIN",
        "LEFT JOIN",
        "RIGHT JOIN",
        "INNER JOIN",
        "OUTER JOIN",
        "ON",
        "AND",
        "OR",
        "WITH",
        "AS",
        "CREATE",
        "VIEW",
        "TABLE",
    ]

    formatted = sql
    for keyword in keywords:
        formatted = formatted.replace(f" {keyword} ", f"\n{keyword} ")
        formatted = formatted.replace(f"\n{keyword}\n", f"\n{keyword} ")

    # Clean up multiple newlines
    while "\n\n" in formatted:
        formatted = formatted.replace("\n\n", "\n")

    return formatted.strip()


def compare_versions(version1: str, version2: str) -> int:
    """Compare semantic versions.

    Returns:
        -1 if version1 < version2
         0 if version1 == version2
         1 if version1 > version2
    """

    def parse_version(v: str) -> tuple:
        return tuple(int(x) for x in v.split("."))

    v1 = parse_version(version1)
    v2 = parse_version(version2)

    if v1 < v2:
        return -1
    elif v1 > v2:
        return 1
    else:
        return 0


def sanitize_identifier(name: str) -> str:
    """Sanitize identifier for SQL."""
    # Remove special characters, replace spaces with underscores
    import re

    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", name)

    # Ensure it doesn't start with a number
    if sanitized and sanitized[0].isdigit():
        sanitized = f"_{sanitized}"

    return sanitized


def get_file_hash(file_path: Union[str, Path]) -> str:
    """Get hash of file contents."""
    import hashlib

    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def flatten_dict(d: Dict[str, Any], parent_key: str = "", sep: str = ".") -> Dict[str, Any]:
    """Flatten nested dictionary."""
    items: list[tuple[str, Any]] = []

    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k

        if isinstance(v, dict):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))

    return dict(items)


def generate_safe_view_name(base_name: str) -> str:
    """Generate a unique, collision-safe temporary view name.

    This function creates a unique view name suitable for use as a temporary
    view in Spark SQL. The name includes a timestamp and UUID to prevent
    collisions when running notebooks in parallel.

    Args:
        base_name: Base name to include in the view name. Will be sanitized
            to remove special characters.

    Returns:
        A unique view name in format: merge_src_{sanitized_base}_{timestamp}_{uuid}

    Example:
        >>> generate_safe_view_name("gold.my_table")
        'merge_src_gold_my_table_1704067200000_a1b2c3d4'
    """
    ts = int(time.time() * 1000)
    uid = uuid.uuid4().hex[:8]

    # Sanitize the base name - remove special characters
    sanitized = (base_name or "").lower()
    for char in [".", "-", "`", " ", '"', "'"]:
        sanitized = sanitized.replace(char, "_")

    # Remove consecutive underscores and trim
    while "__" in sanitized:
        sanitized = sanitized.replace("__", "_")
    sanitized = sanitized.strip("_")

    if not sanitized:
        sanitized = "temp"

    return f"merge_src_{sanitized}_{ts}_{uid}"


def generate_safe_view_name_code() -> str:
    """Generate Python code for creating safe view names in notebooks.

    This returns the Python code that should be embedded in generated notebooks
    to create unique temporary view names at runtime.

    Returns:
        Python code string for the _safe_view function.
    """
    return '''
def _safe_view(base: str) -> str:
    """Generate a unique, collision-safe temporary view name.

    Args:
        base: Base name for the view.

    Returns:
        Unique view name with timestamp and UUID.
    """
    import time
    import uuid
    ts = int(time.time() * 1000)
    uid = uuid.uuid4().hex[:8]
    base = (base or "").lower()
    for char in [".", "-", "`", " ", '"', "'"]:
        base = base.replace(char, "_")
    while "__" in base:
        base = base.replace("__", "_")
    base = base.strip("_") or "temp"
    return f"merge_src_{base}_{ts}_{uid}"
'''


def escape_sql_string(sql: str) -> str:
    """Escape a SQL string for embedding in Python code.

    Properly escapes triple quotes and other special characters that would
    break when embedded in Python string literals.

    Args:
        sql: The SQL string to escape.

    Returns:
        Escaped SQL string safe for embedding in Python triple-quoted strings.
    """
    # Escape triple quotes that would break Python string literals
    return sql.replace('"""', '\\"\\"\\"')


def validate_identifier(name: str) -> bool:
    """Validate that a string is a valid SQL identifier.

    Args:
        name: The identifier to validate.

    Returns:
        True if the identifier is valid.

    Note:
        This is a basic validation. For strict SQL compliance, consider
        using database-specific validation.
    """
    import re

    if not name:
        return False
    # Must start with letter or underscore, contain only alphanumeric and underscore
    pattern = r"^[a-zA-Z_][a-zA-Z0-9_]*$"
    return bool(re.match(pattern, name))
