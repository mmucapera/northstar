"""Auto-populate target_workspace seed SQL with live Fabric workspace item IDs.

After deploying Insights content (notebooks, pipelines, lakehouse) to a workspace,
run this script to resolve the Fabric item IDs and update the northstar-control SQL seed file
(01_first_time_setup.sql) so target_workspace is populated automatically.

Usage:
    uv run python deploy/generate_seed_sql.py
"""

from __future__ import annotations

import re
import shutil
from collections import OrderedDict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
import yaml

from runtime_target_builder import (
    BASE_URL,
    CUSTOMERS,
    TARGETS_FILE,
    WORKSPACE_ROOT,
    _get_token,
    _slugify_customer_name,
)

# Defined here directly so this module is self-contained (also exported by
# runtime_target_builder, but that import is optional).
SCOPE = "https://api.fabric.microsoft.com/.default"

SQL_FILE = (
    WORKSPACE_ROOT
    / "northstar-control"
    / "northstar_control.SQLDatabase"
    / ".sharedqueries"
    / "01_first_time_setup.sql"
)

NOTEBOOK_FILE = (
    WORKSPACE_ROOT
    / "northstar-control"
    / "extract_processor_notebook.Notebook"
    / "notebook-content.py"
)

# The northstar-control/ directory is the version-controlled template. Per-customer output
# folders (ORC_output_{slug}_{env}/) are generated from it and are gitignored.
ORC_TEMPLATE_DIR = WORKSPACE_ROOT / "northstar-control"


def _initialize_orc_output(orc_output_dir: Path) -> None:
    """Sync the northstar-control template into a per-customer output directory.

    Copies all files from northstar-control/ (notebooks, lakehouse definition, SP/table SQL)
    without overwriting any already-generated customer-specific seed SQL so that
    a second call doesn't wipe connection strings from a previous generate_seed run.
    """
    seed_rel = Path("northstar_control.SQLDatabase") / ".sharedqueries" / "01_first_time_setup.sql"
    existing_seed: str | None = None
    if (orc_output_dir / seed_rel).exists():
        existing_seed = (orc_output_dir / seed_rel).read_text(encoding="utf-8")

    shutil.copytree(
        str(ORC_TEMPLATE_DIR),
        str(orc_output_dir),
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns("ORC_output_*"),
    )

    # Restore customer-specific seed SQL that was overwritten by the copy
    if existing_seed is not None:
        (orc_output_dir / seed_rel).write_text(existing_seed, encoding="utf-8")

B2S_PIPELINE_NAME = "PL_MASTER_B2S_ORCH"
S2G_PIPELINE_NAME = "PL_MASTER_S2G_ORCH"
DEFAULT_LAKEHOUSE_NAME = "lkh_001"
SQL_DATABASE_ITEM_NAME = "northstar_control"


# ---------------------------------------------------------------------------
# Fabric API helpers
# ---------------------------------------------------------------------------


def _list_workspace_items(token: str, workspace_id: str) -> List[dict]:
    """List all items in a Fabric workspace."""
    items: List[dict] = []
    url = f"{BASE_URL}/workspaces/{workspace_id}/items"
    headers = {"Authorization": f"Bearer {token}"}

    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        data = response.json()
        items.extend(data.get("value", []))
        url = data.get("continuationUri")

    return items


def _get_sql_database_details(token: str, workspace_id: str, database_id: str) -> dict:
    """Get SQL Database connection details (serverFqdn, databaseName)."""
    url = f"{BASE_URL}/workspaces/{workspace_id}/sqldatabases/{database_id}"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def _find_item(
    items: List[dict], display_name: str, item_type: str
) -> Optional[dict]:
    """Find an item by display name and type."""
    for item in items:
        if item.get("displayName") == display_name and item.get("type") == item_type:
            return item
    return None


def _find_items_by_type(items: List[dict], item_type: str) -> List[dict]:
    """Return all items of a given type."""
    return [i for i in items if i.get("type") == item_type]


# ---------------------------------------------------------------------------
# Target helpers
# ---------------------------------------------------------------------------


def _load_insights_targets() -> Dict[str, dict]:
    """Load insights workspace targets (those that deploy pipelines)."""
    with open(TARGETS_FILE) as f:
        config = yaml.safe_load(f)

    targets = config.get("targets", {})
    insights: Dict[str, dict] = {}
    for name, target in targets.items():
        item_types = target.get("item_types", [])
        if "DataPipeline" in item_types:
            insights[name] = target

    return insights


