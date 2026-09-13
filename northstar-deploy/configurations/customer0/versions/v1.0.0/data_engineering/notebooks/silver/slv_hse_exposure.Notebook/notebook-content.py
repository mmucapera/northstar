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
logger = logging.getLogger("silver.hse_exposure")

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

# Duplicate check on silver.hse_exposure (pre-src_sql)
if spark.catalog.tableExists('silver.hse_exposure'):
    _check_source_duplicates('silver.hse_exposure', ['PeriodId'])
else:
    logger.info(f'[DQ_DUPLICATES] silver.hse_exposure does not exist yet — skipping pre-src_sql check')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

src_sql = '''
SELECT DISTINCT
T.PeriodId,
T.HoursWorked,
T.Sourcefile,
T.Manifest_package,
T.Manifest_file,
T.Load_date,
T.Load_timestamp,
T.Partitionkey,
T.ins_batchid,
T.upd_batchid,
T.Exportdate
FROM bronze.hse_exposure T
'''

cfg = {
    'SOURCE_TABLE': 'bronze.hse_exposure',
    'TARGET_TABLE': 'silver.hse_exposure',
    'SOURCE_SQL': src_sql,
    'MERGE_KEYS': ['PeriodId'],
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

# Duplicate check on silver.hse_exposure (post-src_sql)
if spark.catalog.tableExists('silver.hse_exposure'):
    _check_source_duplicates('silver.hse_exposure', ['PeriodId'])
else:
    logger.info(f'[DQ_DUPLICATES] silver.hse_exposure does not exist yet — skipping post-src_sql check')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

tbl = 'silver.hse_exposure'
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
