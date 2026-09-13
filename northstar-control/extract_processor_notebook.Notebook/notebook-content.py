# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "jupyter",
# META     "jupyter_kernel_name": "python3.11"
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
# MAGIC     "name": "northstar_archive"
# MAGIC   }
# MAGIC }

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python",
# META   "frozen": false,
# META   "editable": true
# META }

# MARKDOWN ********************

# # Extract Processor Notebook
# 
# ---
# 
# ## 1. Setup and Initialization
# 
# ### 1.1. Installation of Required Packages
# **Note:** Polars and pyodbc may already be in the Fabric Python runtime. Installation here is just in case. Run once per session; pip will skip already-installed packages.

# CELL ********************

# %pip install polars pyodbc --quiet

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 2. Parameter Input
# 
# ### 2.1 Fabric Parameter Cell
# _Mark this cell as "Toggle parameter cell" in Fabric. Parameters are injected by the Fabric REST API trigger; all arrive as strings._

# PARAMETERS CELL ********************

EXTRACT_ID = "1"
FILE_NAME  = "20260607_023248_FCT_FinishedZip_StatisticalForecastEMEADEUUKI_ExpertEngine_2026M07.zip"
RUN_MODE   = "normal"     # "normal" | "test_push" | "cleanup" | "recall_cleanup"
SIGNAL_ID  = "0"          # PK from dbo.workspace_signal — used in recall_cleanup mode

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python",
# META   "frozen": true,
# META   "editable": false
# META }

# MARKDOWN ********************

# ### 2.2 Parameter Validation
# _Validates input parameters and ensures correct run mode._

# CELL ********************

extract_id = int(EXTRACT_ID)
file_name  = FILE_NAME.strip()
run_mode   = RUN_MODE.strip().lower() if "RUN_MODE" in dir() else "normal"
signal_id  = int(SIGNAL_ID) if "SIGNAL_ID" in dir() else 0

if run_mode not in ("normal", "test_push", "cleanup", "recall_cleanup", "retry_push"):
    raise ValueError(
        f"Invalid RUN_MODE={run_mode!r}. Must be: normal, test_push, cleanup, recall_cleanup, retry_push"
    )

if run_mode == "normal":
    if extract_id <= 0 or not file_name:
        raise ValueError(
            f"Invalid parameters: EXTRACT_ID={EXTRACT_ID!r}, FILE_NAME={FILE_NAME!r}"
        )

print(f"✓ extract_id={extract_id}  file={file_name}  run_mode={run_mode}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 3. Configuration
# 
# ### 3.1 SQL Connection & Lakehouse Settings
# _SQL connection details and lakehouse storage paths. Update these values as required for your environment._

# CELL ********************

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-5s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("extract_processor")

FALLBACK_SQL_SERVER   = "o2wftynfatiuzeno5ltily6uhm-bdrrtq2k6dgejnqemf6idnt2si.database.fabric.microsoft.com,1433"
FALLBACK_SQL_DATABASE = "northstar_control-f260b1e6-e20d-4708-91b4-d38345863b46"

# ────────────────────────────────────────────────────────────────────────
# OVERRIDE: If auto-discovery fails and fallback is not appropriate,
# uncomment and set these to hard-coded values for manual override:
# ────────────────────────────────────────────────────────────────────────
# MANUAL_SQL_SERVER = None
# MANUAL_SQL_DATABASE = None


def _get_runtime_context_dict() -> dict:
    ctx = notebookutils.runtime.context
    if isinstance(ctx, str):
        import json as _json
        return _json.loads(ctx)
    return dict(ctx)


# SQL_SERVER and SQL_DATABASE may be injected as parameters by the orchestrator.
# If not provided, fall back to the hardcoded values above.
if "SQL_SERVER" not in dir() or not SQL_SERVER:
    SQL_SERVER = FALLBACK_SQL_SERVER
if "SQL_DATABASE" not in dir() or not SQL_DATABASE:
    SQL_DATABASE = FALLBACK_SQL_DATABASE

# Allow manual override if set
if "MANUAL_SQL_SERVER" in dir() and MANUAL_SQL_SERVER:
    SQL_SERVER = MANUAL_SQL_SERVER
if "MANUAL_SQL_DATABASE" in dir() and MANUAL_SQL_DATABASE:
    SQL_DATABASE = MANUAL_SQL_DATABASE

LAKEHOUSE_ROOT = "/lakehouse/default/Files"
OUTBOUND_PATH  = f"{LAKEHOUSE_ROOT}/outbound"      # ADLS Gen2 shortcut (read-only)
STAGING_PATH   = f"{LAKEHOUSE_ROOT}/staging"        # temp unzip target
READY_PATH     = f"{LAKEHOUSE_ROOT}/ready"          # Parquet output (pre-Bronze)

print(f"✓ Configuration loaded (server={SQL_SERVER}, database={SQL_DATABASE})")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ### 3.2 Imports & Logging
# _All necessary imports, logging configuration, and Fabric runtime verification._

# CELL ********************

import json
import struct
import zipfile
import shutil
import logging
import os
import re
from io import BytesIO
from pathlib import Path
from datetime import datetime, timezone

import polars as pl
import pyodbc

# Verify Fabric environment
try:
    _ = notebookutils
except NameError:
    raise RuntimeError("This notebook must run inside Microsoft Fabric")

print("✓ Imports OK")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 4. Database Helper Functions
# 
# ### 4.1 SQL Connection Setup
# ### 4.2 Helper Functions
# _Convenience wrappers for database operations, logging and workspace context retrieval._

# CELL ********************

def get_db_connection():
    """
    Connect to Fabric SQL Database using workspace identity.
    Obtains an Azure AD token via notebookutils and passes it
    to pyodbc through SQL_COPT_SS_ACCESS_TOKEN (attr 1256).
    """
    token = notebookutils.credentials.getToken("https://database.windows.net/")
    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(
        f"<I{len(token_bytes)}s", len(token_bytes), token_bytes
    )
    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={SQL_SERVER},1433;"
        f"DATABASE={SQL_DATABASE};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct})


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def execute_sql(query: str, params: tuple = (), fetch: str = "none"):
    """
    Execute a SQL statement against the Fabric SQL Database.

    Args:
        query:  SQL string with ? placeholders.
        params: Tuple of parameter values.
        fetch:  "none" → commit only (returns rowcount),
                "one"  → single row, "all" → all rows.
    """
    conn = get_db_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)

        if fetch == "one":
            result = cursor.fetchone()
        elif fetch == "all":
            result = cursor.fetchall()
        else:
            result = cursor.rowcount

        conn.commit()
        return result
    finally:
        conn.close()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def update_extract_status(eid: int, status: str, **extra_fields):
    """
    Update dbo.extract.status and cascade the same status to dbo.extract_file.

    Optional extra fields can also be updated.

    Use the sentinel "SYSUTCDATETIME()" for server-side timestamps.

    Example:
        update_extract_status(
            42,
            "VALIDATED",
            is_valid=True,
            validated_at="SYSUTCDATETIME()"
        )
    """

    set_clauses = ["[status] = ?", "[updated_at] = SYSUTCDATETIME()"]
    params: list = [status]

    for col, val in extra_fields.items():
        if val == "SYSUTCDATETIME()":
            set_clauses.append(f"[{col}] = SYSUTCDATETIME()")
        elif val is None:
            set_clauses.append(f"[{col}] = NULL")
        else:
            set_clauses.append(f"[{col}] = ?")
            params.append(val)

    params.append(eid)

    # ----------------------------------------
    # Update extract
    # ----------------------------------------
    sql_extract = f"""
        UPDATE dbo.extract
        SET {', '.join(set_clauses)}
        WHERE [extract_id] = ?
    """

    execute_sql(sql_extract, tuple(params))

    # ----------------------------------------
    # Cascade status to extract_file
    # ----------------------------------------
    sql_files = """
        UPDATE dbo.extract_file
        SET [status] = ?, [pushed_at] = SYSUTCDATETIME()
        WHERE [extract_id] = ?
    """

    execute_sql(sql_files, (status, eid))

    log.info(
        "extract_id=%d → status=%s (extract + files updated)",
        eid,
        status
    )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def log_to_db(
    eid: int,
    level: str,
    category: str,
    message: str,
    push_job_id: int = None,
    function_name: str = None,
):
    """Insert a row into dbo.job_log."""
    execute_sql(
        """
        INSERT INTO dbo.job_log
            ([extract_id], [push_job_id], [log_level], [log_category],
             [message], [function_name], [created_at])
        VALUES (?, ?, ?, ?, ?, ?, SYSUTCDATETIME())
        """,
        (eid, push_job_id, level, category, message[:4000], function_name),
    )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def get_workspace_context() -> dict:
    """Read workspace & lakehouse IDs from Fabric runtime context."""
    ctx = notebookutils.runtime.context
    if isinstance(ctx, str):
        ctx = json.loads(ctx)

    result = {
        "workspace_id":   ctx.get("currentWorkspaceId", ""),
        "workspace_name": ctx.get("currentWorkspaceName", ""),
        "lakehouse_id":   ctx.get("defaultLakehouseId", ""),
        "lakehouse_name": ctx.get("defaultLakehouseName", ""),
    }
    log.info("Workspace context: %s", json.dumps(result))
    return result


