# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "",
# META       "default_lakehouse_workspace_id": ""
# META     }
# META   }
# META }

# CELL ********************

# MAGIC %%configure
# MAGIC {
# MAGIC   "defaultLakehouse": {
# MAGIC     "name": "lkh_001"
# MAGIC   }
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql.functions import col
from datetime import datetime
import logging

spark = SparkSession.builder.getOrCreate()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("silver_failed_batch_cleanup")

SILVER_SCHEMA = "silver"
LOG_SCHEMA = "log"
BATCH_CONTROL_TABLE = f"{LOG_SCHEMA}.audit_batch_control"

# ---- MANUAL OVERRIDE ----
# Specify batch IDs to delete manually. Leave empty [] to auto-detect all FAILED batches.
# Example: manual_batch_ids = [1, 2]
manual_batch_ids = []

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": true,
# META   "editable": false
# META }

# CELL ********************

print(f"\n{'='*100}")
print(f"SILVER LAYER - FAILED BATCH CLEANUP")
print(f"{'='*100}\n")

# Check if audit_batch_control table exists
if not spark.catalog.tableExists(BATCH_CONTROL_TABLE):
    msg = f"[FAILED_BATCH_CLEANUP] Table {BATCH_CONTROL_TABLE} does not exist"
    logger.error(msg)
    raise RuntimeError(msg)
else:
    print(f"✓ Found {BATCH_CONTROL_TABLE}")

if manual_batch_ids:
    # ---- MANUAL MODE: use specified batch IDs ----
    print(f"\n🔧 MANUAL MODE: Using specified batch IDs: {manual_batch_ids}")
    failed_batchids = manual_batch_ids

    # Show the status of the manually selected batches
    batch_id_list = ','.join(map(str, manual_batch_ids))
    df_failed_batches = spark.sql(f"""
        SELECT DISTINCT batchid, batch_status, created_at
        FROM {BATCH_CONTROL_TABLE}
        WHERE batchid IN ({batch_id_list})
        ORDER BY created_at DESC
    """)
    display(df_failed_batches)
else:
    # ---- AUTO MODE: find all FAILED batches ----
    df_failed_batches = spark.sql(f"""
        SELECT DISTINCT batchid, batch_status, created_at
        FROM {BATCH_CONTROL_TABLE}
        WHERE batch_status = 'FAILED'
        ORDER BY created_at DESC
    """)

    failed_batch_count = df_failed_batches.count()
    failed_batchids = []

    if failed_batch_count == 0:
        print(f"\n✓ No failed batches found. No cleanup needed.")
    else:
        print(f"\n⚠️  Found {failed_batch_count} FAILED batches:")
        display(df_failed_batches)
        failed_batchids = [row.batchid for row in df_failed_batches.select("batchid").collect()]

print(f"\nBatchIDs to clean: {failed_batchids}")


if not failed_batchids:
    print("No failed batchids - skipping cleanup")
else:
    # Get all tables in silver schema
    tables = spark.catalog.listTables(SILVER_SCHEMA)
    silver_tables = [t for t in tables if t.tableType and t.tableType.lower() != "view"]
    print(f"Found {len(silver_tables)} tables in schema '{SILVER_SCHEMA}'")
    print(f"{'-'*100}\n")



# Loop through each silver table and delete rows with failed batchids
cleanup_results = []
total_rows_deleted = 0

if not failed_batchids:
    print("No failed batchids - skipping cleanup")

for table_obj in (silver_tables if failed_batchids else []):
    table_name = table_obj.name
    full_table_path = f"{SILVER_SCHEMA}.{table_name}"
    
    try:
        # Check if table has ins_batchid column
        df_table = spark.table(full_table_path)
        columns = [c.lower() for c in df_table.columns]
        
        if 'ins_batchid' not in columns:
            status = "SKIPPED"
            reason = "no ins_batchid column"
            cleanup_results.append({
                'table': full_table_path,
                'status': status,
                'reason': reason,
                'rows_deleted': 0
            })
            print(f"⊘ {full_table_path:50s} | SKIPPED | {reason}")
            continue
        
        # Count rows before deletion
        df_before = spark.table(full_table_path)
        count_before = df_before.count()
        
        # Delete rows where ins_batchid is in failed_batchids list
        if failed_batchids:
            spark.sql(f"""
                DELETE FROM {full_table_path}
                WHERE ins_batchid IN ({','.join(map(str, failed_batchids))})
            """)
        
        # Count rows after deletion
        df_after = spark.table(full_table_path)
        count_after = df_after.count()
        rows_deleted = count_before - count_after
        total_rows_deleted += rows_deleted
        
        if rows_deleted > 0:
            status = "CLEANED"
            reason = f"deleted {rows_deleted} rows"
        else:
            status = "OK"
            reason = "no failed data found"
        
        cleanup_results.append({
            'table': full_table_path,
            'status': status,
            'reason': reason,
            'rows_deleted': rows_deleted
        })
        
        print(f"✓ {full_table_path:50s} | {status:10s} | {reason}")
        
    except Exception as e:
        status = "ERROR"
        reason = str(e)
        cleanup_results.append({
            'table': full_table_path,
            'status': status,
            'reason': reason,
            'rows_deleted': 0
        })
        logger.error(f"[FAILED_BATCH_CLEANUP] Error cleaning {full_table_path}: {e}")
        print(f"✗ {full_table_path:50s} | ERROR    | {reason}")



# Display cleanup summary
print(f"\n{'='*100}")
print(f"CLEANUP SUMMARY")
print(f"{'='*100}\n")

# Create results dataframe
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

schema = StructType([
    StructField("table", StringType(), True),
    StructField("status", StringType(), True),
    StructField("reason", StringType(), True),
    StructField("rows_deleted", IntegerType(), True)
])

df_results = spark.createDataFrame(cleanup_results, schema=schema)
display(df_results)

print(f"\n{'-'*100}")
print(f"Total rows deleted from silver schema: {total_rows_deleted:,}")
print(f"Total tables processed: {len(cleanup_results)}")
print(f"Total tables with failures: {len([r for r in cleanup_results if r['status'] == 'CLEANED'])}")
print(f"\nCleanup completed at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(f"{'='*100}\n")



# Log cleanup summary to audit table
try:
    deleted_batch_ids_str = ','.join(map(str, failed_batchids)) if failed_batchids else ''

    cleanup_summary_query = f"""
    INSERT INTO {LOG_SCHEMA}.audit_batch_cleanup
    SELECT 
        current_timestamp() as cleanup_timestamp,
        '{deleted_batch_ids_str}' as deleted_batch_ids,
        '{total_rows_deleted}' as total_rows_deleted,
        '{len([r for r in cleanup_results if r["status"] == "CLEANED"])}' as tables_cleaned,
        CAST('{len(cleanup_results)}' as INT) as total_tables_processed
    """
    
    # Create audit table if it doesn't exist
    if not spark.catalog.tableExists(f"{LOG_SCHEMA}.audit_batch_cleanup"):
        spark.sql(f"""
            CREATE TABLE {LOG_SCHEMA}.audit_batch_cleanup (
                cleanup_timestamp TIMESTAMP,
                deleted_batch_ids STRING,
                total_rows_deleted STRING,
                tables_cleaned STRING,
                total_tables_processed INT
            )
            USING delta
        """)
    
    spark.sql(cleanup_summary_query)
    print("✓ Cleanup summary logged to audit table")
    
except Exception as e:
    logger.warning(f"[FAILED_BATCH_CLEANUP] Could not log to audit table: {e}")
    print(f"⚠️  Warning: Could not log cleanup summary: {e}")



# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": true,
# META   "editable": false
# META }
