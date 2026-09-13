# src/northstar_formation/functions/registry.py
"""Dynamic function registry and management."""

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..core.models import BuildContext, DynamicFunction
from ..utils.errors import FunctionError
from ..utils.logging import get_logger


logger = get_logger(__name__)


class FunctionRegistry:
    """Registry for dynamic functions."""

    def __init__(self):
        """Initialize function registry."""
        self.core_functions: Dict[str, DynamicFunction] = {}
        self.customer_functions: Dict[str, Dict[str, DynamicFunction]] = {}
        self.active_functions: Dict[str, DynamicFunction] = {}

    def load_functions(self, config_dir: Path, context: BuildContext) -> None:
        """Load functions from configuration files."""
        logger.info("📚 Loading dynamic functions...")

        # Load core functions
        core_path = config_dir / "dynamic_functions.yaml"
        if core_path.exists():
            self._load_core_functions(core_path)

        # Load customer-specific functions
        customer_path = config_dir / f"dynamic_functions.{context.customer.lower()}.yaml"
        if customer_path.exists():
            self._load_customer_functions(customer_path, context.customer)

        # Build active function set for context
        self._build_active_functions(context)

        logger.info("Loaded %d functions for context", len(self.active_functions))

    def _load_core_functions(self, path: Path) -> None:
        """Load core functions from YAML."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if data and "dynamic_functions" in data:
                core_funcs = data["dynamic_functions"].get("core", [])
                for func_data in core_funcs:
                    func = DynamicFunction(**func_data)
                    self.core_functions[func.name] = func
                    logger.debug(f"  Loaded core function: {func.name}")

        except Exception as e:
            logger.error(f"Failed to load core functions: {e}")

    def _load_customer_functions(self, path: Path, customer: str) -> None:
        """Load customer-specific functions from YAML."""
        try:
            with open(path) as f:
                data = yaml.safe_load(f)

            if data and "dynamic_functions" in data:
                custom = data["dynamic_functions"].get("custom", {})
                if custom.get("customer") == customer:
                    functions = custom.get("functions", [])
                    customer_funcs = {}

                    for func_data in functions:
                        func = DynamicFunction(**func_data)
                        customer_funcs[func.name] = func
                        logger.debug(f"  Loaded {customer} function: {func.name}")

                    self.customer_functions[customer] = customer_funcs

        except Exception as e:
            logger.error(f"Failed to load {customer} functions: {e}")

    def _build_active_functions(self, context: BuildContext) -> None:
        """Build active function set for current context."""
        # Start with core functions
        self.active_functions = self.core_functions.copy()

        # Override with customer-specific functions
        if context.customer in self.customer_functions:
            self.active_functions.update(self.customer_functions[context.customer])

    def get_function(self, name: str) -> Optional[DynamicFunction]:
        """Get a function by name."""
        # Ensure name starts with @
        if not name.startswith("@"):
            name = f"@{name}"

        return self.active_functions.get(name)

    def has_function(self, name: str) -> bool:
        """Check if a function exists."""
        if not name.startswith("@"):
            name = f"@{name}"
        return name in self.active_functions

    def list_functions(self) -> List[str]:
        """List all available function names."""
        return sorted(self.active_functions.keys())


class FunctionResolver:
    """Resolve dynamic function calls in expressions."""

    # Pattern to match function calls: @function_name(params)
    FUNCTION_PATTERN = re.compile(r"@(\w+)\((.*?)\)")

    def __init__(self, registry: FunctionRegistry):
        """Initialize resolver with registry."""
        self.registry = registry

    def resolve_expression(self, expression: str, context: Optional[Dict[str, Any]] = None) -> str:
        """Resolve all function calls in an expression."""
        if not expression or "@" not in expression:
            return expression

        resolved = expression

        # Find all function calls
        matches = list(self.FUNCTION_PATTERN.finditer(expression))

        # Process matches in reverse order to maintain positions
        for match in reversed(matches):
            func_name = f"@{match.group(1)}"
            params_str = match.group(2).strip()

            # Resolve the function call
            replacement = self._resolve_function_call(func_name, params_str, context)

            # Replace in expression
            start, end = match.span()
            resolved = resolved[:start] + replacement + resolved[end:]

        return resolved

    def _resolve_function_call(
        self, func_name: str, params_str: str, context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Resolve a single function call."""
        function = self.registry.get_function(func_name)

        if not function:
            raise FunctionError(f"Unknown function: {func_name}")

        # Parse parameters
        params = self._parse_parameters(params_str) if params_str else []

        # Validate parameter count
        expected_count = len(function.parameters)
        actual_count = len(params)

        if expected_count != actual_count:
            raise FunctionError(
                f"Function {func_name} expects {expected_count} parameters, got {actual_count}"
            )

        # Build replacement SQL
        sql = function.sql_replacement

        # Replace parameter placeholders
        for i, param_name in enumerate(function.parameters):
            placeholder = f"{{{param_name}}}"
            if placeholder in sql:
                sql = sql.replace(placeholder, params[i])

        return sql

    def _parse_parameters(self, params_str: str) -> List[str]:
        """Parse function parameters."""
        if not params_str:
            return []

        # Handle nested function calls and quoted strings
        params = []
        current_param = []
        paren_depth = 0
        in_quotes = False
        quote_char = None

        for char in params_str:
            if char in ('"', "'") and not in_quotes:
                in_quotes = True
                quote_char = char
                current_param.append(char)
            elif char == quote_char and in_quotes:
                in_quotes = False
                quote_char = None
                current_param.append(char)
            elif char == "(" and not in_quotes:
                paren_depth += 1
                current_param.append(char)
            elif char == ")" and not in_quotes:
                paren_depth -= 1
                current_param.append(char)
            elif char == "," and paren_depth == 0 and not in_quotes:
                # Parameter boundary
                params.append("".join(current_param).strip())
                current_param = []
            else:
                current_param.append(char)

        # Add last parameter
        if current_param:
            params.append("".join(current_param).strip())

        return params

    def extract_functions(self, expression: str) -> List[Tuple[str, List[str]]]:
        """Extract all function calls from an expression."""
        if not expression or "@" not in expression:
            return []

        functions = []

        for match in self.FUNCTION_PATTERN.finditer(expression):
            func_name = f"@{match.group(1)}"
            params_str = match.group(2).strip()
            params = self._parse_parameters(params_str) if params_str else []
            functions.append((func_name, params))

        return functions

    def validate_expression(self, expression: str) -> List[str]:
        """Validate all function calls in an expression."""
        errors = []

        if not expression or "@" not in expression:
            return errors

        for match in self.FUNCTION_PATTERN.finditer(expression):
            func_name = f"@{match.group(1)}"
            params_str = match.group(2).strip()

            # Check if function exists
            if not self.registry.has_function(func_name):
                errors.append(f"Unknown function: {func_name}")
                continue

            # Check parameter count
            function = self.registry.get_function(func_name)
            params = self._parse_parameters(params_str) if params_str else []

            expected = len(function.parameters)
            actual = len(params)

            if expected != actual:
                errors.append(f"Function {func_name} expects {expected} parameters, got {actual}")

        return errors


class FunctionExpander:
    """Expand function calls in model definitions."""

    def __init__(self, resolver: FunctionResolver):
        """Initialize expander with resolver."""
        self.resolver = resolver

    def expand_model(self, model: Any, context: Optional[Dict[str, Any]] = None) -> Any:
        """Expand all function calls in a model."""
        # This will be called during SQL generation
        # It processes all expressions in columns, filters, etc.

        # Expand column expressions
        if hasattr(model, "columns"):
            for column in model.columns:
                if column.expression:
                    column.expression = self.resolver.resolve_expression(column.expression, context)

        # Expand filter conditions
        if hasattr(model, "where_clause") and model.where_clause:
            model.where_clause = self.resolver.resolve_expression(model.where_clause, context)

        # Expand having clauses
        if hasattr(model, "having_clause") and model.having_clause:
            expanded_having = []
            for clause in model.having_clause:
                expanded_having.append(self.resolver.resolve_expression(clause, context))
            model.having_clause = expanded_having

        return model
