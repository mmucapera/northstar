# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_repair
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: _repair_if_corrupted
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Delta Table Auto-Repair
# Detects and recovers from `DELTA_VERSIONS_NOT_CONTIGUOUS` corruption by reading raw Parquet files and rebuilding the Delta log.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _repair_if_corrupted(table_name: str) -> bool:
    """
    Detect Delta log corruption (non-contiguous versions).
    If found, recover data from raw Parquet files and rebuild the table
    with a clean Delta log. Returns True if repair was performed.
    """
    if not spark.catalog.tableExists(table_name):
        logger.info(f"[REPAIR] Table {table_name} does not exist — skipping corruption check")
        return False

    try:
        spark.table(table_name)
        return False
    except Exception as e:
        if "DELTA_VERSIONS_NOT_CONTIGUOUS" not in str(e):
            raise

        logger.warning(
            f"[REPAIR] Delta log corruption detected for {table_name}. "
            f"Attempting data-preserving recovery..."
        )

        # Extract and log the Delta error detail
        import re
        version_match = re.search(r"\[DELTA_VERSIONS_NOT_CONTIGUOUS\] Versions \(\d+, \d+\) are not contiguous", str(e))
        if version_match:
            logger.info(f"org.apache.spark.sql.delta.DeltaIllegalStateException: {version_match.group(0)}")

        # 1. Get table location (Fabric-compatible)
        location = None

        try:
            desc_rows = spark.sql(f"DESCRIBE FORMATTED {table_name}").collect()
            for row in desc_rows:
                if row[0] and str(row[0]).strip().lower() == "location":
                    location = str(row[1]).strip()
                    break
        except Exception:
            pass

        if not location:
            try:
                parts = table_name.split(".")
                db, tbl = (parts[0], parts[1]) if len(parts) == 2 else ("default", parts[0])
                show_rows = spark.sql(f"SHOW TABLE EXTENDED IN {db} LIKE '{tbl}'").collect()
                for row in show_rows:
                    info = str(row.asDict().get("information", ""))
                    for line in info.split("\n"):
                        if "location:" in line.lower():
                            location = line.split(":", 1)[-1].strip()
                            break
            except Exception:
                pass

        if not location:
            raise RuntimeError(
                f"[REPAIR] Delta log corrupted for {table_name} and could not resolve storage location. "
                f"Manual recovery required."
            )

        # 2. Read raw Parquet files (bypasses Delta log entirely)
        try:
            df_raw = spark.read.parquet(location)
            recovered_rows = df_raw.count()
        except Exception:
            raise RuntimeError(
                f"[REPAIR] Delta log corrupted for {table_name} and Parquet read failed. "
                f"Manual recovery required."
            )

        # Extract short path for logging (Tables/... portion)
        short_path = location
        tables_idx = location.find("Tables/")
        if tables_idx != -1:
            short_path = location[tables_idx:]

        logger.info(f"[REPAIR] Recovered {recovered_rows:,} rows {short_path}")

        # 3. Write recovered data to a temporary backup table
        backup_table = f"{table_name}__recovery_backup"
        logger.info(f"[REPAIR] Writing backup to {backup_table}")
        (
            df_raw.write.format("delta").mode("overwrite")
            .option("overwriteSchema", "true")
            .option("partitionOverwriteMode", "static")
            .saveAsTable(backup_table)
        )

        backup_count = spark.table(backup_table).count()
        if backup_count != recovered_rows:
            raise RuntimeError(
                f"[REPAIR] Backup row count mismatch: expected {recovered_rows}, got {backup_count}. "
                f"Aborting recovery for {table_name}."
            )

        # 4. Drop the corrupted table and rebuild from backup
        spark.sql(f"DROP TABLE IF EXISTS {table_name}")
        logger.info(f"[REPAIR] Dropped corrupted table {table_name}")

        spark.table(backup_table).write.format("delta").mode("overwrite").saveAsTable(table_name)
        final_count = spark.table(table_name).count()
        logger.info(f"[REPAIR] Rebuilt {table_name} with {final_count:,} rows (clean Delta log)")

        # 5. Clean up backup
        spark.sql(f"DROP TABLE IF EXISTS {backup_table}")
        logger.info(f"[REPAIR] Recovery complete for {table_name}")

        return True

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_repair")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
