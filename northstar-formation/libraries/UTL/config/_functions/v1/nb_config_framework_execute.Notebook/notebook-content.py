# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_framework_execute
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: framework_execute
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def framework_execute(cfg, batch_tracker: BatchTracker = None):

  import time as _time
  layer_start = _time.time()
  
  tgt = cfg.get("TARGET_TABLE")
  src_sql = cfg.get("SOURCE_SQL")
  
  # Determine layer from target table name
  layer = None
  if tgt:
      layer_prefix = tgt.split(".")[0].lower() if "." in tgt else ""
      if layer_prefix in ("bronze", "silver", "gold"):
          layer = layer_prefix
  
  # Use global batch tracker if not provided
  if batch_tracker is None:
      batch_tracker = get_batch_tracker()
  try:
      if not tgt or not src_sql:
          raise ValueError("cfg must include TARGET_TABLE and SOURCE_SQL")
      logger.info(f"[FRAMEWORK] Executing for target={tgt}")
      
      # Update batch tracker - start layer
      if batch_tracker and layer:
          batch_tracker.start_layer(layer, target_table=tgt)
      ensure_table_exists_strict(tgt, src_sql)
      _repair_if_corrupted(tgt)
      dfactor_src = spark.sql(src_sql)
      # Evolve schema before checking rows, so new columns are reflected
      evolve_schema(dfactor_src, tgt)
      dfactor_src = match_schema(dfactor_src, tgt)
      # Use head(1) instead of .count() to check emptiness (avoids full source scan)
      if len(dfactor_src.head(1)) == 0:
          logger.warning(f"[FRAMEWORK] No source rows for {tgt} — skipping (nothing to load)")
          
          if batch_tracker and layer:
              batch_tracker.complete_layer(layer, rows_processed=0, target_table=tgt)
          
          return
      # Capture row count before load (stored in cfg for notebook logging)
      cfg['_rows_before_execute'] = spark.table(tgt).count()

      # Extract manifest values from source data (all tables now carry these columns)
      src_cols_lower = {c.lower(): c for c in dfactor_src.columns}
      for _col_key, _cfg_key in [('manifest_package', '_manifest_package'), ('manifest_file', '_manifest_file')]:
          if _col_key in src_cols_lower:
              try:
                  _vals = (
                      dfactor_src.select(src_cols_lower[_col_key])
                        .dropna().distinct().limit(10)
                        .rdd.map(lambda r: str(r[0])).collect()
                  )
                  if _vals:
                      cfg[_cfg_key] = _vals[0] if len(_vals) == 1 else ','.join(_vals)
              except Exception:
                  pass

      dispatch_merge_sql(cfg)
      
      # Get final row count after load
      final_row_count = spark.table(tgt).count()
      cfg['_rows_after_execute'] = final_row_count
      layer_time = _time.time() - layer_start
      
      # Update batch tracker - complete layer
      if batch_tracker and layer:
          batch_tracker.complete_layer(layer, rows=final_row_count, target_table=tgt)
      # logger.info(f"[FRAMEWORK] SUCCESS for target={tgt} ({final_row_count:,} rows, {layer_time:.2f}s)")
      
      # Optimize monitoring log after successful operations
      try:
          optimize_monitoring_log()
      except Exception as e:
          logger.error(f"[FRAMEWORK] Log optimization failed (non-blocking): {e}")
      
      return 1
  except Exception as e:
      # If this was a fail_notebook RuntimeError, just let it propagate
      if "[NOTEBOOK_FAIL]" in str(e):
          raise
      
      # Update batch tracker - fail layer
      if batch_tracker and layer:
          batch_tracker.fail_layer(layer, error_message=str(e), target_table=tgt)
      try:
          log_daily_failure(
              notebook_name=cfg.get("NOTEBOOK_NAME", "UNKNOWN_NOTEBOOK"),
              target=tgt,
              error=str(e)
          )
      except Exception:
          pass  # logging must never break execution
      logger.exception(f"[FRAMEWORK] FAILED for target={tgt}")
      fail_notebook(f"FAILED for {tgt}: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_framework_execute")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
