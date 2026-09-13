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
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

%run nb_utils_config

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

from datetime import datetime
from pyspark.sql.types import StructType, StructField, DateType, IntegerType, TimestampType, StringType
from pyspark.sql import functions as F
from notebookutils import mssparkutils
import logging
from delta.tables import DeltaTable


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("file_receipt_scanner")


def _resolve_extract_id(default=None):
    """Resolve extract id from common runtime variable names/params."""
    candidates = [
        "extract_id",
        "extractid",
        "ExtractId",
        "extraction_id",
        "ExtractionId",
    ]

    g = globals()
    for key in candidates:
        if key in g and g.get(key) not in (None, ""):
            try:
                return int(g.get(key))
            except Exception:
                pass

    try:
        # Fabric runtime context fallback
        ctx = mssparkutils.runtime.context
        for key in candidates:
            val = ctx.get(key) if hasattr(ctx, "get") else None
            if val not in (None, ""):
                try:
                    return int(val)
                except Exception:
                    pass
    except Exception:
        pass

    return default

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

spark.sql("CREATE SCHEMA IF NOT EXISTS log")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

def ensure_file_receipt_table():
    """Ensure the log.audit_package_receipt table exists"""
    if spark.catalog.tableExists("log.audit_package_receipt"):
        return
    
    spark.sql("""
        CREATE TABLE log.audit_package_receipt (
            batchid INT,
            ReceiptDate DATE,
            Domain STRING,
            FileCount INT,
            PackageCount INT,
            ReceivedAt TIMESTAMP
        )
        USING delta
    """)
    print("[FILE_RECEIPT] Created log.audit_package_receipt table")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

def discover_date_folders() -> list:
    """Discover all date folders in Files/archive/parquet/ (YYYY/MM/DD pattern)"""
    dates_found = []
    try:
        base = "Files/archive/parquet"
        extract_id_value = _resolve_extract_id()
        use_orchestrator = bool(globals().get("USE_ORCHESTRATOR", 0))

        if use_orchestrator:
            base = "Files/bronze"
        print(f"\n[FILE_RECEIPT] Discovering date folders in {base}")
        
        # Walk YYYY folders
        try:
            yyyy_items = mssparkutils.fs.ls(base)
        except Exception as e:
            print(f"[FILE_RECEIPT] Could not access {base}: {e}")
            return dates_found
        
        if use_orchestrator:
            # Structure: Files/bronze/<DOMAIN>/YYYY/MM/DD/<extract_id>/...
            for domain_item in yyyy_items:
                if not domain_item.isDir:
                    continue

                domain_root = f"{base}/{domain_item.name}"
                try:
                    yyyy_domain_items = mssparkutils.fs.ls(domain_root)
                except Exception:
                    continue

                for yyyy_item in yyyy_domain_items:
                    if not yyyy_item.isDir:
                        continue

                    yyyy = yyyy_item.name
                    if not yyyy.isdigit() or len(yyyy) != 4:
                        continue

                    yyyy_path = f"{domain_root}/{yyyy}"
                    try:
                        mm_items = mssparkutils.fs.ls(yyyy_path)
                    except Exception:
                        continue

                    for mm_item in mm_items:
                        if not mm_item.isDir:
                            continue

                        mm = mm_item.name
                        if not mm.isdigit() or len(mm) != 2:
                            continue

                        mm_path = f"{yyyy_path}/{mm}"
                        try:
                            dd_items = mssparkutils.fs.ls(mm_path)
                        except Exception:
                            continue

                        for dd_item in dd_items:
                            if not dd_item.isDir:
                                continue

                            dd = dd_item.name
                            if not dd.isdigit() or len(dd) != 2:
                                continue

                            date_path = f"{yyyy}/{mm}/{dd}"

                            # Strict extract filter: only include dates that have exact extract_id folder.
                            if extract_id_value is not None:
                                extract_path = f"{base}/{domain_item.name}/{date_path}/{int(extract_id_value)}"
                                try:
                                    mssparkutils.fs.ls(extract_path)
                                    dates_found.append(date_path)
                                except Exception:
                                    continue
                            else:
                                dates_found.append(date_path)
        else:
            for yyyy_item in yyyy_items:
                if not yyyy_item.isDir:
                    continue

                yyyy = yyyy_item.name
                if not yyyy.isdigit() or len(yyyy) != 4:
                    continue

                # Walk MM folders
                yyyy_path = f"{base}/{yyyy}"
                try:
                    mm_items = mssparkutils.fs.ls(yyyy_path)
                except:
                    continue

                for mm_item in mm_items:
                    if not mm_item.isDir:
                        continue

                    mm = mm_item.name
                    if not mm.isdigit() or len(mm) != 2:
                        continue

                    # Walk DD folders
                    mm_path = f"{yyyy_path}/{mm}"
                    try:
                        dd_items = mssparkutils.fs.ls(mm_path)
                    except:
                        continue

                    for dd_item in dd_items:
                        if not dd_item.isDir:
                            continue

                        dd = dd_item.name
                        if not dd.isdigit() or len(dd) != 2:
                            continue

                        date_path = f"{yyyy}/{mm}/{dd}"
                        dates_found.append(date_path)
        
        print(f"[FILE_RECEIPT] Found {len(dates_found)} date folders")
        for date_path in sorted(dates_found):
            # print(f"  - {date_path}")
            continue
        
        return sorted(set(dates_found))
    
    except Exception as e:
        print(f"[ERROR] Failed to discover date folders: {e}")
        return dates_found

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

