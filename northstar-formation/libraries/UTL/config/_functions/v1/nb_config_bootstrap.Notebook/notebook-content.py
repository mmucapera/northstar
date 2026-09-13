# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_bootstrap
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: imports, spark conf, logger, BatchTracker, PackageTracker
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# # Layered Config Framework
# > Shared utility notebook for all data loading strategies, schema management, and monitoring.  
# > Loaded via `%run nb_utils_config` from bronze, silver, and gold layer notebooks.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Imports & Configuration
# Session-level Spark configuration, logging setup, and dependency initialization.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


# FABRIC FRAMEWORK: MERGE + DQ + OPTIMIZE
#%run /nb_utils_config

from pyexpat import model
import uuid
import time
import time as _time
import logging
import json
import pyarrow.parquet as pq
import pyarrow as pa
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from pyspark.sql.functions import col, lit, current_timestamp
from notebookutils import mssparkutils
from pyspark.sql.types import StructType, StructField, StringType
from pyspark.sql import DataFrame, SparkSession
from datetime import datetime
from functools import reduce
from delta.tables import DeltaTable
spark = SparkSession.builder.getOrCreate()
from pyspark.sql.functions import udf, col, expr
from pyspark.sql.types import IntegerType, StringType
from pyspark.sql.types import LongType
from pyspark.sql.types import TimestampType
import re





# PERFORMANCE OPTIMIZATION: Solutions 2 & 3
spark.conf.set("spark.sql.legacy.timeParserPolicy", "LEGACY")

# Solution 2: Enable broadcast joins for small dimensions (default 10MB is too small)
spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "104857600")  # 100MB threshold

# Solution 2: Enable vectorized Parquet reading for 30-50% faster I/O
spark.conf.set("spark.sql.parquet.enableVectorizedReader", "true")

# Fabric V-Order — 25-50% read acceleration on Delta files. Default on Fabric
# Runtime 1.2+, explicit here so older runtimes and any partial upgrades still get it.
spark.conf.set("spark.sql.parquet.vorder.enabled", "true")

# Dynamic partition overwrite — load strategies that call .mode("overwrite")
# on partitioned tables replace only the affected partitions. Writers that
# legitimately need a full-table schema-changing overwrite (CTAS, repair)
# must override this per-operation via .option("partitionOverwriteMode",
# "static") alongside .option("overwriteSchema", "true") — Delta 1.2+ hard-
# errors on that combo when the session default is dynamic.
spark.conf.set("spark.sql.sources.partitionOverwriteMode", "dynamic")

# Performance optimizations
spark.conf.set("spark.sql.adaptive.enabled", "true")  # Adaptive query optimization
spark.conf.set("spark.sql.adaptive.coalescePartitions.enabled", "true")  # Auto-coalesce partitions
spark.conf.set("spark.sql.parquet.compression.codec", "snappy")  # Better compression
spark.conf.set("spark.sql.caseSensitive", "false")
spark.conf.set("spark.databricks.delta.isolationLevel","SnapshotIsolation")
spark.conf.set("spark.hadoop.fs.azure.io.jackson.maxStringLength", "40000000")

# ============================================================
# INGESTION VERSION — increment with each framework release
# ============================================================
INGESTION_VERSION = "1.0.0"
USE_ORCHESTRATOR = 1

# ============================================================
# DEV MODE — bypass "no source files found" failures.
# When enabled, check_for_model_files logs a warning and returns instead of
# stopping the notebook, so bronze DDL still creates an empty table and the
# rest of the pipeline can run against a valid (empty) schema.
# Toggle at runtime without editing this notebook:
spark.conf.set("insights.dev_mode.allow_missing_source", "true")   # enable
#   spark.conf.set("insights.dev_mode.allow_missing_source", "false")  # disable
# The Spark conf overrides the module-level constant below.
# ============================================================
DEV_MODE_ALLOW_MISSING_SOURCE = 1


def _dev_mode_allow_missing_source() -> bool:
    try:
        override = str(spark.conf.get("insights.dev_mode.allow_missing_source", "")).strip().lower()
    except Exception:
        override = ""
    if override in ("true", "1", "yes", "on"):
        return True
    if override in ("false", "0", "no", "off"):
        return False
    return bool(DEV_MODE_ALLOW_MISSING_SOURCE)


