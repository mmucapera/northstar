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

# # Table Validation Tests
# > Data quality validation framework. Tests are defined declaratively per table.
# > Each test type generates SQL at runtime - no hardcoded queries needed.
# >
# > **To add validations:** edit the `TABLE_TESTS` config in the next cell.

# CELL ********************

from pyspark.sql import SparkSession
from datetime import datetime

spark = SparkSession.builder.getOrCreate()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Test Type Definitions
# Each test type is a function that receives the table name and test parameters,
# and returns a SQL query. The query should return **zero rows** if data is valid.

# CELL ********************

def _q(table, condition, limit=100):
    return f"SELECT * FROM {table} WHERE {condition} LIMIT {limit}"


def test_not_null(table, params):
    """Columns that must not be NULL."""
    queries = []
    for col in params["columns"]:
        queries.append((
            f"{table}: {col} is NULL",
            _q(table, f"`{col}` IS NULL"),
        ))
    return queries


def test_primary_key(table, params):
    """Primary key columns must be unique (no duplicates)."""
    cols = params["columns"]
    col_list = ", ".join(f"`{c}`" for c in cols)
    col_desc = ", ".join(cols)
    return [(
        f"{table}: duplicate primary key ({col_desc})",
        f"SELECT {col_list}, COUNT(*) AS dup_count FROM {table} GROUP BY {col_list} HAVING COUNT(*) > 1 LIMIT 100",
    )]


def test_accepted_values(table, params):
    """Column values must be within a defined set."""
    queries = []
    for col, values in params["checks"].items():
        value_list = ", ".join(f"'{v}'" for v in values)
        queries.append((
            f"{table}: {col} has invalid values (not in [{value_list}])",
            _q(table, f"`{col}` IS NOT NULL AND `{col}` NOT IN ({value_list})"),
        ))
    return queries


def test_comparison(table, params):
    """Column comparisons (e.g. col_a < col_b, col_x >= col_y)."""
    queries = []
    for check in params["checks"]:
        left = check["left"]
        op = check["op"]
        right = check["right"]
        # We test the INVERSE condition to find violations
        inverse_ops = {"<": ">=", "<=": ">", ">": "<=", ">=": "<", "=": "!=", "!=": "="}
        inv_op = inverse_ops.get(op, f"NOT {op}")
        queries.append((
            f"{table}: expected {left} {op} {right}",
            _q(table, f"`{left}` IS NOT NULL AND `{right}` IS NOT NULL AND `{left}` {inv_op} `{right}`"),
        ))
    return queries


def test_row_count_max(table, params):
    """Max number of rows per combination of group columns."""
    group_cols = params["group_by"]
    max_rows = params["max_rows"]
    col_list = ", ".join(f"`{c}`" for c in group_cols)
    col_desc = ", ".join(group_cols)
    return [(
        f"{table}: more than {max_rows} rows per ({col_desc})",
        f"SELECT {col_list}, COUNT(*) AS row_count FROM {table} GROUP BY {col_list} HAVING COUNT(*) > {max_rows} LIMIT 100",
    )]


def test_combination_count(table, params):
    """Total distinct combinations of columns must not exceed a threshold."""
    cols = params["columns"]
    max_combinations = params["max"]
    col_list = ", ".join(f"`{c}`" for c in cols)
    col_desc = ", ".join(cols)
    return [(
        f"{table}: distinct combinations of ({col_desc}) exceed {max_combinations}",
        f"SELECT 'exceeded' AS issue, cnt FROM (SELECT COUNT(*) AS cnt FROM (SELECT DISTINCT {col_list} FROM {table})) WHERE cnt > {max_combinations}",
    )]


def test_referential_integrity(table, params):
    """Values in a column must exist in a reference table/column."""
    queries = []
    for check in params["checks"]:
        col = check["column"]
        ref_table = check["ref_table"]
        ref_col = check.get("ref_column", col)
        queries.append((
            f"{table}: {col} not found in {ref_table}.{ref_col}",
            f"SELECT a.* FROM {table} a LEFT JOIN {ref_table} b ON a.`{col}` = b.`{ref_col}` WHERE b.`{ref_col}` IS NULL AND a.`{col}` IS NOT NULL LIMIT 100",
        ))
    return queries