def _find_orch_target(customer_code: str, environment: str) -> Optional[dict]:
    """Find the northstar-control workspace target for the same customer and environment."""
    with open(TARGETS_FILE) as f:
        config = yaml.safe_load(f)

    targets = config.get("targets", {})
    # Environment is like "DEV_C0040_INSIGHTS" -> want "DEV_C0040_ORCH"
    env_prefix = environment.rsplit("_", 1)[0]  # "DEV_C0040"
    orch_env = f"{env_prefix}_ORCH"

    for name, target in targets.items():
        if target.get("environment", "") == orch_env:
            return target

    # Fallback: match by customer code and "orch" in repository_directory
    for name, target in targets.items():
        target_env = target.get("environment", "")
        if customer_code.upper() in target_env.upper() and "ORCH" in target_env.upper():
            # Match environment tier (DEV/ACC/PRD)
            tier = environment.split("_")[0]
            if target_env.startswith(tier):
                return target

    return None


def _customer_code_from_environment(environment: str) -> str:
    """Extract customer code from environment key (e.g. DEV_C0040_INSIGHTS -> C0040)."""
    match = re.search(r"(C\d+)", environment, re.IGNORECASE)
    return match.group(1).upper() if match else ""


def _customer_name_from_code(customer_code: str) -> str:
    """Look up customer name from the CUSTOMERS list."""
    code_lower = customer_code.lower()
    for cust in CUSTOMERS:
        if cust["customerCode"].lower() == code_lower:
            return cust["customerName"]
    return ""


# ---------------------------------------------------------------------------
# Interactive selection
# ---------------------------------------------------------------------------

ENVIRONMENT_ORDER = {
    "dev": 1,
    "acc": 2,
    "prd": 3,
    "test": 4,
    "uat": 5,
}


def _environment_rank(target: dict) -> int:
    environment = target.get("environment", "")
    env_code = environment.split("_", 1)[0].lower() if environment else ""
    return ENVIRONMENT_ORDER.get(env_code, 99)


def _format_table(rows: list[list[str] | None], headers: list[str]) -> list[str]:
    widths = [len(header) for header in headers]
    for row in rows:
        if row is None:
            continue
        for idx, value in enumerate(row):
            widths[idx] = max(widths[idx], len(value))

    header_line = "  " + " | ".join(header.ljust(widths[idx]) for idx, header in enumerate(headers))
    separator = "  " + "-+-".join("-" * widths[idx] for idx in range(len(headers)))
    lines = [header_line, separator]
    for row in rows:
        if row is None:
            lines.append("")
            continue
        lines.append("  " + " | ".join(value.ljust(widths[idx]) for idx, value in enumerate(row)))
    return lines


def _render_insights_targets(targets: Dict[str, dict]) -> list[str]:
    """Render insights targets as a grouped, sorted table. Returns ordered names."""
    ordered_names: list[str] = []

    # Extract customer name from description "(CustomerName)" pattern
    def _extract_customer(target: dict) -> str:
        desc = target.get("description", "")
        match = re.search(r"\(([^)]+)\)", desc)
        return match.group(1) if match else "Unknown"

    # Extract workspace name from description after " - "
    def _extract_workspace(target: dict) -> str:
        desc = target.get("description", "")
        parts = desc.split(" - ", 1)
        return parts[1] if len(parts) > 1 else ""

    # Group by customer
    grouped: OrderedDict[str, list[tuple[str, dict]]] = OrderedDict()
    for name, target in targets.items():
        customer = _extract_customer(target)
        if customer not in grouped:
            grouped[customer] = []
        grouped[customer].append((name, target))

    print("\nAvailable INSIGHTS workspace targets:\n")
    index = 1

    # Sort groups alphabetically by customer
    sorted_groups = sorted(grouped.items(), key=lambda item: item[0].lower())

    rows: list[list[str] | None] = []
    previous_customer = ""
    for customer, entries in sorted_groups:
        sorted_entries = sorted(
            entries,
            key=lambda item: (
                _environment_rank(item[1]),
                _extract_workspace(item[1]).lower(),
            ),
        )

        if previous_customer and customer != previous_customer:
            rows.append(None)

        for name, target in sorted_entries:
            ordered_names.append(name)
            rows.append(
                [
                    str(index),
                    name,
                    customer,
                    target.get("environment", ""),
                    _extract_workspace(target),
                ]
            )
            index += 1
        previous_customer = customer

    for line in _format_table(rows, ["#", "Target", "Customer", "Environment", "Workspace"]):
        print(line)
    print()

    return ordered_names


def _pick_insights_target(targets: Dict[str, dict]) -> Tuple[str, dict]:
    """Let the user pick from available insights targets."""
    names = _render_insights_targets(targets)

    while True:
        raw = input("\nEnter target number (or 'q' to quit): ").strip()
        if raw.lower() in {"q", "quit", "exit"}:
            raise SystemExit(0)
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(names):
                return names[choice - 1], targets[names[choice - 1]]
        print("Invalid selection. Enter a valid number from the list.")


