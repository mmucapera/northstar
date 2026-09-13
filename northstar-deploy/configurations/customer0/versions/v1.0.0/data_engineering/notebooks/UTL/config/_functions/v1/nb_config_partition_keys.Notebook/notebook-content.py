# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_partition_keys
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: add_partitionkey_regex, _validate_partition_keys
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def add_partitionkey_regex(df, domain: str, manifest_partitionkey_col: str):

    def _build_partitionkey_rlike_pattern(iv: str, domain: str):
        if not iv:
            return None

        iv = iv.strip().strip("'\"")

        # CASE 1 — pattern contains wildcard → REGEX
        if "*" in iv:
            if domain == "OPR":
                regex = (
                    iv.replace("/", "\\\\/")   # double escape slash
                      .replace("*", ".*")
                      .replace("|", "\\\\|")   # double escape pipe
                )
            else:  # FCT
                regex = (
                    iv.replace("/", "\\\\/")   # single escape slash
                      .replace("*", ".*")
                      .replace("|", "\\|")     # single escape pipe
                )

            return f"^{regex}$"

        # CASE 2 — exact value (no wildcard)
        else:
            if domain == "OPR":
                exact = iv.replace("|", "\\\\|")   # double escape pipe
            else:  # FCT
                exact = iv.replace("|", "\\|")     # single escape pipe

            return f"^{exact}$"

    # Wrap Python function as UDF
    build_pattern_udf = F.udf(
        lambda iv: _build_partitionkey_rlike_pattern(iv, domain),
        StringType()
    )

    # Apply UDF and return new dataframe
    return df.withColumn(
        f"{manifest_partitionkey_col}_regex",
        build_pattern_udf(F.col(manifest_partitionkey_col))
    )

