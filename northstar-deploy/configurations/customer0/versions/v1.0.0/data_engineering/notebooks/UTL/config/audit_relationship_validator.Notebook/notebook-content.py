# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse_name": "lkh_001",
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

import logging
from datetime import datetime
from pyspark.sql.types import StructType, StructField, StringType, IntegerType, TimestampType, DoubleType, BooleanType
import time
import uuid

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('semantic_model_validator')

validation_start_time = datetime.now()
logger.info(f'Starting semantic model relationship validations at {validation_start_time}')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Create validation results table if it doesn't exist
logger.info('Setting up validation results table')

spark.sql('''
    CREATE TABLE IF NOT EXISTS log.audit_relationship_validator (
        validation_id STRING,
        validation_timestamp TIMESTAMP,
        validation_date STRING,
        relationship_name STRING,
        fact_table STRING,
        fact_column STRING,
        dimension_table STRING,
        dimension_column STRING,
        orphaned_key_count INT,
        sample_orphaned_keys STRING,
        validation_passed BOOLEAN,
        execution_time_ms DOUBLE,
        error_message STRING
    )
    USING DELTA
''')

logger.info('Validation results table ready')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Define result schema once for all validation cells
result_schema = StructType([
    StructField('validation_id', StringType()),
    StructField('validation_timestamp', TimestampType()),
    StructField('validation_date', StringType()),
    StructField('relationship_name', StringType()),
    StructField('fact_table', StringType()),
    StructField('fact_column', StringType()),
    StructField('dimension_table', StringType()),
    StructField('dimension_column', StringType()),
    StructField('orphaned_key_count', IntegerType()),
    StructField('sample_orphaned_keys', StringType()),
    StructField('validation_passed', BooleanType()),
    StructField('execution_time_ms', DoubleType()),
    StructField('error_message', StringType())
])

