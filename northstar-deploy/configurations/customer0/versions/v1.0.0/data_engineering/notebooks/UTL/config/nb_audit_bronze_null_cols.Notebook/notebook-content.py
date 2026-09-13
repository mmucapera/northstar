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
from pyspark.sql.functions import col, count, when
import re
from collections import defaultdict


BRONZE_SCHEMA = "bronze"
NULL_COLUMN_THRESHOLD = 80  # Percentage: flag if > 20% of columns are entirely null
REPORT_DETAILS = True

print(f"\n{'='*80}")
print(f"BRONZE LAYER NULL COLUMN VALIDATOR")
print(f"Threshold: {NULL_COLUMN_THRESHOLD}% of columns entirely null")
print(f"{'='*80}\n")

# Get all tables in bronze schema
tables = spark.catalog.listTables(BRONZE_SCHEMA)
table_list = [
    t for t in tables
    if t.tableType and t.tableType.lower() != "view"
    and domain.lower() in t.name.lower()
]

print(f"Found {len(table_list)} tables in schema '{BRONZE_SCHEMA}'")
print(f"{'='*80}\n")

# Track validation results
validation_results = {
    "valid": [],
    "flagged": [],
    "errors": []
}

null_column_details = defaultdict(dict)



for table in table_list:
    table_name = table.name
    full_table_name = f"{BRONZE_SCHEMA}.{table_name}"
    
    print(f"\n→ Processing: {full_table_name}")
    
    try:
        # Read the table
        df = spark.table(full_table_name)
        
        # Get row count
        row_count = df.count()
        if row_count == 0:
            print(f"  ⚠ WARNING: Table is empty (0 rows)")
            validation_results["valid"].append(table_name)
            continue
        
        # Get all columns
        columns = df.columns
        total_columns = len(columns)
        
        print(f"  Columns: {total_columns} | Rows: {row_count:,}")
        
        # Check each column for null values
        null_columns = []
        null_column_names = []
        
        for column_name in columns:
            # Count non-null values in column
            non_null_count = df.filter(col(column_name).isNotNull()).count()
            
            # If non_null_count == 0, column is entirely null
            if non_null_count == 0:
                null_columns.append(column_name)
                null_column_names.append(column_name)
        
        # Calculate percentage of null columns
        null_column_percentage = (len(null_columns) / total_columns * 100) if total_columns > 0 else 0
        
        print(f"  Entirely NULL columns: {len(null_columns)}/{total_columns} ({null_column_percentage:.1f}%)")
        
        # Report results
        if null_column_percentage > NULL_COLUMN_THRESHOLD:
            validation_results["flagged"].append(table_name)
            null_column_details[table_name] = {
                "total_columns": total_columns,
                "null_columns": len(null_columns),
                "null_percentage": null_column_percentage,
                "null_column_names": null_column_names,
                "row_count": row_count
            }
            print(f"  🚨 FLAGGED: {null_column_percentage:.1f}% null columns exceeds {NULL_COLUMN_THRESHOLD}% threshold")
            
            if REPORT_DETAILS and null_columns:
                print(f"    Entirely NULL columns:")
                for col_name in null_columns[:10]:
                    print(f"      - {col_name}")
                if len(null_columns) > 10:
                    print(f"      ... and {len(null_columns) - 10} more")
        else:
            validation_results["valid"].append(table_name)
            print(f"  ✓ VALID: {null_column_percentage:.1f}% null columns within threshold")
        
    except Exception as e:
        validation_results["errors"].append((table_name, str(e)))
        print(f"  ❌ ERROR: {str(e)}")


print(f"\n{'='*80}")
print(f"VALIDATION SUMMARY")
print(f"{'='*80}\n")

print(f"✓ Valid Tables:        {len(validation_results['valid'])}")
print(f"🚨 Flagged Tables:     {len(validation_results['flagged'])}")
print(f"❌ Errors:             {len(validation_results['errors'])}")

if validation_results["valid"]:
    print(f"\n✓ VALID TABLES (≤ {NULL_COLUMN_THRESHOLD}% null columns):")
    for table in sorted(validation_results["valid"]):
        print(f"  - {table}")

if validation_results["flagged"]:
    print(f"\n🚨 FLAGGED TABLES (> {NULL_COLUMN_THRESHOLD}% null columns):")
    for table in sorted(validation_results["flagged"]):
        details = null_column_details[table]
        print(f"\n  TABLE: {table}")
        print(f"    Null Columns: {details['null_columns']}/{details['total_columns']} ({details['null_percentage']:.1f}%)")
        print(f"    Rows: {details['row_count']:,}")
        
        if REPORT_DETAILS and details["null_column_names"]:
            print(f"    Entirely NULL columns:")
            for col_name in details["null_column_names"][:15]:
                print(f"      - {col_name}")
            if len(details["null_column_names"]) > 15:
                print(f"      ... and {len(details['null_column_names']) - 15} more")

if validation_results["errors"]:
    print(f"\n❌ TABLES WITH ERRORS:")
    for table, error in validation_results["errors"]:
        print(f"  - {table}: {error}")

if validation_results["flagged"]:
    print(f"\n{'='*80}")
    print(f"🚨 RECOMMENDED ACTIONS FOR FLAGGED TABLES:")
    print(f"{'='*80}\n")
    
    for table in sorted(validation_results["flagged"]):
        details = null_column_details[table]
        print(f"\n{table}:")
        print(f"  1. Investigate why {details['null_columns']} column(s) are entirely null")
        print(f"  2. Check source data - may indicate schema mismatch or incomplete load")
        print(f"  3. Verify column mappings in read_parquet_bulk or data pipeline")
        print(f"  4. Consider dropping unused columns or fixing data source")
        print(f"  5. Re-run validation after correcting source data")

print(f"\n{'='*80}")
if not validation_results["flagged"] and not validation_results["errors"]:
    print(f"✓ ALL BRONZE TABLES PASSED NULL COLUMN VALIDATION - Safe to proceed with silver layer")
else:
    print(f"🚨 REVIEW FLAGGED TABLES BEFORE PROCEEDING WITH SILVER PIPELINES")
print(f"{'='*80}\n")


# Fail if any tables flagged
if validation_results["flagged"] or validation_results["errors"]:
    error_details = []
    
    if validation_results["flagged"]:
        error_details.append(f"{len(validation_results['flagged'])} table(s) with > {NULL_COLUMN_THRESHOLD}% null columns: {', '.join(validation_results['flagged'])}")
    
    if validation_results["errors"]:
        error_details.append(f"{len(validation_results['errors'])} table(s) with errors: {', '.join([t for t, _ in validation_results['errors']])}")
    
    error_message = f"❌ VALIDATION FAILED - {'; '.join(error_details)}"
    print(f"\n{error_message}")
    raise Exception(error_message)



# Success: All validations passed
print(f"\n{'='*80}")
print(f"✓ SUCCESS: ALL BRONZE TABLES NULL COLUMN VALIDATION PASSED")
print(f"{'='*80}")
print(f"Valid Tables: {len(validation_results['valid'])}")
print(f"Null Column Threshold: {NULL_COLUMN_THRESHOLD}%")
print(f"Safe to proceed with silver layer pipelines")
print(f"{'='*80}\n")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