def _pick_item_interactively(
    items: List[dict], item_type: str, purpose: str
) -> dict:
    """Let the user pick an item when auto-detection fails."""
    candidates = _find_items_by_type(items, item_type)
    if not candidates:
        print(f"\n  No {item_type} items found in workspace!")
        raise SystemExit(1)

    print(f"\n  Multiple {item_type} items found. Select {purpose}:\n")
    for idx, item in enumerate(candidates, 1):
        print(f"    {idx}. {item['displayName']}  ({item['id']})")

    while True:
        raw = input(f"\n  Enter number for {purpose}: ").strip()
        if raw.isdigit():
            choice = int(raw)
            if 1 <= choice <= len(candidates):
                return candidates[choice - 1]
        print("  Invalid selection.")


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------


def _generate_insert_sql(
    workspace_id: str,
    workspace_name: str,
    lakehouse_id: str,
    lakehouse_name: str,
    b2s_pipeline_id: str,
    s2g_pipeline_id: str,
) -> str:
    return (
        "INSERT INTO [dbo].[target_workspace] (\n"
        "    [target_workspace_id],\n"
        "    [target_workspace_name],\n"
        "    [target_lakehouse_id],\n"
        "    [target_lakehouse_name],\n"
        "    [enabled],\n"
        "    [domain_filter],\n"
        "    [instance_filter],\n"
        "    [period_type_filter],\n"
        "    [arrived_after],\n"
        "    [b2s_pipeline_id],\n"
        "    [s2g_pipeline_id]\n"
        ")\n"
        "VALUES (\n"
        f"    '{workspace_id}',                  -- target_workspace_id (from Fabric)\n"
        f"    '{workspace_name}',                  -- target_workspace_name\n"
        f"    '{lakehouse_id}',                -- target_lakehouse_id (from Fabric)\n"
        f"    '{lakehouse_name}',                         -- target_lakehouse_name\n"
        "    1,                                 -- enabled\n"
        "    NULL,                              -- domain_filter (NULL = all domains, e.g. 'DP')\n"
        "    NULL,                              -- instance_filter (NULL = all instances, e.g. 'CUSTOMER0')\n"
        "    NULL,                              -- period_type_filter (NULL = all period types, e.g. 'daily')\n"
        "    NULL,                              -- arrived_after (NULL = no arrival cutoff, e.g. '2026-01-01')\n"
        f"    '{b2s_pipeline_id}',             -- b2s_pipeline_id (Fabric pipeline)\n"
        f"    '{s2g_pipeline_id}'              -- s2g_pipeline_id (Fabric pipeline)\n"
        ");"
    )


def _generate_poller_source_sql(
    customer_prefix: str,
    customer_label: str,
    storage_account: str,
    sas_token_placeholder: str = "${INS_ORCH_ADLS_SAS_TOKEN_01}",
) -> str:
    """Generate the poller_source seed SQL block.

    Unified poller: handles all three DP/SP/FCT filename formats.
    """
    combined_pattern = (
        r"^(?:(?:\d{8}_\d{6}_)?"
        r"(?P<domain_code>FCT|SP|DP)"
        r"(?:_FinishedZip|_Full)?_)"
        r"(?P<instance_code>[^_]+)_(?P<report_name>.+)\.zip$"
    )

    sql = (
        "BEGIN TRAN;\n"
        "\n"
        "-- 1) Disable legacy sources\n"
        "UPDATE dbo.poller_source\n"
        "SET enabled = 0, updated_at = SYSUTCDATETIME()\n"
        f"WHERE source_id IN ("
        f"'{customer_prefix}-adls-dev', '{customer_prefix}-adls-finishedzip', "
        f"'{customer_prefix}-adls-full', '{customer_prefix}-adls-dp-generic', "
        f"'{customer_prefix}-adls-fct', '{customer_prefix}-adls-sp', '{customer_prefix}-adls-dp'"
        f");\n"
        "\n"
        f"-- 2) Single unified poller: handles FCT (date-prefixed), SP, and DP formats\n"
        f"IF EXISTS (SELECT 1 FROM dbo.poller_source WHERE source_id = '{customer_prefix}-adls')\n"
        "BEGIN\n"
        "    UPDATE dbo.poller_source\n"
        "    SET\n"
        f"        label = '{customer_label} ADLS',\n"
        f"        storage_account = '{storage_account}',\n"
        "        container = 'outbound',\n"
        "        folder_path = '',\n"
        f"        sas_token = '{sas_token_placeholder}',\n"
        "        poll_interval_seconds = 10,\n"
        "        enabled = 1,\n"
        "        filename_extension = '.zip',\n"
        "        filename_must_contain = '',\n"
        f"        filename_pattern = '{combined_pattern}',\n"
        "        source_code = 'ADLS_POLLER',\n"
        "        source_file_format = 'zip',\n"
        "        domain_code_map = '{\"FCT\":\"DP\",\"SP\":\"SP\",\"DP\":\"DP\"}',\n"
        "        updated_at = SYSUTCDATETIME()\n"
        f"    WHERE source_id = '{customer_prefix}-adls';\n"
        "END\n"
        "ELSE\n"
        "BEGIN\n"
        "    INSERT INTO dbo.poller_source\n"
        "    (\n"
        "        source_id, label, storage_account, container, folder_path, sas_token,\n"
        "        poll_interval_seconds, enabled,\n"
        "        filename_extension, filename_must_contain, filename_pattern,\n"
        "        source_code, source_file_format, domain_code_map\n"
        "    )\n"
        "    VALUES\n"
        "    (\n"
        f"        '{customer_prefix}-adls',\n"
        f"        '{customer_label} ADLS',\n"
        f"        '{storage_account}',\n"
        "        'outbound',\n"
        "        '',\n"
        f"        '{sas_token_placeholder}',\n"
        "        10, 1,\n"
        "        '.zip',\n"
        "        '',\n"
        f"        '{combined_pattern}',\n"
        "        'ADLS_POLLER',\n"
        "        'zip',\n"
        "        '{\"FCT\":\"DP\",\"SP\":\"SP\",\"DP\":\"DP\"}'\n"
        "    );\n"
        "END;\n"
        "\n"
        "COMMIT;\n"
        "GO"
    )

    return sql


