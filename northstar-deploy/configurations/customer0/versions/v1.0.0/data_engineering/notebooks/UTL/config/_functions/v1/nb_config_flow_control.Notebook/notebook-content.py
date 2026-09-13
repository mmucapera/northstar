# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_flow_control
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: stop_notebook, fail_notebook
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Notebook Stop Helper
# Terminates notebook execution with logging. Handles the Fabric `NotebookExit` exception pattern.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def stop_notebook(message: str):
  """
  Stop execution immediately and surface a message.
  In Fabric: mssparkutils.notebook.exit raises NotebookExit (expected).
  We MUST NOT swallow NotebookExit and re-raise RuntimeError, otherwise
  we get double-fail + ugly stack traces.
  
  Also logs the message to the monitoring log before stopping.
  """
  # Log the message before stopping
  try:
      fabric_logger = get_fabric_logger()
      if fabric_logger and hasattr(fabric_logger, "log_notebook_exit"):
          fabric_logger.log_notebook_exit(message)
      else:
          logger.error(f"[NOTEBOOK_EXIT] {message}")
  except Exception as e:
      logger.error(f"[NOTEBOOK_EXIT] Failed to log exit: {e}. Message: {message}")
  
  try:
      from notebookutils import mssparkutils  # Fabric
      mssparkutils.notebook.exit(message)     # raises NotebookExit
  except Exception as e:
      # If this is the expected Fabric NotebookExit, just re-raise it.
      if e.__class__.__name__ == "NotebookExit":
          raise
      # Non-Fabric / unexpected -> raise RuntimeError
      raise RuntimeError(message)


def fail_notebook(message: str):
  """
  Fail the notebook with an unhandled exception.
  Unlike stop_notebook (which exits cleanly as Succeeded), this causes
  Fabric to mark the notebook run as FAILED.
  """
  try:
      fabric_logger = get_fabric_logger()
      if fabric_logger and hasattr(fabric_logger, "log_notebook_exit"):
          fabric_logger.log_notebook_exit(f"FAILED: {message}")
      else:
          logger.error(f"[NOTEBOOK_FAIL] {message}")
  except Exception:
      logger.error(f"[NOTEBOOK_FAIL] {message}")
  
  raise RuntimeError(f"[NOTEBOOK_FAIL] {message}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_flow_control")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
