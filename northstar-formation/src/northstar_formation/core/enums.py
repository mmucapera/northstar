"""Enumeration classes for Northstar Formation.

This module provides type-safe enumerations for load strategies, data layers,
and other configurable values. Using enums instead of magic strings improves
code quality, IDE support, and reduces runtime errors.
"""

from enum import Enum
from typing import Set


class LoadStrategy(str, Enum):
    """Load strategies for data ingestion and transformation.

    These strategies determine how data is merged, inserted, or replaced
    in target tables during ETL operations.

    Attributes:
        BRONZE_TO_SILVER: Standard bronze to silver transformation with deduplication.
        BRONZE_TO_SILVER_LATEST: Bronze to silver with latest record per key.
        DELETE_INSERT: Delete matching records then insert new ones.
        REPLACE_LATEST: Truncate and reload entire table.
        TRUNCATE_INSERT: Alias for REPLACE_LATEST for backward compatibility.
        SILVER_TO_GOLD: Silver to gold layer transformation.
        GOLD: Direct gold layer load.
        SCD2: Slowly changing dimension type 2.
        SCD2_DIM: SCD2 specifically for dimension tables.
        MERGE: Standard MERGE operation.
        APPEND: Append-only inserts.
    """

    BRONZE_TO_SILVER = "bronze_to_silver"
    BRONZE_TO_SILVER_LATEST = "bronze_to_silver_latest"
    DELETE_INSERT = "delete_insert"
    REPLACE_LATEST = "replace_latest"
    TRUNCATE_INSERT = "truncate_insert"
    SILVER_TO_GOLD = "silver_to_gold"
    GOLD = "gold"
    SCD2 = "scd2"
    SCD2_DIM = "scd2_dim"
    LOAD_SCD2 = "load_scd2"
    MERGE = "merge"
    APPEND = "append"

    @classmethod
    def get_scd2_strategies(cls) -> Set["LoadStrategy"]:
        """Return the set of SCD2-related strategies.

        Returns:
            Set of LoadStrategy values that implement SCD2 behavior.
        """
        return {cls.SCD2, cls.SCD2_DIM, cls.LOAD_SCD2}

    @classmethod
    def get_merge_strategies(cls) -> Set["LoadStrategy"]:
        """Return strategies that use MERGE operations.

        Returns:
            Set of LoadStrategy values that perform MERGE operations.
        """
        return {
            cls.BRONZE_TO_SILVER,
            cls.BRONZE_TO_SILVER_LATEST,
            cls.MERGE,
        }

    @classmethod
    def get_replace_strategies(cls) -> Set["LoadStrategy"]:
        """Return strategies that replace/truncate data.

        Returns:
            Set of LoadStrategy values that truncate before loading.
        """
        return {
            cls.REPLACE_LATEST,
            cls.TRUNCATE_INSERT,
            cls.SILVER_TO_GOLD,
            cls.GOLD,
        }

    @classmethod
    def from_string(cls, value: str) -> "LoadStrategy":
        """Convert a string to LoadStrategy, handling aliases.

        Args:
            value: Strategy name as string.

        Returns:
            Corresponding LoadStrategy enum value.

        Raises:
            ValueError: If the strategy name is not recognized.
        """
        normalized = value.lower().strip()

        # Handle common aliases
        aliases = {
            "bronze_to_silver": cls.BRONZE_TO_SILVER_LATEST,
            "snapshot": cls.REPLACE_LATEST,
            "full_refresh": cls.REPLACE_LATEST,
        }

        if normalized in aliases:
            return aliases[normalized]

        try:
            return cls(normalized)
        except ValueError:
            valid = ", ".join(s.value for s in cls)
            raise ValueError(f"Unknown load strategy: '{value}'. Valid strategies: {valid}")


class DataLayer(str, Enum):
    """Standard data layer names for lakehouse architecture.

    These represent the common medallion architecture layers,
    but the system supports arbitrary layer names as strings.

    Attributes:
        BRONZE: Raw data ingestion layer.
        SILVER: Cleansed and conformed data layer.
        GOLD: Business-level aggregated data layer.
        RAW: Alternative name for bronze/landing zone.
        STAGING: Intermediate processing layer.
        CURATED: Alternative name for gold/presentation layer.
    """

    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    RAW = "raw"
    STAGING = "staging"
    CURATED = "curated"

    @classmethod
    def is_standard_layer(cls, layer: str) -> bool:
        """Check if a layer name is a standard layer.

        Args:
            layer: Layer name to check.

        Returns:
            True if the layer is a standard DataLayer value.
        """
        try:
            cls(layer.lower())
            return True
        except ValueError:
            return False


class OutputFormat(str, Enum):
    """Output format options for the transform command.

    Attributes:
        SQL: Generate SQL files only.
        NOTEBOOK: Generate Fabric notebooks only.
        ALL: Generate both SQL and notebooks.
    """

    SQL = "sql"
    NOTEBOOK = "notebook"
    ALL = "all"


class SparkSetting(str, Enum):
    """Common Spark configuration settings.

    These settings can be enabled via notebook_settings in model YAML.

    Attributes:
        LEGACY_TIME_PARSER: Enable legacy time parser policy.
        DISABLE_BROADCAST_JOIN: Disable automatic broadcast joins.
        ADAPTIVE_EXECUTION: Enable adaptive query execution.
    """

    LEGACY_TIME_PARSER = "legacy_time_parser"
    DISABLE_BROADCAST_JOIN = "disable_broadcast_join"
    ADAPTIVE_EXECUTION = "adaptive_execution"