# ============================================================
# Delta table auto-optimize helper.
# Idempotently sets the properties that make repeated appends / merges cheap:
#   * optimizeWrite  — combines small partitions into ~128MB writes
#   * autoCompact    — background compaction of small files after commits
#   * enableDeletionVectors — orders-of-magnitude faster DELETE for fact tables
#   * dataSkippingNumIndexedCols — stats on first N columns for min/max skipping
# Called from ensure_table_exists so every framework target gets these properties.
# ============================================================
def _ensure_delta_autoopt(target: str) -> None:
    try:
        spark.sql(f"""
            ALTER TABLE {target}
            SET TBLPROPERTIES (
                'delta.autoOptimize.optimizeWrite'      = 'true',
                'delta.autoOptimize.autoCompact'        = 'true',
                'delta.enableDeletionVectors'           = 'true',
                'delta.dataSkippingNumIndexedCols'      = '10'
            )
        """)
    except Exception as _e:
        try:
            logger.info(f"[AUTOOPT] Could not set autoOptimize on {target} (non-blocking): {_e}")
        except Exception:
            pass

try:
    logger
except NameError:
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("fabric.framework")

# Suppress noisy Fabric token library INFO messages
logging.getLogger("trident_token_library_wrapper").setLevel(logging.WARNING)

# Global FabricLogger instance for unified monitoring
# Initialize lazily to avoid errors when FabricLogger is not available
_fabric_logger = None
_fabric_logger_init_attempted = False

def get_fabric_logger():
    """Get or create the global FabricLogger instance for unified monitoring"""
    global _fabric_logger, _fabric_logger_init_attempted
    
    if _fabric_logger is None and not _fabric_logger_init_attempted:
        try:
            # Import FabricLogger - ensure nb_utils_logging is run first
            from nb_utils_logging import FabricLogger
            _fabric_logger = FabricLogger(project_name="CUSTOMER0")
        except Exception as e:
            logger.warning(f"[FABRIC_LOGGER] Could not initialize FabricLogger: {e}")
            logger.warning("[FABRIC_LOGGER] Partial load logging will be skipped")
            _fabric_logger_init_attempted = True
        else:
            _fabric_logger_init_attempted = True
    
    return _fabric_logger


# ============================================================
# BATCH TRACKER - Lifecycle tracking across layers
# ============================================================
class BatchTracker:
    def __init__(
        self,
        entity_name: str,
        source_path: str = None,
        source_files: str = None,
        file_count: int = 0,
        notebook_name: str = None,
        batchid: str = None,
    ):

        self.entity_name = entity_name
        self.source_path = source_path
        self.source_files = source_files
        self.file_count = file_count
        self.notebook_name = notebook_name or self._get_notebook_name()
        self.batchid = batchid
        self.start_time = None
        self.layer_start_times = {}
        self._fabric_logger = None
        
    def _get_notebook_name(self) -> str:
        """Get current notebook name from context"""
        try:
            return mssparkutils.runtime.context.get("notebookName", "unknown")
        except:
            return "unknown"
    
    def _get_logger(self):
        """Lazy load the FabricLogger"""
        if self._fabric_logger is None:
            self._fabric_logger = get_fabric_logger()
        return self._fabric_logger
    
    def start(self) -> str:
        """
        Start tracking a new batch.
        
        Returns:
        --------
        str : The generated batch_id
        """
        import time as _time
        self.start_time = _time.time()
        
        fabric_logger = self._get_logger()
        if fabric_logger is None:
            # Generate batch_id even if logger not available
            import uuid
            date_str = datetime.now().strftime("%Y%m%d")
            clean_entity = self.entity_name.split(".")[-1] if "." in self.entity_name else self.entity_name
            self.batchid = f"{date_str}_{clean_entity}_{str(uuid.uuid4())[:8]}"
            logger.warning(f"[BATCH_TRACKER] FabricLogger not available. Batch ID: {self.batchid}")
            return self.batchid
        
        # Generate batch_id
        self.batchid = fabric_logger.generate_batch_id(self.entity_name)
        
        # Start batch in FabricLogger
        fabric_logger.start_batch(
            batchid=self.batchid,
            entity_name=self.entity_name,
            source_path=self.source_path,
            source_files=self.source_files,
            file_count=self.file_count,
            notebook_name=self.notebook_name,
        )
        
        logger.info(f"[BATCH_TRACKER] Started batch: {self.batchid}")
        return self.batchid
    
    def start_layer(self, layer: str, target_table: str = None):

        import time as _time
        self.layer_start_times[layer.lower()] = _time.time()
        
        fabric_logger = self._get_logger()
        if fabric_logger:
            fabric_logger.update_batch_layer(
                batchid=self.batchid,
                layer=layer,
                status="IN_PROGRESS",
                target_table=target_table,
                start_time=datetime.now(),
            )
        
        logger.info(f"[BATCH_TRACKER] Started {layer.upper()} layer for batch: {self.batchid}")
    
    def complete_layer(
        self,
        layer: str,
        rows: int = None,
        target_table: str = None,
    ):

        import time as _time
        
        layer_lower = layer.lower()
        execution_time = None
        
        if layer_lower in self.layer_start_times:
            execution_time = _time.time() - self.layer_start_times[layer_lower]
        
        fabric_logger = self._get_logger()
        if fabric_logger:
            fabric_logger.update_batch_layer(
                batchid=self.batchid,
                layer=layer,
                status="SUCCESS",
                target_table=target_table,
                rows=rows,
                execution_time=execution_time,
                end_time=datetime.now(),
            )
        
        logger.info(f"[BATCH_TRACKER] Completed {layer.upper()} layer: {rows:,} rows in {execution_time:.2f}s" if rows and execution_time else f"[BATCH_TRACKER] Completed {layer.upper()} layer")
    
    def fail_layer(self, layer: str, error_message: str, target_table: str = None):

        fabric_logger = self._get_logger()
        if fabric_logger:
            fabric_logger.update_batch_layer(
                batchid=self.batchid,
                layer=layer,
                status="FAILED",
                target_table=target_table,
            )
            fabric_logger.fail_batch(
                batchid=self.batchid,
                layer=layer,
                error_message=error_message,
            )
        
        logger.error(f"[BATCH_TRACKER] Failed {layer.upper()} layer: {error_message[:100]}")
    
    def complete(self):
        """Mark the entire batch as completed successfully."""
        import time as _time
        
        total_time = None
        if self.start_time:
            total_time = _time.time() - self.start_time
        
        fabric_logger = self._get_logger()
        if fabric_logger:
            fabric_logger.complete_batch(
                batchid=self.batchid,
                total_execution_time=total_time,
            )
        
        logger.info(f"[BATCH_TRACKER] Batch completed: {self.batchid} in {total_time:.2f}s" if total_time else f"[BATCH_TRACKER] Batch completed: {self.batchid}")
    
    def fail(self, layer: str, error_message: str):
        """Mark the entire batch as failed."""
        fabric_logger = self._get_logger()
        if fabric_logger:
            fabric_logger.fail_batch(
                batchid=self.batchid,
                layer=layer,
                error_message=error_message,
            )
        
        logger.error(f"[BATCH_TRACKER] Batch failed: {self.batchid} at {layer.upper()}")
    
    @property
    def current_batchid(self) -> str:
        """Get the current batch ID"""
        return self.batchid


