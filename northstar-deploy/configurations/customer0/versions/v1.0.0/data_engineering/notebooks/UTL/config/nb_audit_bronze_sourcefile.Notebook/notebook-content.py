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

# MARKDOWN ********************

# # Bronze Layer Source File Validator
# > Validates that source files in bronze tables match their respective table names.
# > Detects data loading issues caused by read_parquet_bulk misrouting files.
# > Run this before starting silver layer pipelines.

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql.functions import col, countDistinct, collect_list, when, regexp_extract
import re
from collections import defaultdict

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 1. Configuration
# Define schemas and logging setup

# CELL ********************

BRONZE_SCHEMA = "bronze"
REPORT_MISMATCHES = True
REPORT_WARNINGS = True

# Extract source file pattern from filename
# e.g., "FCT_ProductUnitConversion" from "20260507_192226_FCT_ProductUnitConversion_InitializationEMEADMRDEU2_PreDMR_2026M05.parquet"
# e.g., "unit" from "Unit_SP_Full_One2_20260513_033240.parquet" (new format)
def extract_source_pattern(filename, domain=None):
    """Extract the core table pattern from source filename"""
    if not filename or not isinstance(filename, str):
        return None
    
    # Remove extension
    name = filename.replace(".parquet", "").replace(".csv", "").replace(".txt", "")
    
    # For new format with _sp_full (OPR domain): extract entity before _sp
    # e.g., Unit_SP_Full_One2_* -> unit
    if domain and domain.lower() in ['opr', 'sp'] and '_sp_full' in name.lower():
        # Extract text before _SP_Full
        match = re.search(r'^([A-Za-z0-9]+)_sp_full', name.lower(), re.IGNORECASE)
        if match:
            return match.group(1).lower()
    
    # Old format: date_time_DOMAIN_ENTITY_...
    # Pattern: date_time_TABLENAME_...
    # Look for uppercase sequences that represent table names
    match = re.search(r'([A-Z]{1,3}_[A-Z][a-zA-Z0-9]+)', name)
    if match:
        return match.group(1).lower()
    
    return None

def extract_entity_from_table(table_name):
    """Extract entity name from table name (without domain prefix)
    e.g., 'fct_product' -> domain='fct', entity='product'
    """
    try:
        parts = table_name.lower().split('_', 1)
        if len(parts) == 2:
            domain, entity = parts
            return domain, entity
    except:
        pass
    return None, None

# Normalize table name to pattern
def normalize_table_name(table_name):
    """Normalize table name to match source file pattern"""
    # e.g., "fct_product" stays as "fct_product"
    return table_name.lower()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 2. Scan Bronze Tables
# Iterate through all tables and check for source file mismatches

# CELL ********************

print(f"\n{'='*80}")
print(f"BRONZE LAYER SOURCE FILE VALIDATOR")
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
    "mismatch": [],
    "no_sourcefile_col": [],
    "empty": [],
    "errors": []
}

mismatch_details = defaultdict(dict)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