def _validate_partition_keys(source_table: str, manifest_partitionkey_col: str):
    try:
        logger.info(f"[DQ_PARTITION_KEYS] Validating {source_table} with manifest partition key column: {manifest_partitionkey_col}")
        
        table_only = source_table.split(".")[-1]
        domain = table_only.split("_")[0].upper() if "_" in table_only else None
        logger.info(f"[DQ_PARTITION_KEYS] Domain: {domain}")
        
        # Load source and prefix with bronze_
        df = spark.table(source_table)

        batchid_rows = (
            df.select("ins_batchid")
            .distinct()
            .collect()
        )
        if not batchid_rows:
            logger.warning(f"[DQ_PARTITION_KEYS] Table {source_table} is empty — skipping partition key check")
            return

        batchid = batchid_rows[0][0]

        # display(df.columns)
        
        source_partitionkey_col = None
        for possible_col in ["partitionkey","Partitionkey"]:
            if possible_col in df.columns:
                source_partitionkey_col = possible_col
                break
        
        if source_partitionkey_col is None:
            msg = f"[DQ_PARTITION_KEYS] ERROR: Partition key column not found in source table. Available: {df.columns}"
            logger.error(msg)
            raise RuntimeError(msg)
        
        logger.info(f"[DQ_PARTITION_KEYS] Source partition key column: {source_table}.{source_partitionkey_col}")
        
        # Find manifest file column (try both possible casings)
        manifest_col = None
        for possible_col in ["manifest_file","Manifest_file"]:
            if possible_col in df.columns:
                manifest_col = possible_col
                break
        
        if not manifest_col:
            msg = "[DQ_PARTITION_KEYS] No manifest_file column found – cannot validate"
            logger.error(msg)
            raise RuntimeError(msg)
        
        # Get manifest file paths
        paths = df.select(manifest_col).dropna().distinct().rdd.map(lambda r: str(r[0])).collect()
        if not paths:
            msg = "[DQ_PARTITION_KEYS] No manifest file paths found – cannot validate"
            logger.error(msg)
            raise RuntimeError(msg)
        
        # print(f"Found {len(paths)} manifest file paths")
        
        # Read all manifests
        manifest_dfs = []
        for p in paths:
            try:
                mf = spark.read.parquet(p).toDF(*[c.lower() for c in spark.read.parquet(p).columns])
                
                if "data" in mf.columns and "value" not in mf.columns:
                    mf = mf.withColumnRenamed("data", "value")
                
                mf = (mf
                      .withColumn("key", F.lower(F.col("key")))
                      .withColumn("key", F.regexp_replace(F.col("key"), r"\s+", ""))
                      .withColumn("key", F.regexp_replace(F.col("key"), r"\.", "_")))
                
                folder = p.split("/")[-2]
                mf = mf.withColumn("manifest_package", F.lit(folder))
                mf = mf.withColumn("manifest_file", F.lit(p))
                manifest_dfs.append(mf)
            except Exception as e:
                logger.error(f"[DQ_PARTITION_KEYS] Error reading {p}: {e}")
                raise
        
        if not manifest_dfs:
            msg = "[DQ_PARTITION_KEYS] No manifest dataframes loaded – validation failed"
            logger.error(msg)
            raise RuntimeError(msg)

        # display(manifest_dfs[0])
        
        df_meta = manifest_dfs[0]
        for other in manifest_dfs[1:]:
            df_meta = df_meta.unionByName(other, allowMissingColumns=True)
        
        df_manifest = (
            df_meta
            .groupBy("manifest_package", "manifest_file")
            .pivot("key")
            .agg(F.first("value"))
            )

        try:
            df_manifest = df_manifest.select("manifest_package", "manifest_file", manifest_partitionkey_col)
        except Exception as e:
            msg = f"[DQ_PARTITION_KEYS] Column '{manifest_partitionkey_col}' not found in manifest file."
            logger.error(msg)
            # stop_notebook(msg)
            raise RuntimeError(msg)
        
        # display(df_manifest)

        df_clean = (
            df_manifest
            .withColumn(manifest_partitionkey_col, F.regexp_replace(manifest_partitionkey_col, r"^'|'$", ""))
            .withColumn(manifest_partitionkey_col, F.split(manifest_partitionkey_col, r"','"))        # explode into rows
            .withColumn(manifest_partitionkey_col, F.explode(manifest_partitionkey_col))
            .withColumn(manifest_partitionkey_col, F.regexp_replace(manifest_partitionkey_col, r"'", ""))
        )

        # display(df_clean)

        df_manifest_regex = add_partitionkey_regex(df_clean, domain,manifest_partitionkey_col)

        # display(df_manifest_regex)

        # # Collect source partition keys
        df_bronze_partitionkeys = df.select(source_partitionkey_col)\
                                 .alias("bronze_partitionkey")\
                                 .dropna()\
                                 .distinct()\
                                 .rdd.map(lambda r: str(r[0]))\
                                 .collect()

        cnt_pks = len(df_bronze_partitionkeys)

        df_bronze_partitionkeys = spark.createDataFrame([(x,) for x in df_bronze_partitionkeys], ["bronze_partitionkey"])

        logger.info(f"[DQ_PARTITION_KEYS] {source_table} ({cnt_pks} partition keys):")
        # display(df_bronze_partitionkeys)

        df_bronze_partitionkeys.createOrReplaceTempView(f"{table_only}_tmp")
        df_manifest_regex.createOrReplaceTempView(f"{manifest_partitionkey_col}_regex_tmp")

        # print(f"{table_only}_tmp")
        # print(f"{manifest_partitionkey_col}_regex_tmp")
        tmpview= f"{table_only}_tmp{manifest_partitionkey_col}_regex_tmp"

        # Create a UDF to fix the regex pattern
        def fix_regex_pattern(pattern):
            """Convert stored pattern to valid regex pattern"""
            if pattern is None:
                return None
            # Remove one layer of escaping: ^ONE\\/GB10\\|.*\\|P01$ -> ^ONE\/GB10\|.*\|P01$
            return pattern.replace('\\\\', '\\')

        fix_regex_udf = udf(fix_regex_pattern, StringType())

        # Create a new table/view with fixed regex patterns
        df_regex_fixed = spark.table(f"{manifest_partitionkey_col}_regex_tmp") \
            .withColumn("regex_pattern_rlike", fix_regex_udf(col(f"{manifest_partitionkey_col}_regex"))) \
            .filter(col("regex_pattern_rlike").isNotNull())

        df_regex_fixed.createOrReplaceTempView(f"{manifest_partitionkey_col}_regex_fixed")

        sql_st = f"""
        create or replace temp view {tmpview} as
        select distinct
        a.bronze_partitionkey,
        b.{manifest_partitionkey_col},
        b.{manifest_partitionkey_col}_regex,
        CASE WHEN a.bronze_partitionkey RLIKE b.regex_pattern_rlike THEN 1 ELSE 0 END Match
        from {table_only}_tmp a 
        left join {manifest_partitionkey_col}_regex_fixed b 
        on a.bronze_partitionkey RLIKE b.regex_pattern_rlike
        """

        df = spark.sql(sql_st)

        cnt_no_match = spark.sql(f"select min(match) from {tmpview}").collect()[0][0]

        if cnt_no_match == 1:
            logger.info(f"[DQ_PARTITION_KEYS] All Partitions keys in Manifest file have at least one match in {source_table}")
            display(spark.sql(f"select * from {tmpview}"))
        else:
            df_manifest_regex.select("manifest_package","manifest_file").distinct().createOrReplaceTempView("aux")

            display(
            spark.sql(f"""
                    select distinct {batchid} as batchid,* 
                    from {tmpview}
                    JOIN
                    aux
                    on 1=1
                    limit 5
                    """
                        )
                )

            df = spark.sql(f"""
                    select distinct {batchid} as batchid,manifest_file,manifest_package,'{source_table}' as bronze_table,bronze_partitionkey, current_timestamp() check_timestamp
                    from {tmpview}
                    JOIN
                    aux
                    on 1=1
                    limit 5
                    """
                )
                
            df.write.format("delta").mode("append").saveAsTable("log.audit_dq_partition_keys")
                        
            msg = f"[DQ_PARTITION_KEYS] One or more partitions keys in Manifest file don't have a match in {source_table} limit 5"
            logger.error(msg)
            raise RuntimeError(msg)  # Raise exception to fail notebook
    
    except RuntimeError as runtime_err:
        # Log the error and exit notebook on validation failure
        logger.error(f"[DQ_PARTITION_KEYS] Validation failure: {runtime_err}")
        # stop_notebook(f"[DQ_PARTITION_KEYS] {runtime_err}")
        raise  # Re-raise to ensure notebook fails
    except Exception as e:
        msg = f"[DQ_PARTITION_KEYS] Validation error for {source_table}: {e}"
        logger.error(msg)
        # stop_notebook(msg)
        raise RuntimeError(msg)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_partition_keys")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
