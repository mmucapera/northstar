"""Lineage data models for Northstar Formation.

This module defines the Pydantic models used for tracking data lineage
across the data pipeline, including table-level and column-level lineage.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set

from pydantic import BaseModel, Field


class LineageNodeType(str, Enum):
    """Type of node in lineage graph."""

    TABLE = "table"
    COLUMN = "column"
    EXTERNAL = "external"  # External/source tables not defined in YAML


class LineageEdgeType(str, Enum):
    """Type of edge in lineage graph."""

    DIRECT = "direct"  # Direct table reference (FROM clause)
    TRANSFORMATION = "transformation"  # Column transformation
    JOIN = "join"  # Join relationship
    CTE = "cte"  # CTE reference
    INHERITANCE = "inheritance"  # Model inheritance (extends/inherits_from)


class ColumnLineageNode(BaseModel):
    """Track a single column's lineage.

    Attributes:
        name: Column name.
        table: Table this column belongs to.
        layer: Data layer (bronze, silver, gold).
        data_type: Column data type if known.
        expression: SQL expression if the column is transformed.
        source_columns: List of source columns this column derives from.
        is_computed: True if derived from an expression.
        is_inherited: True if inherited from a parent model.
    """

    name: str = Field(..., description="Column name")
    table: str = Field(..., description="Table this column belongs to")
    layer: Optional[str] = Field(None, description="Data layer (bronze, silver, gold)")
    data_type: Optional[str] = Field(None, description="Column data type")
    expression: Optional[str] = Field(None, description="SQL expression if transformed")
    source_columns: List[ColumnLineageNode] = Field(
        default_factory=list, description="Source columns this derives from"
    )
    is_computed: bool = Field(False, description="True if derived from expression")
    is_inherited: bool = Field(False, description="True if inherited from parent model")

    class Config:
        """Pydantic configuration."""

        frozen = False  # Allow modification during graph building

    def __hash__(self) -> int:
        """Hash for use in sets."""
        return hash((self.name, self.table))

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if not isinstance(other, ColumnLineageNode):
            return False
        return self.name == other.name and self.table == other.table

    @property
    def qualified_name(self) -> str:
        """Get fully qualified column name (table.column)."""
        return f"{self.table}.{self.name}"


class TableLineageNode(BaseModel):
    """Track a single table's lineage.

    Attributes:
        name: Table name.
        layer: Data layer (bronze, silver, gold).
        qualified_name: Fully qualified name (e.g., "bronze.brz_customer").
        source_tables: List of upstream table names.
        columns: List of columns in this table.
        is_external: True if not defined in YAML (external source).
        description: Table description from model.
        kind: Table kind (TABLE, VIEW, CTE).
    """

    name: str = Field(..., description="Table name")
    layer: Optional[str] = Field(None, description="Data layer")
    qualified_name: str = Field(..., description="Fully qualified table name")
    source_tables: List[str] = Field(default_factory=list, description="Upstream table names")
    columns: List[ColumnLineageNode] = Field(
        default_factory=list, description="Columns in this table"
    )
    is_external: bool = Field(False, description="True if not defined in YAML (external source)")
    description: Optional[str] = Field(None, description="Table description")
    kind: Optional[str] = Field(None, description="Table kind (TABLE, VIEW, CTE)")

    class Config:
        """Pydantic configuration."""

        frozen = False

    def __hash__(self) -> int:
        """Hash for use in sets."""
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if not isinstance(other, TableLineageNode):
            return False
        return self.name == other.name

    def get_column(self, column_name: str) -> Optional[ColumnLineageNode]:
        """Get a column by name.

        Args:
            column_name: Name of the column to find.

        Returns:
            ColumnLineageNode if found, None otherwise.
        """
        for col in self.columns:
            if col.name.lower() == column_name.lower():
                return col
        return None


class LineageEdge(BaseModel):
    """Edge between two nodes in lineage graph.

    Attributes:
        source: Source node name.
        target: Target node name.
        edge_type: Type of relationship.
        columns: Columns involved in this edge.
        join_type: Join type for JOIN edges (LEFT, INNER, etc.).
        transformation: Transformation description if applicable.
    """

    source: str = Field(..., description="Source node name")
    target: str = Field(..., description="Target node name")
    edge_type: LineageEdgeType = Field(..., description="Type of relationship")
    columns: List[str] = Field(default_factory=list, description="Columns involved in this edge")
    join_type: Optional[str] = Field(None, description="Join type for JOIN edges")
    transformation: Optional[str] = Field(None, description="Transformation description")

    class Config:
        """Pydantic configuration."""

        frozen = False

    def __hash__(self) -> int:
        """Hash for use in sets."""
        return hash((self.source, self.target, self.edge_type))

    def __eq__(self, other: object) -> bool:
        """Equality check."""
        if not isinstance(other, LineageEdge):
            return False
        return (
            self.source == other.source
            and self.target == other.target
            and self.edge_type == other.edge_type
        )


class ColumnLineageEdge(BaseModel):
    """Edge representing column-level lineage.

    Attributes:
        source_table: Source table name.
        source_column: Source column name.
        target_table: Target table name.
        target_column: Target column name.
        transformation: SQL transformation if any.
        is_direct: True if direct column reference (no transformation).
    """

    source_table: str = Field(..., description="Source table name")
    source_column: str = Field(..., description="Source column name")
    target_table: str = Field(..., description="Target table name")
    target_column: str = Field(..., description="Target column name")
    transformation: Optional[str] = Field(None, description="SQL transformation")
    is_direct: bool = Field(True, description="True if direct column reference")

    @property
    def source_qualified(self) -> str:
        """Get qualified source column name."""
        return f"{self.source_table}.{self.source_column}"

    @property
    def target_qualified(self) -> str:
        """Get qualified target column name."""
        return f"{self.target_table}.{self.target_column}"


class LineageGraph(BaseModel):
    """Complete lineage graph.

    Attributes:
        tables: Dictionary of table name to TableLineageNode.
        edges: List of edges between tables.
        column_edges: List of column-level lineage edges.
    """

    tables: Dict[str, TableLineageNode] = Field(
        default_factory=dict, description="Tables in the graph"
    )
    edges: List[LineageEdge] = Field(default_factory=list, description="Edges between tables")
    column_edges: List[ColumnLineageEdge] = Field(
        default_factory=list, description="Column-level lineage edges"
    )

    class Config:
        """Pydantic configuration."""

        frozen = False

    def add_table(self, table: TableLineageNode) -> None:
        """Add a table to the graph.

        Args:
            table: TableLineageNode to add.
        """
        self.tables[table.name] = table

    def add_edge(self, edge: LineageEdge) -> None:
        """Add an edge to the graph.

        Args:
            edge: LineageEdge to add.
        """
        if edge not in self.edges:
            self.edges.append(edge)

    def add_column_edge(self, edge: ColumnLineageEdge) -> None:
        """Add a column-level edge to the graph.

        Args:
            edge: ColumnLineageEdge to add.
        """
        self.column_edges.append(edge)

    def get_table(self, table_name: str) -> Optional[TableLineageNode]:
        """Get a table by name.

        Args:
            table_name: Name of the table to find.

        Returns:
            TableLineageNode if found, None otherwise.
        """
        return self.tables.get(table_name)

    def get_upstream(self, table_name: str) -> List[str]:
        """Get all tables that feed into this table (recursive).

        Args:
            table_name: Table to find upstream dependencies for.

        Returns:
            List of upstream table names.
        """
        visited: Set[str] = set()
        result: List[str] = []

        def _traverse(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            for edge in self.edges:
                if edge.target == name and edge.source not in visited:
                    result.append(edge.source)
                    _traverse(edge.source)

        _traverse(table_name)
        return result

    def get_downstream(self, table_name: str) -> List[str]:
        """Get all tables that depend on this table (recursive).

        Args:
            table_name: Table to find downstream dependents for.

        Returns:
            List of downstream table names.
        """
        visited: Set[str] = set()
        result: List[str] = []

        def _traverse(name: str) -> None:
            if name in visited:
                return
            visited.add(name)

            for edge in self.edges:
                if edge.source == name and edge.target not in visited:
                    result.append(edge.target)
                    _traverse(edge.target)

        _traverse(table_name)
        return result

    def get_direct_upstream(self, table_name: str) -> List[str]:
        """Get immediate upstream tables (non-recursive).

        Args:
            table_name: Table to find direct upstream dependencies for.

        Returns:
            List of direct upstream table names.
        """
        return [edge.source for edge in self.edges if edge.target == table_name]

    def get_direct_downstream(self, table_name: str) -> List[str]:
        """Get immediate downstream tables (non-recursive).

        Args:
            table_name: Table to find direct downstream dependents for.

        Returns:
            List of direct downstream table names.
        """
        return [edge.target for edge in self.edges if edge.source == table_name]

    def get_column_lineage(self, table: str, column: str) -> List[ColumnLineageNode]:
        """Trace a column back to its sources.

        Args:
            table: Table name containing the column.
            column: Column name to trace.

        Returns:
            List of source ColumnLineageNodes.
        """
        result: List[ColumnLineageNode] = []
        visited: Set[str] = set()

        def _trace(tbl: str, col: str) -> None:
            key = f"{tbl}.{col}"
            if key in visited:
                return
            visited.add(key)

            for edge in self.column_edges:
                if (
                    edge.target_table.lower() == tbl.lower()
                    and edge.target_column.lower() == col.lower()
                ):
                    source_table = self.get_table(edge.source_table)
                    if source_table:
                        source_col = source_table.get_column(edge.source_column)
                        if source_col and source_col not in result:
                            result.append(source_col)
                            _trace(edge.source_table, edge.source_column)

        _trace(table, column)
        return result

    def get_column_impact(self, table: str, column: str) -> List[ColumnLineageNode]:
        """Find all columns that depend on this column (forward lineage).

        Args:
            table: Table name containing the column.
            column: Column name to find impact of.

        Returns:
            List of downstream ColumnLineageNodes.
        """
        result: List[ColumnLineageNode] = []
        visited: Set[str] = set()

        def _trace(tbl: str, col: str) -> None:
            key = f"{tbl}.{col}"
            if key in visited:
                return
            visited.add(key)

            for edge in self.column_edges:
                if (
                    edge.source_table.lower() == tbl.lower()
                    and edge.source_column.lower() == col.lower()
                ):
                    target_table = self.get_table(edge.target_table)
                    if target_table:
                        target_col = target_table.get_column(edge.target_column)
                        if target_col and target_col not in result:
                            result.append(target_col)
                            _trace(edge.target_table, edge.target_column)

        _trace(table, column)
        return result

    def get_tables_by_layer(self, layer: str) -> List[TableLineageNode]:
        """Get all tables in a specific layer.

        Args:
            layer: Layer name (bronze, silver, gold).

        Returns:
            List of tables in that layer.
        """
        return [
            table
            for table in self.tables.values()
            if table.layer and table.layer.lower() == layer.lower()
        ]

    def filter_by_table(self, table_name: str) -> LineageGraph:
        """Create a subgraph focused on a specific table.

        Includes the table and all its upstream/downstream dependencies.

        Args:
            table_name: Table to focus on.

        Returns:
            New LineageGraph containing only relevant tables and edges.
        """
        relevant_tables: Set[str] = {table_name}
        relevant_tables.update(self.get_upstream(table_name))
        relevant_tables.update(self.get_downstream(table_name))

        filtered_tables = {
            name: table for name, table in self.tables.items() if name in relevant_tables
        }

        filtered_edges = [
            edge
            for edge in self.edges
            if edge.source in relevant_tables and edge.target in relevant_tables
        ]

        filtered_column_edges = [
            edge
            for edge in self.column_edges
            if (edge.source_table in relevant_tables and edge.target_table in relevant_tables)
        ]

        return LineageGraph(
            tables=filtered_tables,
            edges=filtered_edges,
            column_edges=filtered_column_edges,
        )

    def filter_by_layer(self, layer: str) -> LineageGraph:
        """Create a subgraph containing only tables in a specific layer.

        Args:
            layer: Layer name to filter by.

        Returns:
            New LineageGraph containing only tables in that layer.
        """
        filtered_tables = {
            name: table
            for name, table in self.tables.items()
            if table.layer and table.layer.lower() == layer.lower()
        }

        table_names = set(filtered_tables.keys())

        filtered_edges = [
            edge for edge in self.edges if edge.source in table_names and edge.target in table_names
        ]

        filtered_column_edges = [
            edge
            for edge in self.column_edges
            if (edge.source_table in table_names and edge.target_table in table_names)
        ]

        return LineageGraph(
            tables=filtered_tables,
            edges=filtered_edges,
            column_edges=filtered_column_edges,
        )

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization.

        Returns:
            Dictionary representation of the graph.
        """
        return {
            "tables": {
                name: {
                    "name": table.name,
                    "layer": table.layer,
                    "qualified_name": table.qualified_name,
                    "source_tables": table.source_tables,
                    "is_external": table.is_external,
                    "description": table.description,
                    "kind": table.kind,
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
                for name, table in self.tables.items()
            },
            "edges": [
                {
                    "source": edge.source,
                    "target": edge.target,
                    "edge_type": edge.edge_type.value,
                    "columns": edge.columns,
                    "join_type": edge.join_type,
                }
                for edge in self.edges
            ],
            "column_edges": [
                {
                    "source_table": edge.source_table,
                    "source_column": edge.source_column,
                    "target_table": edge.target_table,
                    "target_column": edge.target_column,
                    "transformation": edge.transformation,
                    "is_direct": edge.is_direct,
                }
                for edge in self.column_edges
            ],
        }
