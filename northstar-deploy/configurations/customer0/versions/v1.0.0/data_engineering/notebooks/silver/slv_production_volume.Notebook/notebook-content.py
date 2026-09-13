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
logger = logging.getLogger("silver.production_volume")

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

log_layer(layer="SILVER", status="START")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Duplicate check on silver.production_volume (pre-src_sql)
if spark.catalog.tableExists('silver.production_volume'):
    _check_source_duplicates('silver.production_volume', ['PeriodId', 'WellId'])
else:
    logger.info(f'[DQ_DUPLICATES] silver.production_volume does not exist yet — skipping pre-src_sql check')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

src_sql = '''
SELECT DISTINCT
T.PeriodId,
T.WellId,
T.FieldId,
T.FacilityId,
T.OilBbl,
T.GasMscf,
T.WaterBbl,
T.OnstreamHours,
T.WaterCutPct,
T.Sourcefile,
T.Manifest_package,
T.Manifest_file,
T.Load_date,
T.Load_timestamp,
T.Partitionkey,
T.ins_batchid,
T.upd_batchid,
T.Exportdate
FROM bronze.production_volume T
'''

cfg = {
    'SOURCE_TABLE': 'bronze.production_volume',
    'TARGET_TABLE': 'silver.production_volume',
    'SOURCE_SQL': src_sql,
    'MERGE_KEYS': ['PeriodId', 'WellId'],
    'DELETE_KEYS': [],
    'load_strategy': 'bronze_to_silver_latest',
}

status = framework_execute(cfg)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Duplicate check on silver.production_volume (post-src_sql)
if spark.catalog.tableExists('silver.production_volume'):
    _check_source_duplicates('silver.production_volume', ['PeriodId', 'WellId'])
else:
    logger.info(f'[DQ_DUPLICATES] silver.production_volume does not exist yet — skipping post-src_sql check')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

tbl = 'silver.production_volume'
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

log_layer(layer="SILVER", status="SUCCESS")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
