# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "",
# META       "default_lakehouse_name": "lkh_customer0_schema_enabled",
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
# META   "language_group": "synapse_pyspark",
# META   "frozen": true,
# META   "editable": false
# META }

# MARKDOWN ********************

# ## Helper Functions

# CELL ********************

from collections import defaultdict, deque

def _mask_sql(column, prefixes, salt):
    """
    SQL expression that turns a column value into: PREFIX-BUCKET-HASH
    Example: CUST-42-a3f7b2c1
    """
    n = len(prefixes)
    hash_base = f"ABS(CONV(SUBSTR(SHA2(CONCAT(CAST({column} AS STRING), '||', '{salt}'), 256), 1, 8), 16, 10))"
    if n == 1:
        pfx = f"'{prefixes[0]}'"
    else:
        cases = " ".join(f"WHEN {i} THEN '{p}'" for i, p in enumerate(prefixes))
        pfx = f"CASE CAST({hash_base} % {n} AS INT) {cases} ELSE '{prefixes[0]}' END"
    bucket = f"CAST({hash_base} % 100 AS INT)"
    short  = f"SUBSTR(SHA2(CONCAT(CAST({column} AS STRING), '||', '{salt}'), 256), 1, 8)"
    return f"CONCAT({pfx}, '-', {bucket}, '-', {short})"

def _rename_sql(column, mapping):
    """CASE WHEN column = 'old' THEN 'new' ... ELSE column END"""
    cases = " ".join(f"WHEN '{src}' THEN '{tgt}'" for src, tgt in mapping.items())
    return f"CASE {column} {cases} ELSE {column} END"

def _resolve_prefixes(column, mask_prefixes_lookup):
    """Look up the prefix list for a column name (case-insensitive)."""
    for key, prefixes in mask_prefixes_lookup.items():
        if key.lower() == column.lower():
            return prefixes
    return ["GEN"]

def _topo_sort(tables):
    """Sort tables so dependencies come first (topological sort)."""
    name_map = {t["table"]: t for t in tables}
    in_deg = defaultdict(int)
    graph = defaultdict(list)
    for t in tables:
        name = t["table"]
        if name not in in_deg:
            in_deg[name] = 0
        for dep in t.get("depends_on", []):
            graph[dep].append(name)
            in_deg[name] += 1
    queue = deque(n for n in in_deg if in_deg[n] == 0)
    ordered = []
    while queue:
        node = queue.popleft()
        ordered.append(node)
        for child in graph[node]:
            in_deg[child] -= 1
            if in_deg[child] == 0:
                queue.append(child)
    if len(ordered) != len(tables):
        missing = set(t["table"] for t in tables) - set(ordered)
        raise ValueError(f"Circular dependency! Check these tables: {missing}")
    return [name_map[n] for n in ordered]

