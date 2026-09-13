# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_overwrite_partition
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: overwrite_partition
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## overwrite_partition

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def overwrite_partition(cfg):
    """
    Partition-aware overwrite using Delta's replaceWhere.
    Only rewrites files that contain rows matching the current batch's
    DELETE_KEYS values (typically Sourcefile), leaving all other partitions
    intact. Significantly faster than replace_latest for incremental daily loads.
    """
    tgt = cfg["TARGET_TABLE"]
    src_sql = cfg["SOURCE_SQL"]
    partition_keys = cfg.get("DELETE_KEYS") or []

    ensure_table_exists(tgt, src_sql)

    df = spark.sql(src_sql)
    evolve_schema(df, tgt)
    df = match_schema(df, tgt)
    df.persist()

    replace_where = None
    if partition_keys:
        conditions = []
        for key in partition_keys:
            if key in df.columns:
                values = [str(r[0]) for r in df.select(key).dropna().distinct().collect()]
                if values:
                    quoted = ", ".join(f"'{v}'" for v in values)
                    conditions.append(f"{key} IN ({quoted})")
        if conditions:
            replace_where = " AND ".join(conditions)

    writer = (
        df.write
          .format("delta")
          .mode("overwrite")
          .option("overwriteSchema", "false")
    )
    if replace_where:
        writer = writer.option("replaceWhere", replace_where)
        logger.info(f"[OVERWRITE_PARTITION] replaceWhere: {replace_where}")
    else:
        logger.warning(f"[OVERWRITE_PARTITION] No replaceWhere resolved — falling back to full overwrite for {tgt}")
        writer = writer.option("overwriteSchema", "true").option("partitionOverwriteMode", "static")

    writer.saveAsTable(tgt)
    df.unpersist()
    logger.info("overwrite_partition complete")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_overwrite_partition")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
