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

# =============================================
# Fetch All Workspaces and Reports in Microsoft Fabric
# Creates workspace_reports_insights table with all required columns
# =============================================

import sempy.fabric as fabric
import pandas as pd
from pyspark.sql import SparkSession
import pyspark.sql.functions as F
from pyspark.sql.types import *
from datetime import datetime
import time

# Initialize Spark session
spark = SparkSession.builder.appName("FetchWorkspaceReports").getOrCreate()

print("Starting workspace and reports discovery...")
print("=" * 50)

# =============================================
# CONFIGURATION
# =============================================

# Option 1: Fetch ALL workspaces you have access to
fetch_all_workspaces = False
specific_workspace_list = [x.strip() for x in specific_workspace_list]

# Filter options for workspaces (when fetching all)
include_personal_workspaces = False  # Set to True to include "My workspace"
workspace_name_pattern = None  # Set pattern like "CUS-*" to filter workspace names

# =============================================
# 1. Get All Workspaces
# =============================================

print("\n1. Fetching workspaces...")

try:
    if fetch_all_workspaces:
        # Get all workspaces using Fabric API
        all_workspaces_df = fabric.list_workspaces()
        
        # Filter out personal workspaces if needed
        if not include_personal_workspaces:
            all_workspaces_df = all_workspaces_df[all_workspaces_df['Type'] != 'PersonalGroup']
        
        # Filter out admin workspaces (NEW)
        all_workspaces_df = all_workspaces_df[all_workspaces_df['Type'] != 'AdminInsights']
        
        # Filter out specific system workspaces (NEW)
        excluded_workspaces = [
            'Microsoft Fabric Capacity Metrics',
            'Microsoft Fabric Chargeback Reporting'
        ]
        all_workspaces_df = all_workspaces_df[~all_workspaces_df['Name'].isin(excluded_workspaces)]
        
        # Apply name pattern filter if specified
        if workspace_name_pattern:
            import fnmatch
            pattern_filter = all_workspaces_df['Name'].apply(
                lambda x: fnmatch.fnmatch(x, workspace_name_pattern)
            )
            all_workspaces_df = all_workspaces_df[pattern_filter]
        
        workspace_list = all_workspaces_df['Name'].tolist()
        workspace_id_map = dict(zip(all_workspaces_df['Name'], all_workspaces_df['Id']))
        
        print(f"   Found {len(workspace_list)} workspaces")
        print(f"   Workspace types: {all_workspaces_df['Type'].value_counts().to_dict()}")
    else:
        workspace_list = specific_workspace_list
        workspace_id_map = {}  # Will be populated as we process
        print(f"   Using specific list of {len(workspace_list)} workspaces")
        
except Exception as e:
    print(f"   Error fetching workspaces: {str(e)}")
    print("   Falling back to specific workspace list")
    workspace_list = specific_workspace_list
    workspace_id_map = {}

# =============================================
# 1.5. Build Dataset Name Mapping
# =============================================

print("\n1.5. Building dataset name mapping...")

dataset_name_map = {}  # Maps DatasetId to DatasetName

for workspace_name in workspace_list:
    try:
        # Fetch datasets for this workspace
        datasets_df = fabric.list_datasets(workspace=workspace_name)
        
        if not datasets_df.empty:
            # Correct column names: 'Dataset ID' and 'Dataset Name' (with spaces!)
            for _, row in datasets_df.iterrows():
                dataset_id = row.get('Dataset ID', '')  # Changed from 'Id'
                dataset_name = row.get('Dataset Name', '')  # Changed from 'Name'
                if dataset_id:
                    dataset_name_map[dataset_id] = dataset_name
                    
            print(f"   Mapped {len(datasets_df)} datasets from {workspace_name}")
                    
    except Exception as e:
        # Skip workspaces with permission errors silently
        continue

print(f"   Total datasets mapped: {len(dataset_name_map)}")

# =============================================
# 2. Fetch Reports from Each Workspace
# =============================================

print("\n2. Fetching reports from workspaces...")

all_reports_data = []
failed_workspaces = []
reports_summary = {}

