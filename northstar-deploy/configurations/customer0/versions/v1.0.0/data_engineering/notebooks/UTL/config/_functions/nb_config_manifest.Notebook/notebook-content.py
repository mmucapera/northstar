# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_manifest
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: load_extraction_manifest_file
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Extraction Manifest Loader
# Discovers and registers manifest metadata Parquet files into `log.audit_package_manifest` for downstream lookup.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def load_extraction_manifest_file(batchid: int, date_path: str):
    import pyspark.sql.functions as F
    import pyarrow.parquet as pq

    base = f"Files/archive/parquet/{date_path.strip('/')}"
    paths = []

    # ------------------------------------------------------------
    # Unified manifest matcher (SP + DP formats)
    # ------------------------------------------------------------
    def is_manifest_file(name: str) -> bool:
        n = name.lower()

        # SP Full
        if n.startswith("manifest_sp_full") and n.endswith(".parquet"):
            return True

        # SP Daily
        if n.startswith("metadata_sp_daily") and n.endswith(".parquet"):
            return True

        # DP (DMR, DemandPlanningWeekly, etc.)
        if n.startswith("metadata_dp_") and n.endswith(".parquet"):
            return True

        return False

    # ------------------------------------------------------------
    # Only scan the date folder (NOT recursively)
    # DP manifests live at the date level
    # SP manifests may live inside package folders
    # ------------------------------------------------------------
    try:
        items = mssparkutils.fs.ls(base)
    except Exception:
        logger.info(f"⚠️ Cannot list folder: {base}")
        return

    # 1. Collect DP manifests (always at date level)
    for it in items:
        if not it.isDir and is_manifest_file(it.name):
            paths.append(f"{base}/{it.name}")

    # 2. Collect SP manifests (inside package folders)
    for it in items:
        if it.isDir:
            pkg_path = f"{base}/{it.name}"
            try:
                pkg_items = mssparkutils.fs.ls(pkg_path)
            except:
                continue

            for f in pkg_items:
                if not f.isDir and is_manifest_file(f.name):
                    paths.append(f"{pkg_path}/{f.name}")

    # ------------------------------------------------------------
    # No manifests found
    # ------------------------------------------------------------
    if not paths:
        logger.info(f"⚠️ No metadata files found under {base}")
        return

    logger.info(f"Found {len(paths)} metadata files for {date_path}")

    rows = []

    # ------------------------------------------------------------
    # Read + normalize each metadata file
    # ------------------------------------------------------------
    for p in paths:
        df_i = None

        # Try Spark read
        try:
            df_i = (
                spark.read
                    .option("mergeSchema", "false")
                    .option("columnNameOfCorruptRecord", "_bad")
                    .parquet(p)
            )
        except Exception:
            # PyArrow fallback
            try:
                table = pq.read_table(p)
                pandas_df = table.to_pandas()
                pandas_df = pandas_df.where(pandas_df.notnull(), None)
                for c in pandas_df.columns:
                    pandas_df[c] = pandas_df[c].astype("string")
                df_i = spark.createDataFrame(pandas_df)
                logger.info(f"PyArrow fallback succeeded for {p}")
            except Exception:
                logger.info(f"Skipping unreadable metadata file: {p}")
                continue

        # Normalize column names
        df_i = df_i.toDF(*[c.lower() for c in df_i.columns])

        # Normalize key values
        df_i = (
            df_i
            .withColumn("key", F.lower(F.col("key")))
            .withColumn("key", F.regexp_replace(F.col("key"), r"\s+", ""))
            .withColumn("key", F.regexp_replace(F.col("key"), r"\.", "_"))
        )

        # Add folder + metadata
        folder = p.split("/")[-2]
        df_i = (
            df_i
            .withColumn("sourcefolder", F.lit(folder))
            .withColumn("domain", F.upper(F.element_at(F.split(F.lit(folder), "_"), -1)))
            .withColumn("load_timestamp", F.current_timestamp())
            .withColumn("manifest_file", F.lit(p))
        )

        rows.append(df_i)

    if not rows:
        logger.info("⚠️ No valid metadata rows found.")
        return

    # ------------------------------------------------------------
    # Union all metadata rows
    # ------------------------------------------------------------
    df_meta = rows[0]
    for other in rows[1:]:
        df_meta = df_meta.unionByName(other, allowMissingColumns=True)

    # ------------------------------------------------------------
    # Pivot into one row per folder
    # ------------------------------------------------------------
    df_meta = (
        df_meta
        .groupBy("sourcefolder", "manifest_file")
        .pivot("key")
        .agg(F.first("value"))
        .withColumn("load_timestamp", F.current_timestamp())
    )

    df_meta = df_meta.toDF(*[c[0].upper() + c[1:] for c in df_meta.columns])

    # Rename Sourcefolder → Manifest_package
    if "Sourcefolder" in df_meta.columns:
        df_meta = df_meta.withColumnRenamed("Sourcefolder", "Manifest_package")
    
    df_meta = df_meta.withColumn("batchid", F.lit(batchid))

    # Reorder columns
    cols = df_meta.columns

    ordered_cols = []
    if "batchid" in cols:
        ordered_cols.append("batchid")
    if "Manifest_package" in cols:
        ordered_cols.append("Manifest_package")
    if "Manifest_file" in cols:
        ordered_cols.append("Manifest_file")

    for c in cols:
        if c not in ordered_cols:
            ordered_cols.append(c)

    df_meta = df_meta.select(*ordered_cols)

    # ------------------------------------------------------------
    # Write to audit table
    # ------------------------------------------------------------
    df_meta.createOrReplaceTempView("staging_meta")

    # display(df_meta)

    spark.sql("""
    CREATE TABLE IF NOT EXISTS log.audit_package_manifest
    USING delta
    AS SELECT * FROM staging_meta WHERE 1=0
    """)

    delta_tbl = DeltaTable.forName(spark, "log.audit_package_manifest")

    keys = [r["Manifest_package"] for r in df_meta.select("Manifest_package").distinct().collect()]
    delta_tbl.delete(F.col("Manifest_package").isin(keys))

    (
        df_meta
        .write
        .format("delta")
        .mode("append")
        .option("mergeSchema", "true")
        .saveAsTable("log.audit_package_manifest")
    )

    logger.info(f"Loaded metadata rows into log.audit_package_manifest")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_manifest")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
