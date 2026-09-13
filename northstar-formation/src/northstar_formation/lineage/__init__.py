"""Lineage tracking module for Northstar Formation.

This module provides data lineage tracking capabilities for the
Northstar Formation system, including:

- Table-level lineage (which tables feed into which)
- Column-level lineage (column transformations through layers)
- Lineage graph building and analysis
- Export to DOT (Graphviz) and JSON formats

Example usage:
    >>> from northstar_formation.lineage import LineageAnalyzer, DotExporter
    >>> from pathlib import Path
    >>>
    >>> # Analyze lineage from a directory
    >>> analyzer = LineageAnalyzer()
    >>> graph = analyzer.analyze_from_directory("./models")
    >>>
    >>> # Export to DOT format
    >>> exporter = DotExporter()
    >>> exporter.export(graph, Path("lineage.dot"))
    >>>
    >>> # Optionally render to PNG
    >>> exporter.render(Path("lineage.dot"), "png")
"""

from .analyzer import LineageAnalyzer
from .column_tracker import ColumnExpressionParser
from .exporters import DotExporter, JsonExporter
from .graph_builder import LineageGraphBuilder
from .models import (
    ColumnLineageEdge,
    ColumnLineageNode,
    LineageEdge,
    LineageEdgeType,
    LineageGraph,
    LineageNodeType,
    TableLineageNode,
)


__all__ = [
    "ColumnExpressionParser",
    "ColumnLineageEdge",
    "ColumnLineageNode",
    "DotExporter",
    "JsonExporter",
    "LineageAnalyzer",
    "LineageEdge",
    "LineageEdgeType",
    "LineageGraph",
    "LineageGraphBuilder",
    "LineageNodeType",
    "TableLineageNode",
]
