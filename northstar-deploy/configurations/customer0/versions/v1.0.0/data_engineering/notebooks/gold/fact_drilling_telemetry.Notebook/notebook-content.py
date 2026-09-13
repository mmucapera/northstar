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
logger = logging.getLogger("gold.fact_drilling_telemetry")

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
CREATE OR REPLACE TABLE gold.fact_drilling_telemetry AS
SELECT DISTINCT
CAST(xxhash64(WellId) AS BIGINT) AS WellId_key,
CAST(xxhash64(WellboreId) AS BIGINT) AS WellboreId_key,
T.ReportDate,
T.DepthM,
T.RopMPerHr,
T.WobKlbs,
T.Rpm,
T.MudWeightPpg,
T.FlowRateGpm,
T.Npt,
T.Manifest_package,
T.Manifest_file
FROM silver.drilling_telemetry T
'''

cfg = {
    'TARGET_TABLE': 'gold.fact_drilling_telemetry',
    'SOURCE_SQL': src_sql,
    'MERGE_KEYS': ['WellId_key', 'WellboreId_key', 'ReportDate'],
    'DELETE_KEYS': [],
    'load_strategy': 'silver_to_gold',
}

spark.sql(src_sql)
logger.info(f"[DIRECT] Created gold.fact_drilling_telemetry ({spark.table('gold.fact_drilling_telemetry').count()} rows)")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

tbl = 'gold.fact_drilling_telemetry'
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
