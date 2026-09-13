"""
SQL Schema Deployer
===================
Deploys stored procedures and tables from a local .sqlproj directory to a
Fabric SQL Database, and uploads shared queries to the Fabric SQL editor.

fabric-cicd treats SQLDatabase as shell-only (creates the item but does not
push schema).  This module fills that gap:

  1. Schema (tables + stored procedures) → deployed via pyodbc (always)
  2. Shared queries (.sharedqueries/)    → deployed via Fabric updateDefinition
     API which requires a compiled DACPAC.  The DACPAC is built automatically
     using `dotnet build` if the .NET SDK is available.

GO batch separators are handled automatically.
"""

from __future__ import annotations

import base64
import re
import struct
import subprocess
import logging
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
SQL_DATABASE_ITEM_NAME = "northstar_control"

# Shared queries that are destructive — excluded from auto-upload
_SKIP_SHARED_QUERIES = {
    # "01_first_time_setup.sql",          # drops all tables
    # "03_clean_transactional_data.sql",  # deletes all rows
}


# ---------------------------------------------------------------------------
# Fabric API helpers
# ---------------------------------------------------------------------------

def _find_sql_database(token: str, workspace_id: str, display_name: str = SQL_DATABASE_ITEM_NAME) -> Optional[dict]:
    """Find a SQLDatabase item in the workspace by display name."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}"}
    while url:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        for item in data.get("value", []):
            if item.get("type") == "SQLDatabase" and item.get("displayName") == display_name:
                return item
        url = data.get("continuationUri")
    return None


def _get_sql_connection(token: str, workspace_id: str, database_id: str) -> tuple[str, str]:
    """Return (server_fqdn, database_name) for a Fabric SQL Database item."""
    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/sqldatabases/{database_id}"
    resp = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    props = resp.json().get("properties", {})
    server = props.get("serverFqdn") or props.get("connectionString", "")
    database = props.get("databaseName", "")
    if not server or not database:
        raise RuntimeError(f"Could not read SQL connection details: {props}")
    return server, database


# ---------------------------------------------------------------------------
# SQL execution helpers
# ---------------------------------------------------------------------------

def _pyodbc_connect(server: str, database: str, token: str):
    """Open a pyodbc connection using an Azure AD bearer token."""
    import pyodbc  # imported lazily — only needed for SQL deployment

    token_bytes = token.encode("utf-16-le")
    token_struct = struct.pack(f"<I{len(token_bytes)}s", len(token_bytes), token_bytes)

    conn_str = (
        f"DRIVER={{ODBC Driver 18 for SQL Server}};"
        f"SERVER={server},1433;"
        f"DATABASE={database};"
        f"Encrypt=yes;"
        f"TrustServerCertificate=no;"
    )
    return pyodbc.connect(conn_str, attrs_before={1256: token_struct})


def _split_batches(sql: str) -> list[str]:
    """Split a SQL script on GO batch separators."""
    batches = re.split(r"^\s*GO\s*$", sql, flags=re.MULTILINE | re.IGNORECASE)
    return [b.strip() for b in batches if b.strip()]


def _make_idempotent(sql: str) -> str:
    """
    Make a single GO-separated batch idempotent.

    - CREATE PROCEDURE     -> CREATE OR ALTER PROCEDURE
    - CREATE TABLE         -> guarded by IF OBJECT_ID IS NULL
    - CREATE [x] INDEX     -> DROP INDEX IF EXISTS first
    """
    # Stored procedures
    sql = re.sub(
        r"\bCREATE\s+PROCEDURE\b",
        "CREATE OR ALTER PROCEDURE",
        sql,
        flags=re.IGNORECASE,
    )

    # Tables: guard so existing tables are not recreated (avoids data loss)
    if re.search(r"\bCREATE\s+TABLE\b", sql, re.IGNORECASE):
        if "OBJECT_ID" not in sql.upper():
            match = re.search(
                r"\bCREATE\s+TABLE\s+((?:\[?\w+\]?\.)?\[?\w+\]?)",
                sql,
                re.IGNORECASE,
            )
            if match:
                raw = match.group(1).replace("[", "").replace("]", "")
                table_ref = raw if "." in raw else f"dbo.{raw}"
                sql = (
                    f"IF OBJECT_ID(N'{table_ref}', N'U') IS NULL\n"
                    f"BEGIN\n{sql}\nEND"
                )

    # Indexes: drop then re-create so changes to index definitions are applied
    if re.search(r"\bCREATE\s+(?:UNIQUE\s+)?(?:NON)?CLUSTERED\s+INDEX\b", sql, re.IGNORECASE):
        match = re.search(
            r"\bCREATE\s+(?:UNIQUE\s+)?(?:NON)?CLUSTERED\s+INDEX\s+(\[?\w+\]?)\s+ON\s+((?:\[?\w+\]?\.)?\[?\w+\]?)",
            sql,
            re.IGNORECASE,
        )
        if match:
            idx_name = match.group(1)
            table_ref = match.group(2)
            sql = f"DROP INDEX IF EXISTS {idx_name} ON {table_ref};\n{sql}"

    return sql


def _execute_sql_file(conn, file_path: Path, dry_run: bool = False) -> None:
    """Read a .sql file, split on GO, make each batch idempotent, then execute."""
    sql = file_path.read_text(encoding="utf-8")
    # Split on GO FIRST, then make each batch idempotent.
    # Doing it the other way breaks BEGIN...END blocks that span GO separators
    # (e.g. CREATE TABLE followed by index definitions in the same file).
    batches = [_make_idempotent(b) for b in _split_batches(sql)]
    batches = [b for b in batches if b.strip()]

    if not batches:
        return

    if dry_run:
        logger.info("  [dry-run] %s (%d batch(es))", file_path.name, len(batches))
        return

    cursor = conn.cursor()
    try:
        for batch in batches:
            cursor.execute(batch)
        conn.commit()
        logger.info("  \u2714 %s", file_path.name)
    except Exception as exc:
        conn.rollback()
        logger.error("  \u2718 %s \u2014 %s", file_path.name, exc)
        raise
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Shared queries (Fabric SQL editor saved queries)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Shared queries (Fabric SQL editor saved queries)
# ---------------------------------------------------------------------------

def _build_dacpac(sql_dir: Path) -> Optional[Path]:
    """
    Build the .sqlproj to produce a .dacpac using `dotnet build`.
    Runs `dotnet restore` first so packages are always available.
    Returns the path to the built .dacpac, or None if unavailable.
    """
    sqlproj = next(sql_dir.glob("*.sqlproj"), None)
    if not sqlproj:
        return None

    import os, shutil
    local_dotnet = Path(os.environ.get("LOCALAPPDATA", "")) / "dotnet" / "dotnet.exe"
    dotnet_cmd = str(local_dotnet) if local_dotnet.exists() else shutil.which("dotnet")

    if not dotnet_cmd:
        print(
            "  \u26a0 `dotnet` not found \u2014 install the .NET 8 SDK to enable shared query upload.\n"
            "  Run: Invoke-WebRequest https://dot.net/v1/dotnet-install.ps1 -OutFile $env:TEMP\\dotnet-install.ps1\n"
            "       & $env:TEMP\\dotnet-install.ps1 -Channel 8.0 -InstallDir $env:LOCALAPPDATA\\dotnet"
        )
        return None

    def _run(args: list[str], label: str) -> bool:
        try:
            r = subprocess.run(
                args, capture_output=True, text=True, cwd=str(sql_dir), timeout=180
            )
            if r.returncode != 0:
                output = (r.stderr.strip() or r.stdout.strip())[:800]
                print(f"  \u26a0 {label} failed:\n{output}")
                return False
            return True
        except Exception as exc:
            print(f"  \u26a0 {label} error: {exc}")
            return False

    if not _run([dotnet_cmd, "restore", str(sqlproj), "--verbosity", "quiet"], "dotnet restore"):
        return None
    if not _run(
        [dotnet_cmd, "build", str(sqlproj), "--configuration", "Release",
         "--no-restore", "--verbosity", "minimal"],
        "dotnet build",
    ):
        return None

    candidates = sorted(sql_dir.rglob("*.dacpac"))
    if not candidates:
        print("  \u26a0 dotnet build succeeded but no .dacpac found.")
        return None

    dacpac = candidates[0]
    print(f"  Built DACPAC: {dacpac.name}")
    return dacpac


def _deploy_shared_queries(token: str, workspace_id: str, database_id: str, sql_dir: Path) -> None:
    """
    Upload .sharedqueries files to the Fabric SQL Database item definition so
    they appear as saved queries in the Fabric SQL editor.

    Fabric's updateDefinition API for SQLDatabase requires a DACPAC alongside
    the query files.  The DACPAC is built via `dotnet build` (after restore).
    Destructive files (drop/delete scripts) are excluded automatically.
    """
    sharedqueries_dir = sql_dir / ".sharedqueries"
    if not sharedqueries_dir.exists():
        return

    sql_files = sorted(
        f for f in sharedqueries_dir.glob("*.sql")
        if f.name not in _SKIP_SHARED_QUERIES
    )
    if not sql_files:
        return

    print(f"\n  Uploading {len(sql_files)} shared query file(s) to Fabric SQL editor...")

    dacpac = _build_dacpac(sql_dir)
    if not dacpac:
        print("  Skipping shared query upload \u2014 DACPAC build failed (see above).")
        return

    parts: list[dict] = []

    # DACPAC — required by Fabric's updateDefinition for SQLDatabase items
    parts.append({
        "path": dacpac.name,
        "payload": base64.b64encode(dacpac.read_bytes()).decode(),
        "payloadType": "InlineBase64",
    })

    # .platform — tells Fabric the item type
    platform_file = sql_dir / ".platform"
    if platform_file.exists():
        parts.append({
            "path": ".platform",
            "payload": base64.b64encode(platform_file.read_bytes()).decode(),
            "payloadType": "InlineBase64",
        })

    # Shared query files
    for sql_file in sql_files:
        parts.append({
            "path": f".sharedqueries/{sql_file.name}",
            "payload": base64.b64encode(sql_file.read_bytes()).decode(),
            "payloadType": "InlineBase64",
        })

    url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items/{database_id}/updateDefinition"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"definition": {"parts": parts}},
        timeout=60,
    )

    if resp.status_code == 200:
        for f in sql_files:
            print(f"  \u2714 {f.name}")
        return

    if resp.status_code == 202:
        # Long-running operation — poll Location until complete
        import time
        location = resp.headers.get("Location") or resp.headers.get("location", "")
        if not location:
            print("  \u26a0 Upload accepted (202) but no Location header to poll.")
            return
        for _ in range(30):
            time.sleep(10)
            poll = requests.get(location, headers={"Authorization": f"Bearer {token}"}, timeout=30)
            if poll.status_code == 200:
                status = poll.json().get("status", "").lower()
                if status in ("succeeded", "completed", ""):
                    for f in sql_files:
                        print(f"  \u2714 {f.name}")
                    return
                if status in ("failed", "cancelled"):
                    print(f"  \u26a0 Shared query upload failed: {poll.json().get('error', {})}")
                    return
        print("  \u26a0 Shared query upload timed out.")
        return

    print(
        f"  \u26a0 Shared query upload returned HTTP {resp.status_code}: {resp.text[:300]}\n"
        "  Shared queries were NOT updated (schema deploy succeeded)."
    )


# ---------------------------------------------------------------------------
# Main deploy function
# ---------------------------------------------------------------------------

def deploy_sql_schema(
    workspace_id: str,
    token_credential,
    sql_dir: Path,
    dry_run: bool = False,
) -> None:
    """
    Deploy all tables and stored procedures from sql_dir to the Fabric SQL
    Database in the given workspace.

    Args:
        workspace_id:      Fabric workspace ID containing the SQL Database.
        token_credential:  An azure-identity credential (e.g. InteractiveBrowserCredential).
        sql_dir:           Root of the .sqlproj directory (e.g. northstar-control/northstar_control.SQLDatabase).
        dry_run:           Print what would be executed without connecting.
    """
    print("\nDeploying SQL schema...")

    # Acquire tokens
    fabric_token = token_credential.get_token("https://api.fabric.microsoft.com/.default").token
    sql_token = token_credential.get_token("https://database.windows.net/.default").token

    # Locate the SQLDatabase item
    db_item = _find_sql_database(fabric_token, workspace_id)
    if not db_item:
        raise RuntimeError(
            f"SQLDatabase '{SQL_DATABASE_ITEM_NAME}' not found in workspace {workspace_id}"
        )
    database_id = db_item["id"]
    print(f"  Found SQL Database: {db_item['displayName']} ({database_id})")

    # Get connection details
    server, database = _get_sql_connection(fabric_token, workspace_id, database_id)
    print(f"  Server:   {server}")
    print(f"  Database: {database}")

    # Collect .sql files in deployment order: Tables first (dependency order),
    # then StoredProcedures.  Tables must be ordered so that referenced tables
    # are created before the tables that hold foreign keys to them.
    # Alphabetical order does NOT work here (e.g. job_log < push_job but
    # job_log.fk_job_log_push_job references push_job).
    TABLE_DEPLOY_ORDER = [
        "domain_config",      # no FK deps
        "poller_source",      # no FK deps
        "poller_state",       # no FK deps
        "target_workspace",   # no FK deps
        "extract",            # → domain_config
        "extract_file",       # → extract
        "push_job",           # → extract
        "job_log",            # → extract, push_job
        "medallion_sync",     # → extract
        "workspace_signal",   # → target_workspace
    ]
    tables_dir = sql_dir / "dbo" / "Tables"
    sql_files: list[Path] = []
    if tables_dir.exists():
        known = {name: tables_dir / f"{name}.sql" for name in TABLE_DEPLOY_ORDER}
        for name in TABLE_DEPLOY_ORDER:
            p = known[name]
            if p.exists():
                sql_files.append(p)
        # Append any tables not in the explicit list (alphabetically) so new
        # tables are still deployed even if they haven't been added to the order yet
        ordered_names = set(TABLE_DEPLOY_ORDER)
        for p in sorted(tables_dir.glob("*.sql")):
            if p.stem not in ordered_names:
                sql_files.append(p)
    procs_dir = sql_dir / "dbo" / "StoredProcedures"
    if procs_dir.exists():
        sql_files.extend(sorted(procs_dir.glob("*.sql")))

    # Triggers must come after their target tables
    triggers_dir = sql_dir / "dbo" / "Triggers"
    if triggers_dir.exists():
        sql_files.extend(sorted(triggers_dir.glob("*.sql")))

    if not sql_files:
        print("  No .sql files found — nothing to deploy.")
        return

    print(f"  Deploying {len(sql_files)} object(s)...")

    if dry_run:
        for f in sql_files:
            print(f"  [dry-run] {f.relative_to(sql_dir)}")
        return

    conn = _pyodbc_connect(server, database, sql_token)
    try:
        for sql_file in sql_files:
            _execute_sql_file(conn, sql_file)

        # Backfill any existing rows with NULL folder_name (idempotent).
        # Runs after every deploy — no-op for new workspaces and already-populated rows.
        cursor = conn.cursor()
        try:
            cursor.execute("""
                UPDATE [dbo].[extract]
                SET    [folder_name] = LEFT(
                           [source_file_name],
                           LEN([source_file_name]) - CHARINDEX('.', REVERSE([source_file_name]))
                       ),
                       [updated_at]  = SYSUTCDATETIME()
                WHERE  ([folder_name] IS NULL OR [folder_name] = '')
                  AND  [source_file_name] IS NOT NULL
                  AND  CHARINDEX('.', [source_file_name]) > 0
            """)
            conn.commit()
            if cursor.rowcount > 0:
                print(f"  \u2714 Backfilled {cursor.rowcount} row(s) with NULL folder_name")
        except Exception as exc:
            conn.rollback()
            print(f"  \u26a0 folder_name backfill failed: {exc}")
        finally:
            cursor.close()
    finally:
        conn.close()

    print("✔ SQL schema deploy complete")

    # Upload shared queries to the Fabric SQL editor (non-fatal if it fails)
    _deploy_shared_queries(fabric_token, workspace_id, database_id, sql_dir)
