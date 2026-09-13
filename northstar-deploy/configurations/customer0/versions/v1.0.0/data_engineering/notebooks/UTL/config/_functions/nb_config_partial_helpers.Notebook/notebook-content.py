# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_partial_helpers
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: _normalize_domain, _extract_package_folder_from_df, _auto_track_package_entity, _log_partial_load_unified, _get_current_notebook_name
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Partial Loading — Utilities
# Logging, domain normalization, and package-tracking helpers used by `delete_insert` and `delete_insert_manifest`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _normalize_domain(domain: str) -> str:
    """
    Normalize domain names from manifest to standard domain names.
    SP (Sales Planning) -> OPR
    DP (Demand Planning) -> FCT
    """
    if not domain:
        return domain
    
    domain_upper = str(domain).upper().strip()
    if domain_upper == "SP":
        return "OPR"
    elif domain_upper == "DP":
        return "FCT"
    else:
        return domain

def _extract_package_folder_from_df(df) -> str:
    """
    Extract package folder name from DataFrame.

    Supports:
    - direct folder name
    - full file path containing YYYYMMDD_HHMMSS_*
    """
    try:
        import re

        def _find_pkg(text: str):
            if not text:
                return None
            text = str(text)
            m = re.search(r"(\d{8}_\d{6}_[A-Za-z0-9][A-Za-z0-9_]+)", text)
            return m.group(1) if m else None

        if "manifest_package" in df.columns:
            samples = (
                df.select("manifest_package")
                  .dropna()
                  .distinct()
                  .limit(50)
                  .rdd.map(lambda r: r[0])
                  .collect()
            )
            for v in samples:
                pkg = _find_pkg(v)
                if pkg:
                    return pkg

        if "source_folder" in df.columns:
            samples = (
                df.select("source_folder")
                  .dropna()
                  .distinct()
                  .limit(50)
                  .rdd.map(lambda r: r[0])
                  .collect()
            )
            for v in samples:
                pkg = _find_pkg(v)
                if pkg:
                    return pkg

        if "sourcefile" in df.columns:
            samples = (
                df.select("sourcefile")
                  .dropna()
                  .distinct()
                  .limit(50)
                  .rdd.map(lambda r: r[0])
                  .collect()
            )
            for v in samples:
                pkg = _find_pkg(v)
                if pkg:
                    return pkg

        return None

    except Exception:
        return None

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _auto_track_package_entity(
    package_name: str,
    entity_name: str,
    layer: str,
    status: str,
    rows: int = None,
    execution_time: float = None,
    batchid: int = None,

):
    """
    Auto-track a package entity load. Creates or updates audit_package_lifecycle.
    If package_name contains multiple comma-separated packages, tracks each individually.
    """
    try:
        if not package_name:
            logger.info("[PACKAGE-TRACK] package_name is empty, skipping")
            return

        # Handle comma-separated package names (e.g., "SP_Full_One1_xxx,SP_Full_One2_xxx")
        if "," in package_name:
            individual_packages = [p.strip() for p in package_name.split(",") if p.strip()]
            logger.info(f"[PACKAGE-TRACK] Multiple packages detected ({len(individual_packages)}), tracking each individually")
            for pkg in individual_packages:
                _auto_track_package_entity(
                    package_name=pkg,
                    entity_name=entity_name,
                    layer=layer,
                    status=status,
                    rows=rows,
                    execution_time=execution_time,
                    batchid=batchid,
                )
            return

        fabric_logger = get_fabric_logger()
        if fabric_logger is None:
            logger.info(f"[PACKAGE-TRACK] fabric_logger is None, skipping package tracking for {package_name}")
            return
        
        # Skip if package_name looks like a parquet file (wrong extraction)
        if package_name and package_name.endswith(".parquet"):
            # Strip .parquet and use as package name
            package_name = package_name.replace(".parquet", "")
        
        if not package_name:
            logger.info("[PACKAGE-TRACK] package_name is empty, skipping")
            return
        
        logger.info(f"[PACKAGE-TRACK] Tracking: {package_name} | entity: {entity_name} | layer: {layer} | status: {status}")
        
        # Normalize layer
        layer_lower = layer.lower()
        if layer_lower not in ("bronze", "silver", "gold"):
            # Try to infer from entity_name prefix
            if "." in entity_name:
                prefix = entity_name.split(".")[0].lower()
                if prefix in ("bronze", "silver", "gold"):
                    layer_lower = prefix
                else:
                    layer_lower = "bronze"  # default
            else:
                layer_lower = "bronze"
        
        # Check if package record exists for today
        load_date = datetime.now().strftime("%Y-%m-%d")
        package_path = fabric_logger._get_package_summary_path()
        
        try:
            df = spark.read.format("delta").load(package_path)
            existing = df.filter(
                f"manifest_package = '{package_name}' AND load_date = '{load_date}'"
            ).first()
        except Exception as read_err:
            logger.info(f"[PACKAGE-TRACK] Could not read package table (may not exist yet): {read_err}")
            existing = None
        
        if existing is None:
            # Create new package record
            manifest_package = package_name  # Simplified: use package_name as manifest_package
            package_id = fabric_logger.start_package(
                manifest_package=manifest_package,
                batchid = batchid,
            )
            
            if package_id and status in ("SUCCESS", "COMPLETED"):
                fabric_logger.update_package_layer(
                    manifest_package=package_id,
                    layer=layer_lower,
                    status="SUCCESS",
                    end_time=datetime.now(),
                )
                if layer_lower == "gold":
                    fabric_logger.complete_package(
                        manifest_package=package_id,
                        total_execution_time=execution_time,
                    )
        else:
            # Update existing package record
            package_id = existing["manifest_package"]
            
            if status == "IN_PROGRESS":
                fabric_logger.update_package_layer(
                    manifest_package=package_id,
                    layer=layer_lower,
                    status="IN_PROGRESS",
                    start_time=datetime.now(),
                )
            elif status in ("SUCCESS", "COMPLETED"):
                fabric_logger.update_package_layer(
                    manifest_package=package_id,
                    layer=layer_lower,
                    status="SUCCESS",
                    end_time=datetime.now(),
                )
                # When gold completes, finalize the package with total_execution_time
                if layer_lower == "gold":
                    total_time = None
                    try:
                        created = existing["created_at"] or existing["start_time"]
                        if created:
                            total_time = (datetime.now() - created).total_seconds()
                    except Exception:
                        pass
                    fabric_logger.complete_package(
                        manifest_package=package_id,
                        total_execution_time=total_time,
                    )
        
    except Exception as e:
        # Auto-tracking must never break ingestion
        logger.info(f"[WARN] Auto package tracking failed: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _log_partial_load_unified(
    notebook_name: str,
    table_name: str,
    domain: str,
    deleted_combinations: str,
    source_file: str,
    manifest_file: str = None,
    manifest_package: str = None,
    status: str = None,
    message: str = None,
    rows_before: int = 0,
    rows_after: int = 0,
    rows_deleted: int = 0,
    rows_inserted: int = 0,
    execution_time: float = 0.0,
    error_message: str = None,
    operation_type: str = "PARTIAL_LOADING",
    delete_statement: str = None,
    batchid: str = None,
):
    try:
        fabric_logger = get_fabric_logger()
        if fabric_logger is None:
            # Fallback to legacy logging if FabricLogger is not available
            log_partial_load(table_name, domain, deleted_combinations, 
                           source_file, status, message)
            return
        
        # Get notebook name from context if not provided
        if not notebook_name or notebook_name == "unknown":
            notebook_name = _get_current_notebook_name()
        
        # Include delete statement in message if provided

        if delete_statement:
            deleted_combinations = f"{deleted_combinations}\n\nDELETE STATEMENT:\n{delete_statement}"
        
        fabric_logger.log_operation(
            notebook_name=notebook_name,
            table_name=table_name,
            operation_type=operation_type,
            rows_before=rows_before,
            rows_after=rows_after,
            execution_time=execution_time,
            message=message,
            error_message=error_message,
            # Partial loading specific parameters
            domain=domain,
            deleted_combinations=deleted_combinations,
            source_file=source_file,
            manifest_file=manifest_file,
            manifest_package=manifest_package,
            status=status,
            batchid=batchid,
        )
        
    except Exception as e:
        # Logging must never break ingestion
        logger.info(f"[WARN] Failed to log partial load to unified table: {e}")
        # Try legacy fallback
        try:
            log_partial_load(table_name, domain, deleted_combinations, 
                           source_file, status, message)
        except:
            pass

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _get_current_notebook_name() -> str:
    """Get current notebook name from Fabric context with robust fallbacks"""
    try:
        # Try different context keys used in Fabric
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
            
    except Exception as e:
        pass
    
    return "unknown_notebook"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_partial_helpers")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
