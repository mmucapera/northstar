# src/northstar_formation/validators/pipeline.py
"""Validation pipeline for models."""

from abc import ABC, abstractmethod
from typing import Dict, List

import networkx as nx

from ..core.models import ColumnAction, Model, ValidationResult
from ..utils.logging import get_logger


logger = get_logger(__name__)


class BaseValidator(ABC):
    """Base class for validators."""

    @abstractmethod
    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Validate models and return results."""
        pass


class SchemaValidator(BaseValidator):
    """Validate model schemas."""

    # Layer-specific required fields removed - all models just need 'name'
    REQUIRED_FIELDS = ["name"]

    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Validate model schemas."""
        result = ValidationResult(is_valid=True)

        for name, model in models.items():
            # Check required fields (layer-agnostic)
            for field in self.REQUIRED_FIELDS:
                if not hasattr(model, field) or getattr(model, field) is None:
                    # Skip source requirement if model inherits or extends
                    if field == "source" and (model.extends or model.inherits_from):
                        continue

                    result.add_error(
                        model=name,
                        field=field,
                        message=f"Required field '{field}' is missing",
                        suggestion=f"Add '{field}' to your model configuration",
                    )

            # Validate source only if present and not inherited
            if (
                model.source
                and not model.source.base_table
                and not (model.extends or model.inherits_from)
            ):
                result.add_error(
                    model=name,
                    field="source.base_table",
                    message="Source must specify a base_table",
                    suggestion="Add 'base_table' to your source configuration or use extends/inherits_from",
                )

            # Validate columns
            if model.transformations.columns:
                column_names = set()
                for col in model.transformations.columns:
                    # Check for duplicate column names
                    final_name = col.new_name if col.action == ColumnAction.RENAME else col.name
                    if final_name in column_names and col.action != ColumnAction.REMOVE:
                        result.add_error(
                            model=name,
                            field=f"columns.{col.name}",
                            message=f"Duplicate column name: {final_name}",
                            suggestion="Use unique column names or remove duplicates",
                        )
                    column_names.add(final_name)

                    # Validate column actions
                    if col.action == ColumnAction.RENAME and not col.new_name:
                        result.add_error(
                            model=name,
                            field=f"columns.{col.name}",
                            message="Rename action requires 'new_name'",
                            suggestion=f"Add 'new_name' for column {col.name}",
                        )

                    # Validate expressions
                    if not col.expression and col.action in [
                        ColumnAction.ADD,
                        ColumnAction.TRANSFORM,
                    ]:
                        result.add_warning(
                            model=name,
                            field=f"columns.{col.name}",
                            message=f"Column {col.name} has no expression defined",
                            suggestion="Add an expression or use the column name as default",
                        )

        return result


