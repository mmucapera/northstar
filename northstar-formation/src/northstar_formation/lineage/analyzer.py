"""Lineage analyzer for Northstar Formation.

This module provides the main interface for analyzing data lineage
across model definitions, including both table and column-level lineage.
"""

from typing import Dict, List, Optional

import networkx as nx

from ..core.models import BuildContext, Model, ResolvedModel
from ..core.parser import YAMLParser
from ..core.resolver import ModelResolver
from ..utils.errors import CircularDependencyError
from ..utils.logging import get_logger
from .graph_builder import LineageGraphBuilder
from .models import ColumnLineageNode, LineageGraph, TableLineageNode


logger = get_logger(__name__)


class LineageAnalyzer:
    """Analyze data lineage across models.

    This class provides the main interface for lineage analysis,
    coordinating graph building and traversal operations.
    """

    def __init__(self) -> None:
        """Initialize the lineage analyzer."""
        self._graph: Optional[LineageGraph] = None
        self._models: Dict[str, Model] = {}
        self._resolved_models: Dict[str, ResolvedModel] = {}
        self._nx_graph: Optional[nx.DiGraph] = None

    def analyze(
        self,
        models: Dict[str, Model],
        resolved_models: Optional[Dict[str, ResolvedModel]] = None,
    ) -> LineageGraph:
        """Analyze lineage from model definitions.

        Args:
            models: Dictionary of model name to Model.
            resolved_models: Optional resolved models for additional info.

        Returns:
            Complete LineageGraph.

        Raises:
            CircularDependencyError: If circular dependencies are detected.
        """
        logger.info(f"Analyzing lineage for {len(models)} models")

        self._models = models
        self._resolved_models = resolved_models or {}

        # Check for circular dependencies first
        self._check_circular_dependencies()

        # Build the lineage graph
        builder = LineageGraphBuilder()
        self._graph = builder.build(models, resolved_models)

        # Build networkx graph for advanced analysis
        self._build_nx_graph()

        return self._graph

    def analyze_from_directory(
        self,
        models_dir: str,
        context: Optional[BuildContext] = None,
    ) -> LineageGraph:
        """Analyze lineage from a directory of YAML files.

        Args:
            models_dir: Path to directory containing YAML models.
            context: Optional build context for model loading.

        Returns:
            Complete LineageGraph.
        """
        logger.info(f"Analyzing lineage from directory: {models_dir}")

        context = context or BuildContext()

        # Load models
        parser = YAMLParser(models_dir)
        models = parser.load_all_models(context)

        # Resolve models
        resolver = ModelResolver(parser)
        resolved_models = resolver.resolve_all(models, context)

        return self.analyze(models, resolved_models)

    def _check_circular_dependencies(self) -> None:
        """Check for circular dependencies in model definitions.

        Raises:
            CircularDependencyError: If circular dependencies are detected.
        """
        graph = nx.DiGraph()

        for name, model in self._models.items():
            graph.add_node(name)

            if model.extends:
                parent = self._extract_model_name(model.extends)
                if parent in self._models:
                    graph.add_edge(parent, name)

            if model.inherits_from:
                parent = self._extract_model_name(model.inherits_from)
                if parent in self._models:
                    graph.add_edge(parent, name)

            if model.source and model.source.base_table:
                source = model.source.base_table
                if source in self._models:
                    graph.add_edge(source, name)

            for cte in model.ctes:
                if cte.name in self._models:
                    graph.add_edge(cte.name, name)

        if not nx.is_directed_acyclic_graph(graph):
            cycles = list(nx.simple_cycles(graph))
            raise CircularDependencyError(f"Circular dependencies detected in lineage: {cycles}")

    def _build_nx_graph(self) -> None:
        """Build networkx graph for advanced analysis."""
        self._nx_graph = nx.DiGraph()

        if not self._graph:
            return

        # Add nodes
        for table_name, table in self._graph.tables.items():
            self._nx_graph.add_node(
                table_name,
                layer=table.layer,
                is_external=table.is_external,
                kind=table.kind,
            )

        # Add edges
        for edge in self._graph.edges:
            self._nx_graph.add_edge(
                edge.source,
                edge.target,
                edge_type=edge.edge_type.value,
            )

    def get_graph(self) -> Optional[LineageGraph]:
        """Get the current lineage graph.

        Returns:
            LineageGraph if analysis has been performed, None otherwise.
        """
        return self._graph

    def get_upstream(self, table_name: str) -> List[str]:
        """Get all upstream tables (recursive).

        Args:
            table_name: Table to find upstream dependencies for.

        Returns:
            List of upstream table names.
        """
        if not self._graph:
            return []
        return self._graph.get_upstream(table_name)

    def get_downstream(self, table_name: str) -> List[str]:
        """Get all downstream tables (recursive).

        Args:
            table_name: Table to find downstream dependents for.

        Returns:
            List of downstream table names.
        """
        if not self._graph:
            return []
        return self._graph.get_downstream(table_name)

    def get_impact_analysis(self, table_name: str) -> Dict[str, List[str]]:
        """Perform impact analysis for a table.

        Determines what would be affected if this table changes.

        Args:
            table_name: Table to analyze impact for.

        Returns:
            Dictionary with 'direct' and 'indirect' downstream tables.
        """
        if not self._graph:
            return {"direct": [], "indirect": []}

        direct = self._graph.get_direct_downstream(table_name)
        all_downstream = self._graph.get_downstream(table_name)
        indirect = [t for t in all_downstream if t not in direct]

        return {
            "direct": direct,
            "indirect": indirect,
        }

    def get_column_lineage(self, table: str, column: str) -> List[ColumnLineageNode]:
        """Trace a column back to its sources.

        Args:
            table: Table name.
            column: Column name.

        Returns:
            List of source ColumnLineageNodes.
        """
        if not self._graph:
            return []
        return self._graph.get_column_lineage(table, column)

    def get_column_impact(self, table: str, column: str) -> List[ColumnLineageNode]:
        """Find all columns that depend on this column.

        Args:
            table: Table name.
            column: Column name.

        Returns:
            List of downstream ColumnLineageNodes.
        """
        if not self._graph:
            return []
        return self._graph.get_column_impact(table, column)

    def get_resolution_order(self) -> List[str]:
        """Get the topological order for model resolution.

        Returns:
            List of table names in resolution order.
        """
        if not self._nx_graph:
            return []
        return list(nx.topological_sort(self._nx_graph))

    def get_tables_by_layer(self, layer: str) -> List[TableLineageNode]:
        """Get all tables in a specific layer.

        Args:
            layer: Layer name (bronze, silver, gold).

        Returns:
            List of tables in that layer.
        """
        if not self._graph:
            return []
        return self._graph.get_tables_by_layer(layer)

    def filter_by_table(self, table_name: str) -> Optional[LineageGraph]:
        """Create a subgraph focused on a specific table.

        Args:
            table_name: Table to focus on.

        Returns:
            Filtered LineageGraph.
        """
        if not self._graph:
            return None
        return self._graph.filter_by_table(table_name)

    def filter_by_layer(self, layer: str) -> Optional[LineageGraph]:
        """Create a subgraph for a specific layer.

        Args:
            layer: Layer name to filter by.

        Returns:
            Filtered LineageGraph.
        """
        if not self._graph:
            return None
        return self._graph.filter_by_layer(layer)

    def get_path(self, source: str, target: str) -> List[str]:
        """Get the path between two tables.

        Args:
            source: Source table name.
            target: Target table name.

        Returns:
            List of table names forming the path, or empty if no path exists.
        """
        if not self._nx_graph:
            return []

        try:
            return list(nx.shortest_path(self._nx_graph, source, target))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_all_paths(self, source: str, target: str) -> List[List[str]]:
        """Get all paths between two tables.

        Args:
            source: Source table name.
            target: Target table name.

        Returns:
            List of paths (each path is a list of table names).
        """
        if not self._nx_graph:
            return []

        try:
            return list(nx.all_simple_paths(self._nx_graph, source, target))
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return []

    def get_layers_summary(self) -> Dict[str, int]:
        """Get a summary of tables by layer.

        Returns:
            Dictionary of layer name to count.
        """
        if not self._graph:
            return {}

        summary: Dict[str, int] = {}
        for table in self._graph.tables.values():
            layer = table.layer or "unknown"
            summary[layer] = summary.get(layer, 0) + 1

        return summary

    def get_statistics(self) -> Dict[str, any]:
        """Get comprehensive statistics about the lineage.

        Returns:
            Dictionary of statistics.
        """
        if not self._graph:
            return {}

        stats = {
            "total_tables": len(self._graph.tables),
            "total_edges": len(self._graph.edges),
            "column_edges": len(self._graph.column_edges),
            "layers": self.get_layers_summary(),
            "external_tables": sum(1 for t in self._graph.tables.values() if t.is_external),
        }

        # Calculate average depth
        if self._nx_graph and len(self._nx_graph.nodes) > 0:
            try:
                # Find root nodes (no incoming edges)
                roots = [n for n in self._nx_graph.nodes() if self._nx_graph.in_degree(n) == 0]
                if roots:
                    max_depth = 0
                    for root in roots:
                        lengths = nx.single_source_shortest_path_length(self._nx_graph, root)
                        max_depth = max(max_depth, max(lengths.values()))
                    stats["max_depth"] = max_depth
            except Exception:
                pass

        return stats

    def validate_lineage(self) -> List[str]:
        """Validate the lineage for potential issues.

        Returns:
            List of warning/error messages.
        """
        warnings: List[str] = []

        if not self._graph:
            warnings.append("No lineage graph available")
            return warnings

        # Check for orphaned tables (no upstream or downstream)
        for table_name, table in self._graph.tables.items():
            if table.is_external:
                continue

            upstream = self._graph.get_direct_upstream(table_name)
            downstream = self._graph.get_direct_downstream(table_name)

            if not upstream and not downstream:
                warnings.append(f"Table '{table_name}' is orphaned (no connections)")

        # Check for missing source tables
        for edge in self._graph.edges:
            if edge.source not in self._graph.tables:
                warnings.append(f"Source table '{edge.source}' referenced but not defined")

        # Check layer hierarchy
        layer_order = {"bronze": 0, "silver": 1, "gold": 2}
        for edge in self._graph.edges:
            source_table = self._graph.get_table(edge.source)
            target_table = self._graph.get_table(edge.target)

            if source_table and target_table:
                source_layer = source_table.layer or "unknown"
                target_layer = target_table.layer or "unknown"

                source_order = layer_order.get(source_layer.lower(), -1)
                target_order = layer_order.get(target_layer.lower(), -1)

                if source_order >= 0 and target_order >= 0:
                    if source_order > target_order:
                        warnings.append(
                            f"Layer hierarchy violation: {source_table.name} "
                            f"({source_layer}) -> {target_table.name} ({target_layer})"
                        )

        return warnings

    def _extract_model_name(self, reference: str) -> str:
        """Extract model name from a reference.

        Args:
            reference: Model reference.

        Returns:
            Simple model name.
        """
        parts = reference.split(".")
        return parts[-1]
