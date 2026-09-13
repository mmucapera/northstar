"""Core Pydantic models for Northstar Formation.

This module defines the Pydantic models used throughout the Northstar Formation
system for parsing YAML configurations, resolving model inheritance, and
generating SQL/notebooks.

All models are designed to be customer-agnostic. Any customer-specific
behavior should be configured through the YAML files, not hardcoded here.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

from .enums import LoadStrategy


class ModelKind(str, Enum):
    """Model output types."""

    VIEW = "VIEW"
    TABLE = "TABLE"
    CTE = "CTE"


class ColumnAction(str, Enum):
    """Column transformation actions."""

    ADD = "add"
    REMOVE = "remove"
    TRANSFORM = "transform"
    OVERRIDE = "override"
    RENAME = "rename"


class FilterOperation(str, Enum):
    """Filter modification operations."""

    ADD = "add"
    REPLACE = "replace"
    APPEND = "append"


# ---- NEW enums for relationships/audits/optimization ----
class JoinType(str, Enum):
    INNER = "INNER"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    FULL_OUTER = "FULL OUTER"


class RelationshipType(str, Enum):
    ONE_TO_ONE = "one-to-one"
    ONE_TO_MANY = "one-to-many"
    MANY_TO_ONE = "many-to-one"
    MANY_TO_MANY = "many-to-many"


class AuditType(str, Enum):
    NOT_NULL = "NOT_NULL"
    POSITIVE_VALUES = "POSITIVE_VALUES"
    UNIQUE_COMBINATION = "UNIQUE_COMBINATION"
    ACCEPTED_VALUES = "ACCEPTED_VALUES"


# Build Context
class BuildContext(BaseModel):
    """Build context for conditional configuration loading."""

    customer: str = Field(default="STANDARD", description="Customer identifier")
    version: str = Field(default="1.0.0", description="Version string")
    features: List[str] = Field(default_factory=list, description="Enabled features")
    environment: str = Field(default="production", description="Target environment")

    def matches_condition(self, condition: Dict[str, Any]) -> bool:
        """Check if context matches a condition from metadata.applies_when."""
        if not condition:
            return True

        if "customer" in condition and condition["customer"] != self.customer:
            return False

        if "version" in condition:
            version_str = condition["version"]
            if version_str.startswith(">="):
                required_version = version_str[2:].strip()
                if not self._version_gte(self.version, required_version):
                    return False
            elif version_str != self.version:
                return False

        if "feature" in condition and condition["feature"] not in self.features:
            return False

        if "environment" in condition and condition["environment"] != self.environment:
            return False

        return True

    @staticmethod
    def _version_gte(version: str, required: str) -> bool:
        """Compare version strings."""

        def parse_version(v: str) -> tuple:
            return tuple(int(x) for x in v.split("."))

        try:
            return parse_version(version) >= parse_version(required)
        except:
            return False


# Metadata
class Metadata(BaseModel):
    """Model metadata for conditional application."""

    applies_when: Optional[Dict[str, Any]] = Field(
        None, description="Conditions for applying this config"
    )
    uses_functions: Optional[str] = Field(None, description="Path to customer-specific functions")
    author: Optional[str] = None
    created_date: Optional[datetime] = None
    modified_date: Optional[datetime] = None
    tags: List[str] = Field(default_factory=list)


# Column Definitions
class Column(BaseModel):
    """Column definition."""

    name: str = Field(..., description="Column name")
    expression: Optional[str] = Field(None, description="SQL expression or @function()")
    data_type: Optional[str] = Field(None, description="Data type")
    action: Optional[ColumnAction] = Field(None, description="Transformation action")
    new_name: Optional[str] = None
    description: Optional[str] = None
    nullable: bool = True

    @model_validator(mode="after")
    def validate_rename(self):
        if self.action == ColumnAction.RENAME and not self.new_name:
            raise ValueError(f"Column {self.name}: rename action requires new_name")
        return self


# Merge configuration for load strategies
class MergeConfig(BaseModel):
    """Configuration for merge/load operations.

    Attributes:
        merge_keys: Column names used as keys for MERGE operations.
        load_strategy: Strategy for loading data (see LoadStrategy enum).
        delete_keys: Column names used for DELETE operations in delete_insert strategy.
        non_nulls: Column names that must be validated for non-null values before merge.
        purge_domain: Domain identifier for data purging/retention policies.
        full_retention_months: Number of months to retain full historical data.
        snapshot_months: Number of months to retain snapshot data.
    """

    merge_keys: List[str] = Field(default_factory=list, description="Keys for merge operations")
    load_strategy: Optional[str] = Field(
        None,
        description="Load strategy: bronze_to_silver_latest, delete_insert, silver_to_gold, etc.",
    )
    delete_keys: List[str] = Field(
        default_factory=list, description="Keys for delete operations in delete_insert strategy"
    )
    non_nulls: List[str] = Field(
        default_factory=list, description="Columns that must be validated for non-null values before merge"
    )
    partition_by: List[str] = Field(
        default_factory=list,
        description=(
            "Columns to physically partition the target Delta table by. "
            "Only honoured when the target is created (empty). Passed through as "
            "PARTITION_BY in the framework_execute cfg dict."
        ),
    )
    base_conversion_measures: List[str] = Field(
        default_factory=list, description="Keys for base conversion measures in dynamic query generation"
    )
    conversion_lkp_tbl: Optional[str] = Field(
        None,
        description="Conversion lookup table for dynamic query generation",
    )
    src_query_type: Optional[str] = Field(
        None,
        description="Source query type for dynamic SQL generation (e.g., dynamic, static)",
    )
    purge_domain: Optional[str] = Field(
        None,
        description="Domain identifier for data purging/retention policies",
    )
    full_retention_months: Optional[int] = Field(
        None,
        description="Number of months to retain full historical data",
    )
    snapshot_months: Optional[int] = Field(
        None,
        description="Number of months to retain snapshot data",
    )
    plan_over_plan: Optional[int] = Field(
        None,
        description="PlanOverPlan flag for processing",
    )


    @field_validator("load_strategy", mode="before")
    @classmethod
    def validate_load_strategy(cls, v: Optional[str]) -> Optional[str]:
        """Validate that load_strategy is a known strategy or None.

        Args:
            v: The load strategy value to validate.

        Returns:
            The validated load strategy string (lowercase).

        Raises:
            ValueError: If the strategy is not recognized.
        """
        if v is None:
            return None
        try:
            # Validate using the enum, but store as string for flexibility
            LoadStrategy.from_string(v)
            return v.lower().strip()
        except ValueError:
            # Allow unknown strategies with a warning (for extensibility)
            # The actual validation happens at runtime
            return v.lower().strip()


# Lakehouse configuration for Microsoft Fabric
class LakehouseConfig(BaseModel):
    """Configuration for Microsoft Fabric Lakehouse.

    This configuration is used to set the default lakehouse for notebook
    execution. It replaces the external lakehouse_config.json file approach.

    Attributes:
        name: Display name of the lakehouse.
        id: GUID identifier of the lakehouse.
        workspace_id: GUID of the workspace containing the lakehouse.
    """

    name: Optional[str] = Field(None, description="Lakehouse display name")
    id: Optional[str] = Field(None, description="Lakehouse GUID")
    workspace_id: Optional[str] = Field(None, description="Workspace GUID")

    def to_fabric_config(self) -> Dict[str, Any]:
        """Convert to Microsoft Fabric notebook configuration format.

        Returns:
            Dictionary suitable for %%configure magic in Fabric notebooks.
        """
        config: Dict[str, Any] = {}
        if self.name:
            config["name"] = self.name
        if self.id:
            config["id"] = self.id
        if self.workspace_id:
            config["workspaceId"] = self.workspace_id
        return config

    def is_configured(self) -> bool:
        """Check if any lakehouse settings are configured.

        Returns:
            True if at least one setting is provided.
        """
        return bool(self.name or self.id or self.workspace_id)


# Notebook generation settings
class NotebookSettings(BaseModel):
    """Settings for notebook generation.

    This configuration allows per-model customization of notebook behavior,
    replacing hardcoded model name checks with explicit configuration.

    Example YAML:
        model:
          name: my_model
          notebook_settings:
            legacy_time_parser: true
            disable_broadcast_join: true
            lakehouse:
              name: my_lakehouse
              id: "guid-here"

    Attributes:
        legacy_time_parser: Enable LEGACY time parser policy for date handling.
        disable_broadcast_join: Disable automatic broadcast joins for large tables.
        custom_spark_settings: Additional Spark configuration key-value pairs.
        lakehouse: Lakehouse configuration for this model.
        skip_optimize: Skip OPTIMIZE command after data load.
        skip_vacuum: Skip VACUUM command after data load.
        skip_dq_checks: Skip data quality checks.
        parallelism_enabled: Enable Delta table parallelism settings.
    """

    legacy_time_parser: bool = Field(
        default=False,
        description="Enable LEGACY time parser policy (SET spark.sql.legacy.timeParserPolicy = LEGACY)",
    )
    disable_broadcast_join: bool = Field(
        default=False,
        description="Disable automatic broadcast joins (spark.sql.autoBroadcastJoinThreshold = -1)",
    )
    custom_spark_settings: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional Spark configuration settings as key-value pairs",
    )
    lakehouse: Optional[LakehouseConfig] = Field(
        default=None, description="Lakehouse configuration for this model"
    )
    skip_optimize: bool = Field(default=False, description="Skip OPTIMIZE command after data load")
    skip_vacuum: bool = Field(default=False, description="Skip VACUUM command after data load")
    skip_dq_checks: bool = Field(default=False, description="Skip data quality checks")
    parallelism_enabled: Optional[bool] = Field(
        default=None,
        description="Enable Delta parallelism settings (defaults to True for bronze layer)",
    )


# Source Definition
class Source(BaseModel):
    """Source table or query definition."""

    base_table: str = Field(..., description="Base table or model name")
    alias: Optional[str] = None
    database: Optional[str] = None
    table_schema: Optional[str] = Field(None, description="Schema name")
    merge_keys: Optional[MergeConfig] = Field(
        None, description="Merge configuration for load operations"
    )
    load_strategy: Optional[str] = Field(
        None,
        description="Load strategy shorthand directly on source (e.g. load_scd2)",
    )
    scd_logical_key: List[str] = Field(
        default_factory=list,
        description="Logical key fields that uniquely identify a dimension record for SCD2",
    )
    scd_historical_fields: List[str] = Field(
        default_factory=list,
        description="Fields whose changes should be tracked as SCD2 historical records. Use ['All'] to track all non-framework fields.",
    )
    skip_historical: List[str] = Field(
        default_factory=list,
        description="Fields to exclude when scd_historical_fields is ['All']",
    )


# Transformations
class Transformations(BaseModel):
    """Transformation definitions."""

    inherit_columns: bool = Field(False, description="Inherit columns from parent")
    columns: List[Column] = Field(default_factory=list)

    def merge_with(self, other: "Transformations") -> "Transformations":
        adjusted_parent_columns = []
        for col in self.columns:
            expression = (
                col.expression if (col.action == ColumnAction.ADD and col.expression) else col.name
            )
            adjusted_parent_columns.append(
                Column(
                    name=col.name,
                    expression=expression,
                    data_type=col.data_type,
                    description=col.description,
                    nullable=col.nullable,
                    action=col.action,
                    new_name=col.new_name,
                )
            )
        merged_columns = adjusted_parent_columns.copy()

        for col in other.columns:
            if col.action == ColumnAction.ADD:
                merged_columns.append(col)
            elif col.action == ColumnAction.REMOVE:
                merged_columns = [c for c in merged_columns if c.name != col.name]
            elif col.action in [ColumnAction.TRANSFORM, ColumnAction.OVERRIDE]:
                for i, existing in enumerate(merged_columns):
                    if existing.name == col.name:
                        merged_columns[i] = col
                        break
                else:
                    merged_columns.append(col)
            elif col.action == ColumnAction.RENAME:
                for i, existing in enumerate(merged_columns):
                    if existing.name == col.name:
                        existing.name = col.new_name or col.name
                        break
            else:
                for i, existing in enumerate(merged_columns):
                    if existing.name == col.name:
                        merged_columns[i] = col
                        break
                else:
                    merged_columns.append(col)

        return Transformations(
            inherit_columns=other.inherit_columns or self.inherit_columns, columns=merged_columns
        )


# Filter Conditions
class FilterCondition(BaseModel):
    """Filter condition with ID for modification."""

    id: str = Field(..., description="Unique filter identifier")
    condition: str = Field(..., description="SQL WHERE condition")
    operation: Optional[FilterOperation] = Field(
        FilterOperation.ADD, description="How to apply this filter"
    )
    description: Optional[str] = None


class Filters(BaseModel):
    """Filter definitions."""

    where_conditions: List[FilterCondition] = Field(default_factory=list)

    def merge_with(self, other: "Filters") -> "Filters":
        merged_conditions = {}
        condition_texts = set()
        for cond in self.where_conditions:
            merged_conditions[cond.id] = cond
            condition_texts.add(cond.condition.strip().upper())
        for cond in other.where_conditions:
            normalized_condition = cond.condition.strip().upper()
            if cond.operation == FilterOperation.REPLACE:
                if cond.id in merged_conditions:
                    old_condition = merged_conditions[cond.id].condition.strip().upper()
                    condition_texts.discard(old_condition)
                merged_conditions[cond.id] = cond
                condition_texts.add(normalized_condition)
            elif cond.operation == FilterOperation.ADD:
                if cond.id not in merged_conditions and normalized_condition not in condition_texts:
                    merged_conditions[cond.id] = cond
                    condition_texts.add(normalized_condition)
            elif cond.operation == FilterOperation.APPEND:
                if cond.id in merged_conditions:
                    existing = merged_conditions[cond.id]
                    existing.condition = f"({existing.condition}) AND ({cond.condition})"
                elif normalized_condition not in condition_texts:
                    merged_conditions[cond.id] = cond
                    condition_texts.add(normalized_condition)
        return Filters(where_conditions=list(merged_conditions.values()))


# Aggregations
class Aggregations(BaseModel):
    """Aggregation definitions."""

    group_by: List[str] = Field(default_factory=list)
    having: List[str] = Field(default_factory=list)


# CTE Reference
class CTEReference(BaseModel):
    """Reference to a CTE."""

    name: str = Field(..., description="CTE model name")
    alias: str = Field(..., description="Alias in query")


# ---- NEW: relationships/audits/optimization models ----
class ForeignKey(BaseModel):
    local_column: str
    references_table: str
    references_column: str
    relationship_type: RelationshipType
    join_type: JoinType
    alias: Optional[str] = None
    on_expression: Optional[str] = None


class JoinDefinition(BaseModel):
    """Direct join definition for relationships.joins syntax."""
    join_type: JoinType
    ref_table: str
    ref_alias: str
    on_clause: str


class RelationshipConfig(BaseModel):
    foreign_keys: List[ForeignKey] = Field(default_factory=list)
    joins: List[JoinDefinition] = Field(default_factory=list)


class AuditRule(BaseModel):
    type: AuditType
    columns: List[str]
    values: Optional[List[str]] = None  # for ACCEPTED_VALUES


class AuditConfig(BaseModel):
    audits: List[AuditRule] = Field(default_factory=list)


class IndexConfig(BaseModel):
    columns: List[str]
    type: str


class OptimizationConfig(BaseModel):
    partitioned_by: List[str] = Field(default_factory=list)
    clustered_by: List[str] = Field(default_factory=list)
    indexes: List[IndexConfig] = Field(default_factory=list)


# Main Model
class Model(BaseModel):
    """Main model definition.

    This is the primary configuration model parsed from YAML files.
    It supports inheritance, transformation definitions, and various
    output configurations.

    Attributes:
        name: Unique identifier for the model.
        description: Human-readable description of the model's purpose.
        layer: Data layer (bronze, silver, gold, or custom).
        kind: Output type (VIEW, TABLE, or CTE).
        extends: Parent model name for inheritance.
        inherits_from: Alternative to extends for inheritance.
        notebook_settings: Configuration for notebook generation.
        metadata: Additional metadata and conditional application rules.
        source: Source table/query configuration.
        transformations: Column transformations to apply.
        filters: WHERE clause conditions.
        aggregations: GROUP BY and HAVING clauses.
        ctes: Common Table Expression references.
        audits: Data quality audit rules.
        relationships: Foreign key and join definitions.
        optimization: Partitioning and indexing configuration.
        derived_sql: Raw SQL override for complex transformations.
    """

    name: str = Field(..., description="Model name")
    description: Optional[str] = None
    layer: Optional[str] = None
    kind: ModelKind = Field(ModelKind.VIEW, description="Output type")
    extends: Optional[str] = Field(None, description="Parent model to extend")
    inherits_from: Optional[str] = Field(None, description="Model to inherit from")
    customer: Optional[str] = Field(None, description="Customer identifier")

    # Notebook generation settings (replaces hardcoded model name checks)
    notebook_settings: NotebookSettings = Field(
        default_factory=NotebookSettings, description="Settings for notebook generation"
    )

    metadata: Optional[Metadata] = None
    source: Optional[Source] = None
    transformations: Transformations = Field(default_factory=Transformations)
    filters: Filters = Field(default_factory=Filters)
    aggregations: Optional[Aggregations] = None
    ctes: List[CTEReference] = Field(default_factory=list)

    # Data quality and optimization
    audits: AuditConfig = Field(default_factory=AuditConfig)
    relationships: RelationshipConfig = Field(default_factory=RelationshipConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    derived_sql: Optional[str] = None

    def merge_with(self, other: "Model") -> "Model":
        """Merge this model with another, with the other taking precedence.

        Args:
            other: Model to merge with (takes precedence for non-list fields).

        Returns:
            New Model instance with merged configuration.
        """
        # Merge notebook_settings - other takes precedence for set values
        merged_notebook_settings = NotebookSettings(
            legacy_time_parser=(
                other.notebook_settings.legacy_time_parser
                if other.notebook_settings.legacy_time_parser
                else self.notebook_settings.legacy_time_parser
            ),
            disable_broadcast_join=(
                other.notebook_settings.disable_broadcast_join
                if other.notebook_settings.disable_broadcast_join
                else self.notebook_settings.disable_broadcast_join
            ),
            custom_spark_settings={
                **self.notebook_settings.custom_spark_settings,
                **other.notebook_settings.custom_spark_settings,
            },
            lakehouse=other.notebook_settings.lakehouse or self.notebook_settings.lakehouse,
            skip_optimize=(
                other.notebook_settings.skip_optimize
                if other.notebook_settings.skip_optimize
                else self.notebook_settings.skip_optimize
            ),
            skip_vacuum=(
                other.notebook_settings.skip_vacuum
                if other.notebook_settings.skip_vacuum
                else self.notebook_settings.skip_vacuum
            ),
            skip_dq_checks=(
                other.notebook_settings.skip_dq_checks
                if other.notebook_settings.skip_dq_checks
                else self.notebook_settings.skip_dq_checks
            ),
            parallelism_enabled=(
                other.notebook_settings.parallelism_enabled
                if other.notebook_settings.parallelism_enabled is not None
                else self.notebook_settings.parallelism_enabled
            ),
        )

        return Model(
            name=self.name,
            description=other.description or self.description,
            layer=other.layer or self.layer,
            kind=other.kind or self.kind,
            extends=other.extends or self.extends,
            inherits_from=other.inherits_from or self.inherits_from,
            notebook_settings=merged_notebook_settings,
            metadata=other.metadata or self.metadata,
            source=other.source or self.source,
            transformations=self.transformations.merge_with(other.transformations),
            filters=self.filters.merge_with(other.filters),
            audits=other.audits or self.audits,
            relationships=other.relationships or self.relationships,
            optimization=other.optimization or self.optimization,
            aggregations=other.aggregations or self.aggregations,
            ctes=self.ctes + [cte for cte in other.ctes if cte not in self.ctes],
        )


# YAML File Model
class YAMLConfig(BaseModel):
    """Complete YAML configuration file."""

    model: Model
    metadata: Optional[Metadata] = None

    @model_validator(mode="after")
    def copy_metadata(self):
        if self.metadata and not self.model.metadata:
            self.model.metadata = self.metadata
        return self


# Dynamic Functions
class DynamicFunction(BaseModel):
    """Dynamic function definition."""

    name: str = Field(..., description="Function name with @ prefix")
    description: Optional[str] = None
    parameters: List[str] = Field(default_factory=list)
    sql_replacement: str = Field(..., description="SQL to replace function with")

    @field_validator("name")
    def validate_name(cls, v):
        if not v.startswith("@"):
            v = f"@{v}"
        return v


class DynamicFunctionsConfig(BaseModel):
    """Dynamic functions configuration."""

    core: List[DynamicFunction] = Field(default_factory=list)
    custom: Optional[Dict[str, List[DynamicFunction]]] = None


# ---- NEW: JoinSpec used in resolved model ----
class JoinSpec(BaseModel):
    join_type: JoinType
    ref_table: str
    ref_alias: str
    on_clause: str


# Resolved Model (after all processing)
class ResolvedModel(BaseModel):
    """Model after resolution of inheritance, functions, etc.

    This is the fully resolved model ready for SQL/notebook generation.
    All inheritance has been applied, functions expanded, and references resolved.

    Attributes:
        name: Final model name.
        kind: Output type (VIEW, TABLE, CTE).
        layer: Data layer name.
        columns: Resolved column definitions.
        source_table: Fully qualified source table name.
        cte_definitions: CTE SQL definitions keyed by alias.
        where_clause: Resolved WHERE clause.
        group_by_clause: GROUP BY columns.
        having_clause: HAVING conditions.
        order_by_clause: ORDER BY columns.
        description: Model description.
        base_alias: Alias for the base table (default "T").
        joins: JOIN specifications.
        audits: Data quality audit configuration.
        relationships: Relationship configuration.
        optimization: Partitioning and indexing configuration.
        derived_sql: Raw SQL override.
        merge_config: Merge/load operation configuration.
        notebook_settings: Notebook generation settings.
    """

    name: str
    kind: ModelKind
    layer: Optional[str]
    columns: List[Column]
    source_table: str
    cte_definitions: Dict[str, str] = Field(default_factory=dict)
    where_clause: Optional[str] = None
    group_by_clause: Optional[List[str]] = None
    having_clause: Optional[List[str]] = None
    order_by_clause: Optional[List[str]] = None

    description: Optional[str] = None
    base_alias: str = Field(default="T")
    joins: List[JoinSpec] = Field(default_factory=list)
    audits: AuditConfig = Field(default_factory=AuditConfig)
    relationships: RelationshipConfig = Field(default_factory=RelationshipConfig)
    optimization: OptimizationConfig = Field(default_factory=OptimizationConfig)
    filters: "Filters" = Field(default_factory=lambda: Filters())
    derived_sql: Optional[str] = None
    merge_config: Optional[MergeConfig] = Field(None, description="Merge/load configuration")
    notebook_settings: NotebookSettings = Field(
        default_factory=NotebookSettings, description="Notebook generation settings"
    )
    customer: Optional[str] = Field(None, description="Customer identifier from model YAML")
    scd_logical_key: List[str] = Field(
        default_factory=list,
        description="Logical key fields for SCD2 identification",
    )
    scd_historical_fields: List[str] = Field(
        default_factory=list,
        description="Fields tracked for SCD2 historical changes",
    )
    skip_historical: List[str] = Field(
        default_factory=list,
        description="Fields excluded from All-mode SCD2 historical tracking",
    )

    def to_sql(self) -> str:
        """Generate SQL for this model (placeholder for future implementation)."""
        raise NotImplementedError("SQL generation not yet implemented")


# Validation Results
class ValidationError(BaseModel):
    """Validation error detail."""

    model: str
    field: Optional[str] = None
    message: str
    suggestion: Optional[str] = None
    severity: Literal["error", "warning"] = "error"

    def __str__(self) -> str:
        icon = "❌" if self.severity == "error" else "⚠️"
        error = f"{icon} Model '{self.model}'"
        if self.field:
            error += f", field '{self.field}'"
        error += f": {self.message}"
        if self.suggestion:
            error += f"\n💡 Suggestion: {self.suggestion}"
        return error


class ValidationResult(BaseModel):
    """Validation result container."""

    is_valid: bool
    errors: List[ValidationError] = Field(default_factory=list)
    warnings: List[ValidationError] = Field(default_factory=list)

    def add_error(
        self,
        model: str,
        message: str,
        field: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        self.errors.append(
            ValidationError(
                model=model, field=field, message=message, suggestion=suggestion, severity="error"
            )
        )
        self.is_valid = False

    def add_warning(
        self,
        model: str,
        message: str,
        field: Optional[str] = None,
        suggestion: Optional[str] = None,
    ):
        self.warnings.append(
            ValidationError(
                model=model, field=field, message=message, suggestion=suggestion, severity="warning"
            )
        )
