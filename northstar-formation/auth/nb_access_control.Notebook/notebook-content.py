# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# CELL ********************

from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *
import sempy.fabric as fabric
import json
import logging
from datetime import datetime

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

workspace_users = ""
lakehouse_users = ""
workspace_name = ""
customer_name = ""
stage = ""
reports_workspace_id = ""
reports_lakehouse_id = ""
dataset_mappings = ""
permission_matrix = ""
excluded_reports = ""
output_table_name = "user_report_access_control"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def setup_logging():
    """Setup logging configuration"""
    log_format = f'%(asctime)s - {workspace_name} - %(levelname)s - %(message)s'
    logging.basicConfig(
        level=logging.INFO,
        format=log_format,
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    return logging.getLogger(__name__)

logger = setup_logging()
logger.info("=" * 80)
logger.info(f"Starting Access Control Processing")
logger.info(f"Customer: {customer_name}, Stage: {stage}, Workspace: {workspace_name}")
logger.info("=" * 80)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

try:
    # Parse JSON parameters
    dataset_mappings_list = json.loads(dataset_mappings) if dataset_mappings else []
    permission_matrix_list = json.loads(permission_matrix) if permission_matrix else []
    excluded_reports_list = json.loads(excluded_reports) if excluded_reports else []
    
    logger.info(f"Loaded {len(dataset_mappings_list)} dataset mappings")
    logger.info(f"Loaded {len(permission_matrix_list)} permission rules")
    logger.info(f"Loaded {len(excluded_reports_list)} excluded reports")
except Exception as e:
    logger.error(f"Error parsing parameters: {str(e)}")
    raise

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

users_path = f"abfss://{workspace_users}@onelake.dfs.fabric.microsoft.com/{lakehouse_users}"
reports_path = f"abfss://{reports_workspace_id}@onelake.dfs.fabric.microsoft.com/{reports_lakehouse_id}"

logger.info(f"Users path: {users_path}")
logger.info(f"Reports path: {reports_path}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def load_users_data(spark, users_path, logger):
    """Load and process users data"""
    try:
        logger.info("Loading users data...")
        users_df = spark.read.format("delta").load(f"{users_path}/Tables/dbo/users")
        
        # Select and filter relevant columns
        users_df = users_df.select(
            col("PrincipalName").alias("UserEmail"),
            col("UserName"),
            col("GroupName")
        ).filter(col("GroupName").isNotNull()).distinct()
        
        user_count = users_df.count()
        logger.info(f"Loaded {user_count} user-group records")
        
        # Log unique groups for validation
        unique_groups = users_df.select("GroupName").distinct().count()
        logger.info(f"Found {unique_groups} unique groups")
        
        return users_df
    except Exception as e:
        logger.error(f"Error loading users data: {str(e)}")
        raise

def load_reports_data(spark, reports_path, workspace_users, excluded_reports_list, logger):
    """Load and filter reports data. Returns an empty DataFrame if the reports
    table doesn't exist (workspace has no synced reports yet)."""
    reports_schema = StructType([
        StructField("ReportId", StringType(), True),
        StructField("ReportName", StringType(), True),
        StructField("ReportType", StringType(), True),
        StructField("DatasetId", StringType(), True),
        StructField("DatasetName", StringType(), True),
        StructField("DatasetWorkspaceId", StringType(), True),
        StructField("WebUrl", StringType(), True),
        StructField("EmbedUrl", StringType(), True),
        StructField("WorkspaceName", StringType(), True),
        StructField("WorkspaceId", StringType(), True),
        StructField("IsActive", BooleanType(), True),
        StructField("LastSyncDate", TimestampType(), True),
        StructField("SyncedBy", StringType(), True),
    ])
    reports_table_path = f"{reports_path}/Tables/dbo/workspace_reports_insights"
    try:
        logger.info("Loading reports data...")
        workspace_reports_insights_df = spark.read.format("delta").load(reports_table_path)
    except Exception as e:
        msg = str(e)
        # Missing reports lakehouse table is expected when a workspace has no reports.
        if ("PATH_NOT_FOUND" in msg
                or "Path does not exist" in msg
                or "is not a Delta table" in msg
                or "DELTA_MISSING_DELTA_TABLE" in msg):
            logger.warning(
                f"Reports table not found at {reports_table_path} — treating as no "
                f"reports. Access-control output will be empty for this workspace."
            )
            return spark.createDataFrame([], reports_schema)
        logger.error(f"Error loading reports data: {msg}")
        raise

    try:
        # Filter for the workspace being processed and exclude reports starting with Hide_/HIDE_/hide_
        reports_df = workspace_reports_insights_df.filter(
            (col("WorkspaceId") == workspace_users) &
            (col("IsActive") == True) &
            (~col("ReportName").rlike("^(Hide_|HIDE_|hide_)"))
        ).select(
            "ReportId", "ReportName", "ReportType", 
            "DatasetId", "DatasetName", "DatasetWorkspaceId", "WebUrl",
            "EmbedUrl", "WorkspaceName", "WorkspaceId", 
            "IsActive", "LastSyncDate", "SyncedBy"
        )
        
        initial_count = workspace_reports_insights_df.filter(
            (col("WorkspaceId") == workspace_users) &
            (col("IsActive") == True)
        ).count()
        
        count_after_hide_filter = reports_df.count()
        hidden_count = initial_count - count_after_hide_filter
        
        if hidden_count > 0:
            logger.info(f"Found {initial_count} active reports in workspace")
            logger.info(f"Automatically excluded {hidden_count} reports starting with Hide_/HIDE_/hide_")
            logger.info(f"Reports remaining after pattern exclusion: {count_after_hide_filter}")
        else:
            logger.info(f"Found {initial_count} active reports in workspace (none starting with Hide_/HIDE_/hide_)")
        
        # Filter out explicitly excluded reports with detailed logging
        if excluded_reports_list:
            logger.info(f"Explicit exclusion list contains {len(excluded_reports_list)} report name(s): {excluded_reports_list}")
            
            # Find which reports actually exist in the workspace
            existing_report_names = [row['ReportName'] for row in reports_df.select('ReportName').distinct().collect()]
            actually_excluded = [name for name in excluded_reports_list if name in existing_report_names]
            not_found = [name for name in excluded_reports_list if name not in existing_report_names]
            
            if actually_excluded:
                logger.info(f"Reports found and will be explicitly excluded: {actually_excluded}")
                reports_df = reports_df.filter(~col("ReportName").isin(excluded_reports_list))
            
            if not_found:
                logger.warning(f"Reports in exclusion list but not found in workspace: {not_found}")
            
            final_count = reports_df.count()
            excluded_count = count_after_hide_filter - final_count
            logger.info(f"Explicitly excluded {excluded_count} report(s)")
            logger.info(f"Final report count: {final_count}")
        else:
            logger.info("No explicit reports excluded (empty exclusion list)")
            final_count = reports_df.count()
            logger.info(f"Final report count: {final_count}")
        
        return reports_df
    except Exception as e:
        logger.error(f"Error loading reports data: {str(e)}")
        raise


def create_dataset_mapping(spark, dataset_mappings_list, logger):
    """Create dataset to category mapping dataframe"""
    try:
        logger.info("Creating dataset category mapping...")
        
        if not dataset_mappings_list:
            logger.warning("No dataset mappings provided")
            return spark.createDataFrame([], StructType([
                StructField("DatasetName", StringType(), True),
                StructField("ModelCategory", StringType(), True)
            ]))
        
        dataset_mapping_df = spark.createDataFrame(
            dataset_mappings_list, 
            ['DatasetName', 'ModelCategory']
        )
        
        logger.info("Dataset to Category Mapping:")
        dataset_mapping_df.show(truncate=False)
        
        return dataset_mapping_df
    except Exception as e:
        logger.error(f"Error creating dataset mapping: {str(e)}")
        raise

def create_permission_matrix(spark, permission_matrix_list, logger):
    """Create permission matrix dataframe"""
    try:
        logger.info("Creating permission matrix...")
        
        if not permission_matrix_list:
            logger.warning("No permission matrix provided")
            return spark.createDataFrame([], StructType([
                StructField("ModelCategory", StringType(), True),
                StructField("GroupName", StringType(), True),
                StructField("HasAccess", IntegerType(), True)
            ]))
        
        permissions_df = spark.createDataFrame(
            permission_matrix_list, 
            ['ModelCategory', 'GroupName', 'HasAccess']
        )
        
        # Get only active permissions
        active_permissions = permissions_df.filter(col("HasAccess") == 1)
        
        active_count = active_permissions.count()
        logger.info(f"Created {active_count} active permission rules")
        
        return active_permissions
    except Exception as e:
        logger.error(f"Error creating permission matrix: {str(e)}")
        raise

def map_datasets_to_reports(spark, reports_df, reports_path, dataset_mapping_df, logger):
    """Map datasets to reports and add categories"""
    try:
        logger.info("Mapping datasets to reports...")
        
        reports_with_categories = reports_df.join(
            dataset_mapping_df,
            on="DatasetName",
            how="left"
        )
        
        # Log statistics
        with_category = reports_with_categories.filter(col("ModelCategory").isNotNull()).count()
        without_category = reports_with_categories.filter(col("ModelCategory").isNull()).count()
        logger.info(f"Reports with category: {with_category}")
        logger.info(f"Reports without category: {without_category}")
        
        if without_category > 0:
            logger.warning("Reports without category detected. Dataset names may not match mapping.")
            # Show which dataset names don't have mappings
            unmapped = reports_with_categories.filter(col("ModelCategory").isNull()) \
                .select("DatasetName").distinct().collect()
            logger.warning(f"Unmapped dataset names: {[row['DatasetName'] for row in unmapped]}")
        
        return reports_with_categories
    except Exception as e:
        logger.error(f"Error mapping datasets to reports: {str(e)}")
        raise

def create_user_report_access(users_df, reports_with_categories, active_permissions, customer_name, stage, logger):
    """Create the final user report access control table"""
    try:
        logger.info("Creating user report access control...")
        
        # Join users with their active permissions
        user_permissions = users_df.join(
            active_permissions,
            on="GroupName",
            how="inner"
        )
        
        logger.info(f"User-permission combinations: {user_permissions.count()}")
        
        # Create access control records
        user_report_access = user_permissions.select(
            col("UserEmail"),
            col("UserName"), 
            col("GroupName"),
            col("ModelCategory").alias("PermissionModelCategory")
        ).join(
            reports_with_categories.select(
                col("ReportId"),
                col("ReportName"),
                col("ReportType"),
                col("DatasetId"),
                col("DatasetName"),
                col("ModelCategory").alias("ReportModelCategory"),
                col("WorkspaceId"),
                col("WorkspaceName"),
                col("WebUrl"),
                col("EmbedUrl")
            ),
            col("PermissionModelCategory") == col("ReportModelCategory"),
            "inner"
        ).select(
            col("UserEmail"),
            col("UserName"),
            col("GroupName"),
            col("ReportModelCategory").alias("ModelCategory"),
            col("ReportId"),
            col("ReportName"),
            col("ReportType"),
            col("DatasetId"),
            col("DatasetName"),
            col("WorkspaceId"),
            col("WorkspaceName"),
            col("WebUrl"),
            col("EmbedUrl"),
            lit(1).alias("HasAccess"),
            concat_ws(" - ", 
                lit("Access via"), 
                col("GroupName"), 
                lit("group to"), 
                col("ReportModelCategory")
            ).alias("AccessReason"),
            lit(customer_name).alias("Customer"),
            lit(stage).alias("Stage"),
            current_timestamp().alias("LastUpdated"),
            lit(workspace_name).alias("ProcessedWorkspace")
        ).distinct()
        
        # Remove duplicates based on UserEmail and ReportId combination
        # This ensures only one access record per user-report pair
        initial_count = user_report_access.count()
        user_report_access = user_report_access.dropDuplicates(["UserEmail", "ReportId"])
        final_count = user_report_access.count()
        
        duplicates_removed = initial_count - final_count
        if duplicates_removed > 0:
            logger.info(f"Removed {duplicates_removed} duplicate user-report combinations")
        
        logger.info(f"Created {final_count} unique access control records")
        
        return user_report_access
    except Exception as e:
        logger.error(f"Error creating user report access: {str(e)}")
        raise

def save_results(user_report_access, users_path, output_table_name, logger):
    """Save the results to delta table"""
    try:
        logger.info(f"Saving results to {output_table_name}...")
        
        # Write to delta table with overwrite mode
        user_report_access.write \
            .mode("overwrite") \
            .option("overwriteSchema", "true") \
            .format("delta") \
            .save(f"{users_path}/Tables/dbo/{output_table_name}")
        
        logger.info(f"Successfully saved {output_table_name}")
    except Exception as e:
        logger.error(f"Error saving results: {str(e)}")
        raise

def generate_summary_statistics(user_report_access, logger):
    """Generate and log summary statistics"""
    try:
        logger.info("=" * 80)
        logger.info("ACCESS CONTROL SUMMARY")
        logger.info("=" * 80)
        
        # Basic statistics
        total_users = user_report_access.select('UserEmail').distinct().count()
        total_reports = user_report_access.select('ReportId').distinct().count()
        total_records = user_report_access.count()
        
        logger.info(f"Total unique users with access: {total_users}")
        logger.info(f"Total unique reports with access: {total_reports}")
        logger.info(f"Total access records: {total_records}")
        
        # User access summary
        user_access_summary = user_report_access.groupBy("UserEmail", "UserName").agg(
            countDistinct("ReportId").alias("ReportsAccessible"),
            collect_set("GroupName").alias("Groups"),
            collect_set("ModelCategory").alias("AccessibleCategories")
        )
        
        # Reports per user statistics
        reports_per_user = user_access_summary.agg(
            avg("ReportsAccessible").alias("AvgReportsPerUser"),
            min("ReportsAccessible").alias("MinReportsPerUser"),
            max("ReportsAccessible").alias("MaxReportsPerUser")
        ).collect()[0]
        
        logger.info(f"Average reports per user: {reports_per_user['AvgReportsPerUser']:.1f}")
        logger.info(f"Min reports per user: {reports_per_user['MinReportsPerUser']}")
        logger.info(f"Max reports per user: {reports_per_user['MaxReportsPerUser']}")
        
        # Category distribution
        category_dist = user_report_access.groupBy("ModelCategory").count().orderBy("count", ascending=False)
        logger.info("\nAccess by Category:")
        for row in category_dist.collect():
            logger.info(f"  {row['ModelCategory']}: {row['count']} records")
        
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Error generating summary statistics: {str(e)}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

def main():
    """Main execution function"""
    start_time = datetime.now()
    
    try:
        # Initialize Spark session
        spark = SparkSession.builder \
            .appName(f"AccessControl_{workspace_name}") \
            .getOrCreate()
        
        # Step 1: Load data
        users_df = load_users_data(spark, users_path, logger)
        reports_df = load_reports_data(spark, reports_path, workspace_users, excluded_reports_list, logger) 
        
        # Step 2: Create mappings
        dataset_mapping_df = create_dataset_mapping(spark, dataset_mappings_list, logger)
        active_permissions = create_permission_matrix(spark, permission_matrix_list, logger)
        
        # Step 3: Map datasets to reports
        reports_with_categories = map_datasets_to_reports(
            spark, reports_df, reports_path, dataset_mapping_df, logger
        )
        
        # Step 4: Create user report access
        user_report_access = create_user_report_access(
            users_df, reports_with_categories, active_permissions,
            customer_name, stage, logger
        )
        
        # Step 5: Save results
        save_results(user_report_access, users_path, output_table_name, logger)
        
        # Step 6: Generate summary
        generate_summary_statistics(user_report_access, logger)
        
        # Calculate execution time
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        logger.info(f"Processing completed successfully in {duration:.2f} seconds")
        logger.info("=" * 80)
        
    except Exception as e:
        logger.error(f"Processing failed: {str(e)}")
        raise
    finally:
        # Clean up Spark session if needed
        pass

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

if __name__ == "__main__":
    main()

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