def _generate_register_extract_sp_sql() -> str:
    """Generate register_extract SP with domain code remapping (FCT->DP, OPR->SP)."""
    return (
        "CREATE OR ALTER PROCEDURE [dbo].[register_extract]\n"
        "    @folder_path        NVARCHAR(500),\n"
        "    @domain_code        NVARCHAR(20),\n"
        "    @source_code        NVARCHAR(50),\n"
        "    @folder_name        NVARCHAR(200),\n"
        "    @period_year        INT,\n"
        "    @period_month       INT,\n"
        "    @period_day         INT = NULL,\n"
        "    @period_label       NVARCHAR(50) = NULL,\n"
        "    @file_count         INT = NULL,\n"
        "    @total_size_bytes   BIGINT = NULL,\n"
        "    @source_file_name   NVARCHAR(500) = NULL,\n"
        "    @source_file_format NVARCHAR(10) = NULL,\n"
        "    @instance_code      NVARCHAR(50) = NULL,\n"
        "    @report_name        NVARCHAR(100) = NULL,\n"
        "    @extract_id         INT OUTPUT\n"
        "AS\n"
        "BEGIN\n"
        "    SET NOCOUNT ON;\n"
        "    BEGIN TRY\n"
        "        BEGIN TRANSACTION;\n"
        "\n"
        "        -- Remap alias domain codes to their canonical equivalents\n"
        "        -- (mirrors domain_code_map in poller_source; keeps DB consistent\n"
        "        --  even if the poller sends the raw filename token)\n"
        "        SET @domain_code = CASE @domain_code\n"
        "            WHEN 'FCT' THEN 'DP'\n"
        "            WHEN 'OPR' THEN 'SP'\n"
        "            ELSE @domain_code\n"
        "        END;\n"
        "\n"
        "        -- Derive folder_name from source_file_name when caller passes NULL or empty\n"
        "        -- (e.g. files dropped at container root with no subfolder)\n"
        "        IF (@folder_name IS NULL OR @folder_name = '') AND @source_file_name IS NOT NULL\n"
        "        BEGIN\n"
        "            SET @folder_name = CASE\n"
        "                WHEN CHARINDEX('.', @source_file_name) > 0\n"
        "                    THEN LEFT(@source_file_name, LEN(@source_file_name) - CHARINDEX('.', REVERSE(@source_file_name)))\n"
        "                ELSE @source_file_name\n"
        "            END;\n"
        "        END\n"
        "\n"
        "        -- Idempotency: if an extract with this source_file_name already exists, return it\n"
        "        IF @source_file_name IS NOT NULL\n"
        "        BEGIN\n"
        "            SELECT @extract_id = [extract_id]\n"
        "            FROM [dbo].[extract]\n"
        "            WHERE [source_file_name] = @source_file_name;\n"
        "\n"
        "            IF @extract_id IS NOT NULL\n"
        "            BEGIN\n"
        "                COMMIT TRANSACTION;\n"
        "                RETURN;\n"
        "            END\n"
        "        END\n"
        "\n"
        "        -- Find existing latest extract for same period\n"
        "        DECLARE @old_extract_id INT;\n"
        "        SELECT TOP 1 @old_extract_id = [extract_id]\n"
        "        FROM [dbo].[extract]\n"
        "        WHERE [domain_code] = @domain_code\n"
        "          AND [period_year] = @period_year\n"
        "          AND [period_month] = @period_month\n"
        "          AND [is_latest_for_period] = 1;\n"
        "\n"
        "        -- Insert new extract\n"
        "        INSERT INTO [dbo].[extract] (\n"
        "            [domain_code], [source_code], [folder_path], [folder_name],\n"
        "            [period_year], [period_month], [period_day], [period_label],\n"
        "            [actual_file_count], [total_size_bytes],\n"
        "            [source_file_name], [source_file_format], [instance_code], [report_name],\n"
        "            [status], [is_latest_for_period], [has_duplicate_period]\n"
        "        )\n"
        "        VALUES (\n"
        "            @domain_code, @source_code, @folder_path, @folder_name,\n"
        "            @period_year, @period_month, @period_day,\n"
        "            COALESCE(@period_label, CONCAT(@period_year, '-', RIGHT('0' + CAST(@period_month AS VARCHAR(2)), 2))),\n"
        "            @file_count, @total_size_bytes,\n"
        "            @source_file_name, @source_file_format, @instance_code, @report_name,\n"
        "            'NEW', 1,\n"
        "            CASE WHEN @old_extract_id IS NOT NULL THEN 1 ELSE 0 END\n"
        "        );\n"
        "\n"
        "        SET @extract_id = SCOPE_IDENTITY();\n"
        "\n"
        "        -- Supersede old extract if exists\n"
        "        IF @old_extract_id IS NOT NULL\n"
        "        BEGIN\n"
        "            UPDATE [dbo].[extract]\n"
        "            SET [is_latest_for_period] = 0,\n"
        "                [superseded_by_id] = @extract_id,\n"
        "                [has_duplicate_period] = 1,\n"
        "                [updated_at] = SYSUTCDATETIME()\n"
        "            WHERE [extract_id] = @old_extract_id;\n"
        "        END\n"
        "\n"
        "        COMMIT TRANSACTION;\n"
        "    END TRY\n"
        "    BEGIN CATCH\n"
        "        IF @@TRANCOUNT > 0 ROLLBACK TRANSACTION;\n"
        "        THROW;\n"
        "    END CATCH\n"
        "END;"
    )


