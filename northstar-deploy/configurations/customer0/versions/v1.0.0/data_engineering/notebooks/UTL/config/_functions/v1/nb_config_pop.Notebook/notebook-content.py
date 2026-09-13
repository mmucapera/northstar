# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_pop
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: PoP + load_scd2 + build_PlanOverPlan + enrich_with_pop_fields
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Plan-over-Plan (PoP) Enrichment
# Computes period-over-period comparisons by joining current and prior plan snapshots, enabling forecast value-added analysis.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


_POP_COLS_LOWER = {"count", "newinthisversion", "droppedinthisversion"}

def _strip_pop_columns(df: DataFrame) -> DataFrame:
    """Remove any pre-existing PoP columns so we can rebuild cleanly."""
    clean_cols = [c for c in df.columns if c.lower() not in _POP_COLS_LOWER]
    return df.select(clean_cols)

def _append(df: DataFrame, silver_table_path: str) -> None:
    """Append enriched data to a Delta table using catalog-based write."""
    (
    df.write
    .format("delta")
    .mode("append")
    .option("mergeSchema", "true")
    .saveAsTable(silver_table_path)
    )

def _validate_pop_result(spark, source_table: str, output_table: str, version_col: str) -> None:
    """
    Print validation summary comparing source vs enriched temp table.
    Also persists validation data to log.audit_plan_over_plan table for audit/tracking.
    """
    logger.info("\n" + "=" * 60)
    logger.info("  PoP Enrichment — Validation Summary")
    logger.info("=" * 60)

    # Row counts per version
    # logger.info("\nRow counts per version (real vs ghost):")
    version_summary_df = spark.sql(f"""
        SELECT {version_col},
            COUNT(*)                                        AS total_rows,
            SUM(CASE WHEN COUNT = 1 THEN 1 ELSE 0 END)     AS real_rows,
            SUM(NewInThisVersion)                           AS new_in_version,
            SUM(DroppedInThisVersion)                       AS dropped_in_version
        FROM {output_table}
        GROUP BY {version_col}
        ORDER BY {version_col}
    """)
    version_summary_df.show(truncate=False)

    # Compare totals
    source_cols = [c.lower() for c in spark.table(source_table).columns]
    if "count" in source_cols:
        src_count = spark.sql(
            f"SELECT COUNT(*) FROM {source_table} WHERE COUNT = 1"
        ).collect()[0][0]
    else:
        src_count = spark.table(source_table).count()

    tmp_real  = spark.sql(f"SELECT COUNT(*) FROM {output_table} WHERE COUNT = 1").collect()[0][0]
    tmp_total = spark.sql(f"SELECT COUNT(*) FROM {output_table}").collect()[0][0]

    logger.info(f"Source real records          : {src_count:,}")
    logger.info(f"Temp table real records (1s) : {tmp_real:,}")
    logger.info(f"Temp table ghost records (0s): {tmp_total - tmp_real:,}")
    logger.info(f"Temp table total             : {tmp_total:,}")

    if tmp_real == src_count:
        logger.info("✓ Real record count matches source — no duplicates\n")
    else:
        logger.info(f"⚠ MISMATCH: source has {src_count:,} real rows but temp has {tmp_real:,}\n")

    # Sample ghost rows
    ghost_count = tmp_total - tmp_real
    if ghost_count > 0:
        logger.info("Sample ghost rows (DroppedInThisVersion=1):")
        spark.sql(f"""
            SELECT {version_col}, COUNT, NewInThisVersion, DroppedInThisVersion
            FROM {output_table}
            WHERE DroppedInThisVersion = 1
            LIMIT 5
        """).show(truncate=False)

    # Sample new-in-version rows
    logger.info("Sample new-in-version rows (NewInThisVersion=1):")
    spark.sql(f"""
        SELECT {version_col}, COUNT, NewInThisVersion, DroppedInThisVersion
        FROM {output_table}
        WHERE NewInThisVersion = 1
        LIMIT 5
    """).show(truncate=False)

    logger.info("=" * 60)
    logger.info(f"  Output table: {output_table}")
    logger.info("=" * 60 + "\n")

    # ── PERSIST VALIDATION SUMMARY TO LOG TABLE ──────────────────────────────
    summary_data = (
        version_summary_df
        .withColumn(version_col, F.col(version_col).cast("timestamp"))
        .withColumn("Source_table", F.lit(source_table))
        .withColumn("Output_table", F.lit(output_table))
        .withColumn("Validation_timestamp", F.current_timestamp())
        .select(
            F.col("Source_table"),
            F.col("Output_table"),
            F.col(version_col).alias("Version_id"),
            F.col("total_rows").alias("Total_rows"),
            F.col("real_rows").alias("Real_rows"),
            F.col("new_in_version").alias("New_in_version"),
            F.col("dropped_in_version").alias("Dropped_in_version"),
            F.col("Validation_timestamp")
        )
    )

    try:
        spark.sql("""
            CREATE TABLE IF NOT EXISTS log.audit_plan_over_plan (
                Source_table STRING,
                Output_table STRING,
                Version_id TIMESTAMP,
                Total_rows LONG,
                Real_rows LONG,
                New_in_version LONG,
                Dropped_in_version LONG,
                Validation_timestamp TIMESTAMP
            )
            USING delta
        """)
    except Exception as e:
        logger.info(f"[PoP] Table creation (may already exist): {e}")

    # Append validation summary
    (
        summary_data
        .write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable("log.audit_plan_over_plan")
    )

    logger.info(f"[PoP] Validation summary logged to log.audit_plan_over_plan")


