# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_metadata
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: load_metadata_files
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Metadata File Loader
# Reads extraction metadata Parquet files, normalizes keys, and writes pivoted results to `bronze.extraction_metadata`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def load_metadata_files(date_path: str, target_table: str):
    base = f"Files/archive/parquet/{date_path.strip('/')}"
    paths = []

    # Extract domain + entity from target table
    _, tbl = target_table.split(".", 1)
    domain, entity = tbl.split("_", 1)
    domain = domain.lower()
    entity = entity.lower()

    logger.info(f"Metadata loader: domain={domain}, entity={entity}")

    # ------------------------------------------------------------
    # 1. Find metadata parquet files
    # ------------------------------------------------------------
    def walk(path):
        try:
            items = mssparkutils.fs.ls(path)
        except Exception:
            return
        for it in items:
            full = f"{path}/{it.name}"
            if it.isDir:
                walk(full)
            elif (
                it.name.lower().endswith(".parquet")
                and "metadata" in it.name.lower()
            ):
                paths.append(full)

    walk(base)

    if not paths:
        logger.info(f"⚠️ No metadata files found under {base}")
        return

    logger.info(f"Found {len(paths)} metadata files")

    rows = []

    # ------------------------------------------------------------
    # 2. Read + normalize each metadata file
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

        # ------------------------------------------------------------
        # Normalize key values
        # ------------------------------------------------------------
        df_i = (
            df_i
            .withColumn("key", F.lower(F.col("key")))                     # lowercase
            .withColumn("key", F.regexp_replace(F.col("key"), r"\s+", ""))  # remove spaces
            .withColumn(                                                # fix typo
                "key",
                F.when(F.col("key") == "functionalerea", F.lit("functionalArea"))
                 .otherwise(F.col("key"))
            )
            .withColumn(                                                # rename key
                "key",
                F.when(F.col("key") == "muloactionfilter", F.lit("partialloadingstringmu"))
                 .otherwise(F.col("key"))
            )
        )

        # ------------------------------------------------------------
        # Transform data for partialloadingstringmu
        # ------------------------------------------------------------
        df_i = df_i.withColumn(
            "data",
            F.when(
                F.col("key") == "partialloadingstringmu",
                F.concat_ws(
                    ",",
                    F.transform(
                        F.split(F.col("data"), ","),
                        lambda x: F.concat(F.lit("'"), F.trim(x), F.lit("'"))
                    )
                )
            ).otherwise(F.col("data"))
        )

        # Add folder + metadata
        folder = p.split("/")[-2]
        df_i = (
            df_i
            .withColumn("domain", F.lit(domain))
            .withColumn("source_folder", F.lit(folder))
            .withColumn("load_timestamp", F.current_timestamp())
        )

        rows.append(df_i)

    if not rows:
        logger.info("⚠️ No valid metadata rows found.")
        return

    # ------------------------------------------------------------
    # 3. Union all metadata rows
    # ------------------------------------------------------------
    df_meta = rows[0]
    for other in rows[1:]:
        df_meta = df_meta.unionByName(other, allowMissingColumns=True)

    # ------------------------------------------------------------
    # 4. Pivot into one row per folder
    # ------------------------------------------------------------
    df_meta = (
        df_meta
        .groupBy("source_folder")
        .pivot("key")
        .agg(F.first("data"))
        .withColumn("domain", F.lit(domain))
        .withColumn("load_timestamp", F.current_timestamp())
    )

    # ------------------------------------------------------------
    # 5. Write to bronze metadata table
    # ------------------------------------------------------------
    df_meta.write.format("delta").mode("append").saveAsTable("bronze.extraction_metadata")

    logger.info(f"Loaded metadata rows into bronze.extraction_metadata")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": true,
# META   "editable": false
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_metadata")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