def _update_sql_file(
    insert_sql: str,
    poller_sql: str | None = None,
    sp_sql: str | None = None,
    *,
    target_sql_file: Path | None = None,
) -> None:
    """Replace the target_workspace, poller_source, and register_extract blocks in the SQL seed file."""
    sql_path = target_sql_file or SQL_FILE
    content = sql_path.read_text(encoding="utf-8")

    # --- Update target_workspace ---
    pattern = re.compile(
        r"(-- -+\n-- Seed: target_workspace\n-- -+\n\n)"
        r"INSERT INTO \[dbo\]\.\[target_workspace\].*?\);",
        re.DOTALL,
    )

    match = pattern.search(content)
    if match:
        replacement = match.group(1) + insert_sql
        content = content[: match.start()] + replacement + content[match.end() :]
        print(f"\n  Updated target_workspace seed")
    else:
        print(f"\n  Could not find target_workspace INSERT block in SQL file.")
        print("  Generated SQL (copy manually):\n")
        print(insert_sql)

    # --- Update poller_source ---
    # Matches from the section header through the BEGIN TRAN...COMMIT;GO block
    # up to the closing PRINT '' banner.
    if poller_sql:
        poller_pattern = re.compile(
            r"(-- -+\n-- Seed: poller_source[^\n]*\n-- -+\n)"
            r"BEGIN TRAN;.+?(?=\n\nPRINT '')",
            re.DOTALL,
        )

        poller_match = poller_pattern.search(content)
        if poller_match:
            replacement = poller_match.group(1) + poller_sql
            content = content[: poller_match.start()] + replacement + content[poller_match.end() :]
            print(f"  Updated poller_source seed")
        else:
            print(f"\n  Could not find poller_source block in SQL file.")
            print("  Generated SQL (copy manually):\n")
            print(poller_sql)

    # --- Update register_extract SP ---
    if sp_sql:
        sp_pattern = re.compile(
            r"CREATE OR ALTER PROCEDURE \[dbo\]\.\[register_extract\].*?\nEND;",
            re.DOTALL,
        )
        sp_match = sp_pattern.search(content)
        if sp_match:
            content = content[: sp_match.start()] + sp_sql + content[sp_match.end() :]
            print(f"  Updated register_extract SP")
        else:
            print(f"\n  Could not find register_extract SP in SQL file.")
            print("  Generated SQL (copy manually):\n")
            print(sp_sql)

    sql_path.write_text(content, encoding="utf-8")
    print(f"\n  Written to {sql_path.relative_to(WORKSPACE_ROOT)}")