def _collapse_scd2_after_column_removal(
    tgt: str,
    logical_key: list,
    remaining_tracked: list,
    removed_cols: list,
) -> None:
    """
    After columns are removed from SCD2 tracking, collapse adjacent history versions
    that now look identical under the remaining tracked fields.
    Also rewrites scd_hash for all rows using only the remaining fields.

    Algorithm:
      1. For each logical key, order versions by valid_from.
      2. A new group starts when the hash of remaining_tracked fields changes.
      3. Within each group keep only the first version, with:
           valid_from  = earliest in the group
           valid_to    = NULL  (if group contains an is_current row)
                       = MAX(valid_to) otherwise  (= start of next group)
           is_current  = True  if any row in the group was is_current
           scd_hash    = recomputed from remaining_tracked only
    """
    logger.info(
        f"[LOAD_SCD2][SCHEMA_EVOLUTION] Collapsing history for {tgt} "
        f"after removing columns: {removed_cols}. "
        f"Remaining tracked fields: {len(remaining_tracked)}."
    )
    tgt_df = spark.table(tgt)
    before_rows = tgt_df.count()

    # 1. Compute per-row hash of remaining tracked fields
    rem_hash_col = F.xxhash64(
        F.concat_ws("|", *[F.col(c).cast("string") for c in remaining_tracked])
    )
    tgt_df = tgt_df.withColumn("_rem_hash", rem_hash_col)

    # 2. Within each logical key ordered by valid_from, detect group boundaries
    w_key = Window.partitionBy(*[F.col(k) for k in logical_key]).orderBy("valid_from")
    tgt_df = tgt_df.withColumn("_prev_hash", F.lag("_rem_hash").over(w_key))
    tgt_df = tgt_df.withColumn(
        "_new_grp",
        F.when(
            F.col("_prev_hash").isNull() | (F.col("_rem_hash") != F.col("_prev_hash")),
            F.lit(1)
        ).otherwise(F.lit(0))
    )
    tgt_df = tgt_df.withColumn(
        "_grp",
        F.sum("_new_grp").over(w_key.rowsBetween(Window.unboundedPreceding, 0))
    )

    # 3. Per (logical_key, group): derive collapsed temporal columns
    grp_cols = [F.col(k) for k in logical_key] + [F.col("_grp")]
    grp_win  = Window.partitionBy(*grp_cols)
    row_win  = Window.partitionBy(*grp_cols).orderBy("valid_from")

    has_current = F.max(F.col("is_current").cast("int")).over(grp_win).cast("boolean")
    tgt_df = (
        tgt_df
        .withColumn("_min_vf",  F.min("valid_from").over(grp_win))
        .withColumn("_has_cur", has_current)
        # valid_to: NULL when group has a current row, else MAX(valid_to) of the group
        .withColumn("_new_vt",
            F.when(F.col("_has_cur"), F.lit(None).cast("timestamp"))
            .otherwise(F.max("valid_to").over(grp_win))
        )
        .withColumn("_rn", F.row_number().over(row_win))
    )

    # 4. Keep first row per group; update SCD2 temporal cols + recompute scd_hash
    new_hash = F.xxhash64(
        F.concat_ws("|", *[F.col(c).cast("string") for c in remaining_tracked])
    ).cast("long")

    collapsed = (
        tgt_df.filter(F.col("_rn") == 1)
        .withColumn("valid_from", F.col("_min_vf"))
        .withColumn("valid_to",   F.col("_new_vt"))
        .withColumn("is_current", F.col("_has_cur"))
        .withColumn("scd_hash",   new_hash)
        .drop("_rem_hash", "_prev_hash", "_new_grp", "_grp",
              "_min_vf", "_has_cur", "_new_vt", "_rn")
    )

    after_rows = collapsed.count()
    collapsed.write.format("delta").mode("overwrite") \
        .option("overwriteSchema", "false").saveAsTable(tgt)
    logger.info(
        f"[LOAD_SCD2][SCHEMA_EVOLUTION] Collapse complete: "
        f"{before_rows} → {after_rows} rows "
        f"(removed {before_rows - after_rows} redundant history rows)."
    )