def run_merge_with_retry(sql, max_retries=5):
    for attempt in range(max_retries):
        try:
            spark.sql(sql)
            return
        except Exception as e:
            if "ConcurrentAppendException" in str(e):
                print(f"Retrying MERGE (attempt {attempt+1})...")
                time.sleep(1)
            else:
                raise
    raise Exception("MERGE failed after retries")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************



def scan_file_receipts(date_part: str, domain: str = None, extract_id: int = None) -> dict:
    try:
        # Normalize date path
        date_part = date_part.strip("/").replace("-", "/")
        base = f"Files/archive/parquet/{date_part}"
        use_orchestrator = bool(globals().get("USE_ORCHESTRATOR", 0))

        if use_orchestrator:
            if extract_id is None:
                print("[FILE_RECEIPT] USE_ORCHESTRATOR=1 but extract_id is missing - skipping")
                return {
                    "date": datetime.strptime(date_part.replace("/", ""), "%Y%m%d").strftime("%Y-%m-%d"),
                    "domains": {},
                    "total_files": 0,
                    "total_packages": 0,
                }

            domain_upper = domain.upper() if domain else None
            if domain_upper:
                base = f"Files/bronze/{domain_upper}/{date_part}/{int(extract_id)}"
            else:
                # For all domains, scan each exact domain/date/extract path separately.
                base = "Files/bronze"
        
        print(f"\n[FILE_RECEIPT] Scanning directory: {base}")
        if domain:
            print(f"[FILE_RECEIPT] Filtering by domain: {domain.upper()}")
        
        # Initialize tracking
        domain_summary = {}  # domain -> {file_count, package_count}
        package_folders = {}  # package_name -> domain
        loose_timestamps = {}  # domain -> set of YYYYMMDD_HHMMSS timestamps (for new-format files)
        
        # Ensure table exists
        ensure_file_receipt_table()
        
        # Walk the directory structure
        def walk(path, depth=0):
            try:
                items = mssparkutils.fs.ls(path)
            except Exception as e:
                if depth == 0:  # Only warn at top level
                    print(f"[FILE_RECEIPT] Could not access {path}: {e}")
                return
            
            for item in items:
                full_path = f"{path}/{item.name}"
                
                if item.isDir:
                    # Check if this folder matches package pattern (YYYYMMDD_HHMMSS_DOMAIN_...)
                    folder_name = item.name
                    parts = folder_name.split("_")
                    
                    if len(parts) >= 3 and len(parts[0]) == 8 and len(parts[1]) == 6:
                        # This looks like a package folder
                        package_domain = parts[2].upper()
                        
                        # DOMAIN FILTER: Skip if domain filter is set and doesn't match
                        if domain and package_domain != domain.upper():
                            continue
                        
                        if package_domain not in domain_summary:
                            domain_summary[package_domain] = {"file_count": 0, "package_count": 0}
                        
                        domain_summary[package_domain]["package_count"] += 1
                        package_folders[folder_name] = package_domain
                        
                        # Count parquet files in this package
                        try:
                            pkg_items = mssparkutils.fs.ls(full_path)
                            for pkg_item in pkg_items:
                                if pkg_item.name.lower().endswith(".parquet"):
                                    domain_summary[package_domain]["file_count"] += 1
                        except:
                            pass
                    else:
                        # Not a package folder, continue walking
                        walk(full_path, depth + 1)
                
                elif item.name.lower().endswith(".parquet"):
                    # New format: Entity_SP_Full_*_YYYYMMDD_HHMMSS.parquet (loose files at date level)
                    # Detect domain from filename: _SP_ -> OPR, _DP_ -> FCT
                    name_upper = item.name.upper()
                    file_domain = None
                    if "_SP_" in name_upper:
                        file_domain = "OPR"
                    elif "_DP_" in name_upper:
                        file_domain = "FCT"
                    
                    if file_domain:
                        # Skip metadata/manifest files
                        name_lower = item.name.lower()
                        if name_lower.startswith("manifest_") or name_lower.startswith("metadata_"):
                            continue
                        
                        if domain and file_domain != domain.upper():
                            continue
                        
                        if file_domain not in domain_summary:
                            domain_summary[file_domain] = {"file_count": 0, "package_count": 0}
                        
                        domain_summary[file_domain]["file_count"] += 1
                        
                        # Count unique timestamps as packages
                        stem = item.name.rsplit(".", 1)[0]
                        ts_parts = stem.split("_")
                        if len(ts_parts) >= 2:
                            ts_key = f"{ts_parts[-2]}_{ts_parts[-1]}"
                            if file_domain not in loose_timestamps:
                                loose_timestamps[file_domain] = set()
                            if ts_key not in loose_timestamps[file_domain]:
                                loose_timestamps[file_domain].add(ts_key)
                                domain_summary[file_domain]["package_count"] += 1
        
        if use_orchestrator and not domain:
            try:
                domain_items = mssparkutils.fs.ls(base)
            except Exception as e:
                print(f"[FILE_RECEIPT] Could not access {base}: {e}")
                domain_items = []

            for domain_item in domain_items:
                if not domain_item.isDir:
                    continue

                exact_path = f"Files/bronze/{domain_item.name}/{date_part}/{int(extract_id)}"
                try:
                    mssparkutils.fs.ls(exact_path)
                except Exception:
                    # Strict behavior: if exact path doesn't exist for this domain, skip.
                    continue

                walk(exact_path)
        else:
            # Strict behavior: if exact path doesn't exist, skip.
            try:
                mssparkutils.fs.ls(base)
                walk(base)
            except Exception as e:
                print(f"[FILE_RECEIPT] Exact path not found, skipping: {base} ({e})")
        
        # Convert date format to YYYY-MM-DD
        date_formatted = datetime.strptime(date_part.replace("/", ""), "%Y%m%d").strftime("%Y-%m-%d")
        
        # Prepare summary data
        summary = {
            "date": date_formatted,
            "domains": domain_summary,
            "total_files": sum(d["file_count"] for d in domain_summary.values()),
            "total_packages": sum(d["package_count"] for d in domain_summary.values()),
        }
        
        # Log each domain to the receipt table
        if domain_summary:
            rows = []
            for domain, counts in domain_summary.items():
                rows.append((
                    int(batchid),
                    datetime.strptime(date_formatted, "%Y-%m-%d").date(),
                    domain,
                    counts["file_count"],
                    counts["package_count"],
                    datetime.now()
                ))
            
            # Explicit schema to match the table definition
            receipt_schema = StructType([
                StructField("batchid", IntegerType(), True),
                StructField("ReceiptDate", DateType(), True),
                StructField("Domain", StringType(), True),
                StructField("FileCount", IntegerType(), True),
                StructField("PackageCount", IntegerType(), True),
                StructField("ReceivedAt", TimestampType(), True)
            ])
            
            receipt_df = spark.createDataFrame(rows, receipt_schema)
            
            # MERGE to handle if entry already exists for this date/domain
            receipt_df.createOrReplaceTempView("receipt_temp")
            
            run_merge_with_retry(f"""
                MERGE INTO log.audit_package_receipt t
                USING receipt_temp s
                ON t.ReceiptDate = s.ReceiptDate AND t.Domain = s.Domain
                WHEN MATCHED THEN UPDATE SET 
                    FileCount = s.FileCount,
                    PackageCount = s.PackageCount,
                    ReceivedAt = s.ReceivedAt
                WHEN NOT MATCHED THEN INSERT *
            """)
            
            # Print summary
            print(f"\n[FILE_RECEIPT] Summary for {date_formatted}:")
            print(f"  Total Files: {summary['total_files']}")
            print(f"  Total Packages: {summary['total_packages']}")
            for domain, counts in sorted(domain_summary.items()):
                print(f"  {domain}: {counts['file_count']} files in {counts['package_count']} package(s)")
        else:
            print(f"[FILE_RECEIPT] No files found for {date_formatted}")
        
        return summary
        
    except Exception as e:
        print(f"[ERROR] File receipt scan failed: {e}")
        raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

