# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_replace_latest
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: replace_latest
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## replace_latest

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def replace_latest(cfg):
    tgt = cfg["TARGET_TABLE"]
    src_sql = cfg["SOURCE_SQL"]

    ensure_table_exists(tgt, src_sql)

    try:
        df = spark.sql(src_sql)
    except Exception as e:
        stop_notebook(f"Script execution failed for the query: {src_sql}\nError: {str(e)}")

    # Overwrite table and schema with latest definition
    (
        df.write
          .format("delta")
          .mode("overwrite")
          .option("overwriteSchema", "true")
          .option("partitionOverwriteMode", "static")
          .saveAsTable(tgt)
    )

    logger.info("replace_latest complete")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_replace_latest")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
