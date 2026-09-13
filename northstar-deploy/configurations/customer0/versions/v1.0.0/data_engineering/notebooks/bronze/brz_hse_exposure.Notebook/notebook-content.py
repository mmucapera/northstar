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
logger = logging.getLogger("bronze.hse_exposure")

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

logger.info('Executing schema-only DDL for bronze.hse_exposure')
target_tbl = 'bronze.hse_exposure'

# Check if source files exist for this model
check_for_model_files(domain, 'hse_exposure', processing_date, extract_id)

spark.sql('DROP TABLE IF EXISTS bronze.hse_exposure')

ddl = """
CREATE OR REPLACE TABLE bronze.hse_exposure
(
    PeriodId STRING,
    HoursWorked DECIMAL(18,2),
    Sourcefile STRING,
    Manifest_package STRING,
    Manifest_file STRING,
    Load_date DATE,
    Load_timestamp TIMESTAMP,
    Partitionkey STRING,
    ins_batchid INT,
    upd_batchid INT,
    Exportdate TIMESTAMP
)
USING delta
"""
status = spark.sql(ddl)
if status is not None:
   status = 1

read_parquet_bulk(
    domain = domain, 
    extract_id = extract_id, 
    search_param = '_hse_exposure_', 
    processing_date = processing_date, 
    target_tbl = target_tbl, 
    batchid = batchid
)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

tbl = 'bronze.hse_exposure'
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

# Preview — first 10 rows loaded into bronze.hse_exposure
display(spark.sql("SELECT * FROM bronze.hse_exposure LIMIT 10"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