logger.info('Validation result schema defined')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_fct_forecastaccuracy

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Forecastitempropertyid_key -> To: d_fct_forecastitem_properties.Forecastitempropertyid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Forecastitempropertyid_key -> d_fct_forecastitem_properties.Forecastitempropertyid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Forecastitempropertyid_key
    FROM gold.f_fct_forecastaccuracy
    WHERE Forecastitempropertyid_key IS NOT NULL
    AND Forecastitempropertyid_key NOT IN (
        SELECT Forecastitempropertyid_key FROM gold.d_fct_forecastitem_properties
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '571d18b7', 'f_fct_forecastaccuracy', 'Forecastitempropertyid_key',
         'd_fct_forecastitem_properties', 'Forecastitempropertyid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '571d18b7', 'f_fct_forecastaccuracy', 'Forecastitempropertyid_key',
         'd_fct_forecastitem_properties', 'Forecastitempropertyid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Customerid_key -> To: d_fct_customer.Customerid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Customerid_key -> d_fct_customer.Customerid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Customerid_key
    FROM gold.f_fct_forecastaccuracy
    WHERE Customerid_key IS NOT NULL
    AND Customerid_key NOT IN (
        SELECT Customerid_key FROM gold.d_fct_customer
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '1ab81173', 'f_fct_forecastaccuracy', 'Customerid_key',
         'd_fct_customer', 'Customerid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '1ab81173', 'f_fct_forecastaccuracy', 'Customerid_key',
         'd_fct_customer', 'Customerid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Productid_key -> To: d_fct_product.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Productid_key -> d_fct_product.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_fct_forecastaccuracy
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_fct_product
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'cfb92410', 'f_fct_forecastaccuracy', 'Productid_key',
         'd_fct_product', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'cfb92410', 'f_fct_forecastaccuracy', 'Productid_key',
         'd_fct_product', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Timeframe_key -> To: d_fct_timeframe.Timeframe_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Timeframe_key -> d_fct_timeframe.Timeframe_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Timeframe_key
    FROM gold.f_fct_forecastaccuracy
    WHERE Timeframe_key IS NOT NULL
    AND Timeframe_key NOT IN (
        SELECT Timeframe_key FROM gold.d_fct_timeframe
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '0ce24724', 'f_fct_forecastaccuracy', 'Timeframe_key',
         'd_fct_timeframe', 'Timeframe_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '0ce24724', 'f_fct_forecastaccuracy', 'Timeframe_key',
         'd_fct_timeframe', 'Timeframe_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Forecastgroupid_key -> To: d_fct_forecastgroup.Forecastgroupid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Forecastgroupid_key -> d_fct_forecastgroup.Forecastgroupid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Forecastgroupid_key
    FROM gold.f_fct_forecastaccuracy
    WHERE Forecastgroupid_key IS NOT NULL
    AND Forecastgroupid_key NOT IN (
        SELECT Forecastgroupid_key FROM gold.d_fct_forecastgroup
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '28e53b76', 'f_fct_forecastaccuracy', 'Forecastgroupid_key',
         'd_fct_forecastgroup', 'Forecastgroupid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '28e53b76', 'f_fct_forecastaccuracy', 'Forecastgroupid_key',
         'd_fct_forecastgroup', 'Forecastgroupid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Forecastcycleid -> To: d_fct_forecastcycle.Forecastcycleid

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Forecastcycleid -> d_fct_forecastcycle.Forecastcycleid')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Forecastcycleid
    FROM gold.f_fct_forecastaccuracy
    WHERE Forecastcycleid IS NOT NULL
    AND Forecastcycleid NOT IN (
        SELECT Forecastcycleid FROM gold.d_fct_forecastcycle
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '001ca531', 'f_fct_forecastaccuracy', 'Forecastcycleid',
         'd_fct_forecastcycle', 'Forecastcycleid', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '001ca531', 'f_fct_forecastaccuracy', 'Forecastcycleid',
         'd_fct_forecastcycle', 'Forecastcycleid', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_forecastaccuracy.Month_lag -> To: d_fct_lag.Lag_order

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_forecastaccuracy.Month_lag -> d_fct_lag.Lag_order')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Month_lag
    FROM gold.f_fct_forecastaccuracy
    WHERE Month_lag IS NOT NULL
    AND Month_lag NOT IN (
        SELECT Lag_order FROM gold.d_fct_lag
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '3df047f5', 'f_fct_forecastaccuracy', 'Month_lag',
         'd_fct_lag', 'Lag_order', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '3df047f5', 'f_fct_forecastaccuracy', 'Month_lag',
         'd_fct_lag', 'Lag_order', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_fct_saleshistory

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_saleshistory.Customerid_key -> To: d_fct_customer.Customerid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_saleshistory.Customerid_key -> d_fct_customer.Customerid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Customerid_key
    FROM gold.f_fct_saleshistory
    WHERE Customerid_key IS NOT NULL
    AND Customerid_key NOT IN (
        SELECT Customerid_key FROM gold.d_fct_customer
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a96b7dd1', 'f_fct_saleshistory', 'Customerid_key',
         'd_fct_customer', 'Customerid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a96b7dd1', 'f_fct_saleshistory', 'Customerid_key',
         'd_fct_customer', 'Customerid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_saleshistory.Forecastitempropertyid_key -> To: d_fct_forecastitem_properties.Forecastitempropertyid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_saleshistory.Forecastitempropertyid_key -> d_fct_forecastitem_properties.Forecastitempropertyid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Forecastitempropertyid_key
    FROM gold.f_fct_saleshistory
    WHERE Forecastitempropertyid_key IS NOT NULL
    AND Forecastitempropertyid_key NOT IN (
        SELECT Forecastitempropertyid_key FROM gold.d_fct_forecastitem_properties
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'd7304867', 'f_fct_saleshistory', 'Forecastitempropertyid_key',
         'd_fct_forecastitem_properties', 'Forecastitempropertyid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'd7304867', 'f_fct_saleshistory', 'Forecastitempropertyid_key',
         'd_fct_forecastitem_properties', 'Forecastitempropertyid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_saleshistory.Productid_key -> To: d_fct_product.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_saleshistory.Productid_key -> d_fct_product.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_fct_saleshistory
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_fct_product
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '728f8e08', 'f_fct_saleshistory', 'Productid_key',
         'd_fct_product', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '728f8e08', 'f_fct_saleshistory', 'Productid_key',
         'd_fct_product', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_saleshistory.Timeframe_key -> To: d_fct_timeframe.Timeframe_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_saleshistory.Timeframe_key -> d_fct_timeframe.Timeframe_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Timeframe_key
    FROM gold.f_fct_saleshistory
    WHERE Timeframe_key IS NOT NULL
    AND Timeframe_key NOT IN (
        SELECT Timeframe_key FROM gold.d_fct_timeframe
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '327abeed', 'f_fct_saleshistory', 'Timeframe_key',
         'd_fct_timeframe', 'Timeframe_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '327abeed', 'f_fct_saleshistory', 'Timeframe_key',
         'd_fct_timeframe', 'Timeframe_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_fct_saleshistory.Forecastitemid_key -> To: d_fct_forecastitem.Forecastitemid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_fct_saleshistory.Forecastitemid_key -> d_fct_forecastitem.Forecastitemid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Forecastitemid_key
    FROM gold.f_fct_saleshistory
    WHERE Forecastitemid_key IS NOT NULL
    AND Forecastitemid_key NOT IN (
        SELECT Forecastitemid_key FROM gold.d_fct_forecastitem
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '7770e1e6', 'f_fct_saleshistory', 'Forecastitemid_key',
         'd_fct_forecastitem', 'Forecastitemid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '7770e1e6', 'f_fct_saleshistory', 'Forecastitemid_key',
         'd_fct_forecastitem', 'Forecastitemid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_backorderfact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_backorderfact.Duedate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_backorderfact.Duedate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Duedate_key
    FROM gold.f_opr_backorderfact
    WHERE Duedate_key IS NOT NULL
    AND Duedate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '14735e62', 'f_opr_backorderfact', 'Duedate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '14735e62', 'f_opr_backorderfact', 'Duedate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_backorderfact.Certaintyid_key -> To: d_opr_certainty.Certaintyid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_backorderfact.Certaintyid_key -> d_opr_certainty.Certaintyid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Certaintyid_key
    FROM gold.f_opr_backorderfact
    WHERE Certaintyid_key IS NOT NULL
    AND Certaintyid_key NOT IN (
        SELECT Certaintyid_key FROM gold.d_opr_certainty
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'df051747', 'f_opr_backorderfact', 'Certaintyid_key',
         'd_opr_certainty', 'Certaintyid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'df051747', 'f_opr_backorderfact', 'Certaintyid_key',
         'd_opr_certainty', 'Certaintyid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_backorderfact.Productlocationid_key -> To: d_opr_productlocation.Productlocationid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_backorderfact.Productlocationid_key -> d_opr_productlocation.Productlocationid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productlocationid_key
    FROM gold.f_opr_backorderfact
    WHERE Productlocationid_key IS NOT NULL
    AND Productlocationid_key NOT IN (
        SELECT Productlocationid_key FROM gold.d_opr_productlocation
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '44d098f8', 'f_opr_backorderfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '44d098f8', 'f_opr_backorderfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_backorderfact.Customerid_key -> To: d_opr_customer.Customerid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_backorderfact.Customerid_key -> d_opr_customer.Customerid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Customerid_key
    FROM gold.f_opr_backorderfact
    WHERE Customerid_key IS NOT NULL
    AND Customerid_key NOT IN (
        SELECT Customerid_key FROM gold.d_opr_customer
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '8ae9cdeb', 'f_opr_backorderfact', 'Customerid_key',
         'd_opr_customer', 'Customerid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '8ae9cdeb', 'f_opr_backorderfact', 'Customerid_key',
         'd_opr_customer', 'Customerid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_pplmachineconsfact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplmachineconsfact.Processid_key -> To: d_opr_process.Processid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplmachineconsfact.Processid_key -> d_opr_process.Processid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Processid_key
    FROM gold.f_opr_pplmachineconsfact
    WHERE Processid_key IS NOT NULL
    AND Processid_key NOT IN (
        SELECT Processid_key FROM gold.d_opr_process
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'dbbae4c0', 'f_opr_pplmachineconsfact', 'Processid_key',
         'd_opr_process', 'Processid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'dbbae4c0', 'f_opr_pplmachineconsfact', 'Processid_key',
         'd_opr_process', 'Processid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplmachineconsfact.Fromdate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplmachineconsfact.Fromdate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Fromdate_key
    FROM gold.f_opr_pplmachineconsfact
    WHERE Fromdate_key IS NOT NULL
    AND Fromdate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '25da284b', 'f_opr_pplmachineconsfact', 'Fromdate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '25da284b', 'f_opr_pplmachineconsfact', 'Fromdate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplmachineconsfact.Productlocationid_key -> To: d_opr_productlocation.Productlocationid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplmachineconsfact.Productlocationid_key -> d_opr_productlocation.Productlocationid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productlocationid_key
    FROM gold.f_opr_pplmachineconsfact
    WHERE Productlocationid_key IS NOT NULL
    AND Productlocationid_key NOT IN (
        SELECT Productlocationid_key FROM gold.d_opr_productlocation
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '6588d690', 'f_opr_pplmachineconsfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '6588d690', 'f_opr_pplmachineconsfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_pplmachinefact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplmachinefact.Unitid_key -> To: d_opr_unit.Unitid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplmachinefact.Unitid_key -> d_opr_unit.Unitid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Unitid_key
    FROM gold.f_opr_pplmachinefact
    WHERE Unitid_key IS NOT NULL
    AND Unitid_key NOT IN (
        SELECT Unitid_key FROM gold.d_opr_unit
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'c4fff140', 'f_opr_pplmachinefact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'c4fff140', 'f_opr_pplmachinefact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplmachinefact.Fromdate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplmachinefact.Fromdate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Fromdate_key
    FROM gold.f_opr_pplmachinefact
    WHERE Fromdate_key IS NOT NULL
    AND Fromdate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'c8322a9c', 'f_opr_pplmachinefact', 'Fromdate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'c8322a9c', 'f_opr_pplmachinefact', 'Fromdate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_pplprodlocdemfact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Certaintyid_key -> To: d_opr_certainty.Certaintyid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Certaintyid_key -> d_opr_certainty.Certaintyid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Certaintyid_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Certaintyid_key IS NOT NULL
    AND Certaintyid_key NOT IN (
        SELECT Certaintyid_key FROM gold.d_opr_certainty
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '54a91e96', 'f_opr_pplprodlocdemfact', 'Certaintyid_key',
         'd_opr_certainty', 'Certaintyid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '54a91e96', 'f_opr_pplprodlocdemfact', 'Certaintyid_key',
         'd_opr_certainty', 'Certaintyid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Unitid_key -> To: d_opr_unit.Unitid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Unitid_key -> d_opr_unit.Unitid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Unitid_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Unitid_key IS NOT NULL
    AND Unitid_key NOT IN (
        SELECT Unitid_key FROM gold.d_opr_unit
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '67564883', 'f_opr_pplprodlocdemfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '67564883', 'f_opr_pplprodlocdemfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Productid_key -> To: d_opr_productunitconversion.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Productid_key -> d_opr_productunitconversion.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_productunitconversion
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a6e32fc7', 'f_opr_pplprodlocdemfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a6e32fc7', 'f_opr_pplprodlocdemfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Productid_key -> To: d_opr_producttype.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Productid_key -> d_opr_producttype.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_producttype
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a64eda00', 'f_opr_pplprodlocdemfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a64eda00', 'f_opr_pplprodlocdemfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Fromdate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Fromdate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Fromdate_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Fromdate_key IS NOT NULL
    AND Fromdate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '04aecf2b', 'f_opr_pplprodlocdemfact', 'Fromdate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '04aecf2b', 'f_opr_pplprodlocdemfact', 'Fromdate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocdemfact.Productlocationid_key -> To: d_opr_productlocation.Productlocationid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocdemfact.Productlocationid_key -> d_opr_productlocation.Productlocationid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productlocationid_key
    FROM gold.f_opr_pplprodlocdemfact
    WHERE Productlocationid_key IS NOT NULL
    AND Productlocationid_key NOT IN (
        SELECT Productlocationid_key FROM gold.d_opr_productlocation
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'df96a10d', 'f_opr_pplprodlocdemfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'df96a10d', 'f_opr_pplprodlocdemfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_pplprodlocinvfact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocinvfact.Unitid_key -> To: d_opr_unit.Unitid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocinvfact.Unitid_key -> d_opr_unit.Unitid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Unitid_key
    FROM gold.f_opr_pplprodlocinvfact
    WHERE Unitid_key IS NOT NULL
    AND Unitid_key NOT IN (
        SELECT Unitid_key FROM gold.d_opr_unit
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'bd442bad', 'f_opr_pplprodlocinvfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'bd442bad', 'f_opr_pplprodlocinvfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocinvfact.Productid_key -> To: d_opr_productunitconversion.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocinvfact.Productid_key -> d_opr_productunitconversion.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocinvfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_productunitconversion
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a53be55c', 'f_opr_pplprodlocinvfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'a53be55c', 'f_opr_pplprodlocinvfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocinvfact.Productid_key -> To: d_opr_producttype.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocinvfact.Productid_key -> d_opr_producttype.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocinvfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_producttype
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'e2a01057', 'f_opr_pplprodlocinvfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'e2a01057', 'f_opr_pplprodlocinvfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocinvfact.Fromdate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocinvfact.Fromdate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Fromdate_key
    FROM gold.f_opr_pplprodlocinvfact
    WHERE Fromdate_key IS NOT NULL
    AND Fromdate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '12669a62', 'f_opr_pplprodlocinvfact', 'Fromdate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '12669a62', 'f_opr_pplprodlocinvfact', 'Fromdate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocinvfact.Productlocationid_key -> To: d_opr_productlocation.Productlocationid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocinvfact.Productlocationid_key -> d_opr_productlocation.Productlocationid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productlocationid_key
    FROM gold.f_opr_pplprodlocinvfact
    WHERE Productlocationid_key IS NOT NULL
    AND Productlocationid_key NOT IN (
        SELECT Productlocationid_key FROM gold.d_opr_productlocation
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '2b68573b', 'f_opr_pplprodlocinvfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '2b68573b', 'f_opr_pplprodlocinvfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# ## Validating f_opr_pplprodlocprodfact

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Processid_key -> To: d_opr_process.Processid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Processid_key -> d_opr_process.Processid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Processid_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Processid_key IS NOT NULL
    AND Processid_key NOT IN (
        SELECT Processid_key FROM gold.d_opr_process
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '3304c6bb', 'f_opr_pplprodlocprodfact', 'Processid_key',
         'd_opr_process', 'Processid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '3304c6bb', 'f_opr_pplprodlocprodfact', 'Processid_key',
         'd_opr_process', 'Processid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Unitid_key -> To: d_opr_unit.Unitid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Unitid_key -> d_opr_unit.Unitid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Unitid_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Unitid_key IS NOT NULL
    AND Unitid_key NOT IN (
        SELECT Unitid_key FROM gold.d_opr_unit
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '9efa0545', 'f_opr_pplprodlocprodfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '9efa0545', 'f_opr_pplprodlocprodfact', 'Unitid_key',
         'd_opr_unit', 'Unitid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Productid_key -> To: d_opr_productunitconversion.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Productid_key -> d_opr_productunitconversion.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_productunitconversion
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '2464b499', 'f_opr_pplprodlocprodfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '2464b499', 'f_opr_pplprodlocprodfact', 'Productid_key',
         'd_opr_productunitconversion', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Productid_key -> To: d_opr_producttype.Productid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Productid_key -> d_opr_producttype.Productid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productid_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Productid_key IS NOT NULL
    AND Productid_key NOT IN (
        SELECT Productid_key FROM gold.d_opr_producttype
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '248cdc75', 'f_opr_pplprodlocprodfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '248cdc75', 'f_opr_pplprodlocprodfact', 'Productid_key',
         'd_opr_producttype', 'Productid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Fromdate_key -> To: d_calendar.DateId

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Fromdate_key -> d_calendar.DateId')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Fromdate_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Fromdate_key IS NOT NULL
    AND Fromdate_key NOT IN (
        SELECT DateId FROM gold.d_calendar
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '0fe0e21f', 'f_opr_pplprodlocprodfact', 'Fromdate_key',
         'd_calendar', 'DateId', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), '0fe0e21f', 'f_opr_pplprodlocprodfact', 'Fromdate_key',
         'd_calendar', 'DateId', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Validate relationship From: f_opr_pplprodlocprodfact.Productlocationid_key -> To: d_opr_productlocation.Productlocationid_key

validation_id = str(uuid.uuid4())
_start_time = time.time()
error_msg = None

try:
    logger.info(f'Validating: f_opr_pplprodlocprodfact.Productlocationid_key -> d_opr_productlocation.Productlocationid_key')
    
    # Query to find orphaned keys
    orphan_query = f'''
    SELECT
        DISTINCT Productlocationid_key
    FROM gold.f_opr_pplprodlocprodfact
    WHERE Productlocationid_key IS NOT NULL
    AND Productlocationid_key NOT IN (
        SELECT Productlocationid_key FROM gold.d_opr_productlocation
    )
    LIMIT 100
    '''
    
    # Execute query
    orphan_df = spark.sql(orphan_query)
    orphan_count = orphan_df.count()
    orphan_samples = ','.join([str(row[0]) for row in orphan_df.collect()][:10]) if orphan_count > 0 else ''
    
    _elapsed = (time.time() - _start_time) * 1000
    validation_passed = orphan_count == 0
    
    logger.info(f'Result: {orphan_count} orphaned keys found, passed={validation_passed}')
    
    # Create result row
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'e3239a92', 'f_opr_pplprodlocprodfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', orphan_count, orphan_samples, validation_passed, _elapsed, None)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')
    
except Exception as e:
    logger.error(f'Error validating relationship: {e}')
    error_msg = str(e)
    _elapsed = (time.time() - _start_time) * 1000
    
    # Log error
    _now = datetime.now()
    result_data = [
        (validation_id, _now, _now.strftime('%Y-%m-%d'), 'e3239a92', 'f_opr_pplprodlocprodfact', 'Productlocationid_key',
         'd_opr_productlocation', 'Productlocationid_key', -1, '', False, _elapsed, error_msg)
    ]
    
    spark.createDataFrame(result_data, schema=result_schema).write.mode('append').saveAsTable('log.audit_relationship_validator')

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
