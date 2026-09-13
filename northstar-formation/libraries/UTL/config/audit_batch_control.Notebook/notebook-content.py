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
# MAGIC     "name": "lkh_customer0_schema_enabled"
# MAGIC   }
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.sql("CREATE SCHEMA IF NOT EXISTS log")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

spark.sql("""
    CREATE TABLE IF NOT EXISTS log.audit_batch_control (
        batchid INT,
        pl_start STRING,
        pl_end STRING,
        duration_hms STRING,
        source_system STRING,
        ingestion_version STRING,
        batch_status STRING,
        error_message STRING,
        executed_by STRING,
        created_at STRING
    )
    USING DELTA
""")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# pl_start = "15:40:00"
# source_system = "Orchestrator"
# executed_by = "Orchestrator"

print(f"Params:")
print(f"pl_start: {pl_start}")
print(f"source_system: {source_system}")
print(f"Executed_by: {executed_by}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

result = spark.sql("""
    SELECT COALESCE(MAX(batchid), 0) + 1 as next_batchid
    FROM log.audit_batch_control
""").collect()

batchid = result[0]['next_batchid']
print(f"Next batchid: {batchid}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql.functions import current_timestamp
from datetime import datetime
try:
    # Create DataFrame with the new record
    batch_record = spark.createDataFrame([(
        batchid,                    # batchid
        pl_start,                    # pl_start (from parameter)
        None,                        # pl_end
        None,                        # duration_hms
        source_system,               # source_system (from parameter)
        None,                        # ingestion_version
        "STARTED",                   # batch_status
        None,                        # error_message
        executed_by                  # executed_by
    )], """
        batchid INT,
        pl_start STRING,
        pl_end STRING,
        duration_hms STRING,
        source_system STRING,
        ingestion_version STRING,
        batch_status STRING,
        error_message STRING,
        executed_by STRING
    """)
    
    # Add timestamps
    batch_record = batch_record.withColumn("created_at", current_timestamp().cast("string"))
    
    # Insert the record
    batch_record.write.format("delta").mode("append").saveAsTable("log.audit_batch_control")
    
    print(f"[BATCH_CONTROL] Inserted batch record: batchid={batchid}, status=STARTED")
    
except Exception as e:
    print(f"[BATCH_CONTROL] Error inserting batch record: {e}")
    raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# MAGIC %%sql
# MAGIC select *
# MAGIC from log.audit_batch_control

# METADATA ********************

# META {
# META   "language": "sparksql",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

notebook_exit_value = batchid

print(f"notebook_exit_value = notebook_exit_value")
mssparkutils.notebook.exit(notebook_exit_value)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }
