"""JSON exporter for lineage graphs.

This module exports lineage graphs to JSON format for
programmatic use and integration with other tools.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, TextIO, Union

from ...utils.logging import get_logger
from ..models import LineageGraph


logger = get_logger(__name__)


class JsonExporter:
    """Export lineage graph to JSON format.

    This exporter generates JSON files that can be used for:
    - Integration with other tools
    - Web-based visualization
    - Programmatic analysis
    - Documentation generation

    Example:
        >>> from northstar_formation.lineage.exporters.json_exporter import JsonExporter
        >>> exporter = JsonExporter()
        >>> json_content = exporter.export(graph, Path("lineage.json"))
    """

    def __init__(
        self,
        indent: int = 2,
        include_column_lineage: bool = True,
        include_statistics: bool = True,
    ) -> None:
        """Initialize JSON exporter.

        Args:
            indent: JSON indentation level (0 for compact).
            include_column_lineage: Whether to include column-level lineage.
            include_statistics: Whether to include graph statistics.
        """
        self.indent = indent if indent > 0 else None
        self.include_column_lineage = include_column_lineage
        self.include_statistics = include_statistics

    def export(
        self,
        graph: LineageGraph,
        output: Union[Path, TextIO],
        title: Optional[str] = None,
    ) -> str:
        """Export lineage graph to JSON format.

        Args:
            graph: LineageGraph to export.
            output: File path or file-like object to write to.
            title: Optional title/description.

        Returns:
            JSON content as string.
        """
        logger.info("Exporting lineage graph to JSON format")

        json_data = self._build_json(graph, title)
        json_content = json.dumps(json_data, indent=self.indent, ensure_ascii=False)

        if isinstance(output, Path):
            output.write_text(json_content, encoding="utf-8")
            logger.info(f"JSON file written to: {output}")
        else:
            output.write(json_content)

        return json_content

    def _build_json(
        self,
        graph: LineageGraph,
        title: Optional[str],
    ) -> Dict[str, Any]:
        """Build JSON structure from lineage graph.

        Args:
            graph: LineageGraph to convert.
            title: Optional title.

        Returns:
            Dictionary ready for JSON serialization.
        """
        result: Dict[str, Any] = {
            "metadata": {
                "title": title or "Data Lineage",
                "version": "1.0",
                "format": "northstar-formation-lineage",
            },
            "tables": {},
            "edges": [],
        }

        # Add tables
        for name, table in graph.tables.items():
            result["tables"][name] = {
                "name": table.name,
                "layer": table.layer,
                "qualified_name": table.qualified_name,
                "kind": table.kind,
                "is_external": table.is_external,
                "description": table.description,
                "source_tables": table.source_tables,
                "columns": [
                    {
                        "name": col.name,
                        "data_type": col.data_type,
                        "expression": col.expression,
                        "is_computed": col.is_computed,
                        "is_inherited": col.is_inherited,
                    }
                    for col in table.columns
                ],
            }

        # Add edges
        for edge in graph.edges:
            result["edges"].append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "edge_type": edge.edge_type.value,
                    "columns": edge.columns,
                    "join_type": edge.join_type,
                }
            )

        # Add column-level lineage if requested
        if self.include_column_lineage and graph.column_edges:
            result["column_lineage"] = [
                {
                    "source_table": edge.source_table,
                    "source_column": edge.source_column,
                    "target_table": edge.target_table,
                    "target_column": edge.target_column,
                    "transformation": edge.transformation,
                    "is_direct": edge.is_direct,
                }
                for edge in graph.column_edges
            ]

        # Add statistics if requested
        if self.include_statistics:
            result["statistics"] = self._compute_statistics(graph)

        return result

    def _compute_statistics(self, graph: LineageGraph) -> Dict[str, Any]:
        """Compute statistics about the lineage graph.

        Args:
            graph: LineageGraph to analyze.

        Returns:
            Dictionary of statistics.
        """
        layers: Dict[str, int] = {}
        for table in graph.tables.values():
            layer = table.layer or "unknown"
            layers[layer] = layers.get(layer, 0) + 1

        return {
            "total_tables": len(graph.tables),
            "total_edges": len(graph.edges),
            "column_edges": len(graph.column_edges),
            "external_tables": sum(1 for t in graph.tables.values() if t.is_external),
            "tables_by_layer": layers,
        }

    def export_for_visualization(
        self,
        graph: LineageGraph,
        output: Union[Path, TextIO],
    ) -> str:
        """Export in a format optimized for web visualization.

        Generates a structure compatible with common graph visualization
        libraries like D3.js, Cytoscape.js, or vis.js.

        Args:
            graph: LineageGraph to export.
            output: File path or file-like object.

        Returns:
            JSON content as string.
        """
        logger.info("Exporting lineage graph for visualization")

        # Build nodes and links format (common for D3.js)
        nodes = []
        links = []

        # Add table nodes
        for name, table in graph.tables.items():
            layer = table.layer or "unknown"
            nodes.append(
                {
                    "id": name,
                    "label": name,
                    "group": layer,
                    "type": "table",
                    "external": table.is_external,
                    "columns": len(table.columns),
                }
            )

        # Add edges as links
        for edge in graph.edges:
            links.append(
                {
                    "source": edge.source,
                    "target": edge.target,
                    "type": edge.edge_type.value,
                }
            )

        result = {
            "nodes": nodes,
            "links": links,
        }

        json_content = json.dumps(result, indent=self.indent, ensure_ascii=False)

        if isinstance(output, Path):
            output.write_text(json_content, encoding="utf-8")
        else:
            output.write(json_content)

        return json_content

    def export_column_lineage(
        self,
        graph: LineageGraph,
        table: str,
        column: str,
        output: Union[Path, TextIO],
    ) -> str:
        """Export lineage for a specific column.

        Args:
            graph: LineageGraph to query.
            table: Table containing the column.
            column: Column to trace lineage for.
            output: File path or file-like object.

        Returns:
            JSON content as string.
        """
        # Get upstream lineage
        sources = graph.get_column_lineage(table, column)

        # Get downstream impact
        impacts = graph.get_column_impact(table, column)

        result = {
            "target": {
                "table": table,
                "column": column,
            },
            "sources": [
                {
                    "table": col.table,
                    "column": col.name,
                    "layer": col.layer,
                    "expression": col.expression,
                }
                for col in sources
            ],
            "impacts": [
                {
                    "table": col.table,
                    "column": col.name,
                    "layer": col.layer,
                }
                for col in impacts
            ],
            "lineage_edges": [
                {
                    "source_table": edge.source_table,
                    "source_column": edge.source_column,
                    "target_table": edge.target_table,
                    "target_column": edge.target_column,
                    "transformation": edge.transformation,
                    "is_direct": edge.is_direct,
                }
                for edge in graph.column_edges
                if (
                    (edge.target_table == table and edge.target_column == column)
                    or (edge.source_table == table and edge.source_column == column)
                )
            ],
        }

        json_content = json.dumps(result, indent=self.indent, ensure_ascii=False)

        if isinstance(output, Path):
            output.write_text(json_content, encoding="utf-8")
        else:
            output.write(json_content)

        return json_content

    def export_impact_analysis(
        self,
        graph: LineageGraph,
        table: str,
        output: Union[Path, TextIO],
    ) -> str:
        """Export impact analysis for a table.

        Shows what would be affected if this table changes.

        Args:
            graph: LineageGraph to analyze.
            table: Table to analyze impact for.
            output: File path or file-like object.

        Returns:
            JSON content as string.
        """
        direct_downstream = graph.get_direct_downstream(table)
        all_downstream = graph.get_downstream(table)
        indirect_downstream = [t for t in all_downstream if t not in direct_downstream]

        direct_upstream = graph.get_direct_upstream(table)
        all_upstream = graph.get_upstream(table)

        result = {
            "table": table,
            "impact": {
                "direct_downstream": direct_downstream,
                "indirect_downstream": indirect_downstream,
                "total_impacted": len(all_downstream),
            },
            "dependencies": {
                "direct_upstream": direct_upstream,
                "all_upstream": all_upstream,
            },
            "affected_tables": [
                {
                    "name": name,
                    "layer": graph.tables[name].layer if name in graph.tables else None,
                    "is_direct": name in direct_downstream,
                }
                for name in all_downstream
                if name in graph.tables
            ],
        }

        json_content = json.dumps(result, indent=self.indent, ensure_ascii=False)

        if isinstance(output, Path):
            output.write_text(json_content, encoding="utf-8")
        else:
            output.write(json_content)

        return json_content
