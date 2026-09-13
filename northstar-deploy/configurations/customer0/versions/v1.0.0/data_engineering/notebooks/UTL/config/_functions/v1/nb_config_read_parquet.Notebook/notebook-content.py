# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_read_parquet
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: drop_rn, read_parquet_bulk
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Bronze Bulk Parquet Loader
# Discovers, reads, and unions Parquet source files into a bronze Delta table with per-package tracking and audit logging

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def drop_rn(table_name: str) -> DataFrame:
  """
  Drops column '_rn' from the given table and overwrites the table.
  Returns the modified DataFrame.
  """
  df = spark.table(table_name)
  # df.printSchema()
  df = df.drop("_rn")
  # df.printSchema()
  (
      df.write.mode("overwrite")
      .option("overwriteSchema", "true")
      .option("partitionOverwriteMode", "static")
      .saveAsTable(table_name)
  )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def read_parquet_bulk(
  domain: str,
  extract_id: str,
  search_param: str = None,
  processing_date: str = None,
  target_tbl: str = None,
  batchid: str = None
  ):

  batchid = int(batchid)
  
  from datetime import datetime
  from pyspark.sql.types import StringType
  import pyspark.sql.functions as F
  import re

  start_time = _time.time()
  notebook_name = _get_current_notebook_name()

  base = ""

  if USE_ORCHESTRATOR:
      base = _resolve_orchestrator_base_path(domain, processing_date, extract_id)
      if not base:
          logger.info(
              f"⚠️ WARNING: Exact orchestrator path not found for "
              f"domain={domain}, date={processing_date}, extract_id={extract_id}. Skipping load."
          )
          return None
  else:
      base = f"Files/archive/parquet/{processing_date.strip('/')}"
  
  print(base)
  paths = []
  fl = get_fabric_logger()
  # ------------------------------------------------------------
  # Extract domain + entity
  # ------------------------------------------------------------
  try:
      _, tbl = target_tbl.split(".", 1)
      domain, entity = tbl.split("_", 1)
      domain = domain.lower()
      entity = entity.lower()
  except Exception:
      logger.info(f"Invalid target_tbl format: {target_tbl}")
      return None
  # ------------------------------------------------------------
  # Unified parquet filename matcher (old + new formats)
  # FIX: Ensure exact entity name matching, not substring matching
  # FIX: Verify domain in filename matches expected domain
  # E.g., fct_product should NOT match fct_productunitconversion or product_sp_*
  # EXTRA VALIDATION: Also verify search_param is present in filename
  # ============================================================
  def matches_model_file(name: str) -> bool:
      name = name.lower()
      
      # SAFETY CHECK: search_param must be present in filename
      # This prevents ProductUnitConversion files going into Product table
      search_param_clean = search_param.lower().strip('_') if search_param else None
      if search_param_clean and search_param_clean not in name:
          return False  # Reject: search param not found in filename
      
      # DOMAIN BOUNDARY CHECK: Reject files from different domains
      # Files with '_sp_' are for Supply Planning (OPR domain)
      # Files with '_fct_' are for Forecast (FCT domain)
      # If this is a FCT table (domain='fct'), reject SP files
      if domain.lower() == 'fct' and '_sp_full' in name:
          return False  # Reject: SP files are for OPR domain, not FCT
      # If this is an OPR table (domain='opr'), reject FCT files
      if domain.lower() == 'opr' and '_fct_' in name:
          return False  # Reject: FCT files are for FCT domain, not OPR
      
      # Old format:
      # 20260409_162015_OPR_PPLProdLocInvFact_*.parquet or
      # 20260409_162015_FCT_Product_*.parquet
      # MUST have underscore or non-alphanumeric after entity name to avoid substring matches
      old_pattern = re.compile(
          rf"^\d{{8}}_\d{{6}}_{domain}_{entity}(?:_|[^a-z0-9]).*\.parquet$", re.IGNORECASE
      )
      # SP format (OPR/SP):
      # PPLProdLocInvFact_SP_Full_*_20260409_093914.parquet
      # Only match if domain is OPR/SP
      new_pattern = re.compile(
          rf"^{entity}(?:_|[^a-z0-9])sp_.*_\d{{8}}_\d{{6}}\.parquet$", re.IGNORECASE
      ) if domain.lower() in ['opr', 'sp'] else None
      # DP format (FCT/DP):
      # Location_DP_Central_Full_20260728_070408.parquet
      # Only match if domain is FCT/DP
      dp_pattern = re.compile(
          rf"^{entity}(?:_|[^a-z0-9])dp_.*_\d{{8}}_\d{{6}}\.parquet$", re.IGNORECASE
      ) if domain.lower() in ['fct', 'dp'] else None

      matched_old = bool(old_pattern.match(name))
      matched_new = bool(new_pattern and new_pattern.match(name))
      matched_dp  = bool(dp_pattern and dp_pattern.match(name))
      matched = matched_old or matched_new or matched_dp
      if matched:
          logger.debug(f"✓ Pattern matched: {name} (domain={domain}, entity={entity}, search_param={search_param})")
      return matched
  # ------------------------------------------------------------
  # Manifest file detector (two new formats)
  # ------------------------------------------------------------
  def find_manifest_file_for_package(package_folder: str, base_path: str) -> str | None:
      try:
          items = mssparkutils.fs.ls(f"{base_path}/{package_folder}")
      except:
          return None
      for it in items:
          name = it.name.lower()
          # Pattern A: Manifest_SP_Full_*.parquet
          if name.startswith("manifest_sp_full") and name.endswith(".parquet"):
              return f"{base_path}/{package_folder}/{it.name}"
          # Pattern B: MetaData_SP_Daily_*.parquet
          if name.startswith("metadata_sp_daily") and name.endswith(".parquet"):
              return f"{base_path}/{package_folder}/{it.name}"
          # Pattern C: MetaData_DP_* (Demand Planning manifests)
          if name.startswith("metadata_dp_") and name.endswith(".parquet"):
              return f"{base_path}/{package_folder}/{it.name}"
          # Pattern D: Manifest_DP_* (Demand Planning manifests, alternative naming)
          if name.startswith("manifest_dp_") and name.endswith(".parquet"):
              return f"{base_path}/{package_folder}/{it.name}"
      return None
  # ------------------------------------------------------------
  # Recursive file walk
  # ------------------------------------------------------------
  def walk(path, depth=0, max_depth=3):
      try:
          items = mssparkutils.fs.ls(path)
      except Exception:
          return
      
      for it in items:
          full = f"{path}/{it.name}"
          if it.isDir and depth < max_depth:
              walk(full, depth + 1, max_depth)
          elif it.isDir:
              continue
          elif (
              it.name.lower().endswith(".parquet")
              and matches_model_file(it.name)
          ):
              paths.append(full)
  walk(base)
  # ------------------------------------------------------------
  # No files found
  # ------------------------------------------------------------
  if not paths:
      logger.info(f"⚠️ WARNING: No valid '{target_tbl}' parquet files found under {base}.")
      return None
  logger.info(f"Found {len(paths)} candidate {target_tbl} files")
  # ------------------------------------------------------------
  # Group files by package folder
  # ------------------------------------------------------------
  package_files = {}
  for p in paths:
      parts = p.split("/")
      if len(parts) >= 2:
          package_folder = parts[-2]
          if package_folder not in package_files:
              package_files[package_folder] = []
          package_files[package_folder].append(p)
  logger.info(f"[PACKAGE] Found {len(package_files)} unique packages: {list(package_files.keys())}")
  # ------------------------------------------------------------
  # Track packages
  # ------------------------------------------------------------
  tracked_packages = {}
  if fl:
      for package_folder in package_files.keys():
          try:
              package_id = fl.start_package(manifest_package=package_folder, batchid=batchid)
              tracked_packages[package_folder] = package_id
              fl.update_package_layer(
                  manifest_package=package_id,
                  layer="BRONZE",
                  status="IN_PROGRESS",
                  start_time=datetime.now()
              )
              logger.info(f"[PACKAGE] Started tracking: {package_folder}")
          except Exception as e:
              logger.info(f"[PACKAGE] Could not start tracking for {package_folder}: {e}")
  spark.conf.set("spark.sql.parquet.enableVectorizedReader", "false")
  # ------------------------------------------------------------
  # Normalize target schema
  # ------------------------------------------------------------
  tgt = spark.table(target_tbl)
  tgt_schema = {f.name.lower(): f.dataType for f in tgt.schema.fields}
  tgt_cols = list(tgt_schema.keys())
  per_file_dfs = []
  # ------------------------------------------------------------
  # Read each parquet file
  # ------------------------------------------------------------
  for p in paths:
      df_i = None
      try:
          df_i = (
              spark.read
                  .option("mergeSchema", "false")
                  .option("columnNameOfCorruptRecord", "_bad")
                  .parquet(p)
          )
      except Exception as e:
          logger.info(f"Spark read failed for {p}: {e}")
          try:
              import pyarrow.parquet as pq
              table = pq.read_table(p)
              pandas_df = table.to_pandas()
              pandas_df = pandas_df.where(pandas_df.notnull(), None)
              for c in pandas_df.columns:
                  pandas_df[c] = pandas_df[c].astype("string")
              df_i = spark.createDataFrame(pandas_df)
              logger.info(f"PyArrow fallback succeeded for {p}")
          except Exception as e3:
              logger.info(f"Skipping unreadable file {p}: {e3}")
              continue
      df_i = df_i.toDF(*[c.lower() for c in df_i.columns])
      df_i = (
          df_i
          .withColumn("sourcefile", F.lit(p.split("/")[-1]))
          .withColumn("sourcefolder", F.lit(p.split("/")[-2] if len(p.split("/")) >= 2 else None))
          .withColumn("manifest_package", F.lit(p.split("/")[-2] if len(p.split("/")) >= 2 else None))
          .withColumn("load_date", F.current_date())
          .withColumn("load_timestamp", F.current_timestamp())
          .withColumn("ins_batchid", F.lit(batchid))
          .withColumn("upd_batchid", F.lit(batchid))
          .withColumn("valid_from", F.current_date())
          .withColumn("is_current", F.lit(1))
      )
      if "versionid" in df_i.columns and "version_id" not in df_i.columns:
          df_i = df_i.withColumnRenamed("versionid", "version_id")
      per_file_dfs.append(df_i)
  if not per_file_dfs:
      logger.info(f"⚠️ All files unreadable for model '{search_param}'.")
      if fl and tracked_packages:
          for pkg_id in tracked_packages.values():
              fl.fail_package(pkg_id, "BRONZE", "All files unreadable")
      return None
  # ------------------------------------------------------------
  # Union all files
  # ------------------------------------------------------------
  df = per_file_dfs[0]
  for other in per_file_dfs[1:]:
      df = df.unionByName(other, allowMissingColumns=True)
  # Cast + add missing columns
  for col_name, dtype in tgt_schema.items():
      if col_name not in df.columns:
          df = df.withColumn(col_name, F.lit(None).cast(dtype))
      else:
          df = df.withColumn(col_name, F.col(col_name).cast(dtype))
  df = df.select(*tgt_cols)
  # ------------------------------------------------------------
  # Populate manifest_file using filesystem detection
  # ------------------------------------------------------------
  manifest_file_lookup = {}
  for pkg_folder in package_files.keys():
      mf = find_manifest_file_for_package(pkg_folder, base)
      if mf:
          manifest_file_lookup[pkg_folder] = mf
  if "manifest_file" in tgt_cols and "manifest_package" in df.columns:
      mf_rows = [(k, v) for k, v in manifest_file_lookup.items()]
      if mf_rows:
          mf_df = spark.createDataFrame(mf_rows, ["_mf_pkg", "_mf_file"])
          df = df.join(
              F.broadcast(mf_df),
              df["manifest_package"] == mf_df["_mf_pkg"],
              "left"
          )
          df = df.withColumn("manifest_file", F.col("_mf_file")) \
                 .drop("_mf_pkg", "_mf_file")
          df = df.select(*tgt_cols)
  # ------------------------------------------------------------
  # Create temp view
  # ------------------------------------------------------------
  view_name = _safe_view(search_param)
  df.createOrReplaceGlobalTempView(view_name)
  logger.info(f"Created global temp view: global_temp.{view_name}")
  df = df.withColumn("load_date_partition", F.col("load_date").cast("date"))
  # ------------------------------------------------------------
  # Drop + write bronze table
  # ------------------------------------------------------------
  try:
      spark.sql(f"DROP TABLE IF EXISTS {target_tbl}")
  except Exception:
      try:
          detail = spark.sql(f"DESCRIBE DETAIL {target_tbl}").collect()[0]
          table_path = detail["location"]
          mssparkutils.fs.rm(table_path, recurse=True)
      except Exception:
          pass
  try:
      df.write \
          .format("delta") \
          .partitionBy("load_date_partition") \
          .mode("overwrite") \
          .option("overwriteSchema", "true") \
          .option("partitionOverwriteMode", "static") \
          .saveAsTable(target_tbl)
      logger.info(f"[PARTITION] Written data to {target_tbl} with load_date_partition")
  except Exception as e:
      if fl and tracked_packages:
          for pkg_id in tracked_packages.values():
              try:
                  fl.fail_package(pkg_id, "BRONZE", str(e))
              except:
                  pass
      logger.info(f"❌ Failed to write to {target_tbl}: {e}")
      # Log failed operation
      _log_partial_load_unified(
          notebook_name=notebook_name,
          table_name=target_tbl,
          domain=domain.upper() if domain else None,
          deleted_combinations=None,
          source_file=", ".join([p.split("/")[-1] for p in paths[:20]]) if paths else None,
          manifest_package=list(package_files.keys())[0] if package_files else None,
          status="FAILED",
          message=f"Bronze bulk load failed for {target_tbl}",
          rows_before=0,
          rows_after=0,
          execution_time=_time.time() - start_time,
          error_message=str(e)[:2000],
          operation_type="BRONZE_BULK_LOAD",
          batchid=batchid,
      )
      return None
  # ------------------------------------------------------------
  # Mark bronze complete
  # ------------------------------------------------------------
  if fl and tracked_packages:
      for pkg_folder, pkg_id in tracked_packages.items():
          try:
              fl.update_package_layer(
                  manifest_package=pkg_id,
                  layer="BRONZE",
                  status="SUCCESS",
                  end_time=datetime.now()
              )
              logger.info(f"[PACKAGE] Bronze completed for: {pkg_folder}")
          except Exception as e:
              logger.info(f"[PACKAGE] Could not update bronze layer for {pkg_folder}: {e}")
  # ------------------------------------------------------------
  # Log operation to audit_operation_log
  # ------------------------------------------------------------
  execution_time = _time.time() - start_time
  rows_loaded = 0
  try:
      rows_loaded = spark.table(target_tbl).count()
  except Exception:
      pass
  _log_partial_load_unified(
      notebook_name=notebook_name,
      table_name=target_tbl,
      domain=domain.upper() if domain else None,
      deleted_combinations=None,
      source_file=", ".join([p.split("/")[-1] for p in paths[:20]]) if paths else None,
      manifest_file=next(iter(manifest_file_lookup.values()), None) if manifest_file_lookup else None,
      manifest_package=list(package_files.keys())[0] if len(package_files) == 1 else ", ".join(list(package_files.keys())[:10]) if package_files else None,
      status="SUCCESS",
      message=f"Bronze bulk load complete: {len(paths)} files from {len(package_files)} packages, {rows_loaded:,} rows",
      rows_before=0,
      rows_after=rows_loaded,
      execution_time=execution_time,
      operation_type="BRONZE_BULK_LOAD",
      batchid=batchid,
  )
  return view_name

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_read_parquet")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
