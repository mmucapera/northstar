# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
# META }

# MARKDOWN ********************

# ## Imports

# CELL ********************

# nb_utils_logging.py
# Microsoft Fabric Logging Framework - Version 3.4.3

import getpass
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Union
import logging
# import sempy.fabric as sempy_labs
from pyspark.sql import functions as F
from pyspark.sql.types import LongType, StringType


from pyspark.sql import SparkSession  # noqa: E402
from pyspark.sql.functions import (  # noqa: E402
    col,
    current_timestamp,
    date_format,
    dayofmonth,
    dayofweek,
    lit,
    month,
    quarter,
    weekofyear,
    year,
)
from pyspark.sql.types import (  # noqa: E402
    BooleanType,
    DecimalType,
    IntegerType,
    LongType,
    StringType,
    StructField,
    StructType,
    TimestampType,
)
from sempy import fabric  # noqa: E402


try:
    import notebookutils
    from notebookutils import mssparkutils
except ImportError:
    mssparkutils = notebookutils = None


def _get_notebook_name() -> str:
    """Get current notebook name from Fabric context with robust fallbacks"""
    if mssparkutils is None:
        return "unknown_notebook"
    
    try:
        ctx = mssparkutils.runtime.context
        
        # Try common notebook name keys
        for key in ["notebookName", "currentNotebookName", "notebookname"]:
            try:
                name = ctx.get(key) if hasattr(ctx, 'get') else ctx[key]
                if name and str(name).strip() and str(name).lower() != 'none':
                    return str(name)
            except:
                continue
        
        # Try accessing as attribute
        if hasattr(ctx, 'notebookName') and ctx.notebookName:
            return str(ctx.notebookName)
            
    except Exception:
        pass
    
    return "unknown_notebook"


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Helpers

# CELL ********************

# ============================================================
# FabricLogger Singleton
# ============================================================

_FABRIC_LOGGER_SINGLETON = None

def get_fabric_logger(project_name: str = None, force_recreate: bool = False, workspace_name: str = None):
    global _FABRIC_LOGGER_SINGLETON

    if _FABRIC_LOGGER_SINGLETON is not None:
        return _FABRIC_LOGGER_SINGLETON

    if not project_name:
        return None

    _FABRIC_LOGGER_SINGLETON = FabricLogger(
        project_name=project_name,
        force_recreate=force_recreate,
        workspace_name=workspace_name
    )

    return _FABRIC_LOGGER_SINGLETON


def _ensure_delta_table_registered(table_name: str, delta_path: str):
    try:
        if spark.catalog.tableExists(table_name):
            return

        if "." in table_name:
            schema = table_name.split(".")[0]
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS {schema}")

        spark.sql(f"""
            CREATE TABLE IF NOT EXISTS {table_name}
            USING DELTA
            LOCATION '{delta_path}'
        """)
    except Exception:
        pass

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Logger Class

# CELL ********************

# Control variable for FabricLogger initialization output (1=show, 0=silent)
# Set to 0 in your notebook to suppress initialization messages
_show_fabric_logger_output = 0