def _resolve_exportdate_from_manifest(df: DataFrame) -> DataFrame:
    """
    Overwrite `ExportDate` on df using the authoritative `ExtractionDate` value
    from each row's manifest parquet (path stored in the `manifest_file` column).

    The bronze/silver `ExportDate` column is not reliable (frequently NULL in the
    source), so SCD2 versioning cannot depend on it. The package manifest
    (Manifest_SP_*.parquet / Manifest_DP_*.parquet) always carries an
    `ExtractionDate` entry in `yyyyMMdd_HHmmss` format (e.g. `20260814_134913`)
    that uniquely identifies the extraction run — we use that as ExportDate.

    Behaviour:
      * No `manifest_file` column                → df unchanged.
      * No manifest paths or all reads fail      → df unchanged (source value kept).
      * Manifest value present                   → takes precedence over source value
                                                    (coalesced with source as fallback).
    """
    mf_col = next((c for c in df.columns if c.lower() == "manifest_file"), None)
    if mf_col is None:
        return df

    manifest_paths = [
        str(r[0]) for r in
        df.select(mf_col).where(F.col(mf_col).isNotNull()).distinct().collect()
    ]
    if not manifest_paths:
        return df

    lookup_rows = []
    for p in manifest_paths:
        try:
            df_mf = spark.read.parquet(p)
            df_mf = df_mf.toDF(*[c.lower() for c in df_mf.columns])
            if "data" in df_mf.columns and "value" not in df_mf.columns:
                df_mf = df_mf.withColumnRenamed("data", "value")
            df_mf = df_mf.withColumn(
                "key",
                F.lower(F.regexp_replace(F.col("key"), r"\s+", ""))
            )
            row = (
                df_mf.filter(F.col("key") == "extractiondate")
                     .select("value").limit(1).collect()
            )
            if row and row[0][0] is not None:
                lookup_rows.append((p, str(row[0][0])))
            else:
                logger.info(f"[LOAD_SCD2][MANIFEST] No ExtractionDate found in {p}")
        except Exception as e:
            logger.info(f"[LOAD_SCD2][MANIFEST] Could not read manifest {p}: {e}")

    if not lookup_rows:
        return df

    lookup_df = spark.createDataFrame(
        lookup_rows, ["_mf_path", "_manifest_extraction_date_str"]
    ).withColumn(
        "_manifest_extraction_date",
        F.to_timestamp(F.col("_manifest_extraction_date_str"), "yyyyMMdd_HHmmss")
    ).drop("_manifest_extraction_date_str")

    df = (
        df.join(lookup_df, F.col(mf_col) == F.col("_mf_path"), "left")
          .drop("_mf_path")
    )
    exp_col = next((c for c in df.columns if c.lower() == "exportdate"), None)
    if exp_col:
        df = df.withColumn(
            exp_col,
            F.coalesce(
                F.col("_manifest_extraction_date"),
                F.col(exp_col).cast("timestamp"),
            ),
        )
    else:
        df = df.withColumn("ExportDate", F.col("_manifest_extraction_date"))
    df = df.drop("_manifest_extraction_date")
    logger.info(
        f"[LOAD_SCD2][MANIFEST] ExportDate resolved from manifest ExtractionDate "
        f"for {len(lookup_rows)} manifest file(s)"
    )
    return df