def _build_full_sql(entry, source_schema, target_schema, salt, sample_pct,
                    seed_dimensions, prefix_lookup, column_renames, table_filters):
    """
    Build CREATE OR REPLACE TABLE ... AS SELECT ... SQL for one table.
    
    Seed dimensions: sampled via TABLESAMPLE.
    Facts linked to seeds: filtered via WHERE key IN (SELECT key FROM target_schema.seed_dim).
    Other tables: full copy.
    """
    tbl = entry["table"]
    src = f"{source_schema}.{tbl}"
    tgt = f"{target_schema}.{tbl}"
    mask_cols = [c.lower() for c in entry.get("mask", [])]

    # Get columns from source table
    try:
        cols = [f.name for f in spark.table(src).schema.fields]
    except Exception as e:
        return None, f"SKIP {src}: {e}"

    # Determine if this is a seed dimension
    is_seed = tbl in seed_dimensions

    # Determine fact filters from seed dimensions
    fact_key_filters = []
    for seed_tbl, seed_cfg in seed_dimensions.items():
        if tbl in seed_cfg.get("facts", []):
            key_col = seed_cfg["key"]
            # Check if this fact actually has the key column
            if key_col.lower() in [c.lower() for c in cols]:
                fact_key_filters.append(
                    f"{key_col} IN (SELECT {key_col} FROM {target_schema}.{seed_tbl})"
                )

    # Get per-table column renames
    tbl_renames = column_renames.get(tbl, {})

    # Build SELECT list
    select_parts = []
    for c in cols:
        cl = c.lower()
        if cl in mask_cols:
            pfx = _resolve_prefixes(c, prefix_lookup)
            expr = _mask_sql(c, pfx, salt)
            select_parts.append(f"    {expr} AS {c}")
        elif c in tbl_renames:
            expr = _rename_sql(c, tbl_renames[c])
            select_parts.append(f"    {expr} AS {c}")
        else:
            select_parts.append(f"    {c}")
    select_clause = ",\n".join(select_parts)

    # Build WHERE clause
    where_parts = list(fact_key_filters)

    if table_filters and tbl in table_filters:
        where_parts.append(f"({table_filters[tbl]})")

    where_clause = ""
    if where_parts:
        where_clause = "\nWHERE " + "\n  AND ".join(where_parts)

    # Build FROM clause (seed dims get TABLESAMPLE)
    sample_clause = ""
    if is_seed and sample_pct and 0 < sample_pct < 100:
        sample_clause = f" TABLESAMPLE ({sample_pct} PERCENT)"

    sql = f"CREATE OR REPLACE TABLE {tgt} AS\nSELECT\n{select_clause}\nFROM {src}{sample_clause}{where_clause}"

    # Description
    desc_parts = [f"{tgt} ← {src}"]
    if is_seed:          desc_parts.append(f"seed_sample={sample_pct}%")
    if fact_key_filters:  desc_parts.append(f"key_filter={len(fact_key_filters)}")
    if mask_cols:         desc_parts.append(f"mask={entry.get('mask', [])}")
    if tbl_renames:       desc_parts.append(f"rename={list(tbl_renames.keys())}")
    if table_filters and tbl in table_filters: desc_parts.append("filter")
    return sql, " | ".join(desc_parts)

