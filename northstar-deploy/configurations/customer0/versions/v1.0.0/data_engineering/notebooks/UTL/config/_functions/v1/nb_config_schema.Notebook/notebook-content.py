# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_schema
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: match_schema, evolve_schema, _safe_view, ensure_table_exists(_strict)
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Schema Match
# Aligns a source DataFrame's schema with a target Delta table — matching column names (case-insensitive), casting data types, and preserving extra source columns.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def match_schema(df, target_table: str):
  """Align DataFrame schema with target table (case-insensitive column matching).
  
  Preserves ALL columns: matches data types for matching columns, adds NULLs for 
  missing target columns, and keeps any extra source columns not in target.
  """
  try:
      tgt = spark.table(target_table)
  except Exception:
      logger.warning(f"Target table {target_table} not found - skipping schema match")
      return df
  tgt_schema = {f.name.lower(): (f.name, f.dataType) for f in tgt.schema.fields}
  
  # Map lowercase column names to their actual names in source
  dfcols_lower = {c.lower(): c for c in df.columns}
  
  aligned = df
  processed_cols_lower = set()
  # 1. Process target columns (match types, rename if needed)
  for tgt_cname_lower, (tgt_cname, dtype) in tgt_schema.items():
      if tgt_cname_lower in dfcols_lower:
          # Column exists in source with potentially different casing
          src_cname = dfcols_lower[tgt_cname_lower]
          processed_cols_lower.add(tgt_cname_lower)
          
          if src_cname != tgt_cname:
              # Rename to match target casing
              aligned = aligned.withColumnRenamed(src_cname, tgt_cname)
          
          # Cast to target type if different
          aligned = aligned.withColumn(tgt_cname, col(tgt_cname).cast(dtype))
      else:
          # Column doesn't exist in source - add NULL column with target name
          aligned = aligned.withColumn(tgt_cname, lit(None).cast(dtype))
          processed_cols_lower.add(tgt_cname_lower)
  # 2. Keep all extra columns from source that don't exist in target
  #    (these are new columns we want to preserve)
  for src_cname in df.columns:
      src_cname_lower = src_cname.lower()
      if src_cname_lower not in processed_cols_lower and src_cname_lower not in tgt_schema:
          # This column exists in source but not in target - preserve it
          logger.info(f"[SCHEMA MATCH] Preserving new source column: {src_cname}")
          # Column already exists in aligned, nothing to do
          pass
  return aligned

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Schema Evolution
# Handles additive and destructive schema changes between source DataFrames and target Delta tables via `ALTER TABLE ADD/REPLACE COLUMNS`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def evolve_schema(df: DataFrame, target: str):
  logger.info(f"[SCHEMA] Evolving schema for {target}")
  # 1. EARLY EXIT: if source has no rows → skip evolution
  if df.rdd.isEmpty():
      logger.info(f"[SCHEMA] Source is empty → skipping schema evolution for {target}")
      return
  # 2. If table does not exist → create it
  if not spark._jsparkSession.catalog().tableExists(target):
      logger.info("[SCHEMA] Table does not exist → creating with df schema")
      df.limit(0).write.format("delta").saveAsTable(target)
      return
  # 3. Load schemas - use case-insensitive comparison
  target_schema = spark.table(target).schema
  df_schema = df.schema
  # Map lowercase names to original names for comparison
  target_cols = {f.name.lower(): f for f in target_schema}
  df_cols = {f.name.lower(): f for f in df_schema}
  df_cols_orig = {f.name.lower(): f.name for f in df_schema}
  target_cols_orig = {f.name.lower(): f.name for f in target_schema}
  added = [df_cols_orig[c] for c in df_cols if c not in target_cols]
  removed = [target_cols_orig[c] for c in target_cols if c not in df_cols]
  type_changed = [
      c for c in df_cols
      if c in target_cols and df_cols[c].dataType != target_cols[c].dataType
  ]
  logger.info(f"[SCHEMA] Added: {added}")
  logger.info(f"[SCHEMA] Removed: {removed}")
  # logger.info(f"[SCHEMA] Type changes: {type_changed}")
  destructive_change = bool(removed or type_changed)
  # 4. If destructive change AND table has data → skip REPLACE COLUMNS, but still ADD new columns
  if destructive_change:
      row_count = spark.table(target).count()
      if row_count > 0:
          if added:
              logger.info(f"[SCHEMA] Destructive change detected but table has data → only applying ADD COLUMNS ({len(added)} new columns)")
              for col_name in added:
                  f = df_cols[col_name.lower()]
                  sql = f"ALTER TABLE {target} ADD COLUMNS ({col_name} {f.dataType.simpleString()})"
                  try:
                      logger.info(f"[SCHEMA] Adding column: {col_name} ({f.dataType.simpleString()})")
                      spark.sql(sql)
                      logger.info(f"[SCHEMA] ✓ Successfully added column: {col_name}")
                  except Exception as e:
                      if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                          logger.info(f"[SCHEMA] Column {col_name} already exists (skipping)")
                      else:
                          logger.error(f"[SCHEMA] Error adding column {col_name}: {e}")
                          raise
          else:
              logger.info(f"[SCHEMA] Destructive change detected but table has {row_count} rows and no new columns → skipping evolution")
          return
  # 5. If destructive change AND table is empty → rebuild schema
  if destructive_change:
      # logger.info("[SCHEMA] Destructive change but table is empty → applying REPLACE COLUMNS")
      # Build column list using target table's column names (for proper casing)
      # but dataframe's data types
      cols_parts = []
      for df_field in df_schema:
          df_col_lower = df_field.name.lower()
          # Use target table's column name if it exists (case-sensitive match)
          if df_col_lower in target_cols:
              target_col_name = target_cols_orig[df_col_lower]
              cols_parts.append(f"{target_col_name} {df_field.dataType.simpleString()}")
          else:
              # New column not in target - use dataframe's name
              cols_parts.append(f"{df_field.name} {df_field.dataType.simpleString()}")
      cols_sql = ",\n  ".join(cols_parts)
      sql = f"""
      ALTER TABLE {target}
      REPLACE COLUMNS (
        {cols_sql}
      )
      """
      spark.sql(sql)
      logger.info("[SCHEMA] Schema replaced successfully")
      return
  # 6. Only additive changes → ADD COLUMNS
  if added:
      logger.info(f"[SCHEMA] Additive change → ADD COLUMNS ({len(added)} new columns)")
      for col_name in added:
          f = df_cols[col_name.lower()]  # Use lowercase key to lookup
          sql = f"ALTER TABLE {target} ADD COLUMNS ({col_name} {f.dataType.simpleString()})"
          try:
              logger.info(f"[SCHEMA] Adding column: {col_name} ({f.dataType.simpleString()})")
              spark.sql(sql)
              logger.info(f"[SCHEMA] ✓ Successfully added column: {col_name}")
          except Exception as e:
              # Column might already exist, log and continue
              if "Duplicate column" in str(e) or "already exists" in str(e).lower():
                  logger.info(f"[SCHEMA] Column {col_name} already exists (skipping)")
              else:
                  logger.error(f"[SCHEMA] Error adding column {col_name}: {e}")
                  raise
      
      # Verify columns were added by checking updated schema
      updated_schema = spark.table(target).schema
      added_cols_final = [f.name for f in updated_schema if f.name in added]
      logger.info(f"[SCHEMA] Verification: {len(added_cols_final)} of {len(added)} columns confirmed in table")
  logger.info("[SCHEMA] Schema evolution complete")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Safe Temp View Name Generator
