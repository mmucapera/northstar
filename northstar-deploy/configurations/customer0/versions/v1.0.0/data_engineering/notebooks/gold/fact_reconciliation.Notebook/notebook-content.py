# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {}
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

%run nb_utils_logging

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

%run nb_utils_config

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

from pyspark.sql.functions import current_timestamp, lit
from datetime import datetime
import logging
import time

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gold.fact_reconciliation")

# ---- FABRIC LOGGING FRAMEWORK ----
try:
    _fabric_logger = FabricLogger("lkh_001")
    _logging_enabled = True
except ImportError:
    _logging_enabled = False
    logger.warning("Fabric logging not available: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

log_layer(layer="GOLD", status="START")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

src_sql = '''
CREATE OR REPLACE TABLE gold.fact_reconciliation AS
SELECT DISTINCT
CAST(xxhash64(PeriodId) AS BIGINT) AS PeriodId_key,
CAST(xxhash64(FieldId) AS BIGINT) AS FieldId_key,
CAST(xxhash64(PartnerId) AS BIGINT) AS PartnerId_key,
T.AllocatedBbl,
T.LiftedBbl,
T.LiftedBbl - AllocatedBbl AS VarianceBbl,
CASE WHEN AllocatedBbl = 0 THEN NULL ELSE (LiftedBbl - AllocatedBbl) / AllocatedBbl * 100 END AS VariancePct,
CASE WHEN AllocatedBbl = 0 THEN NULL WHEN ABS((LiftedBbl - AllocatedBbl) / AllocatedBbl * 100) >= 3 THEN 'investigate' WHEN ABS((LiftedBbl - AllocatedBbl) / AllocatedBbl * 100) >= 1.5 THEN 'watch' ELSE 'within-tolerance' END AS Flag,
T.CashCallStatus,
T.CashCallUsd,
T.Manifest_package,
T.Manifest_file
FROM silver.reconciliation T
'''

cfg = {
    'TARGET_TABLE': 'gold.fact_reconciliation',
    'SOURCE_SQL': src_sql,
    'MERGE_KEYS': ['PeriodId_key', 'FieldId_key', 'PartnerId_key'],
    'DELETE_KEYS': [],
    'load_strategy': 'silver_to_gold',
}

spark.sql(src_sql)
logger.info(f"[DIRECT] Created gold.fact_reconciliation ({spark.table('gold.fact_reconciliation').count()} rows)")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

tbl = 'gold.fact_reconciliation'
if 'script' not in tbl:
    run_optimize(tbl)
else:
    logger.warning(f'Skipping optimize for script target {tbl}')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

log_layer(layer="GOLD", status="SUCCESS")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