def load_scd2(cfg):
    """
    SCD Type 2 loading strategy (SQL-oriented), Fabric-friendly.

    valid_to on the expired row = incoming ExportDate.
    valid_from on the new row   = incoming ExportDate (same value, clean cutover).
    Initial load (target empty) backdates valid_from to 1900-01-01 instead,
    so pre-existing historical facts can still join to the first version.
    """
    tgt = cfg["TARGET_TABLE"]
    src_sql = cfg["SOURCE_SQL"]
    logical_key = cfg.get("LOGICAL_KEY") or []
    historical_fields = cfg.get("HISTORICAL_FIELDS") or []
    surrogate_key_col = cfg.get("SURROGATE_KEY_COL") or "Surrogate_key"
    ALL_MODE = historical_fields in ("All", ["All"], ["all"], ["ALL"])
    skip_historical_cfg = cfg.get("SKIP_HISTORICAL") or []

    if not logical_key:
        raise RuntimeError(f"load_scd2 requires LOGICAL_KEY for {tgt}")

    def _run_sql(label, sql):
        logger.info(f"[LOAD_SCD2] {label}\n{sql}")
        print(f"\n{'='*80}\n[LOAD_SCD2] {label}\n{'='*80}\n{sql}\n")
        return spark.sql(sql)

    # STEP 0
    ensure_table_exists(tgt, src_sql)
    before = spark.table(tgt).count()
    print(f"[LOAD_SCD2] {tgt} rows BEFORE: {before}")

    # STEP 1
    df = _run_sql("STEP 1: SOURCE_SQL", src_sql)

    # STEP 1b — Manifest-driven ExportDate override.
    # Bronze/silver `Exportdate` is often NULL; the package manifest's
    # `ExtractionDate` (path in the `manifest_file` column) is authoritative.
    df = _resolve_exportdate_from_manifest(df)

    # ── All-mode: resolve historical fields and compute scd_hash dynamically ─────
    if ALL_MODE:
        _ALWAYS_SKIP = {
            c.lower() for c in (
                list(logical_key) + [
                    surrogate_key_col, "scd_hash", "valid_from", "valid_to",
                    "is_current", "ins_batchid", "upd_batchid", "exportdate",
                    "sourcefile", "manifest_file", "manifest_package",
                    "load_date", "load_timestamp", "partitionkey",
                ]
            )
        }
        _user_skip = {c.lower() for c in skip_historical_cfg}
        _all_skip  = _ALWAYS_SKIP | _user_skip
        historical_fields = [
            c for c in df.columns
            if c.lower() not in _all_skip and not c.lower().startswith("_")
        ]
        logger.info(
            f"[LOAD_SCD2][ALL_MODE] Resolved {len(historical_fields)} historical fields"
        )
        df = df.withColumn(
            "scd_hash",
            F.xxhash64(F.concat_ws("|", *[F.col(c).cast("string") for c in historical_fields])).cast("long")
        )

        # ── Ensure scd_hash column exists in target (first-run: table created without it) ──
        _tgt_meta = {c.lower(): c for c in spark.table(tgt).columns}
        if "scd_hash" not in _tgt_meta:
            spark.sql(f"ALTER TABLE {tgt} ADD COLUMN scd_hash BIGINT")
            _tgt_meta = {c.lower(): c for c in spark.table(tgt).columns}

        # ── Schema evolution: new tracked columns not yet in target ───────────────
        _new_cols = [c for c in historical_fields if c.lower() not in _tgt_meta]
        if _new_cols:
            logger.info(f"[LOAD_SCD2][SCHEMA_EVOLUTION] Adding {len(_new_cols)} new tracked column(s): {_new_cols}")
            for _c in _new_cols:
                _col_type = dict(df.dtypes).get(_c, "STRING")
                spark.sql(f"ALTER TABLE {tgt} ADD COLUMN `{_c}` {_col_type}")
            _tgt_meta = {c.lower(): c for c in spark.table(tgt).columns}
            df.createOrReplaceTempView("_scd2_new_cols_src")
            _mc  = " AND ".join([f"t.`{k}` = s.`{k}`" for k in logical_key])
            _set = ", ".join([f"t.`{c}` = s.`{c}`" for c in _new_cols])
            _hsh = ("CAST(xxhash64(concat_ws('|', "
                    + ", ".join([f"CAST(s.`{c}` AS STRING)" for c in historical_fields])
                    + ")) AS BIGINT)")
            spark.sql(f"""
                MERGE INTO {tgt} AS t
                USING (SELECT * FROM _scd2_new_cols_src) AS s
                ON {_mc} AND t.is_current = true
                WHEN MATCHED THEN UPDATE SET {_set}, t.scd_hash = {_hsh}
            """)
            logger.info("[LOAD_SCD2][SCHEMA_EVOLUTION] Current rows updated with new column values and recomputed hash")

        # ── Schema evolution: columns removed from source → collapse history ──────
        _src_lower = {c.lower() for c in df.columns}
        _removed   = [
            c for c in spark.table(tgt).columns
            if c.lower() not in _src_lower
            and c.lower() not in _ALWAYS_SKIP
            and c.lower() not in _user_skip
            and not c.lower().startswith("_")
        ]
        if _removed:
            logger.info(f"[LOAD_SCD2][SCHEMA_EVOLUTION] Columns removed from source: {_removed}")
            _collapse_scd2_after_column_removal(tgt, logical_key, historical_fields, _removed)
        elif before > 0:
            # Rehash target's current rows using the current formula against TARGET values.
            # Using s.* here would adopt the incoming source hash and destroy change detection
            # (every row would classify as UNCHANGED on the next run).
            _mc  = " AND ".join([f"t.`{k}` = s.`{k}`" for k in logical_key])
            _hsh_target = ("CAST(xxhash64(concat_ws('|', "
                    + ", ".join([f"CAST(t.`{c}` AS STRING)" for c in historical_fields])
                    + ")) AS BIGINT)")
            df.createOrReplaceTempView("_scd2_hash_refresh")
            spark.sql(f"""
                MERGE INTO {tgt} AS t
                USING (SELECT DISTINCT {", ".join([f"`{k}`" for k in logical_key])} FROM _scd2_hash_refresh) AS s
                ON {_mc} AND t.is_current = true
                WHEN MATCHED AND (t.scd_hash IS NULL OR t.scd_hash <> {_hsh_target})
                    THEN UPDATE SET t.scd_hash = {_hsh_target}
            """)

    df_cols_lower = [c.lower() for c in df.columns]
    required = (
        ["ExportDate", "is_current", surrogate_key_col] if ALL_MODE
        else ["scd_hash", "ExportDate", "is_current", surrogate_key_col]
    ) + logical_key
    for col in required:
        if col.lower() not in df_cols_lower:
            raise RuntimeError(f"load_scd2: SOURCE_SQL must return '{col}' for {tgt}")

    # Deduplicate source by logical key: keep latest row per key (by ExportDate).
    # Prevents DELTA_MULTIPLE_SOURCE_ROW_MATCHING_TARGET_ROW_IN_MERGE when the
    # source table is itself SCD2-tracked and contains multiple versions per key.
    _exp_col = next(c for c in df.columns if c.lower() == "exportdate")
    from pyspark.sql.window import Window as _Window
    _w_dedup = _Window.partitionBy(*[F.col(k) for k in logical_key]).orderBy(F.col(_exp_col).desc())
    _dedup_before = df.count()
    df = (df.withColumn("_dedup_rn", F.row_number().over(_w_dedup))
            .filter(F.col("_dedup_rn") == 1)
            .drop("_dedup_rn"))
    _dedup_after = df.count()
    if _dedup_after < _dedup_before:
        logger.info(
            f"[LOAD_SCD2] Source deduplicated by {logical_key}: "
            f"{_dedup_before} → {_dedup_after} rows (duplicate logical keys removed)"
        )

    df.createOrReplaceTempView("_scd2_src")
    print(f"[LOAD_SCD2] SOURCE_SQL returned {_dedup_after} row(s)")

    target_cols = spark.table(tgt).columns  # refresh AFTER any schema evolution
    target_cols_lower = [c.lower() for c in target_cols]
    has_batch_tracking = "ins_batchid" in [c.lower() for c in df.columns] and "upd_batchid" in target_cols_lower

    if surrogate_key_col.lower() not in target_cols_lower:
        raise RuntimeError(
            f"load_scd2: TARGET_TABLE {tgt} is missing surrogate key column "
            f"'{surrogate_key_col}' (configured via SURROGATE_KEY_COL)"
        )

    export_date_col = next(c for c in df.columns if c.lower() == "exportdate")

    # STEP 2
    join_cond = " AND ".join([f"s.{k} = t.{k}" for k in logical_key])
    # prev_* aliases only needed when the target schema has explicit Prev{field} columns
    # Skip them in All-mode to avoid projecting 100+ unnecessary columns into the snapshot
    prev_cols_sql = ("" if ALL_MODE else
                     ", ".join([f"t.{f} AS _prev_{f}" for f in historical_fields]))

    classify_sql = f"""
        SELECT
            s.*,
            CASE
                WHEN t.{logical_key[0]} IS NULL THEN 'NEW'
                WHEN t.scd_hash <> s.scd_hash THEN 'CHANGED'
                ELSE 'UNCHANGED'
            END AS _change_type
            {"," + prev_cols_sql if prev_cols_sql else ""}
        FROM _scd2_src s
        LEFT JOIN (SELECT * FROM {tgt} WHERE is_current = true) t
        ON {join_cond}
    """
    classified_df = _run_sql("STEP 2: classify new / changed / unchanged", classify_sql)

    # Per-target snapshot table so parallel SCD notebooks don't share one physical
    # Delta location — the shared "_scd2_classified_snapshot" name was leaving a
    # log behind that Delta could not reconstruct once retention expired
    # (DELTA_TRUNCATED_TRANSACTION_LOG). Also nuke both the legacy name and any
    # stale per-target instance so a corrupt log can't block the write.
    _safe_tgt = re.sub(r"[^A-Za-z0-9]", "_", tgt)
    snapshot_tbl = f"_scd2_classified_snapshot__{_safe_tgt}"
    for _stale in ("_scd2_classified_snapshot", snapshot_tbl):
        try:
            spark.sql(f"DROP TABLE IF EXISTS {_stale}")
        except Exception as _e:
            logger.info(f"[LOAD_SCD2] Ignoring DROP failure for stale snapshot {_stale}: {_e}")
        try:
            mssparkutils.fs.rm(f"Tables/{_stale}", True)
        except Exception:
            pass
        try:
            mssparkutils.fs.rm(f"Tables/dbo/{_stale}", True)
        except Exception:
            pass

    classified_df.write.format("delta").mode("overwrite") \
        .option("overwriteSchema", "true") \
        .option("partitionOverwriteMode", "static") \
        .saveAsTable(snapshot_tbl)
    classified_df = spark.table(snapshot_tbl)
    classified_df.createOrReplaceTempView("_scd2_classified")

    counts = {r["_change_type"]: r["cnt"] for r in spark.sql(
        "SELECT _change_type, COUNT(*) AS cnt FROM _scd2_classified GROUP BY _change_type"
    ).collect()}
    new_count = counts.get("NEW", 0)
    changed_count = counts.get("CHANGED", 0)
    unchanged_count = counts.get("UNCHANGED", 0)
    print(f"[LOAD_SCD2] Classification: NEW={new_count}, CHANGED={changed_count}, UNCHANGED={unchanged_count}")

    # STEP 3 — expire, valid_to = ExportDate
    if changed_count > 0:
        merge_cond = " AND ".join([f"t.{k} = s.{k}" for k in logical_key])
        batch_update = ", t.upd_batchid = s.ins_batchid" if has_batch_tracking else ""
        merge_sql = f"""
            MERGE INTO {tgt} AS t
            USING (SELECT * FROM _scd2_classified WHERE _change_type = 'CHANGED') AS s
            ON {merge_cond} AND t.is_current = true
            WHEN MATCHED THEN UPDATE SET
                t.is_current = false,
                t.valid_to = s.{export_date_col}{batch_update}
        """
        _run_sql("STEP 3: expire changed rows", merge_sql)
    else:
        print("[LOAD_SCD2] No changed rows — nothing to expire")

    # STEP 3b — refresh untracked columns on UNCHANGED rows
    excluded_lower = set(
        [f.lower() for f in historical_fields] +
        [logical_key[0].lower(), "scd_hash", "exportdate",
         "is_current", surrogate_key_col.lower(), "valid_from", "valid_to",
         "ins_batchid", "upd_batchid"]
    )
    untracked_cols = [c for c in df.columns if c.lower() not in excluded_lower]

    if unchanged_count > 0 and untracked_cols:
        set_clause = ", ".join([f"t.{c} = s.{c}" for c in untracked_cols])
        if has_batch_tracking:
            set_clause += ", t.upd_batchid = s.ins_batchid"
        merge_cond = " AND ".join([f"t.{k} = s.{k}" for k in logical_key])
        partition_keys = ", ".join(logical_key)
        refresh_sql = f"""
            MERGE INTO {tgt} AS t
            USING (
                SELECT * FROM (
                    SELECT *, ROW_NUMBER() OVER (PARTITION BY {partition_keys} ORDER BY {export_date_col} DESC) AS _dedup_rn
                    FROM _scd2_classified WHERE _change_type = 'UNCHANGED'
                ) WHERE _dedup_rn = 1
            ) AS s
            ON {merge_cond} AND t.is_current = true
            WHEN MATCHED THEN UPDATE SET {set_clause}
        """
        _run_sql("STEP 3b: refresh untracked columns on unchanged rows", refresh_sql)
    else:
        print("[LOAD_SCD2] No unchanged rows with untracked columns to refresh — skipping")

    # STEP 4 — insert NEW + CHANGED, valid_from = ExportDate (or 1900 on initial load)
    insert_cols, insert_select = [], []
    for c in target_cols:
        c_lower = c.lower()
        if any(c_lower == f"prev{f}".lower() for f in historical_fields):
            f = next(f for f in historical_fields if f"prev{f}".lower() == c_lower)
            insert_cols.append(c); insert_select.append(f"_prev_{f}")
        elif c_lower == "valid_from" and before == 0:
            insert_cols.append(c)
            insert_select.append("CAST('1900-01-01 00:00:00' AS TIMESTAMP)")
        elif c_lower == "valid_from":
            insert_cols.append(c)
            insert_select.append(export_date_col)
        elif c in df.columns:
            matching_col = next((col for col in df.columns if col.lower() == c_lower), None)
            if matching_col:
                insert_cols.append(c)
                insert_select.append(matching_col)

    rows_to_insert = new_count + changed_count
    if rows_to_insert > 0:
        insert_sql = f"""
            INSERT INTO {tgt} ({", ".join(insert_cols)})
            SELECT {", ".join(insert_select)}
            FROM _scd2_classified
            WHERE _change_type IN ('NEW', 'CHANGED')
        """
        _run_sql("STEP 4: insert new/changed version rows", insert_sql)
    else:
        print("[LOAD_SCD2] No new or changed rows — skipping INSERT")

    # STEP 5
    after = spark.table(tgt).count()
    print(
        f"[LOAD_SCD2] {tgt} SUMMARY | before={before} after={after} "
        f"inserted={rows_to_insert} (new={new_count}, changed={changed_count}) "
        f"expired={changed_count} unchanged={unchanged_count}"
    )
    spark.sql(f"DROP TABLE IF EXISTS {snapshot_tbl}")  