def test_scd_integrity(table, params):
    """SCD2 columns: valid_from/valid_to/is_current must be consistent."""
    valid_from = params.get("valid_from", "valid_from")
    valid_to = params.get("valid_to", "valid_to")
    is_current = params.get("is_current", "is_current")
    return [
        (
            f"{table}: current record has NULL {valid_from}",
            _q(table, f"`{is_current}` = true AND `{valid_from}` IS NULL"),
        ),
        (
            f"{table}: current record has non-NULL {valid_to}",
            _q(table, f"`{is_current}` = true AND `{valid_to}` IS NOT NULL"),
        ),
        (
            f"{table}: historical record has NULL {valid_to}",
            _q(table, f"`{is_current}` = false AND `{valid_to}` IS NULL"),
        ),
    ]


def test_custom_sql(table, params):
    """Escape hatch: provide a raw SQL query directly."""
    queries = []
    for check in params["checks"]:
        queries.append((
            f"{table}: {check['description']}",
            check["sql"].replace("{table}", table),
        ))
    return queries


# Registry of test types
TEST_TYPES = {
    "not_null": test_not_null,
    "primary_key": test_primary_key,
    "accepted_values": test_accepted_values,
    "comparison": test_comparison,
    "row_count_max": test_row_count_max,
    "combination_count": test_combination_count,
    "referential_integrity": test_referential_integrity,
    "scd_integrity": test_scd_integrity,
    "custom_sql": test_custom_sql,
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Table Test Configuration
# Define which tests apply to each table. Add/remove entries to expand coverage.

# CELL ********************

TABLE_TESTS = {
    # =========================================================================
    # BRONZE - FCT
    # =========================================================================
    "bronze.fct_saleshistory": [
        {"type": "not_null", "columns": ["Sourcefile", "Forecastitemid", "Load_date", "ins_batchid"]},
        {"type": "primary_key", "columns": ["Forecastitemid", "Fromduedate", "Duedate", "Unitid", "Sourcefile"]},
    ],
    "bronze.fct_product": [
        {"type": "not_null", "columns": ["Sourcefile", "Productid", "Load_date", "ins_batchid"]},
        {"type": "primary_key", "columns": ["Productid", "valid_from"]},
        {"type": "scd_integrity", "valid_from": "valid_from", "valid_to": "valid_to", "is_current": "is_current"},
    ],
    "bronze.fct_forecastitem": [
        {"type": "not_null", "columns": ["Sourcefile", "Forecastitemid", "Load_date", "ins_batchid"]},
        {"type": "primary_key", "columns": ["Forecastitemid", "valid_from"]},
        {"type": "scd_integrity", "valid_from": "valid_from", "valid_to": "valid_to", "is_current": "is_current"},
    ],
    "bronze.fct_customer": [
        {"type": "not_null", "columns": ["Sourcefile", "Customerid", "Load_date", "ins_batchid"]},
    ],
    "bronze.fct_unit": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.fct_generalunitconversion": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.fct_productunitconversion": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.fct_promodefinition": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],

    # =========================================================================
    # BRONZE - OPR
    # =========================================================================
    "bronze.opr_product": [
        {"type": "not_null", "columns": ["Sourcefile", "Productid", "Load_date", "ins_batchid"]},
        {"type": "primary_key", "columns": ["Productid", "valid_from"]},
        {"type": "scd_integrity", "valid_from": "valid_from", "valid_to": "valid_to", "is_current": "is_current"},
    ],
    "bronze.opr_customer": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_location": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_unit": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_productlocation": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_backorderfact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_pplprodlocdemfact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_pplprodlocinvfact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_pplprodlocprodfact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_pplmachinefact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],
    "bronze.opr_pplmachineconsfact": [
        {"type": "not_null", "columns": ["Sourcefile", "Load_date", "ins_batchid"]},
    ],

    # =========================================================================
    # SILVER - FCT
    # =========================================================================
    "silver.fct_saleshistory": [
        {"type": "not_null", "columns": ["Forecastitemid_key", "Unitid_key", "Timeframe_key"]},
        {
            "type": "referential_integrity",
            "checks": [
                {"column": "Forecastitemid", "ref_table": "silver.fct_forecastitem", "ref_column": "Forecastitemid"},
            ],
        },
    ],

    # =========================================================================
    # EXAMPLE: advanced test types (uncomment/adapt as needed)
    # =========================================================================
    # "gold.d_fct_forecastitem": [
    #     {"type": "combination_count", "columns": ["Forecastitemid"], "max": 50000},
    #     {"type": "accepted_values", "checks": {
    #         "Abcclassification": ["A", "B", "C"],
    #     }},
    # ],
    # "bronze.fct_saleshistory": [
    #     {"type": "custom_sql", "checks": [
    #         {"description": "Quantity is negative", "sql": "SELECT * FROM {table} WHERE Quantity < 0 LIMIT 100"},
    #     ]},
    # ],
}

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Test Runner
# Compiles and executes all tests from the configuration above.

# CELL ********************

def compile_tests(table_tests):
    """Compile TABLE_TESTS config into a flat list of (description, sql) tuples."""
    compiled = []
    for table, tests in table_tests.items():
        for test_def in tests:
            test_type = test_def["type"]
            generator = TEST_TYPES.get(test_type)
            if not generator:
                compiled.append((f"{table}: UNKNOWN TEST TYPE '{test_type}'", "SELECT 'error'"))
                continue
            # Build params dict from test_def (everything except 'type')
            params = {k: v for k, v in test_def.items() if k != "type"}
            compiled.extend(generator(table, params))
    return compiled


all_tests = compile_tests(TABLE_TESTS)
results = []
run_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

print(f"Running {len(all_tests)} validation tests at {run_timestamp}\n")
print("=" * 90)

for idx, (description, query) in enumerate(all_tests, 1):
    try:
        df = spark.sql(query)
        bad_row_count = df.count()
        status = "PASS" if bad_row_count == 0 else "FAIL"
        sample_rows = df.limit(5).toPandas().to_dict("records") if bad_row_count > 0 else []
    except Exception as e:
        status = "ERROR"
        bad_row_count = -1
        sample_rows = [{"error": str(e)}]

    results.append({
        "test_number": idx,
        "description": description,
        "status": status,
        "bad_row_count": bad_row_count,
        "sample_rows": sample_rows,
    })

    icon = "✔" if status == "PASS" else ("✖" if status == "FAIL" else "⚠")
    print(f"  {icon} [{status:5s}] #{idx:03d} | {description} | rows: {bad_row_count}")

print("=" * 90)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************

# ## Summary

# CELL ********************

total = len(results)
passed = sum(1 for r in results if r["status"] == "PASS")
failed = sum(1 for r in results if r["status"] == "FAIL")
errors = sum(1 for r in results if r["status"] == "ERROR")

print(f"\n{'=' * 90}")
print(f"  VALIDATION SUMMARY  |  Run: {run_timestamp}")
print(f"{'=' * 90}")
print(f"  Total tests:   {total}")
print(f"  Passed:        {passed}  ✔")
print(f"  Failed:        {failed}  ✖")
print(f"  Errors:        {errors}  ⚠")
print(f"{'=' * 90}\n")

if failed > 0:
    print("FAILED TESTS:\n")
    for r in results:
        if r["status"] == "FAIL":
            print(f"  ✖ #{r['test_number']:03d} | {r['description']}")
            print(f"    Bad rows: {r['bad_row_count']}")
            if r["sample_rows"]:
                print(f"    Sample:   {r['sample_rows'][0]}")
            print()

if errors > 0:
    print("ERRORED TESTS:\n")
    for r in results:
        if r["status"] == "ERROR":
            print(f"  ⚠ #{r['test_number']:03d} | {r['description']}")
            print(f"    Error: {r['sample_rows'][0].get('error', 'unknown')}")
            print()

# Raise if any failures so pipeline can detect it
if failed > 0:
    raise AssertionError(f"{failed} validation test(s) FAILED. See details above.")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