def generate_processing_plan(tables, source_schema, target_schema, masking_phrase, sample_pct,
                             seed_dimensions, mask_prefixes, column_renames, table_filters):
    """Generate and preview SQL transformation plan. Returns list of generated SQL statements."""
    import datetime
    import urllib.parse

    processing_order = _topo_sort(tables)

    print(f"Processing order ({len(processing_order)} tables):")
    print("─" * 60)
    for i, t in enumerate(processing_order, 1):
        is_seed = t["table"] in seed_dimensions
        is_fact = t["table"].startswith("f_")
        deps = f" ← {t['depends_on']}" if t.get("depends_on") else ""
        mask = f" [mask: {t.get('mask',[])}]" if t.get("mask") else ""
        tag = "SEED" if is_seed else ("FACT" if is_fact else "DIM ")
        print(f"  {i:2d}. {tag:4s} {t['table']}{mask}{deps}")

    print()
    print("=" * 70)
    print("GENERATED SQL PREVIEW")
    print("=" * 70)

    _generated = []
    for entry in processing_order:
        sql, desc = _build_full_sql(
            entry, source_schema, target_schema, masking_phrase,
            sample_pct, seed_dimensions, mask_prefixes, column_renames, table_filters
        )
        if sql is None:
            print(f"\n⚠  {desc}")
            continue
        _generated.append({"entry": entry, "sql": sql, "desc": desc})
        print(f"\n-- {desc}")
        print(sql)

    print(f"\n{'=' * 70}")
    print(f"Ready: {len(_generated)} SQL statements")

    # ── Build downloadable .ipynb notebook ────────────────────────────────
    timestamp = datetime.datetime.now().strftime("%Y%m%d")
    nb_name = f"demo_data_{timestamp}"

    import uuid as _uuid, json as _json

    _sql_meta = {"microsoft": {"language": "sparksql", "language_group": "synapse_pyspark"}}

    def _make_cell(source_str):
        src_lines = [line + "\n" for line in source_str.split("\n")]
        if src_lines:
            src_lines[-1] = src_lines[-1].rstrip("\n")
        return {
            "cell_type": "code",
            "source": src_lines,
            "outputs": [],
            "execution_count": None,
            "metadata": _sql_meta,
            "id": str(_uuid.uuid4()),
        }

    cells = []
    cells.append(_make_cell(f"%%sql\nCREATE SCHEMA IF NOT EXISTS {target_schema}"))

    for item in _generated:
        sql_body = f"%%sql\n-- {item['desc']}\n{item['sql']}"
        cells.append(_make_cell(sql_body))

    notebook_json = _json.dumps({
        "cells": cells,
        "metadata": {
            "language_info": {"name": "python"},
            "microsoft": {
                "language": "python",
                "language_group": "synapse_pyspark",
                "ms_spell_check": {"ms_spell_check_language": "en"},
            },
            "nteract": {"version": "nteract-front-end@1.0.0"},
            "spark_compute": {
                "compute_id": "/trident/default",
                "session_options": {"conf": {"spark.synapse.nbs.session.timeout": "1200000"}},
            },
            "kernel_info": {"name": "synapse_pyspark"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }, indent=1)

    print(f"\n💾 Notebook generated: {nb_name}.ipynb ({len(_generated)} SQL cells)")

    content_uri = f"data:application/json;charset=utf-8,{urllib.parse.quote(notebook_json)}"
    html_link = f"""
<div style="background-color: #f0f8ff; padding: 15px; border-radius: 5px; border-left: 4px solid #2196F3;">
    <h4>📥 Download Notebook</h4>
    <a href="{content_uri}" download="{nb_name}.ipynb"
       style="display: inline-block; padding: 10px 20px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 4px; font-weight: bold; cursor: pointer;">
        ⬇️ {nb_name}.ipynb
    </a>
    <p style="margin-top: 10px; font-size: 12px; color: #666;">
        {len(_generated)} SQL cells | Import into Fabric workspace
    </p>
</div>
"""
    displayHTML(html_link)
    return _generated

def execute_data_copy(generated_items, source_schema, target_schema):
    """Execute data copy transformations for all tables."""
    results = []

    # print("=" * 70)
    # print("EXECUTING")
    # print("=" * 70)

    spark.sql(f"CREATE SCHEMA IF NOT EXISTS {target_schema}")

    for item in generated_items:
        entry = item["entry"]
        sql   = item["sql"]
        tbl   = entry["table"]

        # print(f"\n▶ {item['desc']}")
        try:
            spark.sql(sql)
            tgt_cnt = spark.table(f"{target_schema}.{tbl}").count()
            # print(f"  ✓ {tgt_cnt:,} rows")
            results.append((tbl, "SEED" if "seed_sample" in item["desc"] else ("FACT" if tbl.startswith("f_") else "DIM"), tgt_cnt, "OK"))
        except Exception as e:
            err = str(e)[:200]
            print(f"  ✗ FAILED: {err}")
            results.append((tbl, "FACT" if tbl.startswith("f_") else "DIM", None, err))

    return results

def trim_dimensions(tables_config, opr_trimming, fct_trimming, target_schema):
    """Trim dimension tables to remove orphan rows not referenced by fact tables."""
    all_trims = dict(opr_trimming)
    all_trims.update(fct_trimming)

    for t in tables_config:
        if "trim_to_facts" in t:
            all_trims[t["table"]] = t["trim_to_facts"]

    # print("=" * 70)
    # print("TRIMMING DIMENSIONS")
    # print("=" * 70)

    for dim_table, config in all_trims.items():
        key_col = config["key"]
        fact_tables = config["facts"]
        dim_full = f"{target_schema}.{dim_table}"

        union_parts = []
        for ft in fact_tables:
            ft_full = f"{target_schema}.{ft}"
            try:
                fact_cols = [f.name.lower() for f in spark.table(ft_full).schema.fields]
                if key_col.lower() in fact_cols:
                    union_parts.append(f"SELECT DISTINCT {key_col} FROM {ft_full}")
            except Exception:
                pass

        if not union_parts:
            # print(f"\n  SKIP {dim_table}: no matching fact tables found")
            continue

        keys_sql = " UNION ".join(union_parts)

        try:
            trim_sql = f"""
            CREATE OR REPLACE TABLE {dim_full} AS
            SELECT d.* FROM {dim_full} d
            WHERE d.{key_col} IN ({keys_sql})
            """
            spark.sql(trim_sql)
            trimmed_cnt = spark.table(dim_full).count()
            # print(f"\n  ✓ {dim_table}: trimmed to {trimmed_cnt:,} rows")
        except Exception as e:
            print(f"\n  ✗ {dim_table}: {e}")

def validate_referential_integrity(tables_config, seed_dimensions, opr_trimming, fct_trimming, target_schema):
    """
    Check every dim-fact key relationship in both directions:
      - fact_orphans:  fact rows pointing to missing dim key  (should be 0)
      - dim_only_keys: dim keys not in this specific fact     (expected > 0 when dim serves multiple facts)
      - matching_keys: keys present in both
    """
    # Collect all dim→fact relationships from seed dims, trim configs, and trim_to_facts
    relationships = []

    for seed_tbl, cfg in seed_dimensions.items():
        for fact_tbl in cfg["facts"]:
            relationships.append((seed_tbl, cfg["key"], fact_tbl))

    for trim_dict in [opr_trimming, fct_trimming]:
        for dim_tbl, cfg in trim_dict.items():
            for fact_tbl in cfg["facts"]:
                relationships.append((dim_tbl, cfg["key"], fact_tbl))

    for t in tables_config:
        if "trim_to_facts" in t:
            cfg = t["trim_to_facts"]
            for fact_tbl in cfg["facts"]:
                relationships.append((t["table"], cfg["key"], fact_tbl))

    # Deduplicate
    relationships = list(set(relationships))
    relationships.sort()

    results = []
    for dim_tbl, key_col, fact_tbl in relationships:
        dim_full  = f"{target_schema}.{dim_tbl}"
        fact_full = f"{target_schema}.{fact_tbl}"

        try:
            dim_cols  = [c.name.lower() for c in spark.table(dim_full).schema.fields]
            fact_cols = [c.name.lower() for c in spark.table(fact_full).schema.fields]
            if key_col.lower() not in dim_cols or key_col.lower() not in fact_cols:
                continue

            row = spark.sql(f"""
                SELECT
                    COUNT(DISTINCT d.{key_col})  AS dim_keys,
                    COUNT(DISTINCT f.{key_col})  AS fact_keys,
                    COUNT(DISTINCT CASE WHEN f.{key_col} IS NOT NULL THEN d.{key_col} END) AS matching_keys,
                    SUM(CASE WHEN d.{key_col} IS NULL THEN 1 ELSE 0 END) AS fact_orphans
                FROM {fact_full} f
                FULL OUTER JOIN (SELECT DISTINCT {key_col} FROM {dim_full}) d
                    ON f.{key_col} = d.{key_col}
            """).collect()[0]

            results.append((
                dim_tbl, key_col, fact_tbl,
                row["dim_keys"], row["fact_keys"], row["matching_keys"], row["fact_orphans"],
                "✓" if row["fact_orphans"] == 0 else "✗ ORPHANS"
            ))
        except Exception as e:
            results.append((dim_tbl, key_col, fact_tbl, None, None, None, None, str(e)[:80]))

    df = spark.createDataFrame(results, [
        "dimension", "key", "fact", "dim_keys", "fact_keys", "matching_keys", "fact_orphans", "status"
    ])
    print("=" * 90)
    print("REFERENTIAL INTEGRITY CHECK")
    print("  fact_orphans = fact keys not in dim (must be 0)")
    print("  dim_keys > fact_keys is normal when a dim serves multiple facts")
    print("=" * 90)
    display(df.filter("fact_orphans == 0").orderBy("dimension", "fact"))
    # validate_referential_integrity(TABLE_CONFIG, SEED_DIMENSIONS, OPR_DIM_TRIMMING, FCT_DIM_TRIMMING, TARGET_SCHEMA)

def display_results_summary(results):
    """Display a summary table of all processed tables."""
    summary_df = spark.createDataFrame(results, ["table", "type", "rows", "status"])
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    display(summary_df.orderBy("type", "table"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Params

# CELL ********************

SOURCE_SCHEMA  = "gold"
TARGET_SCHEMA  = "gold_demo"
MASKING_PHRASE  = "VCT_BI_202605"
# SAMPLE_PERCENT = 20

# ─── Seed Dimensions ───────────────────────────────────────────────────
# These dimensions are sampled at SAMPLE_PERCENT.
# All facts listed under each seed will be filtered to only include
# rows whose key matches the sampled subset.

SEED_DIMENSIONS = {
    "d_opr_productlocation": {
        "key": "Productlocationid_key",
        "facts": [
            "f_opr_backorderfact", "f_opr_backorderfact_his",
            "f_opr_pplprodlocdemfact", "f_opr_pplprodlocdemfact_his",
            "f_opr_pplprodlocinvfact", "f_opr_pplprodlocinvfact_his",
            "f_opr_pplprodlocprodfact", "f_opr_pplprodlocprodfact_his",
        ],
    },
    "d_fct_forecastitem": {
        "key": "Forecastitemid_key",
        "facts": [
            "f_fct_saleshistory", "f_fct_forecastaccuracy",
        ],
    },
}

# ─── Per-Table Column Renames ──────────────────────────────────────────
# Rename specific column values for any table.
# Format: { "table_name": { "ColumnName": { "old_value": "new_value", ... } } }

COLUMN_RENAMES = {
    "d_fct_forecastgroup": {"Forecastgroupid": {"DMR": "Local", "PreDMR": "Central"}},
}

# ─── Per-Table WHERE Filters ──────────────────────────────────────────
# Extra WHERE clause applied to specific tables (runs on source data).

TABLE_FILTERS = {
    "d_fct_forecastgroup": "Forecastgroupid IN ('Statistical', 'DMR', 'PreDMR')",
}

# ─── Mask Prefixes ─────────────────────────────────────────────────────

MASK_PREFIXES = {
    "Customerid":        ["CUST", "CLIENT", "ACCT"],
    "Locationid":        ["LOC", "AREA", "ZONE"],
    "Machineid":         ["MACHN"],
    "Processid":         ["PROC", "STEP", "OP", "FLOW"],
    "Productid":         ["PROD", "ITEM"],
    "Productlocationid": ["PRODLOC"],
}


TABLE_CONFIG = [

    ########################################## OPR DIMS ##########################################

    {"table": "d_opr_certainty"},
    {"table": "d_opr_customer",             "mask": ["Customerid"]},
    {"table": "d_opr_location",             "mask": ["Locationid"]},
    {"table": "d_opr_process",              "mask": ["Processid"]},
    {"table": "d_opr_product",              "mask": ["Productid"]},
    {"table": "d_opr_productlocation",      "mask": ["Productlocationid"]},
    {
        "table": "d_opr_productlocation_norelation",
        "mask": ["Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {"table": "d_opr_generalunitconversion"},
    {"table": "d_opr_producttype"},
    {"table": "d_opr_productunitconversion"},
    {"table": "d_opr_unit"},

    ########################################## OPR FACTS #########################################

    {
        "table": "f_opr_backorderfact",
        "mask": ["Customerid", "Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_backorderfact_his",
        "mask": ["Customerid", "Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplprodlocdemfact",
        "mask": ["Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplprodlocdemfact_his",
        "mask": ["Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplprodlocinvfact",
        "mask": ["Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplprodlocinvfact_his",
        "mask": ["Productid", "Locationid", "Productlocationid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplmachineconsfact",
        "mask": ["Machineid", "Locationid", "Productid", "Productlocationid"],
        "depends_on": ["d_opr_location"],
    },
    {
        "table": "f_opr_pplmachineconsfact_his",
        "mask": ["Machineid", "Locationid", "Productid", "Productlocationid"],
        "depends_on": ["d_opr_location"],
    },
    {
        "table": "f_opr_pplmachinefact",
        "mask": ["Machineid", "Locationid"],
    },
    {
        "table": "f_opr_pplmachinefact_his",
        "mask": ["Machineid", "Locationid"],
    },
    {
        "table": "f_opr_pplprodlocprodfact",
        "mask": ["Machineid", "Locationid", "Productid", "Productlocationid", "Processid"],
        "depends_on": ["d_opr_productlocation"],
    },
    {
        "table": "f_opr_pplprodlocprodfact_his",
        "mask": ["Machineid", "Locationid", "Productid", "Productlocationid", "Processid"],
        "depends_on": ["d_opr_productlocation"],
    },

    ########################################## FCT DIMS ##########################################

    {"table": "d_fct_calculationlevel"},
    {"table": "d_fct_calendar"},
    {"table": "d_fct_calendar_norelation"},
    {
        "table": "d_fct_customer",
        "mask": ["Customerid"],
        "trim_to_facts": {
            "key": "Customerid_key",
            "facts": [
                "f_fct_saleshistory", "f_fct_forecastaccuracy",
            ],
        },
    },
    {"table": "d_fct_forecastgroup"},
    {"table": "d_fct_kpi_targets"},
    {
        "table": "d_fct_product",
        "mask": ["Productid"],
        "trim_to_facts": {
            "key": "Productid_key",
            "facts": [
                "f_fct_saleshistory", "f_fct_forecastaccuracy",
            ],
        },
    },
    {"table": "d_fct_productunitconversion"},
    {"table": "d_fct_promodefinition"},
    {"table": "d_fct_unit"},
    {
        "table": "d_fct_forecastitem",
        "mask": ["Customerid", "Productid"],
        "depends_on": ["d_fct_customer"],
        "trim_to_facts": {
            "key": "Forecastitemid_key",
            "facts": [
                "f_fct_saleshistory",
            ],
        },
    },
    {"table": "d_fct_forecastitem_properties", "depends_on": ["d_fct_forecastitem"]},

    ########################################## FCT FACTS #########################################

    {
        "table": "f_fct_saleshistory",
        "mask": ["Customerid", "Productid"],
        "depends_on": ["d_fct_forecastitem"],
    },
    {
        "table": "f_fct_forecastaccuracy",
        "mask": ["Customerid", "Productid"],
        "depends_on": ["f_fct_saleshistory", "d_fct_forecastitem_properties", "d_fct_timeframe"],
    },

    ########################################## FCT DERIVED DIMS ##################################

    {"table": "d_fct_forecastcycle"},
    {"table": "d_fct_lag"},
    {"table": "d_fct_lag_norelation", "depends_on": ["d_fct_lag"]},
    {"table": "d_fct_timeframe",      "depends_on": ["f_fct_saleshistory"]},
]

########################################## DIM TRIM ##############################################

OPR_DIM_TRIMMING = {
    "d_opr_customer": {
        "key": "Customerid_key",
        "facts": ["f_opr_backorderfact", "f_opr_backorderfact_his"],
    },
    "d_opr_location": {
        "key": "Locationid_key",
        "facts": [
            "f_opr_pplmachineconsfact", "f_opr_pplmachineconsfact_his",
            "f_opr_pplmachinefact", "f_opr_pplmachinefact_his",
        ],
    },
    "d_opr_process": {
        "key": "Processid_key",
        "facts": ["f_opr_pplprodlocprodfact", "f_opr_pplprodlocprodfact_his"],
    },
    "d_opr_product": {
        "key": "Productid_key",
        "facts": [
            "f_opr_backorderfact", "f_opr_backorderfact_his",
            "f_opr_pplprodlocdemfact", "f_opr_pplprodlocdemfact_his",
            "f_opr_pplprodlocinvfact", "f_opr_pplprodlocinvfact_his",
            "f_opr_pplprodlocprodfact", "f_opr_pplprodlocprodfact_his",
            "f_opr_pplmachineconsfact", "f_opr_pplmachineconsfact_his",
        ],
    },
    "d_opr_productlocation": {
        "key": "Productlocationid_key",
        "facts": [
            "f_opr_backorderfact", "f_opr_backorderfact_his",
            "f_opr_pplprodlocdemfact", "f_opr_pplprodlocdemfact_his",
            "f_opr_pplprodlocinvfact", "f_opr_pplprodlocinvfact_his",
            "f_opr_pplprodlocprodfact", "f_opr_pplprodlocprodfact_his",
        ],
    },
}

FCT_DIM_TRIMMING = {
    "d_fct_timeframe": {
        "key": "Timeframeid_key",
        "facts": [
            "f_fct_saleshistory",
        ],
    },
}


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Execution

# CELL ********************

print("\n" + "#" * 70)
print("# GOLD DEMO DATA GENERATOR")
print("#" * 70)

print(f"\n  Source:  {SOURCE_SCHEMA}")
print(f"  Target:  {TARGET_SCHEMA}")
print(f"  Sample:  {SAMPLE_PERCENT}% (applied to seed dimensions)")
print(f"  Seeds:   {list(SEED_DIMENSIONS.keys())}")

_generated = generate_processing_plan(
    TABLE_CONFIG, SOURCE_SCHEMA, TARGET_SCHEMA, MASKING_PHRASE,
    SAMPLE_PERCENT, SEED_DIMENSIONS, MASK_PREFIXES, COLUMN_RENAMES, TABLE_FILTERS
)

# print("\n[EXECUTE] Running data copy...")
_results = execute_data_copy(_generated, SOURCE_SCHEMA, TARGET_SCHEMA)

# print("\n[TRIM] Removing orphan dimension rows...")
trim_dimensions(TABLE_CONFIG, OPR_DIM_TRIMMING, FCT_DIM_TRIMMING, TARGET_SCHEMA)

display_results_summary(_results)



# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
