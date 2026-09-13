# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_execute_script
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: execute_script
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## execute_script

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def execute_script(cfg):
    src_sql = cfg["SOURCE_SQL"]
    spark.sql(src_sql)
    stop_notebook(f"Script execution complete for target table")
    logger.info("Script execution complete")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_execute_script")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