def build_PlanOverPlan(
silver_table: str,
domain: str,
merge_keys: list,
version_col: str = "Version_id",
) -> None:
    """
    Full PoP rebuild: walks through ALL versions in chronological order,
    enriches each with COUNT / NewInThisVersion / DroppedInThisVersion,
    and writes the complete enriched result directly to the silver table.


    Parameters
    ----------
    silver_table : str
        Fully-qualified source table (e.g. 'silver.opr_backorderfact').
    domain : str
        Domain label (for logging only).
    merge_keys : list
        Columns forming the composite comparison key.
    version_col : str
        Column that identifies each version/snapshot (default 'Version_id').
    """
    start = _time.time()
    output_table = silver_table

    logger.info(f"[PoP] Starting full rebuild for {silver_table} ({domain})")

    if not merge_keys:
        raise ValueError("[PoP] At least one merge key is required")

    # Version column is the version axis, not a business key — never compare on it.
    _orig_merge_keys = list(merge_keys)
    merge_keys = [k for k in merge_keys if k.lower() != version_col.lower()]
    if len(merge_keys) != len(_orig_merge_keys):
        logger.warning(
            f"[PoP] Removed '{version_col}' from merge_keys "
            f"(was {_orig_merge_keys}, now {merge_keys})"
        )
    if not merge_keys:
        raise ValueError(
            f"[PoP] merge_keys is empty after removing version column '{version_col}'"
        )

    # ── 1. Validate table exists ─────────────────────────────────────────────
    if not spark.catalog.tableExists(silver_table):
        raise RuntimeError(f"[PoP] Table {silver_table} does not exist")

    # ── 1b. Refresh table metadata to avoid stale parquet file references ──
    # (e.g. after unit conversion table swap / rename operations)
    spark.sql(f"REFRESH TABLE {silver_table}")

    # ── 2. Read source and strip any pre-existing PoP columns ──
    df_raw = spark.table(silver_table)
    raw_row_count = df_raw.count()
    logger.info(f"[PoP] Read {raw_row_count:,} rows from {silver_table}")

    # If table already has PoP data from a prior run,
    # keep only real records before rebuilding
    raw_cols_lower = [c.lower() for c in df_raw.columns]
    if "count" in raw_cols_lower:
        count_non_null = df_raw.filter(F.col("COUNT").isNotNull()).count()
        if count_non_null > 0:
            # Prior run detected - COUNT has real values (0 or 1).
            # Keep COUNT == 1 (real from prior PoP) and COUNT IS NULL (freshly loaded rows).
            # Drop COUNT == 0 (ghost/dropped rows from prior PoP).
            df_raw = df_raw.filter((F.col("COUNT") == 1) | F.col("COUNT").isNull())
            filtered_row_count = df_raw.count()
            logger.info(f"[PoP] After COUNT filter: {filtered_row_count:,} rows (removed ghost/dropped rows, kept fresh NULL rows)")
        else:
            # COUNT column exists but is ALL NULL - first run from bronze
            logger.info("[PoP] COUNT column detected but all NULL (first run); using all rows as-is")
    else:
        logger.info("[PoP] No COUNT column found (first run or fresh table)")

    df_clean = _strip_pop_columns(df_raw)
    clean_row_count = df_clean.count()
    # logger.info(f"[PoP] After stripping PoP columns: {clean_row_count:,} rows")

    # ── 3. Validate version_col exists and has data ──────────────────────────
    if version_col not in df_clean.columns:
        raise ValueError(f"[PoP] Version column '{version_col}' not found in {silver_table}")

    # Check for non-null values in version column
    non_null_version_count = df_clean.filter(F.col(version_col).isNotNull()).count()
    logger.info(f"[PoP] Non-null values in '{version_col}': {non_null_version_count:,} / {clean_row_count:,}")

    if non_null_version_count == 0:
        logger.error(f"[PoP] Version column '{version_col}' contains only NULL values!")
        logger.error(f"[PoP] Cannot proceed with PoP processing — skipping")
        return

    # Get ordered list of distinct versions
    versions = [
        row[0]
        for row in (
            df_clean
            .select(version_col)
            .filter(F.col(version_col).isNotNull())
            .distinct()
            .orderBy(F.col(version_col).asc())
            .collect()
        )
    ]

    if not versions:
        logger.error(f"[PoP] No distinct values found in column '{version_col}' of {silver_table}")
        logger.error(f"[PoP] Row count was {clean_row_count:,}, but version column appears empty or NULL — skipping")
        return

    logger.info(f"[PoP] Found {len(versions)} version(s)")
    logger.info(f"[PoP] Merge keys: {merge_keys}")
    logger.info(f"[PoP] Version column: {version_col}")
    logger.info(f"[PoP] Processing {clean_row_count:,} total records across {len(versions)} version(s)")

    # ── 4. Walk through versions and enrich ──────────────────────────────────
    all_results = []

    for i, ver in enumerate(versions):
        current_df = df_clean.filter(F.col(version_col) == ver)

        if i == 0:
            # First version: everything is "new", nothing dropped
            enriched = (
                current_df
                .withColumn("COUNT", F.lit(1))
                .withColumn("NewInThisVersion", F.lit(1))
                .withColumn("DroppedInThisVersion", F.lit(0))
            )
            real_cnt = current_df.count()
            # logger.info(
            #     f"[PoP] Version {ver} (init): {real_cnt:,} records, all marked new"
            # )

        else:
            prev_ver = versions[i - 1]
            prev_df = df_clean.filter(F.col(version_col) == prev_ver)

            prev_keys = prev_df.select(merge_keys).distinct()
            curr_keys = current_df.select(merge_keys).distinct()

            # Tag current records: new or carried over
            enriched_current = (
                current_df
                .withColumn("COUNT", F.lit(1))
                .withColumn("DroppedInThisVersion", F.lit(0))
                .join(
                    prev_keys.withColumn("_existed", F.lit(1)),
                    on=merge_keys,
                    how="left",
                )
                .withColumn(
                    "NewInThisVersion",
                    F.when(F.col("_existed").isNull(), F.lit(1))
                    .otherwise(F.lit(0)),
                )
                .drop("_existed")
            )

            # Ghost rows: keys present in prev but missing in current.
            # Stamp them with the CURRENT version so they don't collide with
            # the real prev-version rows on (merge_keys + version_col).
            dropped_keys = prev_keys.join(curr_keys, on=merge_keys, how="left_anti")

            _ver_type = prev_df.schema[version_col].dataType
            ghost_rows = (
                prev_df
                .join(dropped_keys, on=merge_keys, how="inner")
                .withColumn(version_col, F.lit(ver).cast(_ver_type))
                .withColumn("COUNT", F.lit(0))
                .withColumn("NewInThisVersion", F.lit(0))
                .withColumn("DroppedInThisVersion", F.lit(1))
            )
            if "Version_id_key" in prev_df.columns:
                ghost_rows = ghost_rows.withColumn(
                    "Version_id_key",
                    F.xxhash64(F.col(version_col)).cast("bigint"),
                )

            enriched = enriched_current.unionByName(ghost_rows)

            real_cnt  = enriched_current.count()
            new_cnt   = enriched_current.filter(F.col("NewInThisVersion") == 1).count()
            ghost_cnt = ghost_rows.count()
            # logger.info(
            #     f"[PoP] Version {ver} vs {prev_ver}: "
            #     f"real={real_cnt:,}, new={new_cnt:,}, "
            #     f"carried={real_cnt - new_cnt:,}, ghosts={ghost_cnt:,}"
            # )

        all_results.append(enriched)

    # ── 5. Union all versions and write to silver table ──────────────────────
    final_df = reduce(lambda a, b: a.unionByName(b), all_results)
    final_row_count = final_df.count()

    (
        final_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .option("partitionOverwriteMode", "static")
        .saveAsTable(output_table)
    )

    elapsed = _time.time() - start
    logger.info(f"[PoP] Full rebuild complete in {elapsed:.2f}s → {silver_table} ({final_row_count:,} rows)")

    # ── 6. Print validation summary ──────────────────────────────────────────
    _validate_pop_result(spark, silver_table, silver_table, version_col)

