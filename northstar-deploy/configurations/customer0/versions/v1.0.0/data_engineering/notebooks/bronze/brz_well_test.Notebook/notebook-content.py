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
logger = logging.getLogger("bronze.well_test")

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

logger.info('Executing schema-only DDL for bronze.well_test')
target_tbl = 'bronze.well_test'

# Check if source files exist for this model
check_for_model_files(domain, 'well_test', processing_date, extract_id)

spark.sql('DROP TABLE IF EXISTS bronze.well_test')

ddl = """
CREATE OR REPLACE TABLE bronze.well_test
(
    TestId STRING,
    TestDate DATE,
    PeriodId STRING,
    WellId STRING,
    CompletionId STRING,
    DurationHours DECIMAL(9,2),
    OilRateBopd DECIMAL(18,2),
    GasRateMscfd DECIMAL(18,2),
    WaterCutPct DECIMAL(9,2),
    GorScf DECIMAL(18,2),
    ChokeSize64ths INT,
    ThpPsi DECIMAL(18,2),
    Validity STRING,
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
    search_param = '_well_test_', 
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

tbl = 'bronze.well_test'
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

# Preview — first 10 rows loaded into bronze.well_test
display(spark.sql("SELECT * FROM bronze.well_test LIMIT 10"))

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
