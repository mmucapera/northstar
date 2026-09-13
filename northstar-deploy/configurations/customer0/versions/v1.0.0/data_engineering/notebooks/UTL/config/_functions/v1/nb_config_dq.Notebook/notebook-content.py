# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_dq
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: _validate_non_nulls, _check_source_duplicates
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Data Quality Validation Functions
# DQ checks for duplicates and null values with audit logging.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _validate_non_nulls(source_table: str, columns: list):
    try:
        if not spark.catalog.tableExists(source_table):
            msg = f"[DQ_NON_NULLS] Table {source_table} does not exist"
            logger.error(msg)
            # stop_notebook(msg)
            raise RuntimeError(msg)  # Ensure exception propagates

        df = spark.table(source_table)

        batchid_rows = (
            df.select("ins_batchid")
            .distinct()
            .collect()
        )
        if not batchid_rows:
            logger.warning(f"[DQ_NON_NULLS] Table {source_table} is empty — skipping null check")
            return

        batchid = int(batchid_rows[0][0])

        print(f"Batch ID: {batchid}")

        # Validate columns
        table_cols = {c.lower(): c for c in df.columns}
        cols_lower = [c.lower() for c in columns]
        missing_cols = [c for c in cols_lower if c not in table_cols]

        if missing_cols:
            msg = f"[DQ_NON_NULLS] Columns not found in {source_table}: {missing_cols}"
            logger.error(msg)
            # stop_notebook(msg)
            raise RuntimeError(msg)  # Ensure exception propagates

        actual_cols = [table_cols[c] for c in cols_lower]
        logger.info(f"[DQ_NON_NULLS] Checking for NULL values in {source_table} on columns: {actual_cols}")

        total_rows = df.count()

        # Count NULLs per column
        null_counts = {
            col: df.filter(F.col(col).isNull()).count()
            for col in actual_cols
        }

        has_nulls = any(count > 0 for count in null_counts.values())
        null_details_json = json.dumps(null_counts)

        # Stable schema
        audit_schema = StructType([
            StructField("batchid", IntegerType(), True),
            StructField("table_name", StringType(), True),
            StructField("check_columns", StringType(), True),
            StructField("null_counts_by_column_json", StringType(), True),
            StructField("total_rows", LongType(), True),
            StructField("check_timestamp", TimestampType(), True),
            StructField("status", StringType(), True)
        ])

        # Create table only if it doesn't exist
        if not spark.catalog.tableExists("log.audit_dq_source_nulls"):
            spark.sql("""
                CREATE TABLE log.audit_dq_source_nulls (
                    batchid INT,
                    table_name STRING,
                    check_columns STRING,
                    null_counts_by_column_json STRING,
                    total_rows LONG,
                    check_timestamp TIMESTAMP,
                    status STRING
                )
                USING delta
            """)

        # -------------------------
        # NULL FAILURE HANDLING
        # -------------------------
        if has_nulls:
            summary = "; ".join(
                f"{col}: {count} NULLs"
                for col, count in null_counts.items()
                if count > 0
            )

            log_df = spark.createDataFrame([
                (
                    batchid,
                    source_table,
                    ",".join(actual_cols),
                    null_details_json,
                    total_rows,
                    datetime.now(),
                    "FAILED"
                )
            ], schema=audit_schema)

            log_df.write.format("delta").mode("append").saveAsTable("log.audit_dq_source_nulls")

            # Show sample NULL rows
            null_filter = None
            for col in actual_cols:
                cond = F.col(col).isNull()
                null_filter = cond if null_filter is None else (null_filter | cond)

            sample_nulls = df.filter(null_filter).limit(50)
            display(sample_nulls)

            msg = f"[DQ_NON_NULLS] FAILED: Found NULL values in {source_table}. {summary}"
            logger.error(msg)
            raise RuntimeError(msg)  # Raise exception to fail notebook

        else:
            logger.info(
                f"[DQ_NON_NULLS] PASSED: All {len(actual_cols)} columns are NOT NULL "
                f"in {source_table} ({total_rows:,} rows checked)"
            )

        
    except RuntimeError as runtime_err:
        # Log the error and exit notebook on validation failure
        logger.error(f"[DQ_NON_NULLS] Validation failure: {runtime_err}")
        # stop_notebook(f"[DQ_NON_NULLS] {runtime_err}")
        raise  # Re-raise to ensure notebook fails
    except Exception as e:
        msg = f"[DQ_NON_NULLS] Error checking non-null values in {source_table}: {e}"
        logger.error(msg)
        # stop_notebook(msg)
        raise RuntimeError(msg)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## _check_source_duplicates new

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def _check_source_duplicates(source_table: str, columns: list):
    try:
        if not spark.catalog.tableExists(source_table):
            msg = f"[DQ_DUPLICATES] Table {source_table} does not exist"
            logger.error(msg)
            # stop_notebook(msg)
            raise RuntimeError(msg)
        
        df = spark.table(source_table)

        batchid_rows = (
            df.select("ins_batchid")
            .distinct()
            .collect()
        )
        if not batchid_rows:
            logger.warning(f"[DQ_DUPLICATES] Table {source_table} is empty — skipping duplicate check")
            return

        batchid = int(batchid_rows[0][0])

        print(f"Batch ID: {batchid}")

        # Validate columns exist
        table_cols = {c.lower(): c for c in df.columns}
        cols_lower = [c.lower() for c in columns]
        missing_cols = [c for c in cols_lower if c not in table_cols]

        if missing_cols:
            msg = f"[DQ_DUPLICATES] Columns not found in {source_table}: {missing_cols}"
            logger.error(msg)
            # stop_notebook(msg)
            raise RuntimeError(msg)
        
        actual_cols = [table_cols[c] for c in cols_lower]
        logger.info(f"[DQ_DUPLICATES] Checking for duplicates in {source_table} on columns: {actual_cols}")

        total_rows = df.count()

        # ---------------------------------------------------------
        # DATE VALIDATION 1: Fromduedate / Duedate
        # ---------------------------------------------------------
        if "fromduedate" in cols_lower and "duedate" in cols_lower:
            from_col = table_cols["fromduedate"]
            to_col = table_cols["duedate"]

            bad_rows = df.filter(F.col(to_col) < F.col(from_col))
            bad_count = bad_rows.count()

            if bad_count > 0:
                display(bad_rows.limit(50))
                msg = (
                    f"[DQ_DATE_VALIDATION] FAILED: Found {bad_count} rows where "
                    f"{to_col} < {from_col} in {source_table}"
                )
                logger.info(msg)
                # stop_notebook(msg)
                raise RuntimeError(msg)
            else:
                logger.info(
                    f"[DQ_DATE_VALIDATION] PASSED: ALL {to_col} > {from_col}"
                )

        # ---------------------------------------------------------
        # DATE VALIDATION 2: Fromdate / Todate
        # ---------------------------------------------------------
        if "fromdate" in cols_lower and "todate" in cols_lower:
            from_col = table_cols["fromdate"]
            to_col = table_cols["todate"]

            bad_rows = df.filter(F.col(to_col) < F.col(from_col))
            bad_count = bad_rows.count()

            if bad_count > 0:
                display(bad_rows.limit(50))
                msg = (
                    f"[DQ_DATE_VALIDATION] FAILED: Found {bad_count} rows where "
                    f"{to_col} < {from_col} in {source_table}"
                )
                logger.info(msg)
                # stop_notebook(msg)
                raise RuntimeError(msg)
            else:
                logger.info(
                    f"[DQ_DATE_VALIDATION] PASSED: ALL {to_col} > {from_col}"
                )

        # ---------------------------------------------------------
        # DUPLICATE CHECK
        # ---------------------------------------------------------
        dup_groups = (
            df.groupBy(*actual_cols)
              .count()
              .filter(F.col("count") > 1)
        )

        duplicate_count = dup_groups.count()

        # Stable audit schema
        audit_schema = StructType([
            StructField("batchid", IntegerType(), True),
            StructField("table_name", StringType(), True),
            StructField("check_columns", StringType(), True),
            StructField("duplicate_combinations_found", IntegerType(), True),
            StructField("duplicate_details_json", StringType(), True),
            StructField("total_rows", LongType(), True),
            StructField("check_timestamp", TimestampType(), True),
            StructField("status", StringType(), True)
        ])

        # Create table only if it doesn't exist
        if not spark.catalog.tableExists("log.audit_dq_duplicates"):
            spark.sql("""
                CREATE TABLE log.audit_dq_duplicates (
                    batchid INT,
                    table_name STRING,
                    check_columns STRING,
                    duplicate_combinations_found INT,
                    duplicate_details_json STRING,
                    total_rows LONG,
                    check_timestamp TIMESTAMP,
                    status STRING
                )
                USING delta
            """)

        if duplicate_count > 0:

            # Collect sample duplicates (NULL-safe)
            sample_duplicates = (
                dup_groups
                .withColumnRenamed("count", "occurrences")
                .limit(1000)
                .collect()
            )

            duplicate_data = json.dumps([
                {
                    col: (None if row[col] is None else str(row[col]))
                    for col in actual_cols
                } | {"occurrences": row["occurrences"]}
                for row in sample_duplicates
            ])

            # Log failure
            log_df = spark.createDataFrame([
                (
                    batchid,
                    source_table,
                    ",".join(actual_cols),
                    duplicate_count,
                    duplicate_data,
                    total_rows,
                    datetime.now(),
                    "FAILED"
                )
            ], schema=audit_schema)

            log_df.write.format("delta").mode("append").saveAsTable("log.audit_dq_duplicates")

            # Display sample duplicates
            display(
                dup_groups
                .withColumnRenamed("count", "occurrences")
                .orderBy(F.col("occurrences").desc())
                .limit(50)
            )
            
            # ---------------------------------------------------------
            # GENERATE SELECT STATEMENTS FOR EACH DUPLICATE COMBINATION
            # ---------------------------------------------------------
            print("\n" + "="*100)
            print(f"🔍 DEBUG QUERIES FOR DUPLICATES IN {source_table}")
            print("="*100)
            
            # Get all duplicate combinations
            duplicate_combinations = dup_groups.select(*actual_cols).collect()
            
            for i, dup_row in enumerate(duplicate_combinations[:2]):  # Limit to first 10 combinations
                where_conditions = []
                for j, col in enumerate(actual_cols):
                    value = dup_row[j]
                    if value is None:
                        where_conditions.append(f"{col} IS NULL")
                    elif isinstance(value, str):
                        # Escape single quotes in strings
                        escaped_value = value.replace("'", "''")
                        where_conditions.append(f"{col} = '{escaped_value}'")
                    else:
                        where_conditions.append(f"{col} = {value}")
                
                where_clause = " AND ".join(where_conditions)
                select_sql = f"SELECT * FROM {source_table} WHERE {where_clause};"
                
                print(f"\n📋 Duplicate Set #{i+1}:")
                # print(f"   Conditions: {where_clause}")
                print(f"   SQL: {select_sql}")
                print("-"*80)
            
            # if duplicate_count > 2:
            #     print(f"\n⚠️  Showing first 2 of {duplicate_count} duplicate combinations")
            
            # print("="*100 + "\n")

            msg = f"[DQ_DUPLICATES] FAILED: Found {duplicate_count} duplicate combinations in {source_table}"
            logger.error(msg)
            raise RuntimeError(msg)  # Raise exception to fail notebook

        else:
            logger.info(
                f"[DQ_DUPLICATES] PASSED: No duplicates found in {source_table} "
                f"({total_rows:,} rows checked)"
            )

    except RuntimeError as runtime_err:
        # Log the error and exit notebook on validation failure
        logger.error(f"[DQ_DUPLICATES] Validation failure: {runtime_err}")
        # stop_notebook(f"[DQ_DUPLICATES] {runtime_err}")
        raise  # Re-raise to ensure notebook fails
    except Exception as e:
        msg = f"[DQ_DUPLICATES] Error checking duplicates in {source_table}: {e}"
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
print("[CONFIG] loaded nb_config_dq")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
