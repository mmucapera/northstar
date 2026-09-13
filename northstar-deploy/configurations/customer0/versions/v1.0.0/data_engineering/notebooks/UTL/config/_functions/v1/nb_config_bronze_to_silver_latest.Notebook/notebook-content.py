# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_bronze_to_silver_latest
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: bronze_to_silver_latest
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Loading Strategies
# Core data movement patterns dispatched by `framework_execute`. Each function accepts a `cfg` dictionary with `TARGET_TABLE`, `SOURCE_SQL`, `MERGE_KEYS`, and `DELETE_KEYS`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## bronze_to_silver_latest

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def bronze_to_silver_latest(cfg):
  tgt = cfg["TARGET_TABLE"]
  src_sql = cfg["SOURCE_SQL"]
  keys = cfg["MERGE_KEYS"]
  if not keys:
      raise RuntimeError(f"bronze_to_silver_latest requires MERGE_KEYS for {tgt}")
  ensure_table_exists(tgt, src_sql)
  df = spark.sql(src_sql)
  if "Load_timestamp" in df.columns:
      w = Window.partitionBy(*keys).orderBy(F.col("Load_timestamp").desc())
      df = df.withColumn("_rn", F.row_number().over(w)).filter(F.col("_rn") == 1).drop("_rn")
  else:
      df = df.dropDuplicates(keys)
  # Evolve schema first so new columns are added to the table
  evolve_schema(df, tgt)
  # Align to target schema (now possibly evolved)
  df = match_schema(df, tgt)
  view = _safe_view(tgt)
  try:
      spark.catalog.dropTempView(view)
  except Exception:
      pass
  df.createOrReplaceTempView(view)
  join = " AND ".join([f"t.{k} = s.{k}" for k in keys])
  spark.conf.set("spark.databricks.delta.merge.enableLowShuffle", "true")
  spark.sql(f"""
  MERGE INTO {tgt} t
  USING {view} s
  ON {join}
  WHEN MATCHED THEN UPDATE SET *
  WHEN NOT MATCHED THEN INSERT *
  """)
  logger.info("bronze_to_silver_latest complete")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_bronze_to_silver_latest")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