class FabricLogger:
    """Complete Microsoft Fabric logging framework with automatic semantic model creation"""

    def __init__(self, project_name: str, force_recreate: bool = False, workspace_name: str = None):

        self.project_name = project_name
        self.lakehouse_name = f"{project_name}"
        self.semantic_model_name = f"SM_{project_name}_Monitoring"
        self.workspace_id = None
        self.workspace_name = workspace_name
        self.lakehouse_id = None
        self.log_path = None
        self.force_recreate = force_recreate
        self.spark = SparkSession.builder.getOrCreate()

        if _show_fabric_logger_output:
            print("\n" + "=" * 60)
            print("FABRIC LOGGING FRAMEWORK v3.4.3")
            print("=" * 60)
            print("\nProject Configuration:")
            print(f"  • Project Name: {project_name}")
            print(f"  • Lakehouse: {self.lakehouse_name}")
            print(f"  • Semantic Model: {self.semantic_model_name}")

            if force_recreate:
                print("\nWARNING: Force recreate mode - existing data will be lost!")

        try:
            self._setup()
            self._print_final_summary()
        except Exception as e:
            logger.warning(f"[FABRIC_LOGGER] Initialization incomplete: {type(e).__name__}: {str(e)}")
            logger.warning("[FABRIC_LOGGER] Some logging features may be unavailable")

    def _setup(self):
        """Initialize workspace and lakehouse"""
        # Get workspace
        self.workspace_id = fabric.get_notebook_workspace_id()

        # Get workspace name if not provided
        if not self.workspace_name:
            try:
                self.workspace_name = fabric.resolve_workspace_name(self.workspace_id)
            except:
                self.workspace_name = "MyWorkspace"

        # Get or create lakehouse
        if notebookutils:
            self.lakehouse_id = notebookutils.runtime.context.get("defaultLakehouseId")

            if not self.lakehouse_id:
                try:
                    lakehouse = mssparkutils.lakehouse.get(self.lakehouse_name)
                    self.lakehouse_id = lakehouse["id"]
                except:
                    try:
                        mssparkutils.lakehouse.create(
                            name=self.lakehouse_name,
                            description=f"Monitoring lakehouse for {self.project_name} project",
                            workspaceId=self.workspace_id,
                        )
                        lakehouse = mssparkutils.lakehouse.get(self.lakehouse_name)
                        self.lakehouse_id = lakehouse["id"]
                    except Exception:
                        self.lakehouse_id = "current-context"
            
            # Set log path
            if self.lakehouse_id != "current-context":
                self.log_path = f"abfss://{self.workspace_id}@onelake.dfs.fabric.microsoft.com/{self.lakehouse_id}/Tables/log/audit_operation_log"
            else:
                self.log_path = "Tables/log/audit_operation_log"

        # Create or verify all tables
        self._ensure_layer_schemas()
        self._ensure_monitoring_table()
        self._ensure_date_table()
        self._ensure_time_table()
        self._ensure_package_summary_table()

        # Register log tables
        try:
            _ensure_delta_table_registered("log.audit_operation_log", self.log_path)
            _ensure_delta_table_registered(
                "log.dim_date",
                self.log_path.replace("/log/audit_operation_log", "/log/dim_date")
            )
            _ensure_delta_table_registered(
                "log.dim_time",
                self.log_path.replace("/log/audit_operation_log", "/log/dim_time")
            )
            _ensure_delta_table_registered(
                "log.audit_package_lifecycle",
                self.log_path.replace("/log/audit_operation_log", "/log/audit_package_lifecycle")
            )
        except Exception:
            pass

        # Verify tables are ready
        self._verify_tables_ready()


    def _ensure_layer_schemas(self):
        """
        Ensure bronze, silver, and gold schemas exist in the Lakehouse.
        In Fabric, schemas are folder namespaces under /Tables.
        """
        self.schema_status = []
        try:
            base_path = f"abfss://{self.workspace_id}@onelake.dfs.fabric.microsoft.com/{self.lakehouse_id}/Tables"

            schemas = ["bronze", "silver", "gold"]

            for schema in schemas:
                schema_path = f"{base_path}/{schema}"

                try:
                    # Check if folder exists
                    mssparkutils.fs.ls(schema_path)
                    self.schema_status.append((schema, True))
                except Exception:
                    # Create folder
                    try:
                        mssparkutils.fs.mkdirs(schema_path)
                        self.schema_status.append((schema, True))
                    except Exception:
                        self.schema_status.append((schema, False))

        except Exception:
            pass

    def _verify_tables_ready(self, max_retries=15, wait_seconds=2):
        """Verify all tables are accessible before creating semantic model"""
        tables_to_check = [
            ("log.audit_operation_log", self.log_path),
            ("log.dim_date", self.log_path.replace("/log/audit_operation_log", "/log/dim_date")),
            ("log.dim_time", self.log_path.replace("/log/audit_operation_log", "/log/dim_time")),
        ]

        all_ready = True

        for table_name, table_path in tables_to_check:
            table_ready = False

            for attempt in range(max_retries):
                try:
                    df = self.spark.read.format("delta").load(table_path)
                    table_ready = True
                    break
                except Exception:
                    if attempt < max_retries - 1:
                        time.sleep(wait_seconds)
                    else:
                        all_ready = False
                        break

            if not table_ready:
                all_ready = False

        return all_ready

    def _table_exists(self, table_path: str) -> bool:
        """Check if a Delta table exists at the given path"""
        try:
            df = self.spark.read.format("delta").load(table_path)
            return True
        except Exception:
            return False

    def _ensure_monitoring_table(self):
        """Create monitoring log table safely and atomically."""

        table_path = self.log_path

        # If table exists and not forcing recreation, just validate schema
        if self._table_exists(table_path) and not self.force_recreate:
            try:
                existing_df = self.spark.read.format("delta").load(table_path)
                existing_columns = set(existing_df.columns)

                expected_columns = {
                    "notebook_name", "table_name", "operation_type", "user_name",
                    "rows_before", "rows_after", "rows_changed", "execution_time",
                    "message", "error_message", "date_stamp", "time_stamp",
                    "timestamp", "domain", "deleted_combinations", "source_file",
                    "manifest_file", "manifest_package", "status"
                }

                missing = expected_columns - existing_columns
                # Schema evolution will handle automatically
                return

            except Exception:
                pass

        # SAFE ATOMIC CREATION
        try:
            self.spark.sql(f"""
                CREATE TABLE IF NOT EXISTS delta.`{table_path}`
                (
                    batchid INT,
                    manifest_package STRING,
                    manifest_file STRING,
                    notebook_name STRING,
                    table_name STRING,
                    operation_type STRING,
                    user_name STRING,
                    rows_before BIGINT,
                    rows_after BIGINT,
                    rows_changed BIGINT,
                    execution_time DECIMAL(10,6),
                    message STRING,
                    error_message STRING,
                    date_stamp STRING,
                    time_stamp STRING,
                    timestamp TIMESTAMP,
                    domain STRING,
                    deleted_combinations STRING,
                    source_file STRING,
                    status STRING
                )
                USING DELTA
            """)
        except Exception as e:
            logger.warning(f"[FABRIC_LOGGER] Could not create monitoring table at {table_path}: {type(e).__name__}: {str(e)}")


    def _ensure_date_table(self):
        """Create or update date dimension table"""
        try:
            date_table_path = self.log_path.replace("/log/audit_operation_log", "/log/dim_date")

            should_update = False
            if self._table_exists(date_table_path) and not self.force_recreate:
                try:
                    existing_df = self.spark.read.format("delta").load(date_table_path)
                    max_date = existing_df.agg({"date_key": "max"}).collect()[0][0]
                    max_date_obj = datetime.strptime(max_date, "%Y-%m-%d")

                    days_ahead = (datetime.now() + timedelta(days=365) - max_date_obj).days

                    if days_ahead > 0:
                        should_update = True
                    else:
                        return
                except Exception:
                    should_update = True
            else:
                should_update = True

            if should_update or self.force_recreate:
                # Generate date range (2 years back, 2 years forward)
                start_date = datetime.now() - timedelta(days=730)
                end_date = datetime.now() + timedelta(days=730)

                date_list = []
                current_date = start_date
                while current_date <= end_date:
                    date_list.append((current_date.strftime("%Y-%m-%d"),))
                    current_date += timedelta(days=1)

                date_df = self.spark.createDataFrame(date_list, ["date_key"])
                date_df = date_df.withColumn("date_value", col("date_key").cast("date"))

                date_df = (
                    date_df.withColumn("year", year(col("date_value")))
                    .withColumn("month", month(col("date_value")))
                    .withColumn("day", dayofmonth(col("date_value")))
                    .withColumn("quarter", quarter(col("date_value")))
                    .withColumn("week_of_year", weekofyear(col("date_value")))
                    .withColumn("day_of_week", dayofweek(col("date_value")))
                    .withColumn("month_name", date_format(col("date_value"), "MMMM"))
                    .withColumn("day_name", date_format(col("date_value"), "EEEE"))
                    .withColumn(
                        "is_weekend", (dayofweek(col("date_value")).isin([1, 7])).cast("boolean")
                    )
                )

                if self._table_exists(date_table_path) and not self.force_recreate:
                    from delta.tables import DeltaTable

                    delta_table = DeltaTable.forPath(self.spark, date_table_path)

                    delta_table.alias("target").merge(
                        date_df.alias("source"), "target.date_key = source.date_key"
                    ).whenNotMatchedInsertAll().execute()
                else:
                    date_df.write.format("delta").option("mergeSchema", "true").mode(
                        "overwrite"
                    ).save(date_table_path)

        except Exception:
            pass

    def _ensure_time_table(self):
        """Create time dimension table only if it doesn't exist"""
        try:
            time_table_path = self.log_path.replace("/log/audit_operation_log", "/log/dim_time")

            if self._table_exists(time_table_path) and not self.force_recreate:
                return

            time_list = []

            for hour in range(24):
                for minute in range(60):
                    time_key = f"{hour:02d}:{minute:02d}:00"

                    if 0 <= hour < 6:
                        period = "Night"
                    elif 6 <= hour < 12:
                        period = "Morning"
                    elif 12 <= hour < 18:
                        period = "Afternoon"
                    else:
                        period = "Evening"

                    is_business_hours = 9 <= hour < 17

                    time_list.append(
                        (time_key, hour, minute, f"{hour:02d}:00", period, is_business_hours)
                    )

            time_schema = StructType(
                [
                    StructField("time_key", StringType(), False),
                    StructField("hour", IntegerType(), False),
                    StructField("minute", IntegerType(), False),
                    StructField("hour_group", StringType(), False),
                    StructField("time_period", StringType(), False),
                    StructField("is_business_hours", BooleanType(), False),
                ]
            )

            time_df = self.spark.createDataFrame(time_list, time_schema)

            write_mode = "overwrite" if self.force_recreate else "ignore"

            time_df.write.format("delta").option("mergeSchema", "true").mode(write_mode).save(
                time_table_path
            )

        except Exception:
            pass

    # ============================================================
    # PACKAGE-LEVEL TRACKING
    # ============================================================

    def _ensure_package_summary_table(self):
        """Create audit_package_lifecycle table for folder-level lifecycle tracking"""
        try:
            package_table_path = self.log_path.replace("/log/audit_operation_log", "/log/audit_package_lifecycle")

            if self._table_exists(package_table_path) and not self.force_recreate:
                return

            package_schema = StructType([
                StructField("batchid", IntegerType(), True),
                StructField("manifest_package", StringType(), False),
                StructField("load_date", StringType(), True),
                StructField("domain", StringType(), True),
                StructField("package_timestamp", StringType(), True),
                StructField("start_time", TimestampType(), True),
                StructField("end_time", TimestampType(), True),
                StructField("total_execution_time", DecimalType(10, 2), True),
                StructField("current_layer", StringType(), True),
                StructField("overall_status", StringType(), True),
                StructField("bronze_status", StringType(), True),
                StructField("bronze_start", TimestampType(), True),
                StructField("bronze_end", TimestampType(), True),
                StructField("silver_status", StringType(), True),
                StructField("silver_start", TimestampType(), True),
                StructField("silver_end", TimestampType(), True),
                StructField("gold_status", StringType(), True),
                StructField("gold_start", TimestampType(), True),
                StructField("gold_end", TimestampType(), True),
                StructField("error_layer", StringType(), True),
                StructField("error_entity", StringType(), True),
                StructField("error_message", StringType(), True),
                StructField("created_at", TimestampType(), True),
                StructField("updated_at", TimestampType(), True),
            ])

            empty_df = self.spark.createDataFrame([], package_schema)
            write_mode = "overwrite" if self.force_recreate else "ignore"

            empty_df.write.format("delta").option("mergeSchema", "true").mode(write_mode).save(
                package_table_path
            )

        except Exception:
            pass

    def _get_package_summary_path(self) -> str:
        """Get the path for audit_package_lifecycle table"""
        return self.log_path.replace("/log/audit_operation_log", "/log/audit_package_lifecycle")

    def parse_package_name(self, package_name: str) -> dict:
        """
        Parse package folder name into components.
        
        Supports two formats:
          Old: YYYYMMDD_HHMMSS_DOMAIN_Type_System_Frequency
               e.g. 20260214_033024_OPR_FinishedZip_UnisonInsights1ONECH_Daily
               e.g. 20260507_192226_FCT_FinishedZip_InitializationEMEADMRDEU1_PreDMR_2026M05
          New: DOMAIN_Full_Site_YYYYMMDD_HHMMSS
               e.g. SP_Full_One1_20260515_033309
               e.g. DP_Full_One1_20260515_033309
        
        Detection: if parts[0] is an 8-digit date -> old format, otherwise -> new format.
        
        Returns:
        --------
        dict with keys: timestamp, domain, package_type, source_system, frequency
        """
        import re
        parts = package_name.split("_")
        
        result = {
            "timestamp": None,
            "domain": None,
            "package_type": None,
            "source_system": None,
            "frequency": None,
        }
        
        # Detect format: old starts with 8-digit date, new starts with alpha domain
        is_old_format = len(parts) >= 2 and re.match(r'^\d{8}$', parts[0])
        
        if is_old_format:
            # Old format: YYYYMMDD_HHMMSS_DOMAIN_Type_System_Frequency
            if len(parts) >= 2:
                result["timestamp"] = f"{parts[0]}_{parts[1]}"
            if len(parts) >= 3:
                result["domain"] = parts[2]
            if len(parts) >= 4:
                result["package_type"] = parts[3]
            if len(parts) >= 5:
                result["source_system"] = parts[4]
            if len(parts) >= 6:
                result["frequency"] = parts[5]
        else:
            # New format: DOMAIN_Full_Site_YYYYMMDD_HHMMSS
            # e.g. SP_Full_One1_20260515_033309 -> domain=SP, timestamp=20260515_033309
            result["domain"] = parts[0] if len(parts) >= 1 else None
            result["package_type"] = parts[1] if len(parts) >= 2 else None
            result["source_system"] = parts[2] if len(parts) >= 3 else None
            # Find timestamp: look for YYYYMMDD_HHMMSS pattern at the end
            for i in range(len(parts) - 1):
                if re.match(r'^\d{8}$', parts[i]) and re.match(r'^\d{6}$', parts[i + 1]):
                    result["timestamp"] = f"{parts[i]}_{parts[i + 1]}"
                    break
        
        return result

    def discover_packages(self, date_path: str, domain_filter: str = None) -> list:
        """
        Discover all package folders for a given date.
        
        Parameters:
        -----------
        date_path : str
            Date path like '2026/02/14' or '2026-02-14'
        domain_filter : str, optional
            Filter by domain (e.g., 'OPR', 'FCT')
            
        Returns:
        --------
        list of dict: Package info with name, path, parsed components
        """
        try:
            # Normalize date path
            date_path = date_path.strip("/").replace("-", "/")
            base_path = f"Files/archive/parquet/{date_path}"
            
            packages = []
            
            try:
                items = mssparkutils.fs.ls(base_path)
            except Exception as e:
                print(f"[PACKAGE] Could not list {base_path}: {e}")
                return packages
            
            for item in items:
                if item.isDir:
                    package_name = item.name
                    parsed = self.parse_package_name(package_name)
                    
                    # Apply domain filter if specified
                    if domain_filter and parsed.get("domain", "").upper() != domain_filter.upper():
                        continue
                    
                    packages.append({
                        "package_name": package_name,
                        "package_path": f"{base_path}/{package_name}",
                        **parsed
                    })
            
            print(f"[PACKAGE] Discovered {len(packages)} packages in {base_path}")
            return packages
            
        except Exception as e:
            print(f"[PACKAGE] Discovery failed: {e}")
            return []

    def generate_package_id(self, package_name: str) -> str:
        """Generate package ID from package name.
        
        Package ID is simply the package_name (folder name) to ensure
        one row per package. Combined with load_date, this gives a unique key.
        """
        return package_name

    def start_package(
        self,
        manifest_package: str,
        batchid:int = None,
    ) -> str:

        try:
            now = datetime.now()
            load_date = now.strftime("%Y-%m-%d")
            
            # manifest_package is the folder name/package identifier
            folder_name = manifest_package
            
            # Parse package name for domain and timestamp
            parsed = self.parse_package_name(folder_name)
            
            # Check if package already exists for today (by folder_name + load_date)
            # This ensures only ONE row per package per day
            package_path_table = self._get_package_summary_path()
            try:
                existing_df = (
                    self.spark.read.format("delta")
                    .load(package_path_table)
                    .filter(f"manifest_package = '{folder_name}' AND load_date = '{load_date}'")
                    .select("manifest_package")
                    .limit(1)
                )
                existing_row = existing_df.first()
                if existing_row:
                    existing_package_id = existing_row["manifest_package"]
                    print(f"[PACKAGE] Package already exists for today: {folder_name} (ID: {existing_package_id})")
                    return existing_package_id
            except Exception:
                # Table might not exist yet, continue with insert
                pass
            
            # Simplified package data with single manifest_package identifier
            package_data = [(
                batchid,
                folder_name,  # manifest_package (single identifier)
                load_date,
                parsed.get("domain"),
                parsed.get("timestamp"),
                now,  # start_time
                None,  # end_time
                None,  # total_execution_time
                "BRONZE",  # current_layer
                "IN_PROGRESS",  # overall_status
                "PENDING", None, None,  # bronze: status, start, end
                "PENDING", None, None,  # silver: status, start, end
                "PENDING", None, None,  # gold: status, start, end
                None,  # error_layer
                None,  # error_entity
                None,  # error_message
                now,  # created_at
                now,  # updated_at
            )]

            # Consolidated schema with single manifest_package identifier
            package_schema = StructType([
                StructField("batchid", IntegerType(), True),
                StructField("manifest_package", StringType(), False),
                StructField("load_date", StringType(), True),
                StructField("domain", StringType(), True),
                StructField("package_timestamp", StringType(), True),
                StructField("start_time", TimestampType(), True),
                StructField("end_time", TimestampType(), True),
                StructField("total_execution_time", DecimalType(10, 2), True),
                StructField("current_layer", StringType(), True),
                StructField("overall_status", StringType(), True),
                StructField("bronze_status", StringType(), True),
                StructField("bronze_start", TimestampType(), True),
                StructField("bronze_end", TimestampType(), True),
                StructField("silver_status", StringType(), True),
                StructField("silver_start", TimestampType(), True),
                StructField("silver_end", TimestampType(), True),
                StructField("gold_status", StringType(), True),
                StructField("gold_start", TimestampType(), True),
                StructField("gold_end", TimestampType(), True),
                StructField("error_layer", StringType(), True),
                StructField("error_entity", StringType(), True),
                StructField("error_message", StringType(), True),
                StructField("created_at", TimestampType(), True),
                StructField("updated_at", TimestampType(), True),
            ])

            package_df = self.spark.createDataFrame(package_data, package_schema)
            
            # Use MERGE to prevent duplicate rows from concurrent notebook calls
            # Multiple bronze notebooks may call start_package for the same package simultaneously
            # Retry on Delta concurrency conflicts
            import time as _time
            _max_retries = 3
            for _attempt in range(1, _max_retries + 1):
                try:
                    from delta.tables import DeltaTable
                    delta_table = DeltaTable.forPath(self.spark, package_path_table)
                    delta_table.alias("t").merge(
                        package_df.alias("s"),
                        "t.manifest_package = s.manifest_package AND t.load_date = s.load_date"
                    ).whenNotMatchedInsertAll().execute()
                    break
                except Exception as merge_err:
                    err_msg = str(merge_err).lower()
                    # Only fall back to append when the Delta table truly doesn't exist yet (first run).
                    # All other errors (concurrent write conflicts, etc.) should NOT append
                    # because that creates duplicate rows.
                    if "is not a delta table" in err_msg or "path does not exist" in err_msg or "table or view not found" in err_msg or "_delta_log" in err_msg:
                        package_df.write.format("delta").option("mergeSchema", "true").mode("append").save(
                            package_path_table
                        )
                        break
                    elif ("concurrent" in err_msg or "delta_concurrent" in err_msg or "conflictexception" in err_msg or "delta_metadata_changed" in err_msg) and _attempt < _max_retries:
                        _wait = _attempt * 5
                        print(f"[PACKAGE] MERGE conflict on attempt {_attempt}/{_max_retries}. Retrying in {_wait}s...")
                        _time.sleep(_wait)
                    else:
                        print(f"[PACKAGE] MERGE failed (skipping append to avoid duplicate): {merge_err}")
                        break

            print(f"[PACKAGE] Started package: {folder_name} (ID: {folder_name})")
            return folder_name

        except Exception as e:
            print(f"[PACKAGE] Failed to start package: {e}")
            return None

    def update_package_layer(
        self,
        manifest_package: str,
        layer: str,
        status: str,
        start_time: datetime = None,
        end_time: datetime = None,
    ):
        """
        Update a specific layer's status for a package.
        
        Parameters:
        -----------
        package_id : str
            The package identifier
        layer : str
            Layer name: 'BRONZE', 'SILVER', or 'GOLD'
        status : str
            Status: 'IN_PROGRESS', 'SUCCESS', 'FAILED', 'SKIPPED'
        start_time : datetime
            When layer processing started
        end_time : datetime
            When layer processing ended
        """
        try:
            from delta.tables import DeltaTable
            
            package_path = self._get_package_summary_path()
            delta_table = DeltaTable.forPath(self.spark, package_path)
            
            layer_lower = layer.lower()
            load_date = datetime.now().strftime("%Y-%m-%d")
            
            # Determine next layer
            layer_lower = layer.lower()
            now = datetime.now()

            # Determine overall_status properly
            if status == "FAILED":
                overall_status = "FAILED"
                current_layer = layer.upper()
            elif layer_lower == "gold" and status == "SUCCESS":
                overall_status = "COMPLETED"
                current_layer = "COMPLETED"
            elif status == "SUCCESS":
                # Layer completed, move to next layer
                if layer_lower == "bronze":
                    current_layer = "SILVER"
                elif layer_lower == "silver":
                    current_layer = "GOLD"
                else:
                    current_layer = layer.upper()
                overall_status = "IN_PROGRESS"
            else:
                # IN_PROGRESS
                current_layer = layer.upper()
                overall_status = "IN_PROGRESS"
            
            # Build update expressions (simplified - no rows/time per layer)
            update_expr = {
                f"{layer_lower}_status": f"'{status}'",
                "current_layer": f"'{current_layer}'",
                "overall_status": f"'{overall_status}'",
                "updated_at": "current_timestamp()",
            }
            
            if start_time:
                update_expr[f"{layer_lower}_start"] = f"to_timestamp('{start_time.strftime('%Y-%m-%d %H:%M:%S')}')"
            if end_time:
                update_expr[f"{layer_lower}_end"] = f"to_timestamp('{end_time.strftime('%Y-%m-%d %H:%M:%S')}')"
            
            # If failed, update error tracking
            if status == "FAILED":
                update_expr["error_layer"] = f"'{layer.upper()}'"
                update_expr["overall_status"] = "'FAILED'"
            
            # Update package layer status with retry for Delta concurrency conflicts
            import time as _time
            _max_retries = 3
            for _attempt in range(1, _max_retries + 1):
                try:
                    delta_table.update(
                        condition=f"manifest_package = '{manifest_package}'",
                        set=update_expr
                    )
                    print(f"[PACKAGE] Updated {layer.upper()}: {status} for package {manifest_package}")
                    break
                except Exception as _upd_err:
                    _err_msg = str(_upd_err).lower()
                    if ("concurrent" in _err_msg or "delta_concurrent" in _err_msg or "conflictexception" in _err_msg or "delta_metadata_changed" in _err_msg) and _attempt < _max_retries:
                        _wait = _attempt * 5
                        print(f"[PACKAGE] Update conflict on attempt {_attempt}/{_max_retries}. Retrying in {_wait}s...")
                        _time.sleep(_wait)
                        # Re-acquire DeltaTable reference after conflict
                        delta_table = DeltaTable.forPath(self.spark, package_path)
                    else:
                        print(f"[PACKAGE] Failed to update package layer: {_upd_err}")
                        break

        except Exception as e:
            print(f"[PACKAGE] Failed to update package layer: {e}")

    def complete_package(self, manifest_package: str, total_execution_time: float = None):
        """
        Mark a package as completed successfully.
        
        Parameters:
        -----------
        manifest_package : str
            The package identifier
        total_execution_time : float
            Total time for the entire package in seconds
        """
        try:
            from delta.tables import DeltaTable
            
            package_path = self._get_package_summary_path()
            delta_table = DeltaTable.forPath(self.spark, package_path)
            
            update_expr = {
                "current_layer": "'COMPLETED'",
                "overall_status": "'COMPLETED'",
                "end_time": "current_timestamp()",
                "updated_at": "current_timestamp()",
            }
            
            if total_execution_time is not None:
                update_expr["total_execution_time"] = str(round(total_execution_time, 2))
            
            # Update package as completed with retry for Delta concurrency conflicts
            import time as _time
            _max_retries = 3
            for _attempt in range(1, _max_retries + 1):
                try:
                    delta_table.update(
                        condition=f"manifest_package = '{manifest_package}'",
                        set=update_expr
                    )
                    print(f"[PACKAGE] Completed package: {manifest_package}")
                    break
                except Exception as _upd_err:
                    _err_msg = str(_upd_err).lower()
                    if ("concurrent" in _err_msg or "delta_concurrent" in _err_msg or "conflictexception" in _err_msg or "delta_metadata_changed" in _err_msg) and _attempt < _max_retries:
                        _wait = _attempt * 5
                        print(f"[PACKAGE] Complete conflict on attempt {_attempt}/{_max_retries}. Retrying in {_wait}s...")
                        _time.sleep(_wait)
                        delta_table = DeltaTable.forPath(self.spark, package_path)
                    else:
                        print(f"[PACKAGE] Failed to complete package: {_upd_err}")
                        break

        except Exception as e:
            print(f"[PACKAGE] Failed to complete package: {e}")

    def fail_package(self, manifest_package: str, layer: str, error_message: str, error_entity: str = None):
        """
        Mark a package as failed.
        
        Parameters:
        -----------
        manifest_package : str
            The package identifier
        layer : str
            Layer where the failure occurred
        error_message : str
            Error details
        error_entity : str
            Which entity failed (optional)
        """
        try:
            from delta.tables import DeltaTable
            
            package_path = self._get_package_summary_path()
            delta_table = DeltaTable.forPath(self.spark, package_path)
            
            # Escape single quotes in error message
            safe_error = error_message.replace("'", "''")[:1000] if error_message else "Unknown error"
            
            update_expr = {
                "overall_status": "'FAILED'",
                "error_layer": f"'{layer.upper()}'",
                "error_message": f"'{safe_error}'",
                "end_time": "current_timestamp()",
                "updated_at": "current_timestamp()",
                f"{layer.lower()}_status": "'FAILED'",
            }
            
            if error_entity:
                update_expr["error_entity"] = f"'{error_entity}'"
            
            # Mark package as failed with retry for Delta concurrency conflicts
            import time as _time
            _max_retries = 3
            for _attempt in range(1, _max_retries + 1):
                try:
                    delta_table.update(
                        condition=f"manifest_package = '{manifest_package}'",
                        set=update_expr
                    )
                    print(f"[PACKAGE] Failed package: {manifest_package} at layer: {layer}")
                    break
                except Exception as _upd_err:
                    _err_msg = str(_upd_err).lower()
                    if ("concurrent" in _err_msg or "delta_concurrent" in _err_msg or "conflictexception" in _err_msg or "delta_metadata_changed" in _err_msg) and _attempt < _max_retries:
                        _wait = _attempt * 5
                        print(f"[PACKAGE] Fail-update conflict on attempt {_attempt}/{_max_retries}. Retrying in {_wait}s...")
                        _time.sleep(_wait)
                        delta_table = DeltaTable.forPath(self.spark, package_path)
                    else:
                        print(f"[PACKAGE] Failed to mark package as failed: {_upd_err}")
                        break

        except Exception as e:
            print(f"[PACKAGE] Failed to mark package as failed: {e}")

    def get_package_status(self, manifest_package: str):
        """Get the current status of a package"""
        try:
            package_path = self._get_package_summary_path()
            df = self.spark.read.format("delta").load(package_path)
            return df.filter(f"manifest_package = '{manifest_package}'").first()
        except Exception as e:
            print(f"[PACKAGE] Failed to get package status: {e}")
            return None

    def get_packages_by_date(self, load_date: str = None, domain: str = None, limit: int = 100):
        """Get packages for a specific date and/or domain"""
        try:
            package_path = self._get_package_summary_path()
            df = self.spark.read.format("delta").load(package_path)
            
            if load_date:
                df = df.filter(f"load_date = '{load_date}'")
            
            if domain:
                df = df.filter(f"domain = '{domain.upper()}'")
            
            return df.orderBy(col("start_time").desc()).limit(limit)
        except Exception as e:
            print(f"[PACKAGE] Failed to get packages: {e}")
            return None

    def cleanup_old_packages(self, days_to_keep: int = 180):
        """Remove package records older than specified days (default 6 months)"""
        try:
            from delta.tables import DeltaTable
            
            package_path = self._get_package_summary_path()
            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")
            
            df = self.spark.read.format("delta").load(package_path)
            before_count = df.count()
            old_records = df.filter(f"load_date < '{cutoff_str}'").count()
            
            if old_records > 0:
                print(f"Removing {old_records:,} package records older than {cutoff_str}")
                
                delta_table = DeltaTable.forPath(self.spark, package_path)
                delta_table.delete(f"load_date < '{cutoff_str}'")
                delta_table.vacuum(0)
                
                print(f"Cleanup complete. Kept {before_count - old_records:,} package records")
            else:
                print(f"No package records older than {cutoff_str} to remove")
                
        except Exception as e:
            print(f"Could not cleanup old packages: {e}")

    # ============================================================
    # LAYER LOGGING FOR SILVER AND GOLD
    # ============================================================

    def log_layer(
        self,
        layer: str,
        status: str,
        domain: str = None,
        error_message: str = None,
    ) -> int:
        """
        Log the status of a silver or gold layer for packages.
        
        - status='START': Updates all PENDING packages to IN_PROGRESS, sets {layer}_start
        - status='SUCCESS': Updates all IN_PROGRESS packages to SUCCESS, sets {layer}_end
        - status='FAILED': Updates all IN_PROGRESS packages to FAILED, sets {layer}_end and error info
        
        Parameters:
        -----------
        layer : str
            Layer name: 'SILVER', 'GOLD', or 'INTERFACE'
        status : str
            Status: 'START', 'SUCCESS', or 'FAILED'
        domain : str, optional
            Filter by domain (e.g., 'OPR', 'FCT'). If not provided, updates all domains.
        error_message : str, optional
            Error message if status is 'FAILED'
            
        Returns:
        --------
        int : Number of packages updated
            
        Example:
        --------
        # At the start of your silver notebook:
        log_layer(layer="SILVER", status="START")
        
        # At the end (success):
        log_layer(layer="SILVER", status="SUCCESS")
        
        # On failure:
        log_layer(layer="SILVER", status="FAILED", error_message="Validation failed")
        
        # Filter by domain:
        log_layer(layer="SILVER", status="START", domain="OPR")
        """
        try:
            from delta.tables import DeltaTable
            
            now = datetime.now()
            load_date = now.strftime("%Y-%m-%d")
            layer_lower = layer.lower()
            status_upper = status.upper()
            
            if layer_lower not in ("silver", "gold",'interface'):
                print(f"[LAYER] Invalid layer '{layer}'. Must be 'SILVER', 'GOLD', or 'INTERFACE'.")
                return 0
            
            if status_upper not in ("START", "SUCCESS", "FAILED"):
                print(f"[LAYER] Invalid status '{status}'. Must be 'START', 'SUCCESS', or 'FAILED'.")
                return 0
            
            package_path = self._get_package_summary_path()
            delta_table = DeltaTable.forPath(self.spark, package_path)
            
            # Build domain filter
            domain_filter = f" AND domain = '{domain.upper()}'" if domain else ""
            
            if status_upper == "START":
                # Find PENDING packages and set to IN_PROGRESS
                condition = f"{layer_lower}_status = 'PENDING' AND load_date = '{load_date}'{domain_filter}"
                
                try:
                    df = self.spark.read.format("delta").load(package_path)
                    count = df.filter(condition).count()
                except Exception:
                    count = 0
                
                if count == 0:
                    print(f"[LAYER] No pending packages found for {layer.upper()}" + (f" (domain: {domain})" if domain else ""))
                    return 0
                
                delta_table.update(
                    condition=condition,
                    set={
                        f"{layer_lower}_status": "'IN_PROGRESS'",
                        f"{layer_lower}_start": f"to_timestamp('{now.strftime('%Y-%m-%d %H:%M:%S')}')",
                        "current_layer": f"'{layer.upper()}'",
                        "overall_status": "'IN_PROGRESS'",
                        "updated_at": "current_timestamp()",
                    }
                )
                
                print(f"[LAYER] ▶ Started {layer.upper()} for {count} package(s)" + (f" (domain: {domain})" if domain else ""))
                return count
                
            else:
                # Find IN_PROGRESS packages and set to SUCCESS or FAILED
                condition = f"{layer_lower}_status = 'IN_PROGRESS' AND load_date = '{load_date}'{domain_filter}"
                
                try:
                    df = self.spark.read.format("delta").load(package_path)
                    count = df.filter(condition).count()
                except Exception:
                    count = 0
                
                if count == 0:
                    print(f"[LAYER] No in-progress packages found for {layer.upper()}" + (f" (domain: {domain})" if domain else ""))
                    return 0
                
                # Determine overall status based on layer and result
                if status_upper == "FAILED":
                    overall_status = "FAILED"
                    current_layer = layer.upper()
                elif layer_lower == "gold" and status_upper == "SUCCESS":
                    overall_status = "COMPLETED"
                    current_layer = "COMPLETED"
                else:  # silver SUCCESS
                    overall_status = "IN_PROGRESS"
                    current_layer = "GOLD"
                
                # Build update expressions
                update_expr = {
                    f"{layer_lower}_status": f"'{status_upper}'",
                    f"{layer_lower}_end": f"to_timestamp('{now.strftime('%Y-%m-%d %H:%M:%S')}')",
                    "current_layer": f"'{current_layer}'",
                    "overall_status": f"'{overall_status}'",
                    "updated_at": "current_timestamp()",
                }
                
                # If gold completed successfully, also set package end_time
                if layer_lower == "gold" and status_upper == "SUCCESS":
                    update_expr["end_time"] = f"to_timestamp('{now.strftime('%Y-%m-%d %H:%M:%S')}')"
                
                # If failed, update error tracking
                if status_upper == "FAILED":
                    update_expr["error_layer"] = f"'{layer.upper()}'"
                    if error_message:
                        safe_error = error_message.replace("'", "''")[:1000]
                        update_expr["error_message"] = f"'{safe_error}'"
                    update_expr["end_time"] = f"to_timestamp('{now.strftime('%Y-%m-%d %H:%M:%S')}')"
                
                delta_table.update(
                    condition=condition,
                    set=update_expr
                )
                
                status_emoji = "✓" if status_upper == "SUCCESS" else "✗"
                print(f"[LAYER] {status_emoji} Ended {layer.upper()} ({status_upper}) for {count} package(s)" + (f" (domain: {domain})" if domain else ""))
                return count
            
        except Exception as e:
            print(f"[LAYER] Failed to log layer: {e}")
            return 0

    def _semantic_model_exists(self) -> bool:
        """Check if semantic model already exists in the workspace"""
        try:
            datasets = fabric.list_datasets(workspace=self.workspace_name)

            if datasets is not None and not datasets.empty:
                existing_models = datasets["Dataset Name"].tolist()
                return self.semantic_model_name in existing_models

            return False

        except Exception as e:
            print(f"Could not check for existing semantic model: {e}")
            return False

    # def _create_semantic_model(self):
    #     """Create Direct Lake semantic model"""
    #     try:
    #         from sempy_labs.directlake import generate_direct_lake_semantic_model

    #         if self._semantic_model_exists() and not self.force_recreate:
    #             print(f"  Semantic model '{self.semantic_model_name}' already exists")
    #             print("  Tip: Use enhance_semantic_model() to add relationships/measures")
    #             return True

    #         if self.force_recreate:
    #             print(f"  Force recreating: {self.semantic_model_name}")
    #         else:
    #             print(f"  Creating: {self.semantic_model_name}")

    #         lakehouse_name = self.lakehouse_name

    #         print(f"    • Lakehouse: {lakehouse_name}")
    #         print(f"    • Workspace: {self.workspace_name}")

    #         target_tables = ["log.audit_operation_log", "log.dim_date", "log.dim_time"]
    #         print(f"    • Tables: {', '.join(target_tables)}")

    #         print("    Ensuring tables are fully committed...")
    #         time.sleep(3)

    #         result = generate_direct_lake_semantic_model(
    #             dataset=self.semantic_model_name,
    #             workspace=self.workspace_name,
    #             lakehouse=lakehouse_name,
    #             lakehouse_tables=target_tables,
    #             overwrite=True,
    #             refresh=False,
    #         )

    #         print("  Direct Lake semantic model created (without refresh)")

    #         print("    Waiting before adding relationships...")
    #         time.sleep(2)

    #         print("\n  Adding Relationships...")
    #         self._create_semantic_model_relationships()

    #         print("\n  Adding Measures...")
    #         self._create_semantic_model_measures()

    #         print("\n  Refreshing semantic model...")
    #         try:
    #             # Setup auth before refresh
    #             self._setup_fabric_auth_for_tom()
    #             fabric.refresh_dataset(
    #                 dataset=self.semantic_model_name, workspace=self.workspace_name
    #             )
    #             print("    Semantic model refreshed successfully")
    #         except Exception as refresh_error:
    #             print(f"    Refresh failed: {refresh_error}")
    #             print("    Model created but needs manual refresh in Power BI")

    #         return True

    #     except Exception as e:
    #         print(f"  Semantic model creation failed: {e}")
    #         return False

    def _setup_fabric_auth_for_tom(self):
        """Setup working Fabric authentication for TOM operations"""
        try:
            if notebookutils:
                # Use Fabric's native token system that actually works
                token = notebookutils.credentials.getToken("storage")

                # Set environment variable for Azure auth to bypass broken DefaultAzureCredential
                os.environ["AZURE_ACCESS_TOKEN"] = token

                return True
            else:
                print("    notebookutils not available - TOM auth may fail")
                return False
        except Exception as e:
            print(f"    Could not setup Fabric auth: {e}")
            return False

    def _check_relationships_exist_via_fabric(self):
        """Check if relationships exist and return status for each"""
        try:
            relationships = fabric.list_relationships(
                dataset=self.semantic_model_name, workspace=self.workspace_name
            )

            target_relationships = [
                ("log.audit_operation_log", "date_stamp", "log.dim_date", "date_key"),
                ("log.audit_operation_log", "time_stamp", "log.dim_time", "time_key"),
            ]

            relationship_status = {}
            for from_table, from_col, to_table, to_col in target_relationships:
                rel_key = f"{from_table}[{from_col}] -> {to_table}[{to_col}]"
                exists = False
                if not relationships.empty:
                    exists = any(
                        (relationships["From Table"] == from_table)
                        & (relationships["From Column"] == from_col)
                        & (relationships["To Table"] == to_table)
                        & (relationships["To Column"] == to_col)
                    )
                relationship_status[rel_key] = exists
                print(f"    {rel_key}: {'EXISTS' if exists else 'MISSING'}")

            return relationship_status

        except Exception as e:
            print(f"    Could not check relationships via fabric API: {e}")
            return {}

    def _check_measures_exist_via_fabric(self):
        """Check if measures exist and return status for each"""
        try:
            measures = fabric.list_measures(
                dataset=self.semantic_model_name, workspace=self.workspace_name
            )

            target_measures = [
                "Total Operations",
                "Total Rows Changed",
                "Average Execution Time",
                "Error Count",
                "Success Rate",
                "Operations Today",
                "Unique Tables",
                "Unique Notebooks",
            ]

            existing_measures = measures["Measure Name"].tolist() if not measures.empty else []
            measure_status = {}

            for measure_name in target_measures:
                exists = measure_name in existing_measures
                measure_status[measure_name] = exists
                print(f"    {measure_name}: {'EXISTS' if exists else 'MISSING'}")

            return measure_status

        except Exception as e:
            print(f"    Could not check measures via fabric API: {e}")
            return {}

    # def _create_semantic_model_relationships(self):
    #     """Create or update relationships with proper Fabric authentication"""
    #     print("    Checking existing relationships...")

    #     # Get detailed status of each relationship
    #     relationship_status = self._check_relationships_exist_via_fabric()

    #     if not relationship_status:
    #         print("    Could not determine relationship status - proceeding with TOM operations")

    #     # Determine what needs to be done
    #     missing_relationships = [k for k, v in relationship_status.items() if not v]
    #     existing_relationships = [k for k, v in relationship_status.items() if v]

    #     if not missing_relationships and existing_relationships:
    #         print(f"    All {len(existing_relationships)} relationships exist")
    #         print("    Checking for relationship enhancements...")
    #         return True

    #     if missing_relationships:
    #         print(f"    Need to create {len(missing_relationships)} relationships")

    #     # Setup working Fabric authentication for TOM
    #     print("    Setting up Fabric authentication for TOM...")
    #     auth_success = self._setup_fabric_auth_for_tom()
    #     if not auth_success:
    #         print("    Authentication setup failed - falling back to manual instructions")
    #         self._print_relationship_instructions()
    #         return False

    #     # Attempt TOM operations for missing or updating relationships
    #     try:
    #         from sempy_labs.tom import connect_semantic_model

    #         print("    Connecting to semantic model with Fabric auth...")
    #         with connect_semantic_model(
    #             dataset=self.semantic_model_name, readonly=False, workspace=self.workspace_name
    #         ) as tom_model:
    #             relationships = [
    #                 {
    #                     "from_table": "log.monitoring_log",
    #                     "from_column": "date_stamp",
    #                     "to_table": "log.dim_date",
    #                     "to_column": "date_key",
    #                     "from_cardinality": "Many",
    #                     "to_cardinality": "One",
    #                     "cross_filtering_behavior": "OneDirection",
    #                     "is_active": True,
    #                 },
    #                 {
    #                     "from_table": "log.monitoring_log",
    #                     "from_column": "time_stamp",
    #                     "to_table": "log.dim_time",
    #                     "to_column": "time_key",
    #                     "from_cardinality": "Many",
    #                     "to_cardinality": "One",
    #                     "cross_filtering_behavior": "OneDirection",
    #                     "is_active": True,
    #                 },
    #             ]

    #             relationships_created = 0
    #             relationships_updated = 0

    #             # Check existing relationships in TOM model
    #             existing_tom_relationships = {}
    #             for rel in tom_model.model.Relationships:
    #                 rel_key = f"{rel.FromTable.Name}[{rel.FromColumn.Name}] -> {rel.ToTable.Name}[{rel.ToColumn.Name}]"
    #                 existing_tom_relationships[rel_key] = rel

    #             for rel_config in relationships:
    #                 rel_key = f"{rel_config['from_table']}[{rel_config['from_column']}] -> {rel_config['to_table']}[{rel_config['to_column']}]"

    #                 if rel_key in existing_tom_relationships:
    #                     # Update existing relationship properties
    #                     try:
    #                         existing_rel = existing_tom_relationships[rel_key]
    #                         # Update properties if needed
    #                         print(f"    Updated: {rel_key}")
    #                         relationships_updated += 1
    #                     except Exception as e:
    #                         print(f"    Failed to update {rel_key}: {str(e)[:50]}...")
    #                 else:
    #                     # Create new relationship
    #                     try:
    #                         tom_model.add_relationship(**rel_config)
    #                         print(f"    Created: {rel_key}")
    #                         relationships_created += 1
    #                     except Exception as e:
    #                         print(f"    Failed to create {rel_key}: {str(e)[:50]}...")

    #             print(
    #                 f"    Summary: Created {relationships_created}, Updated {relationships_updated}"
    #             )
    #             return (relationships_created + relationships_updated) > 0

    #     except Exception as e:
    #         print(f"    TOM relationship operations failed: {str(e)[:100]}...")
    #         self._print_relationship_instructions()
    #         return False

    # def _create_semantic_model_measures(self):
    #     """Create or update measures with proper Fabric authentication"""
    #     print("    Checking existing measures...")

    #     # Get detailed status of each measure
    #     measure_status = self._check_measures_exist_via_fabric()

    #     if not measure_status:
    #         print("    Could not determine measure status - proceeding with TOM operations")

    #     # Determine what needs to be done
    #     missing_measures = [k for k, v in measure_status.items() if not v]
    #     existing_measures = [k for k, v in measure_status.items() if v]

    #     if not missing_measures and existing_measures:
    #         print(
    #             f"    All {len(existing_measures)} measures exist - will update with latest definitions"
    #         )
    #     elif missing_measures:
    #         print(
    #             f"    Need to create {len(missing_measures)} measures and update {len(existing_measures)} existing ones"
    #         )

    #     # Setup working Fabric authentication for TOM
    #     print("    Setting up Fabric authentication for TOM...")
    #     auth_success = self._setup_fabric_auth_for_tom()
    #     if not auth_success:
    #         print("    Authentication setup failed - falling back to manual instructions")
    #         self._print_measure_instructions()
    #         return False

    #     # Attempt TOM operations for creating/updating measures
    #     try:
    #         from sempy_labs.tom import connect_semantic_model

    #         print("    Connecting to semantic model with Fabric auth...")
    #         with connect_semantic_model(
    #             dataset=self.semantic_model_name, readonly=False, workspace=self.workspace_name
    #         ) as tom_model:
    #             measures = [
    #                 {
    #                     "name": "Total Operations",
    #                     "expression": "COUNTROWS(log.monitoring_log)",
    #                     "format_string": "#,##0",
    #                     "display_folder": "Core Metrics",
    #                 },
    #                 {
    #                     "name": "Total Rows Changed",
    #                     "expression": "SUM(log.monitoring_log[rows_changed])",
    #                     "format_string": "#,##0",
    #                     "display_folder": "Core Metrics",
    #                 },
    #                 {
    #                     "name": "Average Execution Time",
    #                     "expression": "AVERAGE(log.monitoring_log[execution_time])",
    #                     "format_string": '#,##0.00 "seconds"',
    #                     "display_folder": "Performance Metrics",
    #                 },
    #                 {
    #                     "name": "Error Count",
    #                     "expression": "CALCULATE(COUNTROWS(log.monitoring_log), NOT(ISBLANK(log.monitoring_log[error_message])))",
    #                     "format_string": "#,##0",
    #                     "display_folder": "Quality Metrics",
    #                 },
    #                 {
    #                     "name": "Success Rate",
    #                     "expression": "DIVIDE(COUNTROWS(FILTER(log.monitoring_log, ISBLANK(log.monitoring_log[error_message]))), COUNTROWS(log.monitoring_log), 0)",
    #                     "format_string": "0.0%",
    #                     "display_folder": "Quality Metrics",
    #                 },
    #                 {
    #                     "name": "Operations Today",
    #                     "expression": 'CALCULATE(COUNTROWS(log.monitoring_log), log.monitoring_log[date_stamp] = FORMAT(TODAY(), "YYYY-MM-DD"))',
    #                     "format_string": "#,##0",
    #                     "display_folder": "Time Intelligence",
    #                 },
    #                 {
    #                     "name": "Unique Tables",
    #                     "expression": "DISTINCTCOUNT(log.monitoring_log[table_name])",
    #                     "format_string": "#,##0",
    #                     "display_folder": "Core Metrics",
    #                 },
    #                 {
    #                     "name": "Unique Notebooks",
    #                     "expression": "DISTINCTCOUNT(log.monitoring_log[notebook_name])",
    #                     "format_string": "#,##0",
    #                     "display_folder": "Core Metrics",
    #                 },
    #             ]

    #             target_table = None
    #             for table in tom_model.model.Tables:
    #                 if table.Name == "log.monitoring_log":
    #                     target_table = table
    #                     break

    #             if not target_table:
    #                 print("    Table 'log.monitoring_log' not found in model")
    #                 self._print_measure_instructions()
    #                 return False

    #             existing_tom_measures = [m.Name for m in target_table.Measures]
    #             measures_created = 0
    #             measures_updated = 0

    #             for measure_config in measures:
    #                 measure_name = measure_config["name"]

    #                 if measure_name in existing_tom_measures:
    #                     # Update existing measure with latest definition
    #                     try:
    #                         existing_measure = target_table.Measures[measure_name]
    #                         existing_measure.Expression = measure_config["expression"]
    #                         existing_measure.FormatString = measure_config["format_string"]
    #                         existing_measure.DisplayFolder = measure_config["display_folder"]
    #                         print(f"    Updated: {measure_name}")
    #                         measures_updated += 1
    #                     except Exception as e:
    #                         print(f"    Failed to update {measure_name}: {str(e)[:50]}...")
    #                 else:
    #                     # Create new measure
    #                     try:
    #                         tom_model.add_measure(
    #                             table_name="log.monitoring_log",
    #                             measure_name=measure_config["name"],
    #                             expression=measure_config["expression"],
    #                             format_string=measure_config["format_string"],
    #                             display_folder=measure_config["display_folder"],
    #                         )
    #                         print(f"    Created: {measure_name}")
    #                         measures_created += 1
    #                     except Exception as e:
    #                         print(f"    Failed to create {measure_name}: {str(e)[:50]}...")

    #             print(f"    Summary: Created {measures_created}, Updated {measures_updated}")
    #             return (measures_created + measures_updated) > 0

    #     except Exception as e:
    #         print(f"    TOM measures operations failed: {str(e)[:100]}...")
    #         self._print_measure_instructions()
    #         return False

    def _print_relationship_instructions(self):
        """Print manual relationship creation instructions"""
        print("    Create these relationships manually in Power BI:")
        print("      log.monitoring_log[date_stamp] -> log.dim_date[date_key]")
        print("      log.monitoring_log[time_stamp] -> log.dim_time[time_key]")

    def _print_measure_instructions(self):
        """Print instructions for manual measure creation"""
        print("    Create these measures manually in Power BI:")
        print("      • Total Operations = COUNTROWS(log.monitoring_log)")
        print("      • Total Rows Changed = SUM(log.monitoring_log[rows_changed])")
        print("      • Average Execution Time = AVERAGE(log.monitoring_log[execution_time])")
        print(
            "      • Error Count = CALCULATE(COUNTROWS(log.monitoring_log), NOT(ISBLANK(log.monitoring_log[error_message])))"
        )
        print(
            "      • Success Rate = DIVIDE(COUNTROWS(FILTER(log.monitoring_log, ISBLANK(log.monitoring_log[error_message]))), COUNTROWS(log.monitoring_log), 0)"
        )
        print(
            '      • Operations Today = CALCULATE(COUNTROWS(log.monitoring_log), log.monitoring_log[date_stamp] = FORMAT(TODAY(), "YYYY-MM-DD"))'
        )
        print("      • Unique Tables = DISTINCTCOUNT(log.monitoring_log[table_name])")
        print("      • Unique Notebooks = DISTINCTCOUNT(log.monitoring_log[notebook_name])")

    def log_operation(
        self,
        notebook_name: str,
        table_name: str,
        operation_type: str,
        rows_before: int = 0,
        rows_after: int = 0,
        execution_time: Union[float, Decimal] = 0.0,
        message: str = None,
        error_message: str = None,
        user_name: str = None,
        custom_timestamp: datetime = None,
        # Partial loading parameters
        domain: str = None,
        deleted_combinations: str = None,
        source_file: str = None,
        manifest_file: str = None,
        manifest_package: str = None,
        status: str = None,
        batchid: int = None,
    ):
        """Log a data operation - always appends, never overwrites"""

        if custom_timestamp:
            now = custom_timestamp
        else:
            now = datetime.now()
        
        # Extract layer from schema (bronze/silver/gold) - part before first dot
        layer = None
        if table_name and "." in table_name:
            layer = table_name.split(".")[0].lower()  # e.g., "bronze.opr_finishedzip" -> "bronze"
        
        # Extract domain from table name if not provided
        if not domain and table_name and "." in table_name:
            table_part = table_name.split(".")[-1]  # Get part after schema (e.g., d_fct_customer)
            
            # Skip d_ or f_ prefix if present (table type markers, not part of domain)
            if table_part.startswith("d_") or table_part.startswith("f_"):
                table_part = table_part[2:]  # Remove d_/f_ prefix
            
            # Extract domain from remaining part (first segment before underscore)
            if "_" in table_part:
                domain = table_part.split("_")[0].upper()  # e.g., fct_customer -> FCT
            elif len(table_part) >= 3:
                domain = table_part[:3].upper()

        # Auto-detect batchid from target table's ins_batchid if not provided
        if batchid is None and table_name:
            try:
                _tbl_df = self.spark.table(table_name)
                if "ins_batchid" in _tbl_df.columns:
                    _bid_row = _tbl_df.select(F.col("ins_batchid")).orderBy(F.col("ins_batchid").desc()).limit(1).first()
                    if _bid_row and _bid_row[0] is not None:
                        batchid = int(_bid_row[0])
            except Exception:
                pass

        date_stamp = now.strftime("%Y-%m-%d")
        time_stamp = now.strftime("%H:%M:%S")

        log_data = [
            (
                batchid,
                manifest_package,
                manifest_file,
                notebook_name,
                table_name,
                operation_type,
                user_name or get_current_user(),
                int(rows_before),
                int(rows_after),
                int(rows_after - rows_before),
                Decimal(str(execution_time)),
                message,
                error_message,
                date_stamp,
                time_stamp,
                None,
                # Partial loading columns
                domain,
                deleted_combinations,
                source_file,
                status,
                # Layer (data layer: bronze/silver/gold)
                layer,
            )
        ]

        schema = StructType(
            [
                StructField("batchid", IntegerType(), True),
                StructField("manifest_package", StringType(), True),
                StructField("manifest_file", StringType(), True),
                StructField("notebook_name", StringType(), True),
                StructField("table_name", StringType(), True),
                StructField("operation_type", StringType(), True),
                StructField("user_name", StringType(), True),
                StructField("rows_before", LongType(), True),
                StructField("rows_after", LongType(), True),
                StructField("rows_changed", LongType(), True),
                StructField("execution_time", DecimalType(10, 6), True),
                StructField("message", StringType(), True),
                StructField("error_message", StringType(), True),
                StructField("date_stamp", StringType(), True),
                StructField("time_stamp", StringType(), True),
                StructField("timestamp", TimestampType(), True),
                # Partial loading columns
                StructField("domain", StringType(), True),
                StructField("deleted_combinations", StringType(), True),
                StructField("source_file", StringType(), True),
                StructField("status", StringType(), True),
                # Layer (data layer: bronze/silver/gold)
                StructField("layer", StringType(), True),
            ]
        )

        log_df = self.spark.createDataFrame(log_data, schema)

        if custom_timestamp:
            log_df = log_df.withColumn("timestamp", lit(custom_timestamp))
        else:
            log_df = log_df.withColumn("timestamp", current_timestamp())

        log_df.write.format("delta").option("mergeSchema", "true").mode("append").save(
            self.log_path
        )

        # if operation_type == "PARTIAL_LOADING" and status:
        #     print(
        #         f"Logged: {operation_type} [{status}] on {table_name} ({rows_after - rows_before:+,} rows) [{date_stamp}]"
        #     )
        # else:
        #     print(
        #         f"Logged: {operation_type} on {table_name} ({rows_after - rows_before:+,} rows) [{date_stamp}]"
        #     )

    def get_logs(self, table_name: str = None, operation_type: str = None, limit: int = 100):
        """Get monitoring logs with optional filters"""
        df = self.spark.read.format("delta").load(self.log_path)

        if table_name:
            df = df.filter(df.table_name == table_name)
        if operation_type:
            df = df.filter(df.operation_type == operation_type)

        return df.orderBy(df.timestamp.desc()).limit(limit)

    def show_recent(self, limit: int = 10):
        """Show recent operations"""
        self.get_logs(limit=limit).show(truncate=False)

    def get_statistics(self):
        """Get statistics about the monitoring logs"""
        try:
            df = self.spark.read.format("delta").load(self.log_path)

            total_records = df.count()
            unique_notebooks = df.select("notebook_name").distinct().count()
            unique_tables = df.select("table_name").distinct().count()
            unique_operations = df.select("operation_type").distinct().count()

            print("\nMonitoring Statistics:")
            print(f"  Total Records: {total_records:,}")
            print(f"  Unique Notebooks: {unique_notebooks}")
            print(f"  Unique Tables: {unique_tables}")
            print(f"  Unique Operations: {unique_operations}")

            return {
                "total_records": total_records,
                "unique_notebooks": unique_notebooks,
                "unique_tables": unique_tables,
                "unique_operations": unique_operations,
            }

        except Exception as e:
            print(f"Could not get statistics: {e}")
            return None

    def cleanup_old_logs(self, days_to_keep: int = 90):
        """Remove logs older than specified days"""
        try:
            from delta.tables import DeltaTable

            cutoff_date = datetime.now() - timedelta(days=days_to_keep)
            cutoff_str = cutoff_date.strftime("%Y-%m-%d")

            df = self.spark.read.format("delta").load(self.log_path)
            before_count = df.count()
            old_records = df.filter(df.date_stamp < cutoff_str).count()

            if old_records > 0:
                print(f"Removing {old_records:,} records older than {cutoff_str}")

                delta_table = DeltaTable.forPath(self.spark, self.log_path)
                delta_table.delete(f"date_stamp < '{cutoff_str}'")

                delta_table.vacuum(0)

                print(f"Cleanup complete. Kept {before_count - old_records:,} records")
            else:
                print(f"No records older than {cutoff_str} to remove")

        except Exception as e:
            print(f"Could not cleanup logs: {e}")

    def enhance_semantic_model(self):
        """Add relationships and measures to existing semantic model"""
        print("\nEnhancing Semantic Model")
        print("=" * 40)

        if not self._semantic_model_exists():
            print(
                "Semantic model doesn't exist. Create it first with create_semantic_model_when_ready()"
            )
            return False

        print("Model: " + self.semantic_model_name)

        # Check and create relationships
        # print("\nChecking Relationships...")
        # relationships_success = self._create_semantic_model_relationships()

        # Check and create measures
        print("\nChecking Measures...")
        measures_success = self._create_semantic_model_measures()

        # Try to refresh the model
        print("\nRefreshing Model...")
        try:
            self._setup_fabric_auth_for_tom()
            fabric.refresh_dataset(dataset=self.semantic_model_name, workspace=self.workspace_name)
            print("Semantic model refreshed successfully")
        except Exception as e:
            print(f"Refresh failed: {e}")

        print("\nSemantic model enhancement completed!")
        return True

    def create_semantic_model_when_ready(self, max_wait_minutes=5):
        print("\nCreating Semantic Model When Ready")
        print("=" * 50)
        max_retries = max_wait_minutes * 6
        for attempt in range(max_retries):
            print(f"\nAttempt {attempt + 1}/{max_retries}")

            if self._verify_tables_ready(max_retries=3, wait_seconds=1):
                print("\nTables ready - creating semantic model...")
                return self._create_semantic_model()
            elif attempt < max_retries - 1:
                print("Tables not ready, waiting 10 seconds...")
                time.sleep(10)
            else:
                print(f"Tables still not ready after {max_wait_minutes} minutes")
                return False

        return False

    def show_complete_status(self):
        print("\n" + "=" * 60)
        print("FABRIC LOGGING FRAMEWORK STATUS v3.4.3")
        print("=" * 60)

        print(f"\nProject: {self.project_name}")
        print(f"Lakehouse: {self.lakehouse_name}")
        print(f"Semantic Model: {self.semantic_model_name}")
        print(f"Workspace: {self.workspace_name}")

        print("\nTables Status:")
        try:
            df = self.spark.read.format("delta").load(self.log_path)
            print(f"  log.monitoring_log: {df.count():,} records")

            date_path = self.log_path.replace("/log/audit_operation_log", "/log/dim_date")
            date_df = self.spark.read.format("delta").load(date_path)
            max_date = date_df.agg({"date_key": "max"}).collect()[0][0]
            print(f"  log.dim_date: {date_df.count():,} dates (up to {max_date})")

            time_path = self.log_path.replace("/log/audit_operation_log", "/log/dim_time")
            time_df = self.spark.read.format("delta").load(time_path)
            print(f"  log.dim_time: {time_df.count():,} time slots")

        except Exception as e:
            print(f"  Error reading tables: {e}")

        print("\nSemantic Model Status:")
        if self._semantic_model_exists():
            print(f"  Model exists: {self.semantic_model_name}")

            # Check relationships and measures status
            try:
                print("\nRelationship Status:")
                self._check_relationships_exist_via_fabric()

                print("\nMeasures Status:")
                self._check_measures_exist_via_fabric()
            except:
                print("  Could not check relationships/measures status")
        else:
            print(f"  Model not found: {self.semantic_model_name}")
            print("  Use create_semantic_model_when_ready() to create")

        print("\n" + "=" * 60)
        print("Available Operations:")
        print("  • logger.log_operation(...) - Log a new operation")
        print("  • logger.show_recent(10) - Show recent logs")
        print("  • logger.get_statistics() - Show statistics")
        print("  • logger.enhance_semantic_model() - Add relationships & measures")
        print("  • logger.create_semantic_model_when_ready() - Create semantic model safely")
        print("=" * 60 + "\n")

    def _print_final_summary(self):
        """Print the final configuration summary"""
        if _show_fabric_logger_output:
            print("\n" + "=" * 60)
            print("\nProject Configuration:")
            print(f"  • Project Name: {self.project_name}")
            print(f"  • Lakehouse: {self.lakehouse_name}")
            print(f"  • Semantic Model: {self.semantic_model_name}")
            print(f"  • Workspace ID: {self.workspace_id}")
            print(f"  • Using current lakehouse: {self.lakehouse_id[:8]}...")
            
            # Print schema status
            if hasattr(self, 'schema_status'):
                for schema, exists in self.schema_status:
                    if exists:
                        print(f"  ✓ Schema exists: {schema}")
            
            print("\n" + "=" * 60)
            print("\nConfiguration Summary:")
            print(f"  • Project: {self.project_name}")
            print(f"  • Lakehouse: {self.lakehouse_name}")
            print(f"  • Semantic Model: {self.semantic_model_name}")
            print(f"  • Workspace:  {self.workspace_name}")
            print("=" * 60 + "\n")

    

    #updates
    


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Utility Functions