# Connectivity test
_test = execute_sql("SELECT 1", fetch="one")
assert _test and _test[0] == 1, "SQL Database connectivity check FAILED"
print("✓ SQL Database connection OK")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 5. Extract Processing Functions
# 
# ### 5.1 Metadata, ZIP Load, Conversion, Register, Validation, Push, and Cleanup
# _This section provides step-by-step processing logic: metadata loading, ZIP extraction, conversion to Parquet, registration in DB, validation, push to targets, workspace signal handling, and recall cleanup._

# CELL ********************

def load_extract_metadata(eid: int) -> dict:
    """
    Read the extract row.  This is the source of truth for domain_code
    and period — not the filename.
    """
    row = execute_sql(
        """
        SELECT [domain_code], [source_code], [folder_path], [folder_name],
               [source_file_name], [period_year], [period_month], [status],
               [instance_code], [period_type], [arrived_at],
               [extraction_date], [cycle_id], [extraction_def]
          FROM dbo.extract
         WHERE [extract_id] = ?
        """,
        (eid,),
        fetch="one",
    )
    if row is None:
        raise ValueError(f"extract_id={eid} not found in database")

    meta = {
        "domain_code":      row[0],
        "source_code":      row[1],
        "folder_path":      row[2],
        "folder_name":      row[3],
        "source_file_name": row[4],
        "period_year":      row[5],
        "period_month":     row[6],
        "current_status":   row[7],
        "instance_code":    row[8],
        "period_type":      row[9],
        "arrived_at":       row[10],
        "extraction_date":  row[11],
        "cycle_id":         row[12],
        "extraction_def":   row[13],
    }
    log.info(
        "Loaded: domain=%s, instance=%s, period_type=%s, status=%s, period=%d-%02d",
        meta["domain_code"], meta["instance_code"], meta["period_type"],
        meta["current_status"], meta["period_year"], meta["period_month"],
    )
    print(meta)
    return meta


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def read_zip_from_lakehouse(fname: str) -> bytes:
    """
    Read the ZIP from /lakehouse/default/Files/outbound/{fname}.
    The outbound/ folder is a shortcut to the external ADLS Gen2 account.
    """
    zip_filename = Path(fname).name          # strip any accidental path prefix
    zip_path = Path(OUTBOUND_PATH) / zip_filename

    if not zip_path.exists():
        raise FileNotFoundError(f"ZIP not found: {zip_path}")

    size = zip_path.stat().st_size
    log.info("Reading: %s (%s bytes)", zip_path, f"{size:,}")

    data = zip_path.read_bytes()
    log.info("Read %s bytes into memory", f"{len(data):,}")
    return data

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def parse_manifest(zip_bytes: bytes) -> dict:
    """
    Parse the metadata/manifest file from the ZIP archive.

    The file is a key-value TSV (two columns: key, value).
    It is named like: MetaData_DP_DemandPlanningWeekly_…_20260320_230019.tsv
    We look for files whose name starts with 'MetaData' (case-insensitive).

    Returns dict with extracted fields:
        extraction_date (datetime or None), cycle_id (str), extraction_def (str),
        package_def (str)
    """
    manifest_data: dict[str, str] = {}

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        # Find metadata file(s) — starts with "MetaData" (case-insensitive)
        manifest_entries = [
            name for name in zf.namelist()
            if not name.endswith("/")
            and Path(name).name.lower().startswith("metadata")
        ]

        if not manifest_entries:
            log.warning("No manifest file found in ZIP")
            return {"extraction_date": None, "cycle_id": None, "extraction_def": None, "package_def": None}

        # Use the first manifest found
        manifest_name = manifest_entries[0]
        log.info("Parsing manifest: %s", manifest_name)

        raw_bytes = zf.read(manifest_name)

        # Detect encoding: UTF-16 LE BOM (ff fe) or UTF-16 BE BOM (fe ff)
        if raw_bytes[:2] in (b"\xff\xfe", b"\xfe\xff"):
            raw = raw_bytes.decode("utf-16", errors="replace")
        else:
            raw = raw_bytes.decode("utf-8-sig", errors="replace")

        for line in raw.strip().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t", 1)
            if len(parts) == 2:
                key = parts[0].strip()
                # Skip header row
                if key.lower() == "key":
                    continue
                manifest_data[key] = parts[1].strip()

    log.info("Manifest keys found: %s", list(manifest_data.keys()))

    # Extract the fields we need
    extraction_date = None
    raw_date = manifest_data.get("ExtractionDate")
    if raw_date:
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%SZ",
                     "%Y-%m-%d", "%d/%m/%Y %H:%M:%S"):
            try:
                extraction_date = datetime.strptime(raw_date, fmt)
                break
            except ValueError:
                continue
        if extraction_date is None:
            log.warning("Could not parse ExtractionDate: %s", raw_date)

    result = {
        "extraction_date": extraction_date,
        "cycle_id":        manifest_data.get("CycleId"),
        "extraction_def":  manifest_data.get("ExtractionDef"),
        "package_def":     manifest_data.get("PackageDef"),
    }
    log.info(
        "Manifest parsed: extraction_date=%s, cycle_id=%s, extraction_def=%s, package_def=%s",
        result["extraction_date"], result["cycle_id"], result["extraction_def"],
        result["package_def"],
    )
    return result

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def detect_late_arrival(
    eid: int,
    domain_code: str,
    extraction_def: str | None,
    extraction_date: datetime | None,
) -> bool:
    """
    Check if this extract is a late arrival — i.e. an extract with the same
    domain_code + extraction_def but a LATER extraction_date has already
    started or completed B2S processing.

    Returns True if this is a late arrival.
    """
    if extraction_date is None or extraction_def is None:
        log.info("Cannot detect late arrival: extraction_date or extraction_def is None")
        return False

    row = execute_sql(
        """
        SELECT COUNT(*) AS cnt
          FROM dbo.medallion_sync ms
          INNER JOIN dbo.extract e ON ms.extract_id = e.extract_id
         WHERE e.domain_code = ?
           AND e.extraction_def = ?
           AND e.extraction_date > ?
           AND ms.b2s_status IN ('RUNNING', 'SUCCESS', 'FAILED')
        """,
        (domain_code, extraction_def, extraction_date),
        fetch="one",
    )

    already_processed = row[0] if row else 0

    if already_processed > 0:
        log.warning(
            "LATE ARRIVAL DETECTED: extract_id=%d domain=%s extraction_def=%s "
            "extraction_date=%s — %d sync row(s) with later extraction_date "
            "have already started/completed B2S",
            eid, domain_code, extraction_def, extraction_date, already_processed,
        )
        # Flag this extract
        execute_sql(
            "UPDATE dbo.extract SET [is_late_arrival] = 1, [updated_at] = SYSUTCDATETIME() "
            "WHERE [extract_id] = ?",
            (eid,),
        )
        log_to_db(
            eid, "WARNING", "LATE_ARRIVAL",
            f"Late arrival detected: {already_processed} sync row(s) with later "
            f"extraction_date have already been processed through B2S. "
            f"Use POST /medallion-sync/batch/rerun to replay.",
            function_name="detect_late_arrival",
        )
        return True

    return False

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def unzip_and_convert(
    zip_bytes: bytes,
    eid: int,
    domain_code: str,
    folder_name: str = "",
) -> list[dict]:
    """
    Unzip archive, convert tabular files (TSV/CSV) to Parquet via Polars.

    Output: {READY_PATH}/{domain_code}/{eid}/{folder_name}/
    Returns list of per-file metadata dicts.
    """
    if folder_name:
        output_dir  = Path(READY_PATH)   / domain_code / str(eid) / folder_name
    else:
        output_dir  = Path(READY_PATH)   / domain_code / str(eid)
    staging_dir = Path(STAGING_PATH) / domain_code / str(eid)

    # Clean previous attempts (re-run safety)
    for d in (output_dir, staging_dir):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True, exist_ok=True)

    def clean_col_name(name: str) -> str:
        if name is None:
            return "column"
        s = re.sub(r"\s+", "", str(name))
        s = re.sub(r"[^0-9A-Za-z_]", "", s)
        return s or "column"

    def detect_encoding(path: Path) -> str:
        with open(path, "rb") as f:
            bom = f.read(2)
        if bom in (b"\xff\xfe", b"\xfe\xff"):
            return "utf-16"
        return "utf-8"

    def format_partition_keys_value(value: str | None) -> str | None:
        """
        Normalize PartitionKeys payload as a single string where each
        comma-separated partition token is single-quoted.
        Example: A,B -> 'A','B'
        """
        if value is None:
            return None
        raw = str(value).strip()
        if not raw:
            return raw

        parts = [p.strip() for p in raw.split(",") if p.strip()]
        if not parts:
            return ""

        quoted_parts: list[str] = []
        for part in parts:
            token = part
            if len(token) >= 2 and token.startswith("'") and token.endswith("'"):
                token = token[1:-1]
            token = token.replace("'", "")
            quoted_parts.append(f"'{token}'")
        return ",".join(quoted_parts)

    def is_manifest_or_metadata_file(path: Path) -> bool:
        file_name = path.name.lower()
        return file_name.startswith("manifest_") or file_name.startswith("metadata_")

    def load_tabular_with_clean_headers(path: Path, sep: str) -> pl.DataFrame:
        enc = detect_encoding(path)
        source_path = path

        # Polars CSV reader is utf-8 based; normalize utf-16 inputs first.
        if enc == "utf-16":
            utf8_path = path.with_suffix(path.suffix + ".utf8")
            with open(path, "r", encoding="utf-16", errors="replace") as rf:
                text = rf.read()
            with open(utf8_path, "w", encoding="utf-8", errors="replace") as wf:
                wf.write(text)
            source_path = utf8_path

        with open(source_path, "r", encoding="utf-8", errors="replace") as hf:
            header_line = hf.readline().rstrip("\n\r")

        # Some manifest files are simple key/value CSV where values may contain
        # unquoted commas (not valid RFC CSV). For these files, split each row
        # only on the first comma to preserve the full Value field.
        if (
            is_manifest_or_metadata_file(path)
            and sep == ","
            and header_line.strip().lower() == "key,value"
        ):
            records: list[dict[str, str]] = []
            with open(source_path, "r", encoding="utf-8", errors="replace") as rf:
                _ = rf.readline()  # skip header
                for line in rf:
                    row = line.rstrip("\n\r")
                    if not row.strip():
                        continue
                    key, value = (row.split(",", 1) + [""])[:2]
                    records.append({"Key": key.strip(), "Value": value.strip()})

            if source_path != path and source_path.exists():
                source_path.unlink(missing_ok=True)
            return pl.DataFrame(records) if records else pl.DataFrame({"Key": [], "Value": []})

        raw_header_parts = header_line.split(sep) if header_line else []

        keep_indices: list[int] = []
        final_cols: list[str] = []
        seen: set[str] = set()
        for idx, raw_col in enumerate(raw_header_parts):
            cleaned = clean_col_name(raw_col)
            if cleaned in seen:
                continue
            seen.add(cleaned)
            keep_indices.append(idx)
            final_cols.append(cleaned)

        try:
            df_raw = pl.read_csv(
                str(source_path),
                separator=sep,
                has_header=False,
                skip_rows=1,
                infer_schema_length=10_000,
                ignore_errors=True,
                truncate_ragged_lines=True,
                encoding="utf8-lossy",
            )
        except Exception:
            # Header-only file (no data rows) — Polars raises "empty CSV".
            # Build a schema-only (0-row) DataFrame from the parsed column names.
            if source_path != path and source_path.exists():
                source_path.unlink(missing_ok=True)
            if final_cols:
                return pl.DataFrame(schema={col: pl.Utf8 for col in final_cols})
            return pl.DataFrame()

        if source_path != path and source_path.exists():
            source_path.unlink(missing_ok=True)

        if not keep_indices:
            return df_raw

        # Keep first occurrence of duplicate columns and rename to cleaned names.
        valid_pairs = [
            (idx, name)
            for idx, name in zip(keep_indices, final_cols)
            if idx < df_raw.width
        ]
        if not valid_pairs:
            # Data body was empty (0 rows → 0 columns inferred by Polars).
            # Return a schema-only DataFrame so the caller can still write a parquet.
            if final_cols:
                return pl.DataFrame(schema={col: pl.Utf8 for col in final_cols})
            return df_raw

        selected_exprs = [
            pl.col(f"column_{idx + 1}").alias(name)
            for idx, name in valid_pairs
        ]
        return df_raw.select(selected_exprs)

    def clean_tabular_values(
        df: pl.DataFrame,
        apply_manifest_partition_fix: bool = False,
    ) -> pl.DataFrame:
        # Keep delimiters used by source payloads (notably '|' and '*').
        safe_chars = r"[^\p{L}\p{N}_\-\+\(\)\/°% :\.,\|\*<>@#!\?;=&\\\[\]\{\}]"
        cleaned_exprs = []
        for c in df.columns:
            if c.upper() == "PARTITIONKEY":
                cleaned_exprs.append(
                    pl.col(c)
                    .cast(pl.Utf8, strict=False)
                    .str.replace_all("'", "")
                    .alias(c)
                )
                continue
            cleaned_exprs.append(
                pl.col(c)
                .cast(pl.Utf8, strict=False)
                .str.replace_all(r"[\x00-\x1F]", "")
                .str.replace_all("�", "")
                .str.replace_all(safe_chars, "")
                .alias(c)
            )
        out = df.with_columns(cleaned_exprs)

        # Reformat manifest PartitionKeys rows as quoted comma-separated values.
        key_col = next((c for c in out.columns if c.lower() == "key"), None)
        value_col = next((c for c in out.columns if c.lower() == "value"), None)
        if apply_manifest_partition_fix and key_col and value_col:
            out = out.with_columns(
                pl.when(
                    pl.col(key_col)
                    .cast(pl.Utf8, strict=False)
                    .str.starts_with("PartitionKeys.")
                )
                .then(
                    pl.col(value_col)
                    .cast(pl.Utf8, strict=False)
                    .map_elements(format_partition_keys_value, return_dtype=pl.Utf8)
                )
                .otherwise(pl.col(value_col).cast(pl.Utf8, strict=False))
                .alias(value_col)
            )

        # Drop ghost rows (all empty / null values).
        non_empty = [
            pl.col(c).is_not_null() & (pl.col(c).cast(pl.Utf8, strict=False).str.strip_chars() != "")
            for c in out.columns
        ]
        if non_empty:
            out = out.filter(pl.any_horizontal(non_empty))
        return out

    files_meta: list[dict] = []

    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        entries = [e for e in zf.namelist() if not e.endswith("/")]
        log.info("ZIP contains %d file(s)", len(entries))

        for entry_name in entries:
            zf.extract(entry_name, path=str(staging_dir))
            extracted_path = staging_dir / entry_name
            base_name  = Path(entry_name).name
            lower_name = base_name.lower()

            # Decide separator
            if lower_name.endswith(".tsv"):
                sep, src_fmt = "\t", "tsv"
            elif lower_name.endswith(".csv"):
                sep, src_fmt = ",", "csv"
            else:
                sep, src_fmt = None, Path(base_name).suffix.lstrip(".") or "bin"

            if sep is not None:
                # ── Convert tabular → Parquet ──
                try:
                    df = load_tabular_with_clean_headers(extracted_path, sep)
                    df = clean_tabular_values(
                        df,
                        apply_manifest_partition_fix=is_manifest_or_metadata_file(Path(base_name)),
                    )
                    parquet_name = base_name.rsplit(".", 1)[0] + ".parquet"
                    parquet_path = output_dir / parquet_name
                    df.write_parquet(str(parquet_path), compression="snappy")

                    files_meta.append({
                        "file_name":     parquet_name,
                        "original_name": base_name,
                        "size_bytes":    parquet_path.stat().st_size,
                        "row_count":     len(df),
                        "file_format":   "parquet",
                        "error":         None,
                    })
                    if len(df) == 0:
                        log.warning(
                            "  ⚠ %s → %s  (0 rows — empty source file, schema-only parquet written)",
                            base_name, parquet_name,
                        )
                    else:
                        log.info(
                            "  ✓ %s → %s  (%s rows, %s bytes)",
                            base_name, parquet_name,
                            f"{len(df):,}",
                            f"{parquet_path.stat().st_size:,}",
                        )
                except Exception as e:
                    log.error("  ✗ FAILED %s: %s", base_name, e)
                    files_meta.append({
                        "file_name":     base_name,
                        "original_name": base_name,
                        "size_bytes":    0,
                        "row_count":     0,
                        "file_format":   src_fmt,
                        "error":         str(e)[:500],
                    })
            else:
                # ── Non-tabular → copy as-is ──
                dest = output_dir / base_name
                shutil.copy2(str(extracted_path), str(dest))
                files_meta.append({
                    "file_name":     base_name,
                    "original_name": base_name,
                    "size_bytes":    dest.stat().st_size,
                    "row_count":     0,
                    "file_format":   src_fmt,
                    "error":         None,
                })
                log.info("  ⎘ Copied as-is: %s", base_name)

    # Staging cleanup
    shutil.rmtree(staging_dir, ignore_errors=True)

    total_bytes = sum(f["size_bytes"] for f in files_meta)
    log.info(
        "Conversion done: %d file(s), %s total bytes",
        len(files_meta), f"{total_bytes:,}",
    )
    return files_meta

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def register_extract_files(eid: int, domain_code: str, files_meta: list[dict], folder_name: str = ""):
    """Insert one row per output file into dbo.extract_file."""
    # Remove any previous rows for this extract (re-run safety)
    execute_sql("DELETE FROM dbo.extract_file WHERE [extract_id] = ?", (eid,))
    for f in files_meta:
        # Store relative path from lakehouse Files/ root (portable)
        if folder_name:
            rel_path = f"ready/{domain_code}/{eid}/{folder_name}/{f['file_name']}"
        else:
            rel_path = f"ready/{domain_code}/{eid}/{f['file_name']}"

        execute_sql(
            """
            INSERT INTO dbo.extract_file
                ([extract_id], [file_name], [file_path], [file_size_bytes],
                 [original_file_name], [file_format], [row_count],
                 [status], [created_at])
            VALUES (?, ?, ?, ?, ?, ?, ?, 'NEW', SYSUTCDATETIME())
            """,
            (
                eid,
                f["file_name"],
                rel_path,
                f["size_bytes"],
                f["original_name"],
                f["file_format"],
                f["row_count"] if f["row_count"] > 0 else None,
            ),
        )
    log.info("Registered %d file(s) in extract_file", len(files_meta))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def validate_extract(eid: int, domain_code: str, file_count: int) -> dict:
    """
    Check file count against domain_config bounds.
    Returns {"is_valid": bool, "message": str}.
    """
    row = execute_sql(
        """
        SELECT [min_expected_files], [max_expected_files]
          FROM dbo.domain_config
         WHERE [domain_code] = ?
        """,
        (domain_code,),
        fetch="one",
    )

    if row is None:
        msg = f"No domain_config for domain {domain_code} — passed by default"
        log.warning("VALIDATION: %s", msg)
        return {"is_valid": True, "message": msg}

    min_f, max_f = row[0], row[1]

    if min_f is not None and file_count < min_f:
        msg = f"File count {file_count} below minimum {min_f} for {domain_code}"
        log.error("VALIDATION FAILED: %s", msg)
        return {"is_valid": False, "message": msg}

    if max_f is not None and file_count > max_f:
        msg = f"File count {file_count} exceeds maximum {max_f} for {domain_code}"
        log.error("VALIDATION FAILED: %s", msg)
        return {"is_valid": False, "message": msg}

    msg = f"Passed: {file_count} files within [{min_f}, {max_f}] for {domain_code}"
    log.info("VALIDATION OK: %s", msg)
    return {"is_valid": True, "message": msg}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def get_target_workspaces(
    domain_code: str,
    instance_code: str | None,
    period_type: str | None,
    arrived_at,
) -> list[dict]:
    """
    Query dbo.target_workspace for enabled workspaces matching the extract's
    domain, instance, period_type, and arrival date.
    """
    rows = execute_sql(
        """
        SELECT [target_workspace_id],
               [target_workspace_name],
               [target_lakehouse_id],
               [target_lakehouse_name]
          FROM dbo.target_workspace
         WHERE [enabled] = 1
           AND ([domain_filter]      IS NULL OR [domain_filter]      = ?)
           AND ([instance_filter]    IS NULL OR [instance_filter]    = ?)
           AND ([period_type_filter] IS NULL OR [period_type_filter] = ?)
           AND ([arrived_after]      IS NULL OR ? >= [arrived_after])
        """,
        (domain_code, instance_code, period_type, arrived_at),
        fetch="all",
    )

    targets = []
    for r in (rows or []):
        targets.append({
            "workspace_id":   r[0],
            "workspace_name": r[1],
            "lakehouse_id":   r[2],
            "lakehouse_name": r[3],
        })

    log.info(
        "Found %d target workspace(s) for domain=%s, instance=%s, period_type=%s",
        len(targets), domain_code, instance_code, period_type,
    )
    for t in targets:
        log.info("  -> %s (%s)", t["workspace_name"], t["workspace_id"])

    return targets

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def process_workspace_signals(eid: int) -> list[dict]:
    """
    Query pending workspace signals, acknowledge each one, and log.
    The create_workspace_signal SP has already handled the heavy lifting
    (marking push_jobs RECALLED and medallion_sync INVALIDATED).
    The notebook just acknowledges.
    """
    rows = execute_sql(
        """
        SELECT [signal_id], [target_workspace_id], [signal_type],
               [scope_domain], [reason]
          FROM dbo.workspace_signal
         WHERE [status] = 'PENDING'
        """,
        fetch="all",
    )

    signals_processed = []
    for r in (rows or []):
        signal_id    = r[0]
        tgt_ws_id    = r[1]
        signal_type  = r[2]
        scope_domain = r[3]
        reason       = r[4]

        try:
            execute_sql(
                "EXEC dbo.acknowledge_workspace_signal "
                "  @signal_id = ?, @new_status = ?",
                (signal_id, "ACKNOWLEDGED"),
            )
            log.info(
                "Acknowledged signal_id=%d type=%s workspace=%s reason=%s",
                signal_id, signal_type, tgt_ws_id, reason,
            )
            log_to_db(
                eid, "INFO", "SIGNAL",
                f"Acknowledged signal_id={signal_id} type={signal_type} "
                f"workspace={tgt_ws_id} reason={reason}",
                function_name="process_workspace_signals",
            )
            signals_processed.append({
                "signal_id":    signal_id,
                "signal_type":  signal_type,
                "workspace_id": tgt_ws_id,
                "status":       "ACKNOWLEDGED",
            })
        except Exception as sig_err:
            log.warning(
                "Failed to acknowledge signal_id=%d: %s", signal_id, sig_err,
            )
            signals_processed.append({
                "signal_id":    signal_id,
                "signal_type":  signal_type,
                "workspace_id": tgt_ws_id,
                "status":       "ERROR",
                "error":        str(sig_err)[:500],
            })

    if not signals_processed:
        log.info("No pending workspace signals found")

    return signals_processed

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def push_to_workspaces(
    eid: int,
    domain_code: str,
    target_workspaces: list[dict],
    file_count: int,
    total_size_bytes: int,
    arrived_at: datetime,
    source_file_name: str = "",
) -> list[dict]:
    """
    Copy ready/{domain_code}/{eid}/ (Parquet files only) to
    bronze/{domain_code}/{YYYY}/{MM}/{DD}/{eid}/{file_folder}/
    in each target workspace using abfss:// paths and notebookutils.fs.cp.
    Copies files individually to avoid creating extra subfolders.
    """
    if not target_workspaces:
        log.info("No target workspaces — nothing to push")
        return []

    # Derive file_folder from source filename (ZIP name without extension)
    file_folder = source_file_name.rsplit(".", 1)[0] if source_file_name else ""

    # Source path from runtime context
    ctx = get_workspace_context()
    src_ws_id = ctx["workspace_id"]
    src_lh_id = ctx["lakehouse_id"]
    if file_folder:
        src_abfss = (
            f"abfss://{src_ws_id}@onelake.dfs.fabric.microsoft.com/"
            f"{src_lh_id}/Files/ready/{domain_code}/{eid}/{file_folder}/"
        )
    else:
        src_abfss = (
            f"abfss://{src_ws_id}@onelake.dfs.fabric.microsoft.com/"
            f"{src_lh_id}/Files/ready/{domain_code}/{eid}/"
        )
    log.info("Source abfss path: %s", src_abfss)

    # List all files in source (ignore subdirectories)
    try:
        all_items = notebookutils.fs.ls(src_abfss)
        source_files = [item.path for item in all_items if item.isFile]
        log.info("Found %d file(s) to copy: %s", len(source_files),
                 [p.split('/')[-1] for p in source_files])
    except Exception as e:
        log.warning("Could not list source files: %s, will fallback to recursive copy", e)
        source_files = None

    push_results = []

    for target in target_workspaces:
        tgt_ws_id   = target["workspace_id"]
        tgt_ws_name = target["workspace_name"]
        tgt_lh_id   = target["lakehouse_id"]
        tgt_lh_name = target["lakehouse_name"]

        dt = arrived_at
        date_part = f"{dt.year}/{dt.month:02d}/{dt.day:02d}"

        if file_folder:
            bronze_rel = f"bronze/{domain_code}/{date_part}/{eid}/{file_folder}"
        else:
            bronze_rel = f"bronze/{domain_code}/{date_part}/{eid}"

        dst_abfss = (
            f"abfss://{tgt_ws_id}@onelake.dfs.fabric.microsoft.com/"
            f"{tgt_lh_id}/Files/{bronze_rel}/"
        )

        # --- Print output folder ---
        log.info("Output folder for workspace %s (%s): %s", tgt_ws_name, tgt_ws_id, bronze_rel)
        log.info("Full destination abfss path: %s", dst_abfss)

        result = {
            "workspace_id":   tgt_ws_id,
            "workspace_name": tgt_ws_name,
            "push_job_id":    None,
            "status":         "FAILED",
            "error":          None,
        }

        try:
            # 1. create_push_job stored procedure
            conn = get_db_connection()
            try:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DECLARE @pjid INT;
                    EXEC dbo.create_push_job
                        @extract_id            = ?,
                        @target_workspace_id   = ?,
                        @target_workspace_name = ?,
                        @target_lakehouse_id   = ?,
                        @target_lakehouse_name = ?,
                        @bronze_folder_path    = ?,
                        @push_job_id           = @pjid OUTPUT;
                    """,
                    (eid, tgt_ws_id, tgt_ws_name, tgt_lh_id, tgt_lh_name, bronze_rel),
                )
                row = cursor.fetchone()
                conn.commit()
                push_job_id = row[0] if row else None
                if not push_job_id:
                    cursor.execute(
                        "SELECT TOP 1 push_job_id FROM dbo.push_job "
                        "WHERE extract_id = ? AND target_workspace_id = ? "
                        "ORDER BY push_job_id DESC",
                        (eid, tgt_ws_id),
                    )
                    fb = cursor.fetchone()
                    push_job_id = fb[0] if fb else None
            finally:
                conn.close()

            if push_job_id is None:
                raise RuntimeError(
                    f"create_push_job returned no push_job_id for extract_id={eid}, workspace={tgt_ws_id}"
                )

            result["push_job_id"] = push_job_id
            log.info("Created push_job_id=%d for workspace %s (%s)", push_job_id, tgt_ws_name, tgt_ws_id)

            # 2. Mark RUNNING
            execute_sql("EXEC dbo.update_push_job_status @push_job_id = ?, @status = ?", (push_job_id, "RUNNING"))
            log.info("push_job_id=%d -> RUNNING", push_job_id)

            # 3. Copy files (individual copies to avoid extra folders)
            start_ts = datetime.now(timezone.utc)
            if source_files is not None:
                copied = 0
                for src_file in source_files:
                    file_name = src_file.split('/')[-1]
                    dest_file = dst_abfss + file_name
                    notebookutils.fs.cp(src_file, dest_file)
                    copied += 1
                log.info("push_job_id=%d: copied %d file(s) individually", push_job_id, copied)
            else:
                # Fallback: recursive copy (may create subdirectories)
                notebookutils.fs.cp(src_abfss, dst_abfss, recurse=True)
                log.info("push_job_id=%d: used recursive copy", push_job_id)

            elapsed = (datetime.now(timezone.utc) - start_ts).total_seconds()
            log.info("push_job_id=%d: copy completed in %.2fs", push_job_id, elapsed)

            # 4. Mark SUCCESS
            execute_sql(
                "EXEC dbo.update_push_job_status @push_job_id = ?, @status = ?, "
                "@files_attempted = ?, @files_succeeded = ?, @files_failed = ?, @bytes_transferred = ?",
                (push_job_id, "SUCCESS", file_count, file_count, 0, total_size_bytes),
            )
            log.info("push_job_id=%d -> SUCCESS", push_job_id)

            # 5. Update medallion_sync
            execute_sql(
                "EXEC dbo.update_medallion_sync @extract_id = ?, @target_workspace_id = ?, "
                "@bronze_status = ?, @bronze_loaded_at = ?, @bronze_file_count = ?",
                (eid, tgt_ws_id, "LOADED", datetime.now(timezone.utc), file_count),
            )
            log.info("medallion_sync: extract=%d, workspace=%s, bronze=LOADED", eid, tgt_ws_id)

            # 6. Log success
            log_to_db(
                eid, "INFO", "PUSH",
                f"Pushed {file_count} file(s) ({total_size_bytes:,} bytes) to {tgt_ws_name} ({bronze_rel}) in {elapsed:.2f}s",
                push_job_id=push_job_id,
                function_name="push_to_workspaces",
            )

            result["status"] = "SUCCESS"

        except Exception as ws_err:
            log.error("PUSH FAILED for workspace %s (%s): %s", tgt_ws_name, tgt_ws_id, ws_err)
            result["error"] = str(ws_err)[:2000]

            if result["push_job_id"] is not None:
                try:
                    execute_sql(
                        "EXEC dbo.update_push_job_status @push_job_id = ?, @status = ?, @error_message = ?",
                        (result["push_job_id"], "FAILED", str(ws_err)[:4000]),
                    )
                except Exception as db_err:
                    log.error("Could not mark push_job %d as FAILED: %s", result["push_job_id"], db_err)

            log_to_db(
                eid, "ERROR", "PUSH",
                f"Push to {tgt_ws_name} failed: {str(ws_err)[:3500]}",
                push_job_id=result["push_job_id"],
                function_name="push_to_workspaces",
            )

        push_results.append(result)

    success_count = sum(1 for r in push_results if r["status"] == "SUCCESS")
    log.info("Push complete: %d/%d workspace(s) succeeded", success_count, len(push_results))
    return push_results
  

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

def recall_cleanup(sid: int = 0) -> list[dict]:
    """
    Find RECALLED push_jobs (optionally scoped to a specific signal),
    delete their Bronze files from target lakehouses, reset medallion_sync,
    and mark the workspace_signal COMPLETED.
    """

    # ── 1. Find RECALLED push_jobs with their target workspace info ──
    if sid > 0:
        rows = execute_sql(
            """
            SELECT pj.[push_job_id],
                   pj.[extract_id],
                   pj.[target_workspace_id],
                   pj.[target_workspace_name],
                   pj.[target_lakehouse_id],
                   pj.[bronze_folder_path],
                   e.[domain_code]
              FROM dbo.push_job pj
              INNER JOIN dbo.extract e ON pj.extract_id = e.extract_id
             WHERE pj.[status] = 'RECALLED'
               AND pj.[error_message] LIKE '%signal_id=' + CAST(? AS VARCHAR) + '%'
             ORDER BY pj.[push_job_id]
            """,
            (sid,),
            fetch="all",
        )
    else:
        rows = execute_sql(
            """
            SELECT pj.[push_job_id],
                   pj.[extract_id],
                   pj.[target_workspace_id],
                   pj.[target_workspace_name],
                   pj.[target_lakehouse_id],
                   pj.[bronze_folder_path],
                   e.[domain_code]
              FROM dbo.push_job pj
              INNER JOIN dbo.extract e ON pj.extract_id = e.extract_id
             WHERE pj.[status] = 'RECALLED'
             ORDER BY pj.[push_job_id]
            """,
            fetch="all",
        )

    if not rows:
        log.info("No RECALLED push_jobs found — nothing to clean up")
        return []

    log.info("Found %d RECALLED push_job(s) to clean up", len(rows))
    cleanup_results = []

    for r in rows:
        pj_id         = r[0]
        eid           = r[1]
        tgt_ws_id     = r[2]
        tgt_ws_name   = r[3]
        tgt_lh_id     = r[4]
        bronze_rel    = r[5]
        domain_code   = r[6]

        result = {
            "push_job_id":    pj_id,
            "extract_id":     eid,
            "workspace_name": tgt_ws_name,
            "bronze_path":    bronze_rel,
            "file_cleanup":   "SKIPPED",
            "db_cleanup":     "SKIPPED",
        }

        # ── 2. Delete Bronze files from target lakehouse ──
        bronze_abfss = (
            f"abfss://{tgt_ws_id}@onelake.dfs.fabric.microsoft.com/"
            f"{tgt_lh_id}/Files/{bronze_rel}/"
        )
        log.info(
            "push_job_id=%d: deleting %s from %s",
            pj_id, bronze_abfss, tgt_ws_name,
        )

        try:
            notebookutils.fs.rm(bronze_abfss, recurse=True)
            result["file_cleanup"] = "DELETED"
            log.info("  ✓ Bronze files deleted")
        except Exception as rm_err:
            err_str = str(rm_err)
            if "not exist" in err_str.lower() or "not found" in err_str.lower():
                result["file_cleanup"] = "ALREADY_GONE"
                log.info("  ⎘ Bronze path already gone (OK)")
            else:
                result["file_cleanup"] = "FAILED"
                result["file_error"] = err_str[:500]
                log.error("  ✗ Failed to delete: %s", err_str)

        # ── 3. Delete medallion_sync row (clean slate for re-push) ──
        try:
            execute_sql(
                """
                DELETE FROM dbo.medallion_sync
                 WHERE [extract_id] = ?
                   AND [target_workspace_id] = ?
                   AND [b2s_status] = 'INVALIDATED'
                """,
                (eid, tgt_ws_id),
            )
            result["db_cleanup"] = "SYNC_DELETED"
            log.info("  ✓ medallion_sync row deleted")
        except Exception as db_err:
            result["db_cleanup"] = "FAILED"
            result["db_error"] = str(db_err)[:500]
            log.error("  ✗ Failed to delete sync: %s", db_err)

        # ── 4. Log it ──
        log_to_db(
            eid, "INFO", "RECALL_CLEANUP",
            f"Cleaned up push_job_id={pj_id} for {tgt_ws_name}: "
            f"files={result['file_cleanup']}, db={result['db_cleanup']}",
            push_job_id=pj_id,
            function_name="recall_cleanup",
        )

        cleanup_results.append(result)

    # ── 5. Mark signal(s) as COMPLETED ──
    try:
        if sid > 0:
            completed = execute_sql(
                """
                UPDATE dbo.workspace_signal
                   SET [status]          = 'COMPLETED',
                       [acknowledged_at] = COALESCE([acknowledged_at], SYSUTCDATETIME()),
                       [completed_at]    = SYSUTCDATETIME()
                 WHERE [signal_id] = ?
                   AND [status] IN ('PENDING', 'ACKNOWLEDGED')
                """,
                (sid,),
            )
        else:
            completed = execute_sql(
                """
                UPDATE dbo.workspace_signal
                   SET [status]          = 'COMPLETED',
                       [acknowledged_at] = COALESCE([acknowledged_at], SYSUTCDATETIME()),
                       [completed_at]    = SYSUTCDATETIME()
                 WHERE [status] IN ('PENDING', 'ACKNOWLEDGED')
                   AND [signal_type] IN ('RECALL', 'REFILL', 'FULL_RESET')
                """,
            )
        log.info("Marked %d workspace_signal(s) as COMPLETED", completed)
    except Exception as sig_err:
        log.warning("Failed to update signals: %s", sig_err)

    ok = sum(1 for r in cleanup_results if r["file_cleanup"] in ("DELETED", "ALREADY_GONE"))
    log.info("Recall cleanup done: %d/%d succeeded", ok, len(cleanup_results))
    return cleanup_results

print("✓ Processing functions loaded")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 6. Main Processing Logic
# 
# ### 6.1 Main Execution Flow
# _All processing is wrapped in try/except so no extract is ever stuck in PROCESSING._

# CELL ********************

summary = {
    "extract_id":       extract_id,
    "file_name":        file_name,
    "run_mode":         run_mode,
    "status":           "FAILED",       # overwritten on success
    "domain_code":      None,
    "file_count":       0,
    "total_size_bytes": 0,
    "validation":       None,
    "signals":          [],
    "pushes":           [],
    "files":            [],
    "error":            None,
}

if run_mode == "normal":
    # ── NORMAL MODE — full extract processing + multi-workspace push ──
    try:
        # Step 1: Atomically claim the extract (prevents double-trigger)
        rows_affected = execute_sql(
            """
            UPDATE dbo.extract
               SET [status] = 'PROCESSING', [updated_at] = SYSUTCDATETIME()
             WHERE [extract_id] = ?
               AND [status] IN ('NEW', 'TRIGGERED')
            """,
            (extract_id,),
        )
        if rows_affected == 0:
            meta_check = execute_sql(
                "SELECT [status] FROM dbo.extract WHERE [extract_id] = ?",
                (extract_id,),
                fetch="one",
            )
            cur = meta_check[0] if meta_check else "NOT_FOUND"
            msg = (
                f"extract_id={extract_id} not in NEW/TRIGGERED state "
                f"(current={cur}) — skipping to avoid double processing"
            )
            log.warning(msg)
            summary["status"] = "SKIPPED"
            summary["error"]  = msg
            notebookutils.notebook.exit(json.dumps(summary))
        log.info("extract_id=%d → status=PROCESSING", extract_id)

        # Step 2: Load metadata from DB
        metadata    = load_extract_metadata(extract_id)
        domain_code = metadata["domain_code"]
        summary["domain_code"] = domain_code

        # Step 3: Read ZIP from lakehouse shortcut
        zip_bytes = read_zip_from_lakehouse(file_name)

        # Step 3b: Parse manifest from ZIP
        manifest = parse_manifest(zip_bytes)
        summary["manifest"] = {
            "extraction_date": manifest["extraction_date"].isoformat() if manifest["extraction_date"] else None,
            "cycle_id": manifest["cycle_id"],
            "extraction_def": manifest["extraction_def"],
            "package_def": manifest["package_def"],
        }

        # Step 4: Unzip & convert
        folder_name = Path(file_name).stem  # ZIP name without extension
        files_meta       = unzip_and_convert(zip_bytes, extract_id, domain_code, folder_name)
        file_count       = len(files_meta)
        total_size_bytes = sum(f["size_bytes"] for f in files_meta)
        error_files      = [f for f in files_meta if f.get("error")]

        summary["file_count"]       = file_count
        summary["total_size_bytes"] = total_size_bytes
        summary["files"] = [
            {"name": f["file_name"], "size_bytes": f["size_bytes"],
             "row_count": f["row_count"]}
            for f in files_meta
        ]

        del zip_bytes  # free memory

        # Step 5: Update extract with counts & paths
        update_extract_status(
            extract_id, "PROCESSING",
            actual_file_count   = file_count,
            total_size_bytes    = total_size_bytes,
            folder_name         = folder_name,
            staging_folder_path = f"staging/{domain_code}/{extract_id}",
            ready_folder_path   = f"ready/{domain_code}/{extract_id}/{folder_name}",
        )

        # Step 5b: Store manifest fields on extract
        manifest_updates = []
        manifest_params = []
        if manifest["extraction_date"] is not None:
            manifest_updates.append("[extraction_date] = ?")
            manifest_params.append(manifest["extraction_date"])
        if manifest["cycle_id"] is not None:
            manifest_updates.append("[cycle_id] = ?")
            manifest_params.append(manifest["cycle_id"])
        if manifest["extraction_def"] is not None:
            manifest_updates.append("[extraction_def] = ?")
            manifest_params.append(manifest["extraction_def"])
        if manifest["package_def"] is not None:
            manifest_updates.append("[package_def] = ?")
            manifest_params.append(manifest["package_def"])

        if manifest_updates:
            manifest_params.append(extract_id)
            execute_sql(
                f"UPDATE dbo.extract SET {', '.join(manifest_updates)}, "
                f"[updated_at] = SYSUTCDATETIME() WHERE [extract_id] = ?",
                tuple(manifest_params),
            )
            log.info("Stored manifest fields on extract_id=%d", extract_id)

        # Step 5b-2: Check extraction_date against domain cutoff
        if manifest["extraction_date"] is not None:
            cutoff_row = execute_sql(
                "SELECT [extraction_date_cutoff] FROM dbo.domain_config "
                "WHERE [domain_code] = ?",
                (domain_code,),
                fetch="one",
            )
            if cutoff_row and cutoff_row[0] is not None:
                cutoff_dt = cutoff_row[0]
                if manifest["extraction_date"] < cutoff_dt:
                    msg = (
                        f"extraction_date {manifest['extraction_date'].isoformat()} "
                        f"is before cutoff {cutoff_dt.isoformat()} — skipping"
                    )
                    log.info("extract_id=%d: %s", extract_id, msg)
                    update_extract_status(extract_id, "SKIPPED")
                    summary["status"] = "SKIPPED"
                    summary["skip_reason"] = msg
                    notebookutils.notebook.exit(json.dumps(summary))

        # Step 5c: Detect late arrival
        is_late = detect_late_arrival(
            extract_id, domain_code,
            manifest["extraction_def"],
            manifest["extraction_date"],
        )
        summary["is_late_arrival"] = is_late

        # Step 6: Register files in extract_file
        register_extract_files(extract_id, domain_code, files_meta, folder_name)

        # Step 7: Validate
        validation = validate_extract(extract_id, domain_code, file_count)
        summary["validation"] = validation

        if validation["is_valid"]:
            # Happy path: VALIDATED
            update_extract_status(
                extract_id, "VALIDATED",
                is_valid           = True,
                validation_message = validation["message"][:500],
                validated_at       = "SYSUTCDATETIME()",
            )

            # Step 9: Process pending workspace signals
            signals = process_workspace_signals(extract_id)
            summary["signals"] = signals

            # Step 10: Get matching target workspaces
            target_workspaces = get_target_workspaces(
                domain_code   = domain_code,
                instance_code = metadata.get("instance_code"),
                period_type   = metadata.get("period_type"),
                arrived_at    = metadata.get("arrived_at"),
            )

            # Step 11: Push to all matching workspaces
            push_results = push_to_workspaces(
                extract_id, domain_code, target_workspaces,
                file_count, total_size_bytes,
                arrived_at=metadata["arrived_at"],
                source_file_name=file_name,
            )
            summary["pushes"] = push_results
            summary["status"] = "VALIDATED"

        else:
            # Validation failed
            update_extract_status(
                extract_id, "FAILED",
                is_valid           = False,
                validation_message = validation["message"][:500],
                validated_at       = "SYSUTCDATETIME()",
            )
            log_to_db(
                extract_id, "ERROR", "VALIDATION",
                validation["message"],
                function_name="validate_extract",
            )
            summary["status"] = "FAILED"

        # Log any per-file conversion errors (non-fatal)
        for ef in error_files:
            log_to_db(
                extract_id, "WARNING", "CONVERSION",
                f"File {ef['original_name']} failed: {ef.get('error', '?')}",
                function_name="unzip_and_convert",
            )

    except Exception as e:
        # GLOBAL ERROR HANDLER — extract never stuck in PROCESSING
        log.exception("FATAL ERROR extract_id=%d: %s", extract_id, e)
        summary["status"] = "FAILED"
        summary["error"]  = str(e)[:2000]

        try:
            update_extract_status(
                extract_id, "FAILED",
                validation_message=f"Notebook error: {str(e)[:490]}",
            )
            log_to_db(
                extract_id, "ERROR", "NOTEBOOK",
                f"Fatal: {str(e)[:3500]}",
                function_name="main_execution",
            )
        except Exception as db_err:
            log.error("Could not update DB after failure: %s", db_err)

elif run_mode == "test_push":
    # ── TEST_PUSH MODE — test cross-workspace copy (no push_jobs / status changes) ──
    try:
        metadata    = load_extract_metadata(extract_id)
        domain_code = metadata["domain_code"]
        summary["domain_code"] = domain_code

        target_workspaces = get_target_workspaces(
            domain_code   = domain_code,
            instance_code = metadata.get("instance_code"),
            period_type   = metadata.get("period_type"),
            arrived_at    = metadata.get("arrived_at"),
        )

        if not target_workspaces:
            log.warning("No target workspaces matched — nothing to test")
            summary["status"] = "NO_TARGETS"
        else:
            ctx = get_workspace_context()
            src_abfss = (
                f"abfss://{ctx['workspace_id']}@onelake.dfs.fabric.microsoft.com/"
                f"{ctx['lakehouse_id']}/Files/ready/{domain_code}/{extract_id}/"
            )

            test_results = []
            for target in target_workspaces:
                dest = (
                    f"abfss://{target['workspace_id']}"
                    f"@onelake.dfs.fabric.microsoft.com/"
                    f"{target['lakehouse_id']}/Files/"
                    f"_test_cross_ws_push/{domain_code}/{extract_id}/"
                )
                r = {
                    "workspace_id":   target["workspace_id"],
                    "workspace_name": target["workspace_name"],
                    "status":         "FAILED",
                }
                try:
                    start = datetime.now(timezone.utc)
                    notebookutils.fs.cp(src_abfss, dest, recurse=True)
                    elapsed = (datetime.now(timezone.utc) - start).total_seconds()
                    r["status"]  = "SUCCESS"
                    r["seconds"] = round(elapsed, 2)
                    log.info(
                        "Test copy to %s OK (%.2fs)",
                        target["workspace_name"], elapsed,
                    )
                except Exception as cp_err:
                    r["error"] = str(cp_err)[:1000]
                    log.error(
                        "Test copy to %s FAILED: %s",
                        target["workspace_name"], cp_err,
                    )
                test_results.append(r)

            summary["pushes"] = test_results
            ok = sum(1 for r in test_results if r["status"] == "SUCCESS")
            summary["status"] = "TEST_COMPLETE" if ok > 0 else "TEST_FAILED"

    except Exception as e:
        log.exception("TEST_PUSH FAILED: %s", e)
        summary["status"] = "FAILED"
        summary["error"]  = str(e)[:2000]

elif run_mode == "cleanup":
    # ── CLEANUP MODE — remove test data from target workspaces ──
    try:
        metadata    = load_extract_metadata(extract_id)
        domain_code = metadata["domain_code"]
        summary["domain_code"] = domain_code

        target_workspaces = get_target_workspaces(
            domain_code   = domain_code,
            instance_code = metadata.get("instance_code"),
            period_type   = metadata.get("period_type"),
            arrived_at    = metadata.get("arrived_at"),
        )

        cleanup_results = []
        for target in target_workspaces:
            path = (
                f"abfss://{target['workspace_id']}"
                f"@onelake.dfs.fabric.microsoft.com/"
                f"{target['lakehouse_id']}/Files/"
                f"_test_cross_ws_push/{domain_code}/{extract_id}/"
            )
            r = {
                "workspace_id":   target["workspace_id"],
                "workspace_name": target["workspace_name"],
                "status":         "FAILED",
            }
            try:
                notebookutils.fs.rm(path, recurse=True)
                r["status"] = "CLEANED"
                log.info("Cleaned test data from %s", target["workspace_name"])
            except Exception as rm_err:
                r["error"] = str(rm_err)[:1000]
                log.warning(
                    "Cleanup for %s: %s (may already be clean)",
                    target["workspace_name"], rm_err,
                )
            cleanup_results.append(r)

        summary["pushes"] = cleanup_results
        summary["status"] = "CLEANUP_COMPLETE"

    except Exception as e:
        log.exception("CLEANUP FAILED: %s", e)
        summary["status"] = "FAILED"
        summary["error"]  = str(e)[:2000]

elif run_mode == "recall_cleanup":
    # ── RECALL_CLEANUP MODE — delete Bronze files for RECALLED push_jobs ──
    try:
        cleanup_results = recall_cleanup(sid=signal_id)

        if not cleanup_results:
            summary["status"] = "NO_RECALLS"
            log.info("Nothing to clean up")
        else:
            summary["pushes"] = cleanup_results
            ok = sum(
                1 for r in cleanup_results
                if r["file_cleanup"] in ("DELETED", "ALREADY_GONE")
            )
            summary["status"] = (
                "RECALL_CLEANUP_COMPLETE" if ok == len(cleanup_results)
                else "RECALL_CLEANUP_PARTIAL"
            )

    except Exception as e:
        log.exception("RECALL_CLEANUP FAILED: %s", e)
        summary["status"] = "FAILED"
        summary["error"]  = str(e)[:2000]

elif run_mode == "retry_push":
    # ── RETRY_PUSH MODE — re-push to workspaces with RECALLED/FAILED push_jobs ──
    try:
        metadata    = load_extract_metadata(extract_id)
        domain_code = metadata["domain_code"]
        summary["domain_code"] = domain_code

        # Find workspaces that need re-push (no active SUCCESS/PENDING/RUNNING push_job)
        pending = execute_sql(
            """
            SELECT tw.[target_workspace_id]  AS workspace_id,
                   tw.[target_workspace_name] AS workspace_name,
                   tw.[target_lakehouse_id]   AS lakehouse_id,
                   tw.[target_lakehouse_name] AS lakehouse_name
              FROM dbo.target_workspace tw
             WHERE tw.[enabled] = 1
               AND (tw.[domain_filter]      IS NULL OR tw.[domain_filter]      = ?)
               AND (tw.[instance_filter]    IS NULL OR tw.[instance_filter]    = ?)
               AND (tw.[period_type_filter] IS NULL OR tw.[period_type_filter] = ?)
               AND (tw.[arrived_after]      IS NULL OR ? >= tw.[arrived_after])
               AND NOT EXISTS (
                   SELECT 1 FROM dbo.push_job pj
                    WHERE pj.[extract_id] = ?
                      AND pj.[target_workspace_id] = tw.[target_workspace_id]
                      AND pj.[status] IN ('PENDING', 'RUNNING', 'SUCCESS')
               )
            """,
            (
                domain_code,
                metadata.get("instance_code"),
                metadata.get("period_type"),
                metadata.get("arrived_at"),
                extract_id,
            ),
            fetch="all",
        )

        if not pending:
            summary["status"] = "NO_PENDING"
            log.info("No pending re-pushes for extract_id=%d", extract_id)
        else:
            target_workspaces = [
                {
                    "workspace_id":   r[0],
                    "workspace_name": r[1],
                    "lakehouse_id":   r[2],
                    "lakehouse_name": r[3],
                }
                for r in pending
            ]
            file_count       = metadata.get("actual_file_count", 0)
            total_size_bytes = metadata.get("total_size_bytes", 0)

            push_results = push_to_workspaces(
                extract_id, domain_code, target_workspaces,
                file_count, total_size_bytes,
                arrived_at=metadata["arrived_at"],
                source_file_name=metadata.get("source_file_name", ""),
            )
            summary["pushes"] = push_results
            ok = sum(1 for r in push_results if r["status"] == "SUCCESS")
            summary["status"] = "RETRY_COMPLETE" if ok == len(push_results) else "RETRY_PARTIAL"

    except Exception as e:
        log.exception("RETRY_PUSH FAILED: %s", e)
        summary["status"] = "FAILED"
        summary["error"]  = str(e)[:2000]

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# MARKDOWN ********************

# ---
# 
# ## 7. Summary & Completion
# 
# ### 7.1 Summary Output and Notebook Exit
# _Outputs a summary and exits for orchestrator integration. Keep this in its own cell; exit() overwrites output._

# CELL ********************

summary["completed_at"] = datetime.now(timezone.utc).isoformat()

pushes = summary.get("pushes", [])
push_ok = sum(1 for p in pushes if p.get("status") == "SUCCESS")

log.info("=" * 60)
log.info(
    "COMPLETE: extract_id=%d  status=%s  mode=%s  files=%d  size=%s  "
    "pushes=%d/%d ok  signals=%d",
    extract_id,
    summary["status"],
    summary.get("run_mode", "normal"),
    summary.get("file_count", 0),
    f'{summary.get("total_size_bytes", 0):,}',
    push_ok,
    len(pushes),
    len(summary.get("signals", [])),
)
for p in pushes:
    if p.get("status") not in ("SUCCESS", "CLEANED"):
        log.warning(
            "  PUSH FAILED: workspace=%s error=%s",
            p.get("workspace_name", "?"),
            str(p.get("error", "?"))[:200],
        )
log.info("=" * 60)




# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

# Structured JSON exit — capturable by Fabric REST API / orchestrator
# notebookutils.notebook.exit(json.dumps(summary)) --uncomment for live

def print_summary(summary: dict, indent: int = 0):
    """Recursively print all key/value pairs in a readable format."""
    pad = "  " * indent

    for key, value in summary.items():
        if isinstance(value, dict):
            print(f"{pad}{key}:")
            print_summary(value, indent + 1)
        else:
            print(f"{pad}{key}: {value}")

# Usage:
print_summary(summary)


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python"
# META }

# CELL ********************

import time
import requests

def trigger_pipeline(
    workspace_id: str,
    pipeline_id: str,
    pipeline_name: str = "",
    parameters: dict = None,
) -> str | None:
    """Trigger a pipeline with parameters and return the Location URL for polling."""
    token = notebookutils.credentials.getToken("https://api.fabric.microsoft.com")
    url = (
        f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}"
        f"/items/{pipeline_id}/jobs/instances?jobType=Pipeline"
    )
    body = None
    if parameters:
        body = {"executionData": {"parameters": parameters}}

    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
    )
    if resp.status_code in (200, 201, 202):
        location = resp.headers.get("Location", "")
        log.info("Triggered %s → %s (params=%s)", pipeline_name, resp.status_code, parameters)
        return location
    else:
        log.error("Failed to trigger %s: %s %s", pipeline_name, resp.status_code, resp.text[:500])
        return None


def wait_for_pipeline(location_url: str, pipeline_name: str = "", timeout: int = 1800) -> str:
    """Poll until pipeline completes. Returns final status."""
    start = time.time()
    while time.time() - start < timeout:
        token = notebookutils.credentials.getToken("https://api.fabric.microsoft.com")
        resp = requests.get(location_url, headers={"Authorization": f"Bearer {token}"})
        if resp.status_code == 200:
            data = resp.json()
            status = data.get("status", "Unknown")
            if status in ("Completed", "Failed", "Cancelled"):
                log.info("%s finished: %s", pipeline_name, status)
                return status
            log.info("%s status: %s — waiting...", pipeline_name, status)
        time.sleep(30)
    log.error("%s timed out after %ds", pipeline_name, timeout)
    return "Timeout"


# Pipeline parameters
# extraction_date passed to B2S must match the date used to write the bronze path,
# which is derived from arrived_at (not the manifest extraction_date).
arrived_at_dt = metadata.get("arrived_at")
processing_date_str = arrived_at_dt.strftime("%Y-%m-%dT%H:%M:%SZ") if arrived_at_dt else ""

pipeline_params = {
    "source_system": "Orchestrator",
    "executed_by": "Orchestrator",
    "domain_code": summary.get("domain_code", ""),
    "extract_id": str(extract_id),
    "extraction_date": processing_date_str,
}

WS_ID = "3c6bac21-087c-4529-b7cd-939a39925cf2"
B2S_PIPELINE_ID = "d14c7036-4b23-420a-95fa-56929cf4f39e"
S2G_PIPELINE_ID = "d0029504-b1a0-40b0-8d19-6fcc9f7771ff"

# 1. Trigger B2S and wait
b2s_location = trigger_pipeline(WS_ID, B2S_PIPELINE_ID, "B2S", pipeline_params)
if b2s_location:
    b2s_status = wait_for_pipeline(b2s_location, "B2S")

    # 2. Only trigger S2G if B2S succeeded
    if b2s_status == "Completed":
        s2g_location = trigger_pipeline(WS_ID, S2G_PIPELINE_ID, "S2G", pipeline_params)
        if s2g_location:
            wait_for_pipeline(s2g_location, "S2G")
    else:
        log.error("B2S did not complete successfully — skipping S2G")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "jupyter_python",
# META   "frozen": true,
# META   "editable": false
# META }
