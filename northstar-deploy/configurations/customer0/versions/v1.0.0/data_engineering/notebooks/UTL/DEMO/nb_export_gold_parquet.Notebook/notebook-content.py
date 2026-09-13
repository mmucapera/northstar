# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "",
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
# META   "language_group": "synapse_pyspark",
# META   "frozen": true,
# META   "editable": false
# META }

# CELL ********************

from notebookutils import mssparkutils
from datetime import datetime
import zipfile
import tempfile
import os

source_schemas = ["gold_demo"]
base_path = "Files/gold_export"

# customer = "customer0"
export_dir = "Files/gold_export"
date_str = datetime.now().strftime("%Y%m%d")
zip_path = f"Files/gold_export/{customer}_gold_export_{date_str}.zip"

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

for schema in source_schemas:
    print(f"Scanning schema: {schema}")
    tables = spark.catalog.listTables(schema)

    for t in tables:
        if t.tableType and t.tableType.lower() == "view":
            continue
        
        # if 'product' in t.name:
        if 1 == 1:
            src_table = f"{schema}.{t.name}"
            print(f"  - Processing table: {src_table}")

            try:
                df = spark.table(src_table)
            except Exception as e:
                print(f"    ! Failed to read {src_table}: {e}")
                continue

            # Export path
            export_path = f"{base_path}/{t.name}.parquet"

            # Write as a single parquet file
            (
                df.coalesce(1)
                .write
                .mode("overwrite")
                .parquet(export_path)
            )

            print(f"      -> exported to {export_path}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# Temp local root + zip path
local_root = tempfile.mkdtemp(prefix="gold_export_")
local_zip = os.path.join(local_root, f"{customer}_gold_export_{date_str}.zip")

# 1) Copy each parquet folder from OneLake -> local
items = mssparkutils.fs.ls(export_dir)

for item in items:
    if item.name.endswith(".parquet"):
        # Local target dir for this parquet folder
        local_target_dir = os.path.join(local_root, item.name)
        os.makedirs(local_target_dir, exist_ok=True)

        # Copy folder recursively to local
        # src: OneLake path (e.g. abfss://.../Files/...)
        # dst: local file:/ path
        mssparkutils.fs.cp(item.path, f"file:{local_target_dir}", recurse=True)

# 2) Zip the local tree
with zipfile.ZipFile(local_zip, "w", zipfile.ZIP_DEFLATED) as zipf:
    for root, _, files in os.walk(local_root):
        for fname in files:
            if fname.endswith(".parquet"):
                full_path = os.path.join(root, fname)
                rel_path = os.path.relpath(full_path, local_root)
                zipf.write(full_path, arcname=rel_path)

# 3) Copy ZIP back to OneLake
mssparkutils.fs.cp(f"file:{local_zip}", zip_path, True)

print(f"ZIP created at {zip_path}")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# --- Alternative: Individual ZIP per parquet (saves space, easier to copy) ---
# Each .parquet folder gets its own .zip, then the original parquet folder is deleted.

local_root = tempfile.mkdtemp(prefix="gold_export_ind_")

items = mssparkutils.fs.ls(export_dir)

for item in items:
    if item.name.endswith(".parquet"):
        folder_name = item.name  # e.g. "table_name.parquet"
        zip_name = folder_name.replace(".parquet", ".zip")

        # Local paths
        local_parquet_dir = os.path.join(local_root, folder_name)
        local_zip_file = os.path.join(local_root, zip_name)
        os.makedirs(local_parquet_dir, exist_ok=True)

        # 1) Copy parquet folder from OneLake -> local
        mssparkutils.fs.cp(item.path, f"file:{local_parquet_dir}", recurse=True)

        # 2) Zip only this parquet folder
        with zipfile.ZipFile(local_zip_file, "w", zipfile.ZIP_DEFLATED) as zipf:
            for root, _, files in os.walk(local_parquet_dir):
                for fname in files:
                    if fname.endswith(".parquet"):
                        full_path = os.path.join(root, fname)
                        rel_path = os.path.relpath(full_path, local_root)
                        zipf.write(full_path, arcname=rel_path)

        # 3) Copy individual ZIP back to OneLake
        onelake_zip_path = f"{export_dir}/{zip_name}"
        mssparkutils.fs.cp(f"file:{local_zip_file}", onelake_zip_path, True)

        # 4) Delete the original parquet folder from OneLake
        mssparkutils.fs.rm(item.path, recurse=True)

        print(f"  {folder_name} -> {zip_name} (original deleted)")

print("Individual ZIPs created, parquet folders removed.")


# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