# Generates collision-free temporary view names using timestamps, UUIDs, and the Spark session ID.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _safe_view(base: str) -> str:
  ts = int(time.time() * 1000)
  ts_human = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
  uid = uuid.uuid4().hex[:8]
  base = (base or "").lower()
  for char in [".", "-", "`", " ", '"', "'"]:
      base = base.replace(char, "_")
  while "__" in base:
      base = base.replace("__", "_")
  base = base.strip("_") or "temp"
  session_id = spark.sparkContext.applicationId
  return f"merge_src_{base}_{ts_human}_{ts}_{uid}_{session_id}"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Table Creation Guards

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def ensure_table_exists(target: str, source_sql: str, partition_by=None):
  # partition_by is honoured only when creating a new (empty) target. If the
  # table already exists with a different partition scheme, a warning is logged
  # and the existing scheme is kept — physical repartition requires a manual
  # rebuild.
  if spark.catalog.tableExists(target):
      if partition_by:
          try:
              detail_rows = spark.sql(f"DESCRIBE DETAIL {target}").collect()
              existing_partition = list(detail_rows[0]["partitionColumns"]) if detail_rows else []
              wanted = [c for c in partition_by]
              if [c.lower() for c in existing_partition] != [c.lower() for c in wanted]:
                  logger.warning(
                      f"[SCHEMA] {target} already exists partitioned by {existing_partition!r}, "
                      f"but yaml requests {wanted!r}. Keeping existing scheme. "
                      f"To repartition, drop and reload the table."
                  )
          except Exception as _e:
              logger.info(f"[SCHEMA] Could not inspect partitions of {target}: {_e}")
      _ensure_delta_autoopt(target)
      return
  df0 = spark.sql(source_sql).limit(0)
  writer = (
      df0.write.format("delta").mode("overwrite")
      .option("overwriteSchema", "true")
      .option("partitionOverwriteMode", "static")
  )
  if partition_by:
      writer = writer.partitionBy(*partition_by)
      logger.info(f"[SCHEMA] Creating {target} partitioned by {partition_by}")
  writer.saveAsTable(target)
  _ensure_delta_autoopt(target)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def ensure_table_exists_strict(target: str, source_sql: str):
    """
    If target doesn't exist, create it from source_sql schema.
    If creation fails, stop notebook.

    Additional rule:
    - If 'script' appears anywhere in the target name (case-insensitive),
      do NOT create the table.
    """
    # Guard: never create tables whose names contain 'script'
    if "script" in target.lower():
        logger.info(f"[FRAMEWORK] Skipping creation for target '{target}' because it contains 'script'.")
        return

    # Normal logic
    if spark.catalog.tableExists(target):
        _ensure_delta_autoopt(target)
        return

    logger.info(f"[FRAMEWORK] Target {target} does not exist. Creating it (strict).")
    try:
        df0 = spark.sql(source_sql).limit(0)
        (
            df0.write.format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .option("partitionOverwriteMode", "static")
            .saveAsTable(target)
        )
        _ensure_delta_autoopt(target)
        logger.info(f"[FRAMEWORK] Created empty target table {target}")
    except Exception as e:
        logger.exception(f"[FRAMEWORK] Failed to create target table {target} from source SQL")
        stop_notebook(f"FAILED: could not create target table {target}. Reason: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_schema")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
