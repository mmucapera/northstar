# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_dispatch
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: dispatch_merge_sql
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Framework Dispatcher
# Entry point for all loading strategies. `framework_execute(cfg)` resolves the configured `load_strategy`, runs schema evolution, executes the load, and performs post-load optimization.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def dispatch_merge_sql(cfg):
    strat = (cfg.get("load_strategy") or "").lower()
    
    if strat in ("bronze_to_silver", "bronze_to_silver_latest"):
        bronze_to_silver_latest(cfg)
    elif strat == "delete_insert":
        delete_insert(cfg)
    elif strat == "delete_insert_manifest":
        delete_insert_manifest(cfg)
    elif strat in ("replace_latest", "truncate_insert", "silver_to_gold", "gold"):
        replace_latest(cfg)
    elif strat == "overwrite_partition":
        overwrite_partition(cfg)
    elif strat in ("script", "execute_script"):
        execute_script(cfg)
    elif strat == "load_scd2":
        load_scd2(cfg)
    else:
        raise ValueError(f"Unsupported load_strategy: {strat}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_dispatch")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
