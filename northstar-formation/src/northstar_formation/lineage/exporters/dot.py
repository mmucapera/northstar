"""Graphviz DOT format exporter for lineage graphs.

This module exports lineage graphs to Graphviz DOT format,
which can be rendered to various image formats using the
graphviz command-line tools.
"""

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, TextIO, Union

from ...utils.logging import get_logger
from ..models import LineageEdgeType, LineageGraph, TableLineageNode


logger = get_logger(__name__)


class DotExporter:
    """Export lineage graph to Graphviz DOT format.

    This exporter generates DOT files that can be rendered using
    Graphviz tools (dot, neato, etc.) to create visual representations
    of the data lineage.

    Example:
        >>> from northstar_formation.lineage.exporters.dot import DotExporter
        >>> exporter = DotExporter()
        >>> dot_content = exporter.export(graph, Path("lineage.dot"))
        >>> exporter.render(Path("lineage.dot"), "png")
    """

    # Color scheme for layers (following medallion architecture)
    LAYER_COLORS: Dict[str, str] = {
        "bronze": "#CD7F32",  # Bronze color
        "silver": "#C0C0C0",  # Silver color
        "gold": "#FFD700",  # Gold color
        "external": "#808080",  # Gray for external
        "unknown": "#CCCCCC",  # Light gray for unknown
    }

    LAYER_BG_COLORS: Dict[str, str] = {
        "bronze": "#FDF5E6",  # Light bronze/tan
        "silver": "#F5F5F5",  # Light silver/gray
        "gold": "#FFFACD",  # Light gold/lemon
        "external": "#E8E8E8",  # Light gray
        "unknown": "#FFFFFF",  # White
    }

    LAYER_ORDER: Dict[str, int] = {
        "external": 0,
        "bronze": 1,
        "silver": 2,
        "gold": 3,
        "unknown": 4,
    }

    def __init__(
        self,
        show_columns: bool = True,
        show_column_types: bool = False,
        rankdir: str = "LR",
        max_columns: int = 20,
        cluster_by_layer: bool = True,
        show_edge_labels: bool = True,
        font_name: str = "Helvetica",
        font_size: int = 10,
    ) -> None:
        """Initialize DOT exporter.

        Args:
            show_columns: Whether to show column names in table nodes.
            show_column_types: Whether to show column data types.
            rankdir: Graph direction (LR=left-to-right, TB=top-to-bottom,
                    BT=bottom-to-top, RL=right-to-left).
            max_columns: Maximum columns to show before truncating.
            cluster_by_layer: Whether to group tables by layer in subgraphs.
            show_edge_labels: Whether to show labels on edges.
            font_name: Font family for labels.
            font_size: Base font size.
        """
        self.show_columns = show_columns
        self.show_column_types = show_column_types
        self.rankdir = rankdir
        self.max_columns = max_columns
        self.cluster_by_layer = cluster_by_layer
        self.show_edge_labels = show_edge_labels
        self.font_name = font_name
        self.font_size = font_size

    def export(
        self,
        graph: LineageGraph,
        output: Union[Path, TextIO],
        title: Optional[str] = None,
    ) -> str:
        """Export lineage graph to DOT format.

        Args:
            graph: LineageGraph to export.
            output: File path or file-like object to write to.
            title: Optional title for the graph.

        Returns:
            DOT content as string.
        """
        logger.info("Exporting lineage graph to DOT format")

        dot_content = self._build_dot(graph, title)

        if isinstance(output, Path):
            output.write_text(dot_content, encoding="utf-8")
            logger.info(f"DOT file written to: {output}")
        else:
            output.write(dot_content)

        return dot_content

    def _build_dot(self, graph: LineageGraph, title: Optional[str]) -> str:
        """Build DOT content from lineage graph.

        Args:
            graph: LineageGraph to convert.
            title: Optional title.

        Returns:
            Complete DOT content as string.
        """
        lines: List[str] = []

        # Graph header
        lines.append("digraph DataLineage {")
        lines.append(f"    rankdir={self.rankdir};")
        lines.append(
            f'    node [shape=record, fontname="{self.font_name}", fontsize={self.font_size}];'
        )
        lines.append(f'    edge [fontname="{self.font_name}", fontsize={self.font_size - 1}];')

        if title:
            escaped_title = self._escape_dot_string(title)
            lines.append(f'    label="{escaped_title}";')
            lines.append('    labelloc="t";')
            lines.append("    fontsize=14;")
        else:
            lines.append('    label="Data Lineage";')
            lines.append('    labelloc="t";')
            lines.append("    fontsize=14;")

        lines.append("")

        if self.cluster_by_layer:
            # Group tables by layer into subgraphs
            tables_by_layer = self._group_by_layer(graph)

            # Sort layers by order
            sorted_layers = sorted(
                tables_by_layer.keys(), key=lambda x: self.LAYER_ORDER.get(x.lower(), 99)
            )

            for layer in sorted_layers:
                tables = tables_by_layer[layer]
                lines.extend(self._build_layer_subgraph(layer, tables))
        else:
            # Add all tables without clustering
            for table in graph.tables.values():
                layer = table.layer or "unknown"
                color = self.LAYER_COLORS.get(layer.lower(), "#CCCCCC")
                lines.append(self._build_table_node(table, color, indent=4))

        # Add edges
        lines.append("")
        lines.append("    // Edges")
        for edge in graph.edges:
            lines.append(self._build_edge(edge))

        lines.append("}")

        return "\n".join(lines)

    def _group_by_layer(self, graph: LineageGraph) -> Dict[str, List[TableLineageNode]]:
        """Group tables by their layer.

        Args:
            graph: LineageGraph to group.

        Returns:
            Dictionary of layer name to list of tables.
        """
        layers: Dict[str, List[TableLineageNode]] = {}

        for table in graph.tables.values():
            layer = table.layer or "unknown"
            if layer not in layers:
                layers[layer] = []
            layers[layer].append(table)

        return layers

    def _build_layer_subgraph(
        self,
        layer: str,
        tables: List[TableLineageNode],
    ) -> List[str]:
        """Build a subgraph for a layer.

        Args:
            layer: Layer name.
            tables: Tables in this layer.

        Returns:
            List of DOT lines for this subgraph.
        """
        layer_lower = layer.lower()
        color = self.LAYER_COLORS.get(layer_lower, "#CCCCCC")
        bg_color = self.LAYER_BG_COLORS.get(layer_lower, "#FFFFFF")

        # Sanitize layer name for cluster ID
        cluster_id = self._sanitize_id(layer)

        lines: List[str] = []
        lines.append(f"    subgraph cluster_{cluster_id} {{")
        lines.append(f'        label="{layer.title()} Layer";')
        lines.append("        style=filled;")
        lines.append(f'        fillcolor="{bg_color}";')
        lines.append(f'        color="{color}";')
        lines.append("        penwidth=2;")
        lines.append("")

        for table in tables:
            lines.append(self._build_table_node(table, color, indent=8))

        lines.append("    }")
        lines.append("")

        return lines

    def _build_table_node(
        self,
        table: TableLineageNode,
        border_color: str,
        indent: int = 8,
    ) -> str:
        """Build a table node with optional columns.

        Args:
            table: TableLineageNode to render.
            border_color: Border color for the node.
            indent: Indentation level.

        Returns:
            DOT line for this node.
        """
        node_id = self._sanitize_id(table.name)
        indent_str = " " * indent

        if not self.show_columns or not table.columns:
            # Simple node without columns
            label = self._escape_dot_string(table.name)
            return f'{indent_str}{node_id} [label="{label}", color="{border_color}", penwidth=2];'

        # Record-style node with columns
        columns = table.columns[: self.max_columns]
        col_lines: List[str] = []

        for col in columns:
            col_text = col.name
            if self.show_column_types and col.data_type:
                col_text = f"{col.name}: {col.data_type}"
            # Escape special characters for DOT
            col_text = self._escape_record_string(col_text)
            col_lines.append(col_text)

        if len(table.columns) > self.max_columns:
            remaining = len(table.columns) - self.max_columns
            col_lines.append(f"... +{remaining} more")

        # Build record label: {table_name|col1\lcol2\l...}
        table_name_escaped = self._escape_record_string(table.name)
        cols_str = "\\l".join(col_lines) + "\\l"
        label = f"{{{table_name_escaped}|{cols_str}}}"

        return f'{indent_str}{node_id} [label="{label}", color="{border_color}", penwidth=2];'

    def _build_edge(self, edge) -> str:
        """Build an edge line.

        Args:
            edge: LineageEdge to render.

        Returns:
            DOT line for this edge.
        """
        source_id = self._sanitize_id(edge.source)
        target_id = self._sanitize_id(edge.target)

        # Edge styling based on type
        attrs: List[str] = []

        if edge.edge_type == LineageEdgeType.JOIN:
            attrs.append("style=dashed")
            attrs.append('color="#4169E1"')  # Royal blue
            if self.show_edge_labels and edge.join_type:
                attrs.append(f'label="{edge.join_type}"')

        elif edge.edge_type == LineageEdgeType.CTE:
            attrs.append("style=dotted")
            attrs.append('color="#9932CC"')  # Purple
            if self.show_edge_labels:
                attrs.append('label="CTE"')

        elif edge.edge_type == LineageEdgeType.INHERITANCE:
            attrs.append("style=bold")
            attrs.append('color="#228B22"')  # Forest green
            if self.show_edge_labels:
                attrs.append('label="extends"')

        elif edge.edge_type == LineageEdgeType.TRANSFORMATION:
            attrs.append('color="#FF8C00"')  # Dark orange
            if self.show_edge_labels:
                attrs.append('label="transform"')

        else:
            # DIRECT edge - default styling
            attrs.append('color="#333333"')

        attrs_str = ", ".join(attrs) if attrs else ""
        if attrs_str:
            return f"    {source_id} -> {target_id} [{attrs_str}];"
        else:
            return f"    {source_id} -> {target_id};"

    def _sanitize_id(self, name: str) -> str:
        """Sanitize name for use as DOT node ID.

        Args:
            name: Name to sanitize.

        Returns:
            Sanitized ID safe for DOT.
        """
        # Replace special characters with underscore
        sanitized = name.replace(".", "_").replace("-", "_").replace(" ", "_")
        sanitized = sanitized.replace("(", "_").replace(")", "_")

        # Ensure it starts with a letter or underscore
        if sanitized and sanitized[0].isdigit():
            sanitized = f"t_{sanitized}"

        return sanitized

    def _escape_dot_string(self, s: str) -> str:
        """Escape a string for use in DOT labels.

        Args:
            s: String to escape.

        Returns:
            Escaped string.
        """
        # Escape backslashes first, then quotes
        return s.replace("\\", "\\\\").replace('"', '\\"')

    def _escape_record_string(self, s: str) -> str:
        """Escape a string for use in DOT record labels.

        Record labels have additional special characters.

        Args:
            s: String to escape.

        Returns:
            Escaped string.
        """
        # Escape special DOT record characters
        result = s.replace("\\", "\\\\")
        result = result.replace('"', '\\"')
        result = result.replace("<", "\\<")
        result = result.replace(">", "\\>")
        result = result.replace("{", "\\{")
        result = result.replace("}", "\\}")
        result = result.replace("|", "\\|")
        return result

    def render(
        self,
        dot_file: Path,
        output_format: str = "png",
        output_file: Optional[Path] = None,
    ) -> Path:
        """Render DOT file to image using graphviz.

        Args:
            dot_file: Path to DOT file.
            output_format: Output format (png, svg, pdf).
            output_file: Output file path. Defaults to dot_file with new extension.

        Returns:
            Path to rendered file.

        Raises:
            RuntimeError: If graphviz is not installed.
            subprocess.CalledProcessError: If rendering fails.
        """
        # Check if graphviz is installed
        if not shutil.which("dot"):
            raise RuntimeError(
                "Graphviz 'dot' command not found. "
                "Install graphviz: brew install graphviz (macOS) "
                "or apt-get install graphviz (Linux)"
            )

        if output_file is None:
            output_file = dot_file.with_suffix(f".{output_format}")

        logger.info(f"Rendering DOT file to {output_format}: {output_file}")

        subprocess.run(
            ["dot", f"-T{output_format}", str(dot_file), "-o", str(output_file)],
            check=True,
            capture_output=True,
            text=True,
        )

        logger.info(f"Rendered to: {output_file}")
        return output_file

    def export_column_lineage(
        self,
        graph: LineageGraph,
        table: str,
        column: str,
        output: Union[Path, TextIO],
        title: Optional[str] = None,
    ) -> str:
        """Export column-level lineage to DOT format.

        Creates a focused graph showing the lineage of a specific column.

        Args:
            graph: LineageGraph to export from.
            table: Table containing the column.
            column: Column to trace lineage for.
            output: File path or file-like object.
            title: Optional title.

        Returns:
            DOT content as string.
        """
        lines: List[str] = []

        # Get column lineage
        source_columns = graph.get_column_lineage(table, column)

        # Build focused graph
        lines.append("digraph ColumnLineage {")
        lines.append(f"    rankdir={self.rankdir};")
        lines.append(
            f'    node [shape=box, fontname="{self.font_name}", fontsize={self.font_size}];'
        )
        lines.append(f'    edge [fontname="{self.font_name}", fontsize={self.font_size - 1}];')

        effective_title = title or f"Column Lineage: {table}.{column}"
        lines.append(f'    label="{self._escape_dot_string(effective_title)}";')
        lines.append('    labelloc="t";')
        lines.append("    fontsize=14;")
        lines.append("")

        # Target column (highlighted)
        target_id = self._sanitize_id(f"{table}_{column}")
        lines.append(
            f'    {target_id} [label="{table}.{column}", style=filled, fillcolor="#FFD700"];'
        )

        # Source columns
        seen_nodes = {target_id}
        for src_col in source_columns:
            src_id = self._sanitize_id(f"{src_col.table}_{src_col.name}")
            if src_id not in seen_nodes:
                layer = src_col.layer or "unknown"
                color = self.LAYER_BG_COLORS.get(layer.lower(), "#FFFFFF")
                lines.append(
                    f'    {src_id} [label="{src_col.table}.{src_col.name}", style=filled, fillcolor="{color}"];'
                )
                seen_nodes.add(src_id)

        # Edges
        lines.append("")
        for edge in graph.column_edges:
            if edge.target_table == table and edge.target_column == column:
                src_id = self._sanitize_id(f"{edge.source_table}_{edge.source_column}")
                tgt_id = self._sanitize_id(f"{edge.target_table}_{edge.target_column}")

                if edge.is_direct:
                    lines.append(f"    {src_id} -> {tgt_id};")
                else:
                    transform_label = (
                        edge.transformation[:30] + "..."
                        if edge.transformation and len(edge.transformation) > 30
                        else edge.transformation or ""
                    )
                    lines.append(
                        f'    {src_id} -> {tgt_id} [label="{self._escape_dot_string(transform_label)}", style=dashed];'
                    )

        lines.append("}")

        dot_content = "\n".join(lines)

        if isinstance(output, Path):
            output.write_text(dot_content, encoding="utf-8")
        else:
            output.write(dot_content)

        return dot_content