# Global batch tracker for use across notebook cells
_current_batch_tracker = None

def get_batch_tracker() -> BatchTracker:
    """Get the current batch tracker instance"""
    global _current_batch_tracker
    return _current_batch_tracker

def set_batch_tracker(tracker: BatchTracker):
    """Set the current batch tracker instance"""
    global _current_batch_tracker
    _current_batch_tracker = tracker

def create_batch_tracker(
    entity_name: str,
    source_path: str = None,
    source_files: str = None,
    file_count: int = 0,
    auto_start: bool = True,
) -> BatchTracker:

    global _current_batch_tracker
    
    tracker = BatchTracker(
        entity_name=entity_name,
        source_path=source_path,
        source_files=source_files,
        file_count=file_count,
    )
    
    if auto_start:
        tracker.start()
    
    _current_batch_tracker = tracker
    return tracker


# ============================================================
# PACKAGE TRACKER - Folder-level lifecycle tracking
# ============================================================
class PackageTracker:
    
    def __init__(
        self,
        date_path: str = None,
        domain_filter: str = None,
        notebook_name: str = None,
    ):

        self.date_path = date_path
        self.domain_filter = domain_filter
        self.notebook_name = notebook_name or self._get_notebook_name()
        
        self.current_package_id = None
        self.current_package_name = None
        self.package_start_time = None
        self.layer_start_times = {}
        self._fabric_logger = None
        self._discovered_packages = []
        
    def _get_notebook_name(self) -> str:
        """Get current notebook name from context"""
        try:
            return mssparkutils.runtime.context.get("notebookName", "unknown")
        except:
            return "unknown"
    
    def _get_logger(self):
        """Lazy load the FabricLogger"""
        if self._fabric_logger is None:
            self._fabric_logger = get_fabric_logger()
        return self._fabric_logger
    
    def discover_packages(self, date_path: str = None, domain_filter: str = None) -> list:

        use_date_path = date_path or self.date_path
        use_domain = domain_filter or self.domain_filter
        
        fabric_logger = self._get_logger()
        if fabric_logger is None:
            logger.error("[PACKAGE_TRACKER] FabricLogger not available. Cannot discover packages.")
            return []
        
        self._discovered_packages = fabric_logger.discover_packages(use_date_path, use_domain)
        return self._discovered_packages
    
    def get_discovered_packages(self) -> list:
        """Get the list of discovered packages"""
        return self._discovered_packages
    
    def start_package(
        self,
        package_name: str,
        package_path: str,
        batchid: int = None,


    ) -> str:

        import time as _time
        self.package_start_time = _time.time()
        self.current_package_name = package_name
        self.layer_start_times = {}
        
        # Extract folder name from package_path for consistent manifest_package identifier
        if package_path and "/" in package_path:
            manifest_package = package_path.rstrip("/").split("/")[-1]
        else:
            manifest_package = package_name
        
        fabric_logger = self._get_logger()
        if fabric_logger is None:
            # Use manifest_package as package_id for consistency (no UUID)
            self.current_package_id = manifest_package
            logger.warning(f"[PACKAGE_TRACKER] FabricLogger not available. Package ID: {self.current_package_id}")
            return self.current_package_id
        
        self.current_package_id = fabric_logger.start_package(
            manifest_package=manifest_package,
            batchid=batchid,
        )
        
        logger.info(f"[PACKAGE_TRACKER] Started package: {package_name}")
        return self.current_package_id
    
    def start_layer(self, layer: str):

        import time as _time
        self.layer_start_times[layer.lower()] = _time.time()
        
        fabric_logger = self._get_logger()
        if fabric_logger and self.current_package_id:
            fabric_logger.update_package_layer(
                manifest_package=self.current_package_id,
                layer=layer,
                status="IN_PROGRESS",
                start_time=datetime.now(),
            )
        
        logger.info(f"[PACKAGE_TRACKER] Started {layer.upper()} for package: {self.current_package_name}")
    
    def complete_layer(
        self,
        layer: str,
        entities_loaded: int = None,
        rows: int = None,
    ):
        import time as _time
        
        layer_lower = layer.lower()
        execution_time = None
        
        if layer_lower in self.layer_start_times:
            execution_time = _time.time() - self.layer_start_times[layer_lower]
        
        fabric_logger = self._get_logger()
        if fabric_logger and self.current_package_id:
            fabric_logger.update_package_layer(
                manifest_package=self.current_package_id,
                layer=layer,
                status="SUCCESS",
                end_time=datetime.now(),
            )
        
        log_msg = f"[PACKAGE_TRACKER] Completed {layer.upper()}"
        if entities_loaded and rows and execution_time:
            log_msg += f": {entities_loaded} entities, {rows:,} rows in {execution_time:.2f}s"
        logger.info(log_msg)
    
    def fail_layer(self, layer: str, error_message: str, error_entity: str = None):
        fabric_logger = self._get_logger()
        if fabric_logger and self.current_package_id:
            fabric_logger.fail_package(
                manifest_package=self.current_package_id,
                layer=layer,
                error_message=error_message,
                error_entity=error_entity,
            )
        
        logger.error(f"[PACKAGE_TRACKER] Failed {layer.upper()}: {error_message[:100]}")
    
    def complete_package(self):
        """Mark the current package as completed successfully."""
        import time as _time
        
        total_time = None
        if self.package_start_time:
            total_time = _time.time() - self.package_start_time
        
        fabric_logger = self._get_logger()
        if fabric_logger and self.current_package_id:
            fabric_logger.complete_package(
                manifest_package=self.current_package_id,
                total_execution_time=total_time,
            )
        
        log_msg = f"[PACKAGE_TRACKER] Completed package: {self.current_package_name}"
        if total_time:
            log_msg += f" in {total_time:.2f}s"
        logger.info(log_msg)
        
        # Reset for next package
        prev_id = self.current_package_id
        self.current_package_id = None
        self.current_package_name = None
        self.package_start_time = None
        self.layer_start_times = {}
        
        return prev_id
    
    def fail_package(self, layer: str, error_message: str, error_entity: str = None):
        """Mark the current package as failed."""
        fabric_logger = self._get_logger()
        if fabric_logger and self.current_package_id:
            fabric_logger.fail_package(
                package_id=self.current_package_id,
                layer=layer,
                error_message=error_message,
                error_entity=error_entity,
            )
        
        logger.error(f"[PACKAGE_TRACKER] Package failed: {self.current_package_name} at {layer.upper()}")
    
    @property
    def package_id(self) -> str:
        """Get the current package ID"""
        return self.current_package_id
    
    @property
    def package_name(self) -> str:
        """Get the current package name"""
        return self.current_package_name


# Global package tracker for use across notebook cells
_current_package_tracker = None

def get_package_tracker() -> PackageTracker:
    """Get the current package tracker instance"""
    global _current_package_tracker
    return _current_package_tracker

def set_package_tracker(tracker: PackageTracker):
    """Set the current package tracker instance"""
    global _current_package_tracker
    _current_package_tracker = tracker

def create_package_tracker(
    date_path: str,
    domain_filter: str = None,
    auto_discover: bool = True,
) -> PackageTracker:
    global _current_package_tracker
    
    tracker = PackageTracker(
        date_path=date_path,
        domain_filter=domain_filter,
    )
    
    if auto_discover:
        tracker.discover_packages()
    
    _current_package_tracker = tracker
    return tracker

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_bootstrap")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