# CELL ********************

def get_current_user() -> str:
    """Get current user"""
    try:
        return getpass.getuser()
    except:
        return "fabric_user"


def time_operation(func):
    """Decorator to time operations"""

    def wrapper(*args, **kwargs):
        start_time = time.time()
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            return result, execution_time, None
        except Exception as e:
            execution_time = time.time() - start_time
            return None, execution_time, str(e)

    return wrapper


# ============================================================
# CONVENIENCE WRAPPER FUNCTION FOR LAYER LOGGING
# ============================================================

def log_layer(
    layer: str,
    status: str,
    domain: str = None,
    error_message: str = None,
) -> int:
    """
    Log the status of a silver or gold layer for packages.
    This is a convenience wrapper that uses the singleton FabricLogger.
    
    - status='START': Updates all PENDING packages to IN_PROGRESS, sets {layer}_start
    - status='SUCCESS': Updates all IN_PROGRESS packages to SUCCESS, sets {layer}_end
    - status='FAILED': Updates all IN_PROGRESS packages to FAILED, sets {layer}_end and error info
    
    Parameters:
    -----------
    layer : str
        Layer name: 'SILVER' or 'GOLD'
    status : str
        Status: 'START', 'SUCCESS', or 'FAILED'
    domain : str, optional
        Filter by domain (e.g., 'OPR', 'FCT'). If not provided, updates all domains.
    error_message : str, optional
        Error message if status is 'FAILED'
        
    Returns:
    --------
    int : Number of packages updated
        
    Example:
    --------
    # At the start of your silver DAG notebook:
    %run EXEC/nb_utils_logging
    logger = get_fabric_logger(project_name="lkh_customer0_schema_enabled")
    
    log_layer(layer="SILVER", status="START")
    
    # ... run your silver transformations via DAG ...
    
    log_layer(layer="SILVER", status="SUCCESS")
    
    # Or on failure:
    log_layer(layer="SILVER", status="FAILED", error_message="Validation failed")
    
    # Filter by domain:
    log_layer(layer="SILVER", status="START", domain="OPR")
    """
    try:
        fabric_logger = get_fabric_logger()
        if fabric_logger is None:
            print(f"[LAYER] FabricLogger not initialized. Call get_fabric_logger(project_name='...') first.")
            return 0
        
        return fabric_logger.log_layer(
            layer=layer,
            status=status,
            domain=domain,
            error_message=error_message,
        )
    except Exception as e:
        print(f"[LAYER] Error in log_layer: {e}")
        return 0

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
