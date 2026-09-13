# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
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

# Get current workspace name and store it in variables
import sempy.fabric as fabric

# Current workspace ID from notebook runtime context
current_workspace_id = notebookutils.runtime.context['currentWorkspaceId']

# Look up the workspace name via Fabric APIs
ws_df = fabric.list_workspaces()
current_workspace_name = ws_df.loc[ws_df['Id'] == current_workspace_id, 'Name'].iloc[0]

# Store in list for downstream use
specific_workspace_list = [current_workspace_name]

print(f"Current workspace ID: {current_workspace_id}")
print(f"Current workspace name: {current_workspace_name}")
print(f"specific_workspace_list: {specific_workspace_list}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

ctx = notebookutils.runtime.context
print(ctx['defaultLakehouseName'])
print(ctx['defaultLakehouseId'])


# Workspace/Lakehouse identifiers
REPORTS_WORKSPACE_ID = current_workspace_id
LAKEHOUSE_ID = ctx['defaultLakehouseId']

# Customer configuration (JSON strings)
LAKEHOUSE_NAME = ctx['defaultLakehouseName']
DATASET_MAPPINGS = "[[\"SM_FCT\", \"FCT\"], [\"SM_OPR\", \"OPR\"]]"
PERMISSION_MATRIX = "[[\"FCT\", \"OMP_EVERYONE\", 1],[\"OPR\", \"OMP_EVERYONE\", 1],[\"FCT\", \"AN_EveryOne\", 1],[\"OPR\", \"AN_EveryOne\", 1]]"
EXCLUDED_REPORTS = "[]"

# Processing configuration
TARGET_NOTEBOOK = "nb_access_control"
OUTPUT_TABLE_NAME = "user_report_access_control"
TIMEOUT_PER_CELL = 300
RETRY_COUNT = 1
RETRY_INTERVAL = 0
DAG_TIMEOUT = 43200
DAG_CONCURRENCY = 5

## ALL REPORTS NO FILTER ON PATTERN

# ctx = notebookutils.runtime.context
# print(ctx['defaultLakehouseName'])
# print(ctx['defaultLakehouseId'])


# # Workspace/Lakehouse identifiers
# REPORTS_WORKSPACE_ID = current_workspace_id
# LAKEHOUSE_ID = ctx['defaultLakehouseId']

# # Customer configuration (JSON strings)
# LAKEHOUSE_NAME = ctx['defaultLakehouseName']

# # Grant every report in this workspace to OMP_EVERYONE. Dataset mappings are
# # auto-discovered from the workspace_reports_insights table (populated by
# # nb_fetch_reports upstream), so no per-model list needs to be maintained.
# import json
# _datasets = [
#     r.DatasetName for r in spark.sql(
#         "SELECT DISTINCT DatasetName FROM dbo.workspace_reports_insights "
#         "WHERE DatasetName IS NOT NULL AND DatasetName <> ''"
#     ).collect()
# ]
# print(f"Discovered {len(_datasets)} distinct semantic model(s) in this workspace")
# DATASET_MAPPINGS = json.dumps([[name, "ALL"] for name in _datasets])
# PERMISSION_MATRIX = "[[\"ALL\", \"OMP_EVERYONE\", 1]]"
# EXCLUDED_REPORTS = "[]"

# # Processing configuration
# TARGET_NOTEBOOK = "nb_access_control"
# OUTPUT_TABLE_NAME = "user_report_access_control"
# TIMEOUT_PER_CELL = 300
# RETRY_COUNT = 1
# RETRY_INTERVAL = 0
# DAG_TIMEOUT = 43200
# DAG_CONCURRENCY = 5

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import pandas as pd
import sempy.fabric as fabric
import json
import pprint as pp
from datetime import datetime
import logging

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

import json

# Parse JSON parameters
DATASET_MAPPINGS = json.loads(DATASET_MAPPINGS) if isinstance(DATASET_MAPPINGS, str) else DATASET_MAPPINGS
PERMISSION_MATRIX = json.loads(PERMISSION_MATRIX) if isinstance(PERMISSION_MATRIX, str) else PERMISSION_MATRIX
EXCLUDED_REPORTS = json.loads(EXCLUDED_REPORTS) if isinstance(EXCLUDED_REPORTS, str) else EXCLUDED_REPORTS

# Validate required parameters
if not REPORTS_WORKSPACE_ID:
    raise ValueError("REPORTS_WORKSPACE_ID is required")
if not LAKEHOUSE_ID:
    raise ValueError("LAKEHOUSE_ID is required")
if not LAKEHOUSE_NAME:
    raise ValueError("LAKEHOUSE_NAME is required")
if not DATASET_MAPPINGS:
    raise ValueError("DATASET_MAPPINGS cannot be empty")
if not PERMISSION_MATRIX:
    raise ValueError("PERMISSION_MATRIX cannot be empty")

# Build config objects for use in functions
CUSTOMER_CONFIG = {
    "lakehouse": LAKEHOUSE_NAME,
    "reports_workspace_id": REPORTS_WORKSPACE_ID,
    "reports_lakehouse_id": LAKEHOUSE_ID,
    "dataset_mappings": DATASET_MAPPINGS,
    "permission_matrix": PERMISSION_MATRIX,
    "excluded_reports": EXCLUDED_REPORTS,
}

PROCESSING_CONFIG = {
    "target_notebook": TARGET_NOTEBOOK,
    "output_table_name": OUTPUT_TABLE_NAME,
    "timeout_per_cell": TIMEOUT_PER_CELL,
    "retry_count": RETRY_COUNT,
    "retry_interval": RETRY_INTERVAL,
    "dag_timeout": DAG_TIMEOUT,
    "dag_concurrency": DAG_CONCURRENCY,
}

print(f"Reports Workspace ID: {REPORTS_WORKSPACE_ID}")
print(f"Lakehouse ID: {LAKEHOUSE_ID}")
print(f"Dataset Mappings: {DATASET_MAPPINGS}")
print(f"Permission Matrix: {PERMISSION_MATRIX}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def setup_logging():
    """Setup logging configuration"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

def build_dag_activity(ws_name, workspace_id, lakehouse_id, customer_config, processing_config):
    """Build a DAG activity for a workspace"""
    return {
        "name": ws_name,
        "path": processing_config["target_notebook"],
        "timeoutPerCellInSeconds": processing_config["timeout_per_cell"],
        "retryPolicy": {
            "retryCount": processing_config["retry_count"],
            "retryIntervalInSeconds": processing_config["retry_interval"]
        },
        "args": {
            "workspace_name": ws_name,
            "workspace_users": workspace_id,
            "lakehouse_users": lakehouse_id,
            "reports_workspace_id": customer_config["reports_workspace_id"],
            "reports_lakehouse_id": customer_config["reports_lakehouse_id"],
            "dataset_mappings": json.dumps(customer_config["dataset_mappings"]),
            "permission_matrix": json.dumps(customer_config["permission_matrix"]),
            "excluded_reports": json.dumps(customer_config["excluded_reports"]),
            "output_table_name": processing_config["output_table_name"]
        }
    }

def execute_dag(dag, logger):
    """Execute the DAG using mssparkutils"""
    try:
        logger.info(f"Executing DAG with {len(dag['activities'])} activities")
        result = mssparkutils.notebook.runMultiple(dag)
        logger.info("DAG execution completed successfully")
        return result
    except Exception as e:
        logger.error(f"DAG execution failed: {str(e)}")
        raise

def get_workspace_name(workspace_id, logger):
    """Get workspace name from workspace ID"""
    try:
        df = fabric.list_workspaces()
        ws_df = df[df['Id'] == workspace_id]
        if ws_df.empty:
            logger.warning(f"Workspace with ID {workspace_id} not found")
            return None
        return ws_df['Name'].iloc[0]
    except Exception as e:
        logger.error(f"Error getting workspace name: {str(e)}")
        return None

def main():
    """Main orchestration function"""
    logger = setup_logging()
    
    logger.info("=" * 80)
    logger.info("Starting Access Control Processing Orchestration")
    logger.info(f"Reports Workspace ID: {REPORTS_WORKSPACE_ID}")
    logger.info(f"Lakehouse ID: {LAKEHOUSE_ID}")
    logger.info("=" * 80)
    
    # Get workspace name from ID
    ws_name = get_workspace_name(REPORTS_WORKSPACE_ID, logger)
    if not ws_name:
        raise ValueError(f"Could not find workspace with ID: {REPORTS_WORKSPACE_ID}")
    
    logger.info(f"Processing workspace: {ws_name}")
    
    # Build DAG with single activity
    activity = build_dag_activity(
        ws_name, 
        REPORTS_WORKSPACE_ID, 
        LAKEHOUSE_ID, 
        CUSTOMER_CONFIG, 
        PROCESSING_CONFIG
    )
    
    dag = {
        "activities": [activity],
        "timeoutInSeconds": PROCESSING_CONFIG["dag_timeout"],
        "concurrency": PROCESSING_CONFIG["dag_concurrency"]
    }
    
    logger.info("\nDAG Structure:")
    pp.pprint(dag, depth=2)
    
    # Execute the DAG
    start_time = datetime.now()
    result = execute_dag(dag, logger)
    end_time = datetime.now()
    
    # Report results
    duration = (end_time - start_time).total_seconds()
    logger.info("=" * 80)
    logger.info("Execution Summary")
    logger.info(f"Total duration: {duration:.2f} seconds")
    logger.info(f"Workspace processed: {ws_name}")
    logger.info("=" * 80)
    
    return result

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    result = main()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
