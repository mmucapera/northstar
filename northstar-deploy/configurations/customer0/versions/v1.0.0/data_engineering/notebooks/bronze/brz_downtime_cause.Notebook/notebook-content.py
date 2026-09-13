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
logger = logging.getLogger("bronze.downtime_cause")

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

logger.info('Executing schema-only DDL for bronze.downtime_cause')
target_tbl = 'bronze.downtime_cause'

# Check if source files exist for this model
check_for_model_files(domain, 'downtime_cause', processing_date, extract_id)

spark.sql('DROP TABLE IF EXISTS bronze.downtime_cause')

ddl = """
CREATE OR REPLACE TABLE bronze.downtime_cause
(
    CauseId STRING,
    CauseName STRING,
    Sourcefile STRING,
    Manifest_package STRING,
    Manifest_file STRING,
    Load_date DATE,
    Load_timestamp TIMESTAMP,
    Partitionkey STRING,
    ins_batchid INT,
    upd_batchid INT,
    Exportdate TIMESTAMP,
    valid_from TIMESTAMP,
    valid_to TIMESTAMP,
    is_current BOOLEAN
)
USING delta
"""
status = spark.sql(ddl)
if status is not None:
   status = 1

read_parquet_bulk(
    domain = domain, 
    extract_id = extract_id, 
    search_param = '_downtime_cause_', 
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

tbl = 'bronze.downtime_cause'
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

# Preview — first 10 rows loaded into bronze.downtime_cause
display(spark.sql("SELECT * FROM bronze.downtime_cause LIMIT 10"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