for idx, workspace_name in enumerate(workspace_list, 1):
    try:
        print(f"   [{idx}/{len(workspace_list)}] Processing: {workspace_name}")
        
        # Get reports from current workspace
        reports_df = fabric.list_reports(workspace=workspace_name)
        
        if reports_df.empty:
            print(f"      No reports found")
            continue
        
        # Debug: Print available columns
        print(f"      Available columns: {reports_df.columns.tolist()}")
        
        # Based on the API response, we have these columns with spaces:
        # ['Id', 'Report Type', 'Name', 'Web Url', 'Embed Url', 
        #  'Is From Pbix', 'Is Owned By Me', 'Dataset Id', 'Dataset Workspace Id', 
        #  'Users', 'Subscriptions']
        
        # Rename columns to match required schema
        column_mapping = {
            'Id': 'ReportId',
            'Name': 'ReportName',
            'Report Type': 'ReportType',
            'Dataset Id': 'DatasetId',
            'Dataset Name': 'DatasetName',
            'Dataset Workspace Id': 'DatasetWorkspaceId',
            'Web Url': 'WebUrl',
            'Embed Url': 'EmbedUrl',
            'Is From Pbix': 'IsFromPbix',
            'Is Owned By Me': 'IsOwnedByMe'
        }
        
        # Apply column renames
        for old_name, new_name in column_mapping.items():
            if old_name in reports_df.columns:
                reports_df = reports_df.rename(columns={old_name: new_name})
        
        # Add workspace information
        reports_df['WorkspaceName'] = workspace_name
        
        # Try to get workspace ID if not already in map
        if workspace_name not in workspace_id_map:
            try:
                ws_info = fabric.list_workspaces()
                ws_info = ws_info[ws_info['Name'] == workspace_name]
                if not ws_info.empty:
                    workspace_id_map[workspace_name] = ws_info.iloc[0]['Id']
            except:
                pass
        
        reports_df['WorkspaceId'] = workspace_id_map.get(workspace_name, '')
        reports_df['DatasetName'] = reports_df['DatasetId'].map(dataset_name_map)
        
        # Add system columns
        reports_df['IsActive'] = True
        reports_df['LastSyncDate'] = pd.Timestamp.now()
        reports_df['SyncedBy'] = 'SYSTEM_SYNC'
        
        # Select only the columns we need for workspace_reports_insights table
        required_columns = [
            'ReportId',
            'ReportName', 
            'ReportType',
            'DatasetId',
            'DatasetName',  # NEW
            'DatasetWorkspaceId',
            'WebUrl',
            'EmbedUrl',
            'IsFromPbix',
            'IsOwnedByMe',
            'WorkspaceName',
            'WorkspaceId',
            'IsActive',
            'LastSyncDate',
            'SyncedBy'
        ]
        
        # Check which columns are present and select them
        available_columns = [col for col in required_columns if col in reports_df.columns]
        workspace_reports_insights = reports_df[available_columns].copy()
        
        # Add any missing columns with default values
        for col in required_columns:
            if col not in workspace_reports_insights.columns:
                if col in ['IsActive']:
                    workspace_reports_insights[col] = True
                elif col in ['LastSyncDate']:
                    workspace_reports_insights[col] = pd.Timestamp.now()
                elif col in ['SyncedBy']:
                    workspace_reports_insights[col] = 'SYSTEM_SYNC'
                elif col in ['IsFromPbix', 'IsOwnedByMe']:
                    workspace_reports_insights[col] = False
                else:
                    workspace_reports_insights[col] = None
        
        # Store summary
        reports_summary[workspace_name] = len(workspace_reports_insights)
        
        # Append to collection
        all_reports_data.append(workspace_reports_insights)
        
        print(f"      ✓ Found {len(workspace_reports_insights)} reports")
        
        # Small delay to avoid rate limiting
        if idx % 10 == 0:
            time.sleep(1)
            
    except Exception as e:
        print(f"      ✗ Error: {str(e)}")
        import traceback
        print(f"      Traceback: {traceback.format_exc()}")
        failed_workspaces.append(workspace_name)
        continue

# =============================================
# 3. Combine and Process Results
# =============================================

print("\n3. Processing results...")