def _update_notebook_file(
    workspace_id: str,
    b2s_pipeline_id: str,
    s2g_pipeline_id: str,
    sql_server: str | None = None,
    sql_database: str | None = None,
    *,
    target_notebook_file: Path | None = None,
) -> None:
    """Update the extract_processor notebook with resolved IDs."""
    nb_path = target_notebook_file or NOTEBOOK_FILE
    content = nb_path.read_text(encoding="utf-8")

    # --- Update WS_ID, B2S_PIPELINE_ID, S2G_PIPELINE_ID ---
    content = re.sub(
        r'^WS_ID = ".*"',
        f'WS_ID = "{workspace_id}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r'^B2S_PIPELINE_ID = ".*"',
        f'B2S_PIPELINE_ID = "{b2s_pipeline_id}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )
    content = re.sub(
        r'^S2G_PIPELINE_ID = ".*"',
        f'S2G_PIPELINE_ID = "{s2g_pipeline_id}"',
        content,
        count=1,
        flags=re.MULTILINE,
    )

    # --- Update SQL connection fallbacks ---
    if sql_server:
        content = re.sub(
            r'^FALLBACK_SQL_SERVER = ".*"',
            f'FALLBACK_SQL_SERVER = "{sql_server}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )
    if sql_database:
        content = re.sub(
            r'^FALLBACK_SQL_DATABASE = ".*"',
            f'FALLBACK_SQL_DATABASE = "{sql_database}"',
            content,
            count=1,
            flags=re.MULTILINE,
        )

    nb_path.write_text(content, encoding="utf-8")
    print(f"  Updated {nb_path.relative_to(WORKSPACE_ROOT)}")


# ---------------------------------------------------------------------------
# Non-interactive API (used by Streamlit deploy UI)
# ---------------------------------------------------------------------------


def generate_seed_for_target(
    insights_target: dict,
    orch_target: dict | None,
    credential,
    *,
    customer_prefix: str,
    customer_label: str,
    storage_account: str,
) -> dict:
    """Generate seed SQL and update the notebook for a customer workspace pair.

    Non-interactive version of main() for use by the Streamlit deploy UI.
    Writes files into the per-customer northstar-control output directory and returns a summary.
    """
    workspace_id = insights_target["workspace_id"]
    environment = insights_target.get("environment", "")
    customer_code = _customer_code_from_environment(environment)

    # Determine the northstar-control output directory from the orch_target
    if orch_target:
        repo_dir = orch_target.get("repository_directory", "northstar-control")
    else:
        repo_dir = "northstar-control"
    orc_output_dir = (
        WORKSPACE_ROOT / "northstar-control" / repo_dir
        if repo_dir.startswith("ORC_output_")
        else WORKSPACE_ROOT / repo_dir
    )

    _initialize_orc_output(orc_output_dir)

    target_sql_file = (
        orc_output_dir / "northstar_control.SQLDatabase" / ".sharedqueries" / "01_first_time_setup.sql"
    )
    target_notebook_file = (
        orc_output_dir / "extract_processor_notebook.Notebook" / "notebook-content.py"
    )

    token = credential.get_token(SCOPE).token
    items = _list_workspace_items(token, workspace_id)

    # Resolve lakehouse
    lakehouse = _find_item(items, DEFAULT_LAKEHOUSE_NAME, "Lakehouse")
    if not lakehouse:
        lakehouses = _find_items_by_type(items, "Lakehouse")
        if not lakehouses:
            raise ValueError("No Lakehouse found in INSIGHTS workspace")
        lakehouse = lakehouses[0]

    # Resolve pipelines
    b2s_pipeline = _find_item(items, B2S_PIPELINE_NAME, "DataPipeline")
    if not b2s_pipeline:
        candidates = [p for p in _find_items_by_type(items, "DataPipeline") if "B2S" in p.get("displayName", "")]
        if not candidates:
            raise ValueError(f"Pipeline '{B2S_PIPELINE_NAME}' not found in workspace")
        b2s_pipeline = candidates[0]

    s2g_pipeline = _find_item(items, S2G_PIPELINE_NAME, "DataPipeline")
    if not s2g_pipeline:
        candidates = [p for p in _find_items_by_type(items, "DataPipeline") if "S2G" in p.get("displayName", "")]
        if not candidates:
            raise ValueError(f"Pipeline '{S2G_PIPELINE_NAME}' not found in workspace")
        s2g_pipeline = candidates[0]

    # Resolve northstar-control SQL Database connection details
    sql_server: str | None = None
    sql_database: str | None = None
    if orch_target:
        orch_items = _list_workspace_items(token, orch_target["workspace_id"])
        sql_db_item = _find_item(orch_items, SQL_DATABASE_ITEM_NAME, "SQLDatabase")
        if not sql_db_item:
            sql_dbs = _find_items_by_type(orch_items, "SQLDatabase")
            sql_db_item = sql_dbs[0] if sql_dbs else None
        if sql_db_item:
            try:
                props = _get_sql_database_details(token, orch_target["workspace_id"], sql_db_item["id"]).get("properties", {})
                sql_server = props.get("serverFqdn") or props.get("connectionString")
                sql_database = props.get("databaseName")
            except Exception:
                pass

    insert_sql = _generate_insert_sql(
        workspace_id=workspace_id,
        workspace_name=customer_code,
        lakehouse_id=lakehouse["id"],
        lakehouse_name=lakehouse["displayName"],
        b2s_pipeline_id=b2s_pipeline["id"],
        s2g_pipeline_id=s2g_pipeline["id"],
    )
    poller_sql = _generate_poller_source_sql(
        customer_prefix=customer_prefix,
        customer_label=customer_label,
        storage_account=storage_account,
    )
    sp_sql = _generate_register_extract_sp_sql()

    _update_sql_file(insert_sql, poller_sql, sp_sql, target_sql_file=target_sql_file)
    _update_notebook_file(
        workspace_id=workspace_id,
        b2s_pipeline_id=b2s_pipeline["id"],
        s2g_pipeline_id=s2g_pipeline["id"],
        sql_server=sql_server,
        sql_database=sql_database,
        target_notebook_file=target_notebook_file,
    )

    return {
        "orc_output_dir": str(orc_output_dir),
        "lakehouse": lakehouse["displayName"],
        "b2s_pipeline": b2s_pipeline["displayName"],
        "s2g_pipeline": s2g_pipeline["displayName"],
        "sql_server": sql_server,
        "sql_database": sql_database,
    }


def main() -> None:
    targets = _load_insights_targets()
    if not targets:
        print("No insights targets found in deploy_targets.yml")
        raise SystemExit(1)

    target_name, target = _pick_insights_target(targets)
    workspace_id = target["workspace_id"]
    tenant_id = target["tenant_id"]
    environment = target.get("environment", "")
    customer_code = _customer_code_from_environment(environment)
    customer_name = _customer_name_from_code(customer_code)
    customer_slug = _slugify_customer_name(customer_name) if customer_name else ""

    print(f"\nSelected: {target_name}")
    print(f"  Workspace ID:  {workspace_id}")
    print(f"  Customer:      {customer_name} ({customer_code})")
    print(f"  Tenant:        {tenant_id}")

    # --- Ask for poller_source configuration ---
    print("\n--- Poller Source Configuration ---")
    default_prefix = customer_slug[:4] if len(customer_slug) > 4 else customer_slug
    prefix_input = input(f"  Customer prefix for source_ids [{default_prefix}]: ").strip()
    customer_prefix = prefix_input if prefix_input else default_prefix

    customer_label = customer_prefix.title()
    label_input = input(f"  Customer label for display [{customer_label}]: ").strip()
    if label_input:
        customer_label = label_input

    storage_account = target.get("storage_account", "").strip()
    if storage_account:
        print(f"  Storage account name: {storage_account}  (from deploy_targets.yml)")
    else:
        storage_account = input("  Storage account name: ").strip()
        if not storage_account:
            print("  Storage account is required!")
            raise SystemExit(1)

    # --- Authenticate & fetch items ---
    print("\nAuthenticating with Fabric API...")
    token = _get_token(tenant_id)

    print(f"Querying items in workspace...")
    items = _list_workspace_items(token, workspace_id)
    print(f"  Found {len(items)} items")

    # --- Resolve lakehouse ---
    lakehouse = _find_item(items, DEFAULT_LAKEHOUSE_NAME, "Lakehouse")
    if not lakehouse:
        lakehouses = _find_items_by_type(items, "Lakehouse")
        if len(lakehouses) == 1:
            lakehouse = lakehouses[0]
            print(f"  Lakehouse '{DEFAULT_LAKEHOUSE_NAME}' not found, using '{lakehouse['displayName']}'")
        elif lakehouses:
            lakehouse = _pick_item_interactively(items, "Lakehouse", "lakehouse")
        else:
            print("  No Lakehouse found in workspace!")
            raise SystemExit(1)

    lakehouse_name = lakehouse["displayName"]
    lakehouse_id = lakehouse["id"]

    # --- Resolve pipelines ---
    b2s_pipeline = _find_item(items, B2S_PIPELINE_NAME, "DataPipeline")
    if not b2s_pipeline:
        print(f"  Pipeline '{B2S_PIPELINE_NAME}' not found!")
        b2s_pipeline = _pick_item_interactively(items, "DataPipeline", "B2S pipeline")

    s2g_pipeline = _find_item(items, S2G_PIPELINE_NAME, "DataPipeline")
    if not s2g_pipeline:
        print(f"  Pipeline '{S2G_PIPELINE_NAME}' not found!")
        s2g_pipeline = _pick_item_interactively(items, "DataPipeline", "S2G pipeline")

    # --- Resolve northstar-control workspace SQL Database ---
    sql_server: str | None = None
    sql_database: str | None = None

    orch_target = _find_orch_target(customer_code, environment)
    if orch_target:
        orch_ws_id = orch_target["workspace_id"]
        print(f"\nFound northstar-control workspace: {orch_target.get('description', orch_ws_id)}")
        print(f"  Querying items in northstar-control workspace...")
        orch_items = _list_workspace_items(token, orch_ws_id)

        sql_db_item = _find_item(orch_items, SQL_DATABASE_ITEM_NAME, "SQLDatabase")
        if not sql_db_item:
            # Try any SQLDatabase
            sql_dbs = _find_items_by_type(orch_items, "SQLDatabase")
            if len(sql_dbs) == 1:
                sql_db_item = sql_dbs[0]
            elif sql_dbs:
                sql_db_item = _pick_item_interactively(orch_items, "SQLDatabase", "SQL Database")

        if sql_db_item:
            print(f"  Found SQL Database: {sql_db_item['displayName']} ({sql_db_item['id']})")
            try:
                db_details = _get_sql_database_details(token, orch_ws_id, sql_db_item["id"])
                props = db_details.get("properties", {})
                sql_server = props.get("serverFqdn") or props.get("connectionString")
                sql_database = props.get("databaseName")
                if sql_server:
                    print(f"  SQL Server:   {sql_server}")
                if sql_database:
                    print(f"  SQL Database: {sql_database}")
            except Exception as e:
                print(f"  Warning: Could not get SQL Database details: {e}")
                print("  You can enter them manually.")
                sql_server = input("  FALLBACK_SQL_SERVER (or Enter to skip): ").strip() or None
                sql_database = input("  FALLBACK_SQL_DATABASE (or Enter to skip): ").strip() or None
        else:
            print("  No SQL Database found in northstar-control workspace.")
    else:
        print(f"\n  No northstar-control workspace target found for {customer_code} / {environment}.")
        print("  Enter SQL connection details manually (or Enter to skip):")
        sql_server = input("  FALLBACK_SQL_SERVER: ").strip() or None
        sql_database = input("  FALLBACK_SQL_DATABASE: ").strip() or None

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    print(f"\n  Insights Workspace: {workspace_id}")
    print(f"  Lakehouse:          {lakehouse_name} -> {lakehouse_id}")
    print(f"  B2S Pipeline:       {b2s_pipeline['displayName']} -> {b2s_pipeline['id']}")
    print(f"  S2G Pipeline:       {s2g_pipeline['displayName']} -> {s2g_pipeline['id']}")
    if sql_server:
        print(f"  SQL Server:         {sql_server}")
    if sql_database:
        print(f"  SQL Database:       {sql_database}")
    print(f"\n  Poller source:")
    print(f"    Prefix:          {customer_prefix}")
    print(f"    Label:           {customer_label}")
    print(f"    Storage account: {storage_account}")

    # --- Generate SQL ---
    insert_sql = _generate_insert_sql(
        workspace_id=workspace_id,
        workspace_name=customer_code,
        lakehouse_id=lakehouse_id,
        lakehouse_name=lakehouse_name,
        b2s_pipeline_id=b2s_pipeline["id"],
        s2g_pipeline_id=s2g_pipeline["id"],
    )

    poller_sql = _generate_poller_source_sql(
        customer_prefix=customer_prefix,
        customer_label=customer_label,
        storage_account=storage_account,
    )

    sp_sql = _generate_register_extract_sp_sql()

    print("\n--- Generated target_workspace SQL ---\n")
    print(insert_sql)
    print("\n--- Generated poller_source SQL ---\n")
    print(poller_sql)
    print("\n--- Generated register_extract SP (domain code remap) ---\n")
    print(sp_sql)

    # --- Confirm & write ---
    while True:
        raw = input("\nUpdate all files? (y/N): ").strip().lower()
        if raw in {"", "n", "no"}:
            print("Skipped.")
            break
        if raw in {"y", "yes"}:
            _update_sql_file(insert_sql, poller_sql, sp_sql)
            _update_notebook_file(
                workspace_id=workspace_id,
                b2s_pipeline_id=b2s_pipeline["id"],
                s2g_pipeline_id=s2g_pipeline["id"],
                sql_server=sql_server,
                sql_database=sql_database,
            )
            break
        print("Enter 'y' or 'n'.")


if __name__ == "__main__":
    main()
