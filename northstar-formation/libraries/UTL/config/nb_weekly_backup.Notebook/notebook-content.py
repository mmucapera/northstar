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

# MARKDOWN ********************

# ## Imports

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, when, sha2, concat_ws, lit, substring, floor, abs
import re
from pyspark.sql.functions import (
    col, lit, sha2, concat_ws, substring, abs, conv, array, element_at, current_date, date_format
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Variables


# CELL ********************

source_schemas = ["silver"]

today_str = (
    spark.range(1)
         .select(date_format(current_date(), "yyyyMMdd").alias("d"))
         .first()["d"]
)
target_schema = "silver_autogen_backup_" + today_str

print(f"Source Schema: {source_schemas}")
print(f"Target Schema: {target_schema}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Execution

# CELL ********************

results = []

for schema in source_schemas:
    print(f"Scanning schema: {schema}")
    tables = spark.catalog.listTables(schema)

    for t in tables:
        if t.tableType and t.tableType.lower() == "view":
            continue

        src_table = f"{schema}.{t.name}"
        print(f"  - Processing table: {src_table}")

        try:
            df = spark.table(src_table)
        except Exception as e:
            print(f"    ! Failed to read {src_table}: {e}")
            continue

        src_count = df.count()
        print(f"    • Source rows: {src_count}")

        out_count = df.count()
        print(f"    • Rows after: {out_count}")

        # Determine target schema
        target_db_raw = target_schema
        target_db = target_db_raw
        target_table = t.name
        target_full = f"{target_db}.{target_table}"

        try:
            spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{target_db}`")
        except Exception as e:
            print(f"    ! Failed to create schema {target_db}: {e}")

        # Write output table
        try:
            df.write.mode("overwrite").saveAsTable(target_full)
            print(f"    ✓ Backed up table table to {target_full} (rows: {out_count})")
            results.append((src_table, target_full, src_count, out_count))
        except Exception as e:
            print(f"    ! Failed to back up table write {target_full}: {e}")
            results.append((src_table, target_full, src_count, None))

# Summary DataFrame
summary_df = spark.createDataFrame(results, ["source_table", "target_table", "source_rows", "target_rows"])
display(summary_df)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Cleanup old backups (older than 4 weeks)

# CELL ********************

from datetime import datetime, timedelta

cutoff_date = (datetime.now() - timedelta(weeks=4)).strftime("%Y%m%d")
print(f"Cutoff date: {cutoff_date} — dropping backup schemas created before this date")

all_schemas = [row.namespace for row in spark.sql("SHOW SCHEMAS").collect()]

backup_prefix = "silver_autogen_backup_"
dropped = []

for schema_name in sorted(all_schemas):
    if not schema_name.startswith(backup_prefix):
        continue

    date_suffix = schema_name[len(backup_prefix):]

    # Validate it looks like YYYYMMDD
    if len(date_suffix) != 8 or not date_suffix.isdigit():
        print(f"  Skipping {schema_name} — unexpected date format")
        continue

    if date_suffix < cutoff_date:
        print(f"  Dropping {schema_name} (backup date {date_suffix} < cutoff {cutoff_date})")
        try:
            spark.sql(f"DROP SCHEMA IF EXISTS `{schema_name}` CASCADE")
            dropped.append(schema_name)
            print(f"    ✓ Dropped")
        except Exception as e:
            print(f"    ! Failed to drop {schema_name}: {e}")
    else:
        print(f"  Keeping {schema_name} (backup date {date_suffix} >= cutoff {cutoff_date})")

print(f"\nDropped {len(dropped)} old backup schema(s): {dropped}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