def enrich_with_pop_fields(
spark: SparkSession,
silver_table_path: str,
new_version_df: DataFrame,
version_col: str = "Version_id",
comparison_key_cols: list = None,
) -> DataFrame:
    """
    Enriches ONE incoming version with PoP fields by comparing against the
    immediately preceding version in the Silver table.


    Writes enriched result (real rows + ghost rows) directly to the silver table.

    Returns the enriched DataFrame.
    """
    if not comparison_key_cols:
        raise ValueError("[PoP] At least one comparison key column required")

    output_table = silver_table_path

    # Identify the new version value
    new_version_val = (
        new_version_df
        .select(F.max(version_col))
        .collect()[0][0]
    )

    # Load Silver and find the immediately preceding version
    silver_df = spark.table(silver_table_path)

    preceding_version_val = (
        silver_df
        .filter(F.col(version_col) < new_version_val)
        .select(F.max(version_col).alias("prev_version"))
        .collect()[0]["prev_version"]
    )

    # Strip any existing PoP columns from incoming data
    new_version_df = _strip_pop_columns(new_version_df)

    # ── Initialization path ──────────────────────────────────────────────────
    if preceding_version_val is None:
        logger.info(f"[PoP] No preceding version. Initializing for {new_version_val}.")
        result_df = (
            new_version_df
            .withColumn("COUNT", F.lit(1))
            .withColumn("NewInThisVersion", F.lit(1))
            .withColumn("DroppedInThisVersion", F.lit(0))
        )
        (
            result_df.write
            .format("delta")
            .mode("overwrite")
            .option("overwriteSchema", "true")
            .option("partitionOverwriteMode", "static")
            .saveAsTable(output_table)
        )
        _validate_pop_result(spark, silver_table_path, output_table, version_col)
        return result_df

    logger.info(f"[PoP] New: {new_version_val} | Previous: {preceding_version_val}")
    logger.info(f"[PoP] Comparison keys: {comparison_key_cols}")

    # ── Previous-version keys (real records only, COUNT=1) ───────────────────
    prev_keys_df = (
        silver_df
        .filter(
            (F.col(version_col) == preceding_version_val)
            & (F.col("COUNT") == 1)
        )
        .select(comparison_key_cols)
        .distinct()
    )

    new_keys_df = new_version_df.select(comparison_key_cols).distinct()

    # ── Enrich new-version records ───────────────────────────────────────────
    new_enriched_df = (
        new_version_df
        .withColumn("COUNT", F.lit(1))
        .withColumn("DroppedInThisVersion", F.lit(0))
        .join(
            prev_keys_df.withColumn("_exists_in_prev", F.lit(1)),
            on=comparison_key_cols,
            how="left",
        )
        .withColumn(
            "NewInThisVersion",
            F.when(F.col("_exists_in_prev").isNull(), F.lit(1))
            .otherwise(F.lit(0)),
        )
        .drop("_exists_in_prev")
    )

    # ── Ghost rows for dropped keys ──────────────────────────────────────────
    dropped_keys_df = prev_keys_df.join(new_keys_df, on=comparison_key_cols, how="left_anti")

    prev_real_clean = _strip_pop_columns(
        silver_df.filter(
            (F.col(version_col) == preceding_version_val)
            & (F.col("COUNT") == 1)
        )
    )

    ghost_rows_df = (
        prev_real_clean
        .join(dropped_keys_df, on=comparison_key_cols, how="inner")
        .withColumn(version_col, F.lit(new_version_val))
        .withColumn("COUNT", F.lit(0))
        .withColumn("NewInThisVersion", F.lit(0))
        .withColumn("DroppedInThisVersion", F.lit(1))
    )

    # ── Combine and write to silver table ──────────────────────────────────────
    result_df = new_enriched_df.unionByName(ghost_rows_df)

    (
        result_df.write
        .format("delta")
        .mode("overwrite")
        .option("overwriteSchema", "true")
        .option("partitionOverwriteMode", "static")
        .saveAsTable(output_table)
    )

    # ── Audit log ────────────────────────────────────────────────────────────
    total     = new_version_df.count()
    new_count = new_enriched_df.filter(F.col("NewInThisVersion") == 1).count()
    dropped   = ghost_rows_df.count()

    logger.info(f"[PoP] Real records       : {total:,}")
    logger.info(f"[PoP] NewInThisVersion   : {new_count:,}")
    logger.info(f"[PoP] Carried over       : {total - new_count:,}")
    logger.info(f"[PoP] Ghosts (dropped)   : {dropped:,}")
    logger.info(f"[PoP] Total written      : {total + dropped:,}")

    _validate_pop_result(spark, silver_table_path, output_table, version_col)

    return result_df

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_pop")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
