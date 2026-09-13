"""Graph builder for lineage analysis.

This module builds the lineage graph from resolved models,
handling both table-level and column-level dependencies.
"""

from typing import Dict, List, Optional, Set

from ..core.models import Model, ResolvedModel
from ..utils.logging import get_logger
from .column_tracker import ColumnExpressionParser
from .models import (
    ColumnLineageEdge,
    ColumnLineageNode,
    LineageEdge,
    LineageEdgeType,
    LineageGraph,
    TableLineageNode,
)


logger = get_logger(__name__)


class LineageGraphBuilder:
    """Build lineage graph from models.

    This class constructs a complete lineage graph by analyzing
    model definitions and their relationships.
    """

    def __init__(self) -> None:
        """Initialize the graph builder."""
        self.expression_parser = ColumnExpressionParser()
        self._graph: Optional[LineageGraph] = None

    def build(
        self,
        models: Dict[str, Model],
        resolved_models: Optional[Dict[str, ResolvedModel]] = None,
    ) -> LineageGraph:
        """Build a lineage graph from model definitions.

        Args:
            models: Dictionary of model name to Model.
            resolved_models: Optional resolved models for additional column info.

        Returns:
            Complete LineageGraph.
        """
        logger.info(f"Building lineage graph from {len(models)} models")

        self._graph = LineageGraph()
        external_tables: Set[str] = set()

        # Build a mapping from qualified names to model names
        # e.g., "silver.fct_customer" -> "fct_customer" (silver layer model)
        # Since model names no longer have brz_/slv_ prefixes, we map by layer
        self._qualified_to_model: Dict[str, str] = {}
        self._model_by_layer: Dict[str, Dict[str, str]] = {}  # layer -> {base_name -> model_name}

        for model_name, model in models.items():
            layer_val = model.layer
            if layer_val:
                layer = layer_val.value if hasattr(layer_val, "value") else str(layer_val)
            else:
                layer = "unknown"
            # For gold models with d_/f_ prefix, extract base name
            base_name = model_name
            for prefix in ["d_", "f_"]:
                if model_name.startswith(prefix):
                    base_name = model_name[len(prefix) :]
                    break

            # Create qualified name mapping
            qualified_name = f"{layer}.{base_name}"
            self._qualified_to_model[qualified_name] = model_name

            # Also map the full model name directly
            full_qualified = f"{layer}.{model_name}"
            self._qualified_to_model[full_qualified] = model_name

            # Track by layer for cross-layer resolution
            if layer not in self._model_by_layer:
                self._model_by_layer[layer] = {}
            self._model_by_layer[layer][base_name] = model_name
            self._model_by_layer[layer][model_name] = model_name

        # First pass: Create table nodes
        for model_name, model in models.items():
            self._add_table_node(model_name, model, resolved_models)

            # Track external tables (source tables not in models)
            if model.source and model.source.base_table:
                source_table = model.source.base_table
                if source_table not in models and source_table != "__SCHEMA_ONLY__":
                    if "." in source_table:
                        # Check if this qualified name maps to an existing model
                        if source_table not in self._qualified_to_model:
                            # Truly external table
                            external_tables.add(source_table)

        # Add external table nodes
        for ext_table in external_tables:
            self._add_external_table_node(ext_table)

        # Second pass: Create edges
        for model_name, model in models.items():
            self._add_edges_for_model(model_name, model, models)

        # Third pass: Build column-level lineage
        for model_name, model in models.items():
            resolved = resolved_models.get(model_name) if resolved_models else None
            self._build_column_lineage(model_name, model, models, resolved)

        logger.info(
            f"Built lineage graph with {len(self._graph.tables)} tables "
            f"and {len(self._graph.edges)} edges"
        )

        return self._graph

    def _add_table_node(
        self,
        model_name: str,
        model: Model,
        resolved_models: Optional[Dict[str, ResolvedModel]] = None,
    ) -> None:
        """Add a table node to the graph.

        Args:
            model_name: Name of the model.
            model: Model definition.
            resolved_models: Optional resolved models for column info.
        """
        layer = model.layer if model.layer else "unknown"
        qualified_name = f"{layer}.{model_name}"

        # Build column list
        columns: List[ColumnLineageNode] = []

        # Prefer resolved model columns if available
        resolved = resolved_models.get(model_name) if resolved_models else None
        if resolved and resolved.columns:
            for col in resolved.columns:
                columns.append(
                    ColumnLineageNode(
                        name=col.name,
                        table=model_name,
                        layer=layer,
                        data_type=col.data_type,
                        expression=col.expression,
                        is_computed=bool(col.expression and col.expression != col.name),
                        is_inherited=False,
                    )
                )
        elif model.transformations and model.transformations.columns:
            for col in model.transformations.columns:
                columns.append(
                    ColumnLineageNode(
                        name=col.name,
                        table=model_name,
                        layer=layer,
                        data_type=col.data_type,
                        expression=col.expression,
                        is_computed=bool(col.expression and col.expression != col.name),
                        is_inherited=False,
                    )
                )

        # Get source tables
        source_tables: List[str] = []
        if model.source and model.source.base_table:
            if model.source.base_table != "__SCHEMA_ONLY__":
                source_tables.append(model.source.base_table)

        # Add inheritance sources
        if model.extends:
            source_tables.append(self._extract_model_name(model.extends))
        if model.inherits_from:
            source_tables.append(self._extract_model_name(model.inherits_from))

        # Add CTE sources
        for cte in model.ctes:
            source_tables.append(cte.name)

        table_node = TableLineageNode(
            name=model_name,
            layer=layer,
            qualified_name=qualified_name,
            source_tables=list(set(source_tables)),
            columns=columns,
            is_external=False,
            description=model.description,
            kind=model.kind.value if model.kind else "TABLE",
        )

        self._graph.add_table(table_node)

    def _add_external_table_node(self, table_name: str) -> None:
        """Add an external (non-model) table node.

        Args:
            table_name: Fully qualified table name.
        """
        # Extract simple name from qualified name
        parts = table_name.split(".")
        simple_name = parts[-1] if parts else table_name

        table_node = TableLineageNode(
            name=table_name,
            layer="external",
            qualified_name=table_name,
            source_tables=[],
            columns=[],
            is_external=True,
            description=f"External table: {table_name}",
            kind="EXTERNAL",
        )

        self._graph.add_table(table_node)

    def _resolve_qualified_table(self, table_ref: str) -> str:
        """Resolve a qualified table reference to its model name if possible.

        Args:
            table_ref: Table reference (may be qualified like 'silver.fct_customer').

        Returns:
            Model name if found, otherwise the original reference.
        """
        # First check direct mapping
        if table_ref in self._qualified_to_model:
            return self._qualified_to_model[table_ref]
        return table_ref

    def _add_edges_for_model(
        self,
        model_name: str,
        model: Model,
        all_models: Dict[str, Model],
    ) -> None:
        """Add edges for a model's dependencies.

        Args:
            model_name: Name of the model.
            model: Model definition.
            all_models: All available models.
        """
        # Source table edge
        if model.source and model.source.base_table:
            source_table = model.source.base_table
            if source_table != "__SCHEMA_ONLY__":
                # Resolve qualified name to model name if possible
                resolved_source = self._resolve_qualified_table(source_table)
                edge_type = LineageEdgeType.DIRECT
                self._graph.add_edge(
                    LineageEdge(
                        source=resolved_source,
                        target=model_name,
                        edge_type=edge_type,
                    )
                )

        # Inheritance edge (extends)
        if model.extends:
            parent_name = self._extract_model_name(model.extends)
            self._graph.add_edge(
                LineageEdge(
                    source=parent_name,
                    target=model_name,
                    edge_type=LineageEdgeType.INHERITANCE,
                )
            )

        # Inheritance edge (inherits_from)
        if model.inherits_from:
            parent_name = self._extract_model_name(model.inherits_from)
            self._graph.add_edge(
                LineageEdge(
                    source=parent_name,
                    target=model_name,
                    edge_type=LineageEdgeType.INHERITANCE,
                )
            )

        # CTE edges
        for cte in model.ctes:
            self._graph.add_edge(
                LineageEdge(
                    source=cte.name,
                    target=model_name,
                    edge_type=LineageEdgeType.CTE,
                )
            )

        # Join edges (from relationships)
        if model.relationships and model.relationships.foreign_keys:
            for fk in model.relationships.foreign_keys:
                # Resolve qualified name to model name if possible
                resolved_ref_table = self._resolve_qualified_table(fk.references_table)
                self._graph.add_edge(
                    LineageEdge(
                        source=resolved_ref_table,
                        target=model_name,
                        edge_type=LineageEdgeType.JOIN,
                        columns=[fk.local_column, fk.references_column],
                        join_type=fk.join_type.value if fk.join_type else "LEFT",
                    )
                )

    def _build_column_lineage(
        self,
        model_name: str,
        model: Model,
        all_models: Dict[str, Model],
        resolved: Optional[ResolvedModel] = None,
    ) -> None:
        """Build column-level lineage for a model.

        Args:
            model_name: Name of the model.
            model: Model definition.
            all_models: All available models.
            resolved: Optional resolved model.
        """
        # Get source table name
        source_table = None
        if model.source and model.source.base_table:
            if model.source.base_table != "__SCHEMA_ONLY__":
                source_table = model.source.base_table

        # Get parent model for inheritance
        parent_name = None
        if model.extends:
            parent_name = self._extract_model_name(model.extends)
        elif model.inherits_from:
            parent_name = self._extract_model_name(model.inherits_from)

        # Determine the primary source for column lineage
        primary_source = source_table or parent_name

        if not primary_source:
            # No source to trace lineage from
            return

        # Get columns to process
        columns = resolved.columns if resolved else model.transformations.columns

        if not columns:
            return

        for col in columns:
            self._trace_column_lineage(
                target_table=model_name,
                target_column=col.name,
                expression=col.expression,
                primary_source=primary_source,
                all_models=all_models,
                inherit_columns=model.transformations.inherit_columns
                if model.transformations
                else False,
            )

    def _trace_column_lineage(
        self,
        target_table: str,
        target_column: str,
        expression: Optional[str],
        primary_source: str,
        all_models: Dict[str, Model],
        inherit_columns: bool = False,
    ) -> None:
        """Trace lineage for a single column.

        Args:
            target_table: Target table name.
            target_column: Target column name.
            expression: SQL expression for the column.
            primary_source: Primary source table.
            all_models: All available models.
            inherit_columns: Whether columns are inherited.
        """
        # If expression is None or matches column name, it's a direct reference
        if not expression or expression == target_column:
            # Direct reference from primary source
            self._graph.add_column_edge(
                ColumnLineageEdge(
                    source_table=primary_source,
                    source_column=target_column,
                    target_table=target_table,
                    target_column=target_column,
                    transformation=None,
                    is_direct=True,
                )
            )
            return

        # Parse expression for column references
        refs = self.expression_parser.extract_source_columns_with_table(expression)

        if not refs:
            # No column references found (e.g., current_timestamp, literal)
            # Still record the transformation
            self._graph.add_column_edge(
                ColumnLineageEdge(
                    source_table=primary_source,
                    source_column="<computed>",
                    target_table=target_table,
                    target_column=target_column,
                    transformation=expression,
                    is_direct=False,
                )
            )
            return

        # Create edges for each source column
        for table_alias, source_col in refs:
            # Resolve table alias to actual table name
            source_table = primary_source
            if table_alias and table_alias != "T":
                # Could be a CTE alias or joined table
                source_table = self._resolve_table_alias(table_alias, primary_source, all_models)

            # Determine if it's a direct reference
            is_direct = self.expression_parser.is_simple_reference(expression, target_column)

            self._graph.add_column_edge(
                ColumnLineageEdge(
                    source_table=source_table,
                    source_column=source_col,
                    target_table=target_table,
                    target_column=target_column,
                    transformation=expression if not is_direct else None,
                    is_direct=is_direct,
                )
            )

    def _resolve_table_alias(
        self,
        alias: str,
        default_table: str,
        all_models: Dict[str, Model],
    ) -> str:
        """Resolve a table alias to actual table name.

        Args:
            alias: Table alias to resolve.
            default_table: Default table if alias can't be resolved.
            all_models: All available models.

        Returns:
            Resolved table name.
        """
        # Common aliases that refer to the primary table
        if alias.upper() in {"T", "SRC", "SOURCE"}:
            return default_table

        # Check if alias matches a model name
        if alias in all_models:
            return alias

        # Check if alias matches a table in the graph
        if self._graph and alias in self._graph.tables:
            return alias

        # Default to the provided default
        return default_table

    def _extract_model_name(self, reference: str) -> str:
        """Extract model name from a reference.

        Args:
            reference: Model reference (may include schema prefix).

        Returns:
            Simple model name.
        """
        parts = reference.split(".")
        return parts[-1]

    def get_stats(self) -> Dict[str, int]:
        """Get statistics about the lineage graph.

        Returns:
            Dictionary of statistics.
        """
        if not self._graph:
            return {}

        return {
            "total_tables": len(self._graph.tables),
            "external_tables": sum(1 for t in self._graph.tables.values() if t.is_external),
            "bronze_tables": len(self._graph.get_tables_by_layer("bronze")),
            "silver_tables": len(self._graph.get_tables_by_layer("silver")),
            "gold_tables": len(self._graph.get_tables_by_layer("gold")),
            "total_edges": len(self._graph.edges),
            "column_edges": len(self._graph.column_edges),
        }