print("\n" + "="*60)
print("FILE RECEIPT SCANNER - BATCH PROCESSOR")
print("="*60)

# Parameters
domain = None  # Set to None to load ALL domains, or specify a domain like 'FCT', 'OPR', etc.
days_to_count = nr_days_to_count

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

 # Set to limit to last n days, or None for all discovered dates

# Discover all date folders
current_extract_id = _resolve_extract_id()
print(f"[FILE_RECEIPT] Resolved extract_id: {current_extract_id}")
all_dates = discover_date_folders()

# Filter to only last n days if specified
if days_to_count and all_dates:
    all_dates = all_dates[-days_to_count:]
    print(f"[FILE_RECEIPT] Limited to last {days_to_count} day(s)")

if not all_dates:
    print("\n[FILE_RECEIPT] No date folders found!")
else:
    print(f"\n[FILE_RECEIPT] Processing {len(all_dates)} date(s)...")
    
    # Scan each date and collect aggregated results
    all_results = []
    total_files = 0
    total_packages = 0
    all_domains = set()
    
    for date_path in all_dates:
        
        summary = scan_file_receipts(date_path, domain, current_extract_id)
        all_results.append(summary)
        total_files += summary['total_files']
        total_packages += summary['total_packages']
        all_domains.update(summary['domains'].keys())
        print(date_path)
        try:
            if not bool(globals().get("USE_ORCHESTRATOR", 0)):
                load_extraction_manifest_file(batchid, date_path)
        except Exception as e:
            logger.error(f"[FILE_RECEIPT] Could not load manifest for {date_path}: {type(e).__name__}: {str(e)}")
    
    print("\n" + "="*60)
    print("SCAN COMPLETE")
    print("="*60)
    print(f"\nAggregated Results:")
    print(f"  Date Range: {all_dates[0]} to {all_dates[-1]}")
    print(f"  Total Files: {total_files}")
    print(f"  Total Packages: {total_packages}")
    print(f"  Domains: {', '.join(sorted(all_domains)) if all_domains else 'None'}")
    print("\nlog.audit_package_receipt updated successfully")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark",
# META   "frozen": false,
# META   "editable": true
# META }

# CELL ********************

from pyspark.sql import functions as F
from datetime import date, timedelta

# Load table
df = spark.table("log.audit_package_receipt")

# Cast ReceiptDate if needed
df = df.withColumn("ReceiptDate", F.to_date("ReceiptDate", "M/d/yy"))

# Define 2-day window (today + yesterday)
today = date.today()
yesterday = today - timedelta(days=1)

# Filter to last 2 days
recent = df.filter(F.col("ReceiptDate") >= F.lit(yesterday))

# Detect presence of each domain
has_fct = recent.filter(F.col("Domain") == "FCT").count() > 0
has_opr = recent.filter(F.col("Domain") == "OPR").count() > 0

# Derive exit value
if has_fct and has_opr:
    notebook_exit_value = "Default"
elif has_opr:
    notebook_exit_value = "OPR"
elif has_fct:
    notebook_exit_value = "FCT"
else:
    notebook_exit_value = "NONE"

print(f"notebook_exit_value = {notebook_exit_value}")
mssparkutils.notebook.exit(notebook_exit_value)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