if all_reports_data:
    # Combine all dataframes
    final_reports_df = pd.concat(all_reports_data, ignore_index=True)
    
    print(f"   Total reports found: {len(final_reports_df)}")
    print(f"   Total workspaces with reports: {len(reports_summary)}")
    
    if failed_workspaces:
        print(f"   Failed to access {len(failed_workspaces)} workspaces: {failed_workspaces[:5]}...")
    
    # Fill any NaN values with appropriate defaults
    final_reports_df = final_reports_df.fillna({
        'ReportType': 'PowerBIReport',
        'DatasetId': '',
        'DatasetName': '',
        'DatasetWorkspaceId': '',
        'WorkspaceId': '',
        'WebUrl': '',
        'EmbedUrl': '',
        'IsFromPbix': False,
        'IsOwnedByMe': False,
        'IsActive': True,
        'SyncedBy': 'SYSTEM_SYNC'
    })
    
    # Ensure boolean columns are boolean type
    bool_columns = ['IsFromPbix', 'IsOwnedByMe', 'IsActive']
    for col in bool_columns:
        if col in final_reports_df.columns:
            final_reports_df[col] = final_reports_df[col].astype(bool)
    
    # Convert datetime column
    final_reports_df['LastSyncDate'] = pd.to_datetime(final_reports_df['LastSyncDate'])
    
    print("   Converting to Spark DataFrame...")
    
    # Define explicit schema for Spark DataFrame
    spark_schema = StructType([
        StructField("ReportId", StringType(), True),
        StructField("ReportName", StringType(), True),
        StructField("ReportType", StringType(), True),
        StructField("DatasetId", StringType(), True),
        StructField("DatasetName", StringType(), True),
        StructField("DatasetWorkspaceId", StringType(), True),
        StructField("WebUrl", StringType(), True),
        StructField("EmbedUrl", StringType(), True),
        StructField("IsFromPbix", BooleanType(), True),
        StructField("IsOwnedByMe", BooleanType(), True),
        StructField("WorkspaceName", StringType(), True),
        StructField("WorkspaceId", StringType(), True),
        StructField("IsActive", BooleanType(), True),
        StructField("LastSyncDate", TimestampType(), True),
        StructField("SyncedBy", StringType(), True)
    ])
    
    # Create Spark DataFrame with explicit schema
    spark_reports_df = spark.createDataFrame(final_reports_df, schema=spark_schema)
    
    # =============================================
    # 4. Create/Update workspace_reports_insights Table
    # =============================================
    
    print("\n4. Creating/Updating workspace_reports_insights table...")
    
    try:
        # Drop existing table if it exists to ensure correct schema
        try:
            spark.sql("DROP TABLE IF EXISTS dbo.workspace_reports_insights")
            print("   Dropped existing workspace_reports_insights table")
        except:
            pass
        
        # Create the table with all required columns
        spark_reports_df.write \
            .mode("overwrite") \
            .option("overwriteSchema", "true") \
            .saveAsTable("dbo.workspace_reports_insights")
        
        print(f"   ✓ workspace_reports_insights table created with {spark_reports_df.count()} records")
        
        # Verify the table structure
        print("\n   Table Schema:")
        spark.sql("DESCRIBE dbo.workspace_reports_insights").show(truncate=False)
        
    except Exception as e:
        print(f"   ✗ Error creating workspace_reports_insights table: {str(e)}")
    
    # =============================================
    # 5. Summary Statistics
    # =============================================
    
    print("\n" + "=" * 50)
    print("SUMMARY STATISTICS")
    print("=" * 50)
    
    try:
        # Total reports
        total_count = spark.sql("SELECT COUNT(*) as count FROM dbo.workspace_reports_insights").collect()[0]['count']
        print(f"\nTotal Reports: {total_count}")
                
        # Sample data
        print("\nSample Records (first 5):")
        display(
            spark.sql("""
            SELECT 
                ReportId,
                ReportName,
                WorkspaceName,
                ReportType,
                IsActive,
                DatasetId,
                DatasetName
            FROM dbo.workspace_reports_insights
        """)
        )
        
    except Exception as e:
        print(f"   Could not generate statistics: {str(e)}")
    
else:
    print("   No reports data collected from any workspace")

print("\n" + "=" * 50)
print("WORKSPACE REPORTS TABLE CREATED SUCCESSFULLY!")
print("=" * 50)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