for table in table_list:
    table_name = table.name
    full_table_name = f"{BRONZE_SCHEMA}.{table_name}"
    normalized_name = normalize_table_name(table_name)
    
    # Extract domain and entity from table name
    # e.g., 'fct_product' -> domain='fct', entity='product'
    domain, entity = extract_entity_from_table(table_name)
    
    print(f"\n→ Processing: {full_table_name} (entity='{entity}')")
    
    try:
        # Read the table
        df = spark.table(full_table_name)
        
        # Check if sourcefile column exists
        if "sourcefile" not in df.columns:
            print(f"  ⚠ WARNING: No 'sourcefile' column found")
            validation_results["no_sourcefile_col"].append(table_name)
            continue
        
        # Get unique source files
        source_files = df.select("sourcefile").distinct().collect()
        source_file_list = [row[0] for row in source_files if row[0] is not None]
        
        if not source_file_list:
            print(f"  ℹ INFO: Table is empty or sourcefile column has no values — skipping")
            validation_results["empty"].append(table_name)
            continue
        
        print(f"  Found {len(source_file_list)} unique source files")
        
        # Extract patterns from each source file
        mismatched_files = []
        matched_files = []
        
        for source_file in source_file_list:
            source_pattern = extract_source_pattern(source_file, domain=domain)
            file_lower = source_file.lower()
            
            # FOUR-LAYER VALIDATION
            # 1. Domain + entity boundary check (e.g., fct_product or opr_unit)
            has_domain_entity = normalized_name in source_pattern if source_pattern else False
            
            # For OPR/SP new format files (_sp_full), check if entity matches
            # e.g., opr_unit table with Unit_SP_Full_* file -> unit in pattern
            if not has_domain_entity and domain and domain.lower() in ['opr', 'sp'] and '_sp_full' in file_lower:
                has_domain_entity = entity.lower() in source_pattern if source_pattern else False
            
            # 2. Entity name must be present (without domain)
            # e.g., 'product' must be in filename to match 'fct_product' table
            has_entity = entity.lower() in file_lower if entity else False
            
            # 3. STRICT: entity must NOT be followed by alphanumeric (prevents substring matching)
            # e.g., 'product_' OK, 'productunitconversion' NOT OK
            # For OPR/_sp_full format, entity is followed by _sp
            entity_boundary_ok = True
            if entity:
                # Check for proper boundary (underscore or non-alphanumeric after entity)
                entity_with_boundary = re.search(rf"{entity}(?:_|[^a-z0-9])", file_lower, re.IGNORECASE)
                entity_boundary_ok = bool(entity_with_boundary)
            
            # 4. DOMAIN BOUNDARY CHECK: Reject files from different domains
            # Files with '_sp_full' are for Supply Planning (OPR domain) - VALID for OPR
            # Files with '_fct_' are for Forecast (FCT domain)
            # If this is a FCT table (domain='fct'), reject SP files
            # If this is an OPR table (domain='opr'), SP files are VALID
            domain_boundary_ok = True
            domain_mismatch_reason = None
            if domain and domain.lower() == 'fct' and '_sp_full' in file_lower:
                domain_boundary_ok = False
                domain_mismatch_reason = f"file is from SP (Supply Planning/OPR) domain, not FCT domain"
            elif domain and domain.lower() == 'opr' and '_fct_' in file_lower:
                domain_boundary_ok = False
                domain_mismatch_reason = f"file is from FCT (Forecast) domain, not OPR domain"
            
            # All checks must pass
            if source_pattern and has_domain_entity and has_entity and entity_boundary_ok and domain_boundary_ok:
                matched_files.append(source_file)
                print(f"    ✓ {source_file}")
            else:
                mismatch_reason = []
                if not has_domain_entity:
                    mismatch_reason.append(f"domain_entity mismatch (pattern: {source_pattern})")
                if not has_entity:
                    mismatch_reason.append(f"entity '{entity}' not found in filename")
                if not entity_boundary_ok:
                    mismatch_reason.append(f"entity '{entity}' not properly bounded (substring match detected)")
                if not domain_boundary_ok:
                    mismatch_reason.append(domain_mismatch_reason)
                
                mismatched_files.append((source_file, source_pattern, " | ".join(mismatch_reason)))
                print(f"    ✗ {source_file} ({' | '.join(mismatch_reason)})")
        
        # Report results
        if mismatched_files and REPORT_MISMATCHES:
            validation_results["mismatch"].append(table_name)
            mismatch_details[table_name] = {
                "matched": matched_files,
                "mismatched": mismatched_files,
                "total_files": len(source_file_list),
                "mismatch_count": len(mismatched_files),
                "entity": entity,
                "domain": domain
            }
            print(f"  🚨 MISMATCH DETECTED: {len(mismatched_files)} file(s) do not match table '{table_name}'")
        elif not mismatched_files:
            validation_results["valid"].append(table_name)
            print(f"  ✓ VALID: All source files match table name")
        
    except Exception as e:
        validation_results["errors"].append((table_name, str(e)))
        print(f"  ❌ ERROR: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 3. Validation Summary Report

# CELL ********************

print(f"\n{'='*80}")
print(f"VALIDATION SUMMARY")
print(f"{'='*80}\n")

print(f"✓ Valid Tables:             {len(validation_results['valid'])}")
print(f"🚨 Tables with Mismatches:  {len(validation_results['mismatch'])}")
print(f"⚠ No sourcefile Column:     {len(validation_results['no_sourcefile_col'])}")
print(f"ℹ Empty Tables (skipped):   {len(validation_results['empty'])}")
print(f"❌ Errors:                  {len(validation_results['errors'])}")

if validation_results["valid"]:
    print(f"\n✓ VALID TABLES:")
    for table in sorted(validation_results["valid"]):
        print(f"  - {table}")

if validation_results["mismatch"]:
    print(f"\n🚨 TABLES WITH SOURCE FILE MISMATCHES:")
    for table in sorted(validation_results["mismatch"]):
        details = mismatch_details[table]
        print(f"\n  TABLE: {table}")
        print(f"    Domain: {details.get('domain', 'N/A')} | Entity: {details.get('entity', 'N/A')}")
        print(f"    Total Files: {details['total_files']} | Mismatched: {details['mismatch_count']}")
        
        if details["mismatched"]:
            print(f"    Mismatched Files:")
            for src_file, pattern, reason in details["mismatched"]:
                print(f"      - {src_file}")
                print(f"        Reason: {reason}")

if validation_results["no_sourcefile_col"]:
    print(f"\n⚠ TABLES WITHOUT 'sourcefile' COLUMN:")
    for table in sorted(validation_results["no_sourcefile_col"]):
        print(f"  - {table}")

if validation_results["empty"]:
    print(f"\nℹ EMPTY TABLES (skipped, not an error):")
    for table in sorted(validation_results["empty"]):
        print(f"  - {table}")

if validation_results["errors"]:
    print(f"\n❌ TABLES WITH ERRORS:")
    for table, error in validation_results["errors"]:
        print(f"  - {table}: {error}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## 4. Recommended Actions
# Based on validation results, take corrective action

# CELL ********************

if validation_results["mismatch"]:
    print(f"\n{'='*80}")
    print(f"🚨 RECOMMENDED ACTIONS FOR MISMATCHED TABLES:")
    print(f"{'='*80}\n")
    
    for table in sorted(validation_results["mismatch"]):
        details = mismatch_details[table]
        entity = details.get('entity', 'unknown')
        print(f"\n{table} (entity='{entity}'):")
        print(f"  1. Verify source files contain '{entity}' in their name")
        print(f"  2. Check read_parquet_bulk search_param matches entity name")
        print(f"  3. Review {len(details['mismatched'])} mismatched file(s):")
        
        for src_file, pattern, reason in details["mismatched"][:5]:
            print(f"     - {src_file}")
            print(f"       Issue: {reason}")
        
        if len(details["mismatched"]) > 5:
            print(f"     ... and {len(details['mismatched']) - 5} more")
        
        print(f"  4. Truncate table and reload with corrected source configuration")

print(f"\n{'='*80}")
if not validation_results["mismatch"] and not validation_results["errors"]:
    print(f"✓ ALL BRONZE TABLES PASSED VALIDATION - Safe to proceed with silver layer")
else:
    print(f"🚨 REVIEW MISMATCHES BEFORE PROCEEDING WITH SILVER PIPELINES")
print(f"{'='*80}\n")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Display distinct source files per table (regardless of validation result)
sourcefile_records = []

for table in table_list:
    table_name = table.name
    full_table_name = f"{BRONZE_SCHEMA}.{table_name}"
    
    try:
        df = spark.table(full_table_name)
        
        if "sourcefile" not in df.columns:
            continue
        
        # Get distinct source files
        source_files = df.select("sourcefile").distinct().collect()
        source_file_list = [row[0] for row in source_files if row[0] is not None]
        
        # Create record for each source file
        for source_file in source_file_list:
            sourcefile_records.append({
                "table_name": table_name,
                "sourcefile": source_file
            })
    except Exception:
        pass

# Create and display dataframe
if sourcefile_records:
    from pyspark.sql.types import StructType, StructField, StringType
    
    schema = StructType([
        StructField("table_name", StringType(), True),
        StructField("sourcefile", StringType(), True)
    ])
    
    sourcefile_df = spark.createDataFrame(sourcefile_records, schema=schema)
    sourcefile_df.show(truncate=False, n=1000)
else:
    print("No source files found in any tables")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Fail if any issues detected (empty tables are NOT a failure)
if validation_results["mismatch"] or validation_results["errors"] or validation_results["no_sourcefile_col"]:
    error_details = []
    
    if validation_results["mismatch"]:
        error_details.append(f"{len(validation_results['mismatch'])} table(s) with source file mismatches: {', '.join(validation_results['mismatch'])}")
    
    if validation_results["errors"]:
        error_details.append(f"{len(validation_results['errors'])} table(s) with errors: {', '.join([t for t, _ in validation_results['errors']])}")
    
    if validation_results["no_sourcefile_col"]:
        error_details.append(f"{len(validation_results['no_sourcefile_col'])} table(s) without sourcefile column: {', '.join(validation_results['no_sourcefile_col'])}")
    
    error_message = f"❌ VALIDATION FAILED - {'; '.join(error_details)}"
    print(f"\n{error_message}")
    raise Exception(error_message)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Success: All validations passed
print(f"\n{'='*80}")
print(f"✓ SUCCESS: ALL BRONZE TABLES VALIDATION PASSED")
print(f"{'='*80}")
print(f"Valid Tables: {len(validation_results['valid'])}")
print(f"Safe to proceed with silver layer pipelines")
print(f"{'='*80}\n")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
