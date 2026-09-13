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

# Loads the webapp login allowlist from Files/users.csv (pipe-delimited:
# user|user_group) into dbo.users. This is the table the webapp's login
# check queries - see frontend/src/data/auth-check.ts. Run by pl_auth on its
# midnight schedule, so an edit to users.csv takes effect the next night;
# safe to trigger this notebook directly for an immediate refresh.

from notebookutils import mssparkutils

USERS_PATH = "Files/users.csv"

try:
    mssparkutils.fs.ls(USERS_PATH)
    exists = True
except Exception:
    exists = False

if exists:
    df = spark.read.format("csv").option("header", "true").option("sep", "|").load(USERS_PATH)
    df.write.mode("overwrite").option("overwriteSchema", "true").saveAsTable("dbo.users")
    print(f"Loaded {df.count()} authorized user(s) into dbo.users")
else:
    print(f"Skipping load - {USERS_PATH} does not exist")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