class DependencyValidator(BaseValidator):
    """Validate model dependencies."""

    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Validate dependencies between models."""
        result = ValidationResult(is_valid=True)
        graph = nx.DiGraph()

        # Build dependency graph
        for name, model in models.items():
            graph.add_node(name)

            # Check inheritance dependencies
            if model.extends:
                parent = self._extract_model_name(model.extends)
                if parent not in models:
                    result.add_error(
                        model=name,
                        field="extends",
                        message=f"Parent model '{parent}' not found",
                        suggestion=f"Ensure '{parent}' exists or remove the extends reference",
                    )
                else:
                    graph.add_edge(parent, name)

            if model.inherits_from:
                parent = self._extract_model_name(model.inherits_from)
                if parent not in models:
                    result.add_error(
                        model=name,
                        field="inherits_from",
                        message=f"Parent model '{parent}' not found",
                        suggestion=f"Ensure '{parent}' exists or remove the inherits_from reference",
                    )
                else:
                    graph.add_edge(parent, name)

            # Check CTE dependencies
            for cte in model.ctes:
                if cte.name not in models:
                    result.add_error(
                        model=name,
                        field="ctes",
                        message=f"CTE '{cte.name}' not found",
                        suggestion=f"Create CTE model '{cte.name}' or remove the reference",
                    )
                else:
                    graph.add_edge(cte.name, name)

        # Check for circular dependencies
        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            for cycle in cycles:
                cycle_str = " → ".join(cycle + [cycle[0]])
                result.add_error(
                    model=cycle[0],
                    message=f"Circular dependency detected: {cycle_str}",
                    suggestion="Remove one of the dependencies to break the cycle",
                )

        # Layer hierarchy validation removed - any layer dependency is valid

        return result

    def _extract_model_name(self, reference: str) -> str:
        """Extract model name from reference.

        If reference is layer-qualified (e.g., 'bronze.fct_customer'), keep it as-is.
        Otherwise, return just the last part for backward compatibility.
        """
        parts = reference.split(".")
        for idx, part in enumerate(parts):
            if part in ("bronze", "silver", "gold", "interface"):
                return ".".join(parts[idx:])
        return parts[-1]


class FilterValidator(BaseValidator):
    """Validate filter configurations."""

    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Validate filter IDs and conditions."""
        result = ValidationResult(is_valid=True)

        for name, model in models.items():
            if not model.filters.where_conditions:
                continue

            # Check for duplicate filter IDs within a model
            filter_ids = set()
            for filter_cond in model.filters.where_conditions:
                if filter_cond.id in filter_ids:
                    result.add_error(
                        model=name,
                        field="filters",
                        message=f"Duplicate filter ID: {filter_cond.id}",
                        suggestion="Use unique IDs for each filter condition",
                    )
                filter_ids.add(filter_cond.id)

                # Validate filter condition syntax (basic check)
                if not filter_cond.condition or filter_cond.condition.strip() == "":
                    result.add_error(
                        model=name,
                        field=f"filters.{filter_cond.id}",
                        message=f"Filter '{filter_cond.id}' has empty condition",
                        suggestion="Add a valid SQL condition",
                    )

        return result


class FunctionValidator(BaseValidator):
    """Validate dynamic function usage."""

    def __init__(self, function_registry=None):
        """Initialize with optional function registry."""
        self.function_registry = function_registry

    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Validate function calls in expressions."""
        result = ValidationResult(is_valid=True)

        if not self.function_registry:
            # Can't validate without registry
            return result

        for name, model in models.items():
            # Check column expressions
            for col in model.transformations.columns:
                if col.expression and "@" in col.expression:
                    errors = self._validate_expression(col.expression)
                    for error in errors:
                        result.add_error(
                            model=name,
                            field=f"columns.{col.name}",
                            message=error,
                            suggestion="Check function name and parameters",
                        )

            # Check filter conditions
            for filter_cond in model.filters.where_conditions:
                if "@" in filter_cond.condition:
                    errors = self._validate_expression(filter_cond.condition)
                    for error in errors:
                        result.add_error(
                            model=name,
                            field=f"filters.{filter_cond.id}",
                            message=error,
                            suggestion="Check function name and parameters in filter",
                        )

        return result

    def _validate_expression(self, expression: str) -> List[str]:
        """Validate function calls in an expression."""
        # This would use the FunctionResolver's validate_expression method
        # Simplified for now
        errors = []
        import re

        pattern = re.compile(r"@(\w+)\((.*?)\)")
        for match in pattern.finditer(expression):
            func_name = f"@{match.group(1)}"
            if self.function_registry and not self.function_registry.has_function(func_name):
                errors.append(f"Unknown function: {func_name}")

        return errors


class ValidationPipeline:
    """Main validation pipeline."""

    def __init__(self, function_registry=None):
        """Initialize validation pipeline."""
        self.validators = [
            SchemaValidator(),
            DependencyValidator(),
            FilterValidator(),
            FunctionValidator(function_registry),
        ]

    def validate(self, models: Dict[str, Model]) -> ValidationResult:
        """Run all validators and collect results."""
        logger.info("Validating %d models...", len(models))

        combined_result = ValidationResult(is_valid=True)

        for validator in self.validators:
            result = validator.validate(models)

            # Combine results
            combined_result.errors.extend(result.errors)
            combined_result.warnings.extend(result.warnings)

            if result.errors:
                combined_result.is_valid = False

        # Log summary
        if combined_result.is_valid:
            if combined_result.warnings:
                logger.info("Validation passed with %d warning(s)", len(combined_result.warnings))
            else:
                logger.info("Validation passed")
        else:
            logger.error("Validation failed with %d error(s)", len(combined_result.errors))

        return combined_result
