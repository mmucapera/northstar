# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_optimize
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: run_optimize, optimize_monitoring_log
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def run_optimize(table: str):
  if not spark.catalog.tableExists(table):
      logger.error(f"[OPTIMIZE] Table does not exist: {table} (skipping)")
      return
  logger.info(f"[OPTIMIZE] Optimizing {table}")

  # ── 1. Set Delta table properties ──────────────────────────────────────
  try:
      spark.sql(f"""
          ALTER TABLE {table}
          SET TBLPROPERTIES (
              'delta.autoOptimize.optimizeWrite' = 'true',
              'delta.autoOptimize.autoCompact' = 'true',
              'delta.dataSkippingNumIndexedCols' = '10',
              'delta.deletedFileRetentionDuration' = 'interval 7 days'
          )
      """)
      logger.info(f"[OPTIMIZE] Table properties set for {table}")
  except Exception as e:
      logger.warning(f"[OPTIMIZE] Could not set table properties for {table}: {e}")

  # ── 2. OPTIMIZE with Z-ORDER ──────────────────────────────────────────
  # Pick Z-ORDER columns based on which columns exist in the table.
  # Priority: Partitionkey (OPR facts) > Forecastcycleid+Forecastitemid_key
  #           > Forecastitemid_key+Timeframe_key (fct_saleshistory)
  try:
      cols_lower = {c.lower(): c for c in spark.table(table).columns}
      zorder_cols = []

      if "partitionkey" in cols_lower:
          zorder_cols = [cols_lower["partitionkey"]]
      elif "forecastcycleid" in cols_lower and "forecastitemid_key" in cols_lower:
          zorder_cols = [cols_lower["forecastcycleid"], cols_lower["forecastitemid_key"]]
      elif "forecastitemid_key" in cols_lower and "timeframe_key" in cols_lower:
          zorder_cols = [cols_lower["forecastitemid_key"], cols_lower["timeframe_key"]]

      if zorder_cols:
          zorder_str = ", ".join(zorder_cols)
          spark.sql(f"OPTIMIZE {table} ZORDER BY ({zorder_str})")
          logger.info(f"[OPTIMIZE] OPTIMIZE + ZORDER BY ({zorder_str}) completed for {table}")
      else:
          spark.sql(f"OPTIMIZE {table}")
          logger.info(f"[OPTIMIZE] OPTIMIZE completed for {table} (no Z-ORDER candidates)")
  except Exception as e:
      logger.warning(f"[OPTIMIZE] OPTIMIZE failed for {table}: {e}")

  # ── 3. VACUUM ─────────────────────────────────────────────────────────
  try:
      spark.sql(f"VACUUM {table}")
      logger.info(f"[OPTIMIZE] VACUUM completed for {table}")
  except Exception as e:
      logger.warning(f"[OPTIMIZE] VACUUM failed for {table}: {e}")

  logger.info(f"[OPTIMIZE] Completed for {table}")

def optimize_monitoring_log():
  """Optimize and maintain the audit_operation_log delta table"""
  try:
      from delta.tables import DeltaTable
      
      dt = DeltaTable.forName(spark, "log.audit_operation_log")
      
      dt.optimize().executeCompaction()
      dt.vacuum(retentionHours=1440)  # 1440 hours = 60 days
      
  except Exception as e:
      logger.info(f"[WARN] Failed to optimize monitoring_log: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_optimize")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
