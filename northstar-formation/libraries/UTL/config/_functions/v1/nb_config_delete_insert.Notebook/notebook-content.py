# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_delete_insert
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: delete_insert
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Delete Insert

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def delete_insert_manifest(cfg):
    import time as _time
    import json

    src_tbl = cfg.get("SOURCE_TABLE")

    if src_tbl:
        batchid = (
            spark.table(src_tbl)
                 .select("ins_batchid")
                 .distinct()
                 .collect()[0][0]
        )

    print(f"[DELETE_INSERT_MANIFEST] BatchID: {batchid}")

    start_time = _time.time()
    
    tgt = cfg["TARGET_TABLE"]
    src_sql = cfg["SOURCE_SQL"]
    manifest_keys = cfg.get("DELETE_KEYS") or ["Extractiondef", "Extractionversion", "Packagedef"]
    partition_by = cfg.get("PARTITION_BY") or []

    notebook_name = _get_current_notebook_name()

    ensure_table_exists(tgt, src_sql, partition_by=partition_by)
    _repair_if_corrupted(tgt)

    # Delta autoOptimize properties are now applied inside ensure_table_exists via
    # _ensure_delta_autoopt (bootstrap). Kept as a defensive no-op reference here
    # in case the target was created outside the framework.
    _ensure_delta_autoopt(tgt)

    # Skip full table scan for 'before' count — only used for logging.
    # Use 0 as placeholder; the final 'after' count is what matters for monitoring.
    before = 0
    logger.info(f"[DELETE_INSERT_MANIFEST] {tgt} starting load (before-count skipped for performance)")
    
    # Read source data
    df = spark.sql(src_sql)
    df.persist()
    inserted = df.count()
    
    # Extract manifest_package from data
    source_folder_col = None
    for c in df.columns:
        if c.lower() == "manifest_package":
            source_folder_col = c
            break
    
    if not source_folder_col:
        raise RuntimeError(f"Source data must have 'manifest_package' column for [DELETE_INSERT_MANIFEST] on {tgt}")

    # Get unique source_folder values
    source_folders = (
        df.select(source_folder_col)
          .dropna()
          .distinct()
          .rdd.map(lambda r: str(r[0]))
          .collect()
    )
    
    logger.info(f"[DELETE_INSERT_MANIFEST] Found {len(source_folders)} unique source folders")
    
    if not source_folders:
        raise RuntimeError(
            f"[DELETE_INSERT_MANIFEST] No non-null manifest_package values found in source data for {tgt}. "
            f"Ensure the bronze table has manifest_package populated."
        )
    
    # ------------------------------------------------------------
    # READ MANIFEST DIRECTLY FROM manifest_file COLUMN
    # Bronze tables store the metadata parquet path in manifest_file.
    # Read those files directly — no need for audit_package_manifest table.
    # ------------------------------------------------------------
    manifest_file_col = None
    for c in df.columns:
        if c.lower() == "manifest_file":
            manifest_file_col = c
            break

    manifest_file_paths = []
    if manifest_file_col:
        manifest_file_paths = (
            df.select(manifest_file_col)
              .dropna()
              .distinct()
              .rdd.map(lambda r: str(r[0]))
              .collect()
        )

    manifest_file_value = manifest_file_paths[0] if len(manifest_file_paths) == 1 else (
        ",".join(manifest_file_paths) if manifest_file_paths else None
    )
    manifest_package_value = source_folders[0] if len(source_folders) == 1 else ",".join(source_folders)

    df_manifest = None

    if manifest_file_paths:
        # Read manifest parquet files directly and pivot key/value pairs
        manifest_dfs = []
        for mf_path in manifest_file_paths:
            try:
                df_mf = spark.read.parquet(mf_path)
                df_mf = df_mf.toDF(*[c.lower() for c in df_mf.columns])
                # Normalize value column name (some metadata files use 'data' instead of 'value')
                if "data" in df_mf.columns and "value" not in df_mf.columns:
                    df_mf = df_mf.withColumnRenamed("data", "value")
                # Normalize keys
                df_mf = (
                    df_mf
                    .withColumn("key", F.lower(F.col("key")))
                    .withColumn("key", F.regexp_replace(F.col("key"), r"\s+", ""))
                    .withColumn("key", F.regexp_replace(F.col("key"), r"\.", "_"))
                )
                folder = mf_path.split("/")[-2]
                df_mf = df_mf.withColumn("manifest_package", F.lit(folder))
                df_mf = df_mf.withColumn("manifest_file", F.lit(mf_path))
                manifest_dfs.append(df_mf)
            except Exception as e:
                logger.info(f"[DELETE_INSERT_MANIFEST] Could not read manifest file {mf_path}: {e}")

        if manifest_dfs:
            df_meta_raw = manifest_dfs[0]
            for other in manifest_dfs[1:]:
                df_meta_raw = df_meta_raw.unionByName(other, allowMissingColumns=True)

            # Pivot key/value into columns per package folder
            df_manifest = (
                df_meta_raw
                .groupBy("manifest_package", "manifest_file")
                .pivot("key")
                .agg(F.first("value"))
            )
            # Capitalize column names to match manifest convention
            df_manifest = df_manifest.toDF(*[c[0].upper() + c[1:] if c not in ("manifest_package", "manifest_file") else c for c in [col_name.lower() for col_name in df_manifest.columns]])
            # Fix known column names
            col_map = {c.lower(): c for c in df_manifest.columns}
            if "manifest_package" in col_map:
                df_manifest = df_manifest.withColumnRenamed(col_map["manifest_package"], "Manifest_package")
            if "manifest_file" in col_map:
                df_manifest = df_manifest.withColumnRenamed(col_map["manifest_file"], "Manifest_file")

            logger.info(f"[DELETE_INSERT_MANIFEST] Read {df_manifest.count()} manifest entries from parquet files")
            # logger.info(f"[DELETE_INSERT_MANIFEST] Manifest columns: {df_manifest.columns}")

    # Fallback: query audit_package_manifest table if direct read failed
    if df_manifest is None or df_manifest.count() == 0:
        logger.info("[DELETE_INSERT_MANIFEST] Direct manifest file read failed or empty — falling back to audit_package_manifest table")
        source_folders_list = ",".join([f"'{sf}'" for sf in source_folders])
        manifest_query = f"""
            SELECT *
            FROM log.audit_package_manifest
            WHERE manifest_package IN ({source_folders_list})
        """
        logger.info(f"[DELETE_INSERT_MANIFEST] Fallback query: {manifest_query}")
        df_manifest = spark.sql(manifest_query)
        manifest_count = df_manifest.count()

        if manifest_count == 0:
            logger.error(f"[DELETE_INSERT_MANIFEST] No manifest entries found for source folders: {source_folders}")
            raise RuntimeError(f"No manifest data found for the provided source folders: {source_folders}")
    
    # Rename 'Extractiondef' -> 'Snapshottype' if the manifest has 'Extractiondef'
    # and the configured DELETE_KEYS expect 'Snapshottype'

    manifest_col_map = {c.lower(): c for c in df_manifest.columns}
    if ".opr_" in tgt and "extractiondef" in manifest_col_map and "snapshottype" not in manifest_col_map:
        if any(mk.lower() == "snapshottype" for mk in manifest_keys):
            df_manifest = df_manifest.withColumnRenamed(manifest_col_map["extractiondef"], "Snapshottype")
            logger.info("[DELETE_INSERT_MANIFEST] Renamed manifest column 'Extractiondef' → 'Snapshottype'")
            # UPDATE manifest_keys to replace "Extractiondef" with "Snapshottype"
            manifest_keys = [mk if mk.lower() != "extractiondef" else "Snapshottype" for mk in manifest_keys]
            logger.info(f"[DELETE_INSERT_MANIFEST] Updated manifest_keys: {manifest_keys}")

    manifest_col_map = {c.lower(): c for c in df_manifest.columns}
    if ".fct_" in tgt and "extractiondef" in manifest_col_map and "forecastgroupid" not in manifest_col_map:
        if any(mk.lower() == "forecastgroupid" for mk in manifest_keys):
            df_manifest = df_manifest.withColumnRenamed(manifest_col_map["extractiondef"], "Forecastgroupid")
            logger.info("[DELETE_INSERT_MANIFEST] Renamed manifest column 'Extractiondef' → 'Forecastgroupid'")

            manifest_keys = [mk if mk.lower() != "extractiondef" else "Forecastgroupid" for mk in manifest_keys]
            logger.info(f"[DELETE_INSERT_MANIFEST] Updated manifest_keys: {manifest_keys}")
            
        if any(mk.lower() == "forecastcycleid" for mk in manifest_keys):
            df_manifest = df_manifest.withColumnRenamed(manifest_col_map["cycleid"], "Forecastcycleid")
            logger.info("[DELETE_INSERT_MANIFEST] Renamed manifest column 'cycleid' → 'Forecastcycleid'")
            # Replace W→1 and M→0 in Forecastcycleid values
            df_manifest = df_manifest.withColumn(
                "Forecastcycleid",
                F.regexp_replace(
                    F.regexp_replace(F.col("Forecastcycleid"), "M", "0"),
                    "W",
                    "1"
                )
            )


    # Manifest / target schema
    manifest_cols = [c.lower() for c in df_manifest.columns]
    target_cols = [c.lower() for c in spark.table(tgt).columns]

    # ----------------------------------------------------------------------
    # AUTO-EVOLVE TARGET TABLE TO INCLUDE MISSING MANIFEST KEYS
    #
    # For partitionkeys_* manifest keys, we never add the manifest-named
    # column (e.g. 'Partitionkeys_productlocation') to the target.
    # Instead we ensure the actual data column 'Partitionkey' exists.
    # This guarantees _resolve_target_column always finds a valid candidate.
    # ----------------------------------------------------------------------
    missing_cols = []
    for mk in manifest_keys:
        mk_lower = mk.lower()

        if mk_lower.startswith("partitionkeys_"):
            # Map to the real data column, not the manifest key name
            if "partitionkey" not in target_cols:
                missing_cols.append("Partitionkey")
            continue

        if mk_lower not in target_cols:
            missing_cols.append(mk)

    # Deduplicate — multiple partitionkeys_* entries would otherwise add 'Partitionkey' twice
    missing_cols = list(dict.fromkeys(missing_cols))

    if missing_cols:
        logger.error(f"[DELETE_INSERT_MANIFEST] Auto-adding missing columns to {tgt}: {missing_cols}")

        for colname in missing_cols:
            try:
                spark.sql(f"ALTER TABLE {tgt} ADD COLUMN ({colname} STRING)")
                logger.info(f"[DELETE_INSERT_MANIFEST] Added column {colname} STRING to {tgt}")
            except Exception as e:
                logger.error(f"[DELETE_INSERT_MANIFEST] Failed to add column {colname}: {e}")
                raise

        target_cols = [c.lower() for c in spark.table(tgt).columns]

    # ----------------------------------------------------------------------
    # MATCH SCHEMA AFTER AUTO-EVOLVE
    # ----------------------------------------------------------------------
    df = match_schema(df, tgt)

    # ----------------------------------------------------------------------
    # RESOLVER: manifest key -> actual target column name
    #
    # partitionkeys_* are manifest naming conventions that map to the real
    # data column 'Partitionkey' in the target. We exclude partitionkeys_*
    # from candidates to avoid matching spuriously-named columns that may
    # have been added by earlier buggy runs.
    #
    # By the time this runs, auto-evolve has already guaranteed 'Partitionkey'
    # exists, so a missing candidate here is always an unexpected hard error.
    # ----------------------------------------------------------------------
    def _resolve_target_column(manifest_key: str) -> str:
        mk_lower = manifest_key.lower()
        live_cols_map = {c.lower(): c for c in spark.table(tgt).columns}

        if mk_lower.startswith("partitionkeys_"):
            candidates = [
                v for k, v in live_cols_map.items()
                if k.startswith("partitionkey") and not k.startswith("partitionkeys_")
            ]

            # logger.info(
            #     f"[DELETE_INSERT_MANIFEST] _resolve_target_column: "
            #     f"manifest_key='{manifest_key}', usable candidates (excl. manifest-named)={candidates}"
            # )

            if candidates:
                chosen = candidates[0]
                logger.info(f"[DELETE_INSERT_MANIFEST] Mapping '{manifest_key}' → '{chosen}'")
                return chosen

            # Should never reach here — auto-evolve above guarantees 'Partitionkey' exists
            raise RuntimeError(
                f"[DELETE_INSERT_MANIFEST] 'Partitionkey' column missing from {tgt} after auto-evolve. "
                f"This is unexpected — check ensure_table_exists and ALTER TABLE permissions."
            )

        # Exact case-insensitive match for all other keys
        if mk_lower in live_cols_map:
            return live_cols_map[mk_lower]

        logger.error(
            f"[DELETE_INSERT_MANIFEST] Could not resolve target column for manifest key "
            f"'{manifest_key}'. Using it as-is in DELETE condition."
        )
        return manifest_key

    # Validate manifest has required keys (log only)
    for mk in manifest_keys:
        if mk.lower() not in manifest_cols:
            logger.error(
                f"[DELETE_INSERT_MANIFEST] Manifest key '{mk}' not found in extraction_manifest schema. "
                f"Available columns: {df_manifest.columns}"
            )

    # Extract delete combinations from manifest (for logging)
    df_manifest_select = df_manifest.select([F.col(mk) for mk in manifest_keys])

    delete_combinations_list = (
        df_manifest_select
          .dropna()
          .distinct()
          .limit(50000)
          .rdd
          .map(lambda row: {mk: str(row[mk]) for mk in manifest_keys})
          .collect()
    )

    delete_combinations_str = json.dumps(delete_combinations_list)
    
    # Extract domain from manifest (with table name fallback)
    domain = None
    try:
        if "domain" in manifest_cols:
            domain = df_manifest.select("domain").dropna().limit(1).collect()[0][0]
    except Exception:
        pass
    
    domain = _normalize_domain(domain)
    
    if not domain:
        # Fallback: extract from target table name (e.g., silver.opr_backorderfact -> OPR)
        table_only = tgt.split(".")[-1] if "." in tgt else tgt
        if "_" in table_only:
            domain = table_only.split("_")[0].upper()
    
    # Extract source file if present
    source_file_col = None
    for c in df.columns:
        if c.lower() == "sourcefile":
            source_file_col = c
            break
    
    source_file_str = None
    if source_file_col:
        try:
            source_files = (
                df.select(source_file_col)
                  .dropna()
                  .distinct()
                  .limit(1000)
                  .rdd.map(lambda r: str(r[0]))
                  .collect()
            )
            source_file_str = ",".join(source_files)
        except Exception as e:
            logger.info(f"[WARN] Could not extract SourceFile: {e}")
    
    # Layer extraction
    layer = tgt.split(".")[0].lower() if "." in tgt else "bronze"
    
    # Auto-track package using manifest_package from DataFrame column
    package_name = manifest_package_value
    
    if package_name:
        _auto_track_package_entity(
            package_name=package_name,
            entity_name=tgt,
            layer=layer,
            status="IN_PROGRESS",
        )
    
    # Log delete start
    _log_partial_load_unified(
        notebook_name=notebook_name,
        table_name=tgt,
        domain=domain,
        deleted_combinations=delete_combinations_str,
        source_file=source_file_str,
        manifest_file=manifest_file_value,
        manifest_package=manifest_package_value,
        status="DELETE_STARTED",
        message=f"Preparing manifest-driven delete for {tgt} (manifest keys: {manifest_keys})",
        rows_before=before,
        rows_after=before,
        operation_type="PARTIAL_LOADING_MANIFEST",
        batchid=batchid,
    )
    
    # Build DELETE conditions from manifest
    partition_key_clauses = []
    regular_key_clauses = []
    
    # Check for date range columns in SOURCE DATA (not manifest)
    # to support incremental deletes with date ranges
    # NOTE: Only for saleshistory tables (skip OPR and non-saleshistory FCT tables)
    has_from = "Fromduedate" in df.columns
    has_to = "Duedate" in df.columns
    use_source_date_range = has_from and has_to and domain != "OPR" and "saleshistory" in tgt.lower()

    if use_source_date_range:
        r = df.agg(
            F.min("Fromduedate").alias("min_fd"),
            F.max("Duedate").alias("max_dd")
        ).collect()[0]
        min_fd = r["min_fd"]
        max_dd = r["max_dd"]
        if min_fd is not None and max_dd is not None:
            regular_key_clauses.append(f"(Fromduedate >= '{min_fd}' AND Duedate <= '{max_dd}')")
    
    for mk in manifest_keys:
        if mk.lower() not in manifest_cols:
            continue
        
        # Skip date-related manifest keys if we already used source-based date range
        # (e.g., Saleshistory_Fromdate, Saleshistory_Todate are redundant with Fromduedate/Duedate)
        if use_source_date_range and any(date_term in mk.lower() for date_term in ["date", "from", "to"]):
            logger.info(f"[DELETE_INSERT_MANIFEST] Skipping manifest key '{mk}' — date range already added from source data")
            continue

        vals = (
            df_manifest.select(mk)
              .distinct()
              .dropna()
              .limit(50000)
              .collect()
        )
        if not vals:
            continue
        
        # _resolve_target_column raises on unresolvable partitionkeys_* — intentional
        target_col = _resolve_target_column(mk)

        if "partitionkeys" in mk.lower():
            exact_vals = []
            regex_parts = []
            for v in vals:
                raw = str(v[0])
                individual_vals = [p.strip().strip("'\"") for p in raw.split(",")]
                for iv in individual_vals:
                    if not iv:
                        continue
                    if "*" in iv:
                        # Domain-specific escaping: OPR uses double-escape, FCT uses single-escape
                        if domain == "OPR" :
                            # logger.info("OPR detected - applying double escaping for RLIKE regex")
                            regex = (
                            iv.replace("/", "\\\\/")   # escape slash
                            .replace("*", ".*")
                            .replace("|", "\\\\|")
                        )
                        if domain == "FCT" :
                            # logger.info("FCT detected - applying double escaping for RLIKE regex")
                            regex = (
                            iv.replace("/", "\\\\/")   # escape slash
                            .replace("*", ".*")
                            .replace("|", "\\\\|")
                        )

                        regex_parts.append(regex)
                    else:
                        # Domain-specific escaping for exact values
                        if domain == "OPR":
                            logger.info("OPR detected - applying double escaping for exact match")
                            exact_vals.append(iv.replace("|", "\\\\|"))
                        else:  # FCT or other domains
                            logger.info("FCT domain detected - applying single escaping for exact match")
                            exact_vals.append(iv.replace("|", "\\|"))

            subclauses = []

            # Exact matches via IN clause (much smaller than individual RLIKEs)
            if exact_vals:
                # Batch IN clauses to stay well under SQL size limits
                _IN_BATCH = 10000
                for i in range(0, len(exact_vals), _IN_BATCH):
                    batch = exact_vals[i:i+_IN_BATCH]
                    in_list = ",".join([f"'{v}'" for v in batch])
                    subclauses.append(f"{target_col} IN ({in_list})")

            # Wildcard matches via individual RLIKE clauses
            if regex_parts:
                for regex in regex_parts:
                    subclauses.append(f"{target_col} RLIKE '^{regex}$'")

            if subclauses:
                condition = " OR\n        ".join(subclauses)
                condition = f"(\n        {condition}\n    )"
                partition_key_clauses.append(condition)
        else:
            in_list = ",".join([f"'{str(v[0])}'" for v in vals])
            condition = f"{target_col} IN ({in_list})"
            regular_key_clauses.append(condition)
    
    where_clauses = regular_key_clauses + partition_key_clauses

    # Scope INSERT to the same predicate as DELETE.  Otherwise bronze rows whose
    # Partitionkey doesn't match the manifest's declared regex are appended but
    # never deleted, silently duplicating on every rerun.
    df_to_write = df
    dropped_out_of_scope = 0
    if where_clauses:
        insert_where_sql = " AND ".join(where_clauses)
        try:
            df_to_write = df.filter(insert_where_sql)
            df_to_write.persist()
            in_scope = df_to_write.count()
            dropped_out_of_scope = max(inserted - in_scope, 0)
            if dropped_out_of_scope > 0:
                logger.warning(
                    f"[DELETE_INSERT_MANIFEST] {tgt}: dropped {dropped_out_of_scope} "
                    f"bronze row(s) outside the manifest's declared partitionkey scope — "
                    f"the DELETE predicate would not cover them, so they would create "
                    f"duplicates on rerun. Fix upstream extraction filters to align."
                )
            inserted = in_scope
        except Exception as e:
            logger.warning(
                f"[DELETE_INSERT_MANIFEST] {tgt}: could not scope INSERT to DELETE clause "
                f"({e}); falling back to unfiltered INSERT."
            )
            df_to_write = df
            dropped_out_of_scope = 0

    # Execute delete + insert with retry for Delta concurrency conflicts
    _max_retries = 3
    deleted = 0
    delete_sql = None
    for _attempt in range(1, _max_retries + 1):
        try:
            deleted = 0
            delete_sql = None
            if where_clauses:
                where_sql = " AND\n".join(where_clauses)
                delete_sql = f"DELETE FROM \n{tgt}\nWHERE {where_sql}\n"
                logger.info(f"[DELETE_INSERT_MANIFEST] Executing DELETE for {tgt}")
                logger.info(f"[DELETE_INSERT_MANIFEST] Manifest file(s) in use: {manifest_file_value}")
                logger.info(f"{'='*100}")
                logger.info(f"[DELETE_INSERT_MANIFEST] Generated DELETE SQL for {tgt}:")
                logger.info(f"{'='*100}")
                logger.info(f"{delete_sql}")
                logger.info(f"{'='*100}")
                
                spark.sql(delete_sql)
            else:
                logger.info("[DELETE_INSERT_MANIFEST] No delete conditions - skipping delete")

            # Skip after_delete full scan — deleted count approximated from source rows.
            # Deletion vectors make the DELETE fast but the COUNT would still scan all files.
            after_delete = before  # placeholder; exact deleted count not needed
            deleted = inserted     # for snapshot tables: deleted ≈ inserted
            logger.info(f"[DELETE_INSERT_MANIFEST] DELETE complete (approx. {deleted} rows replaced)")
            
            _log_partial_load_unified(
                notebook_name=notebook_name,
                table_name=tgt,
                domain=domain,
                deleted_combinations=delete_combinations_str,
                source_file=source_file_str,
                manifest_file=manifest_file_value,
                manifest_package=manifest_package_value,
                status="DELETE_SUCCESS",
                message=f"Manifest-based delete deleted {deleted} rows from {tgt}",
                rows_before=before,
                rows_after=after_delete,
                rows_deleted=deleted,
                operation_type="PARTIAL_LOADING_MANIFEST",
                delete_statement=delete_sql,
                batchid=batchid,
            )

            # Insert new rows (scoped to same predicate as DELETE — see df_to_write above)
            df_to_write.write.mode("append").option("mergeSchema", "true").format("delta").saveAsTable(tgt)
            break  # success — exit retry loop

        except Exception as e:
            _is_delta_conflict = (
                'DELTA_METADATA_CHANGED' in str(e) or 'MetadataChangedException' in str(e)
            )
            if _is_delta_conflict and _attempt < _max_retries:
                _wait = _attempt * 10
                logger.warning(
                    f"[DELETE_INSERT_MANIFEST] Delta metadata conflict on attempt "
                    f"{_attempt}/{_max_retries} for {tgt}. Retrying in {_wait}s..."
                )
                _time.sleep(_wait)
                # Re-read before count since table may have changed
                before = spark.table(tgt).count()
                continue

            # Not a retriable conflict, or retries exhausted — log and raise
            _log_partial_load_unified(
                notebook_name=notebook_name,
                table_name=tgt,
                domain=domain,
                deleted_combinations=delete_combinations_str,
                source_file=source_file_str,
                manifest_file=manifest_file_value,
                manifest_package=manifest_package_value,
                status="DELETE_FAILED",
                message=f"Manifest-based delete/insert failed for {tgt}"
                    + (f" after {_max_retries} retries (Delta conflict)" if _is_delta_conflict else ""),
                rows_before=before,
                rows_after=before,
                error_message=str(e),
                operation_type="PARTIAL_LOADING_MANIFEST",
                delete_statement=delete_sql,
                batchid=batchid,
            )
            raise
    
    after = spark.table(tgt).count()
    logger.info(f"[DELETE_INSERT_MANIFEST] Rows INSERTED: {inserted}")
    logger.info(f"[DELETE_INSERT_MANIFEST] {tgt} rows AFTER: {after}")
    logger.info("[DELETE_INSERT_MANIFEST] complete")
    
    execution_time = _time.time() - start_time
    
    _log_partial_load_unified(
        notebook_name=notebook_name,
        table_name=tgt,
        domain=domain,
        deleted_combinations=delete_combinations_str,
        source_file=source_file_str,
        manifest_file=manifest_file_value,
        manifest_package=manifest_package_value,
        status="PARTIAL_LOAD_COMPLETE",
        message=f"Manifest-driven partial load complete: deleted {deleted}, inserted {inserted}",
        rows_before=before,
        rows_after=after,
        rows_deleted=deleted,
        rows_inserted=inserted,
        execution_time=execution_time,
        operation_type="PARTIAL_LOADING_MANIFEST",
        delete_statement=delete_sql,
        batchid=batchid,
    )
    
    if package_name:
        _auto_track_package_entity(
            package_name=package_name,
            entity_name=tgt,
            layer=layer,
            status="SUCCESS",
            rows=after,
            execution_time=execution_time,
        )
    
    try:
        df.unpersist()
    except Exception:
        pass
# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_delete_insert")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
