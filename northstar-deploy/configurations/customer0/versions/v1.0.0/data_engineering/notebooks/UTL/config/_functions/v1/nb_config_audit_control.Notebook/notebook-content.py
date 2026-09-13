# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_audit_control
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: update_audit_batch_control
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Audit Batch Control — End-of-Pipeline Update
# Updates `log.audit_batch_control` with `pl_end`, `duration_hms`, manifest metadata,
# extraction info, `ingestion_version`, and final `batch_status`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


def update_audit_batch_control(
    batchid: int,
    manifest_package: str = None,
    manifest_file: str = None,
    batch_status: str = "COMPLETED",
    error_message: str = None,
):
    """
    Call at the end of the pipeline to close the audit_batch_control record.
    Only batchid is required — manifest_package and manifest_file are auto-resolved
    from audit_package_manifest using the load_date already stored in the
    audit_batch_control row if not passed explicitly.

    Updates:
      - pl_end             : timestamp when the pipeline finished
      - duration_hms       : elapsed time since pl_start (HH:MM:SS)
      - batch_status       : final status (COMPLETED / FAILED)
      - error_message      : optional error detail on failure
    """
    try:
        pl_end = datetime.now()
        pl_end_str = pl_end.strftime("%Y-%m-%d %H:%M:%S")

        # ── Read the existing audit_batch_control row ──────────────────
        existing_rows = []
        try:
            existing_rows = spark.sql(
                f"SELECT pl_start FROM log.audit_batch_control WHERE batchid = {batchid} LIMIT 1"
            ).collect()
            print(existing_rows)
        except Exception as e:
            logger.warning(f"[BATCH_CONTROL] Could not read existing batch record: {e}")

        existing = existing_rows[0] if existing_rows else None

        # ── Compute duration_hms from stored pl_start ──────────────────
        duration_hms = None
        if existing:
            try:
                existing_dict = {k.lower(): v for k, v in existing.asDict().items()}
                pl_start_val = existing_dict.get("pl_start")
                if pl_start_val:
                    pl_start_dt = datetime.fromisoformat(str(pl_start_val))
                    # Strip timezone info if present so both datetimes are naive
                    if pl_start_dt.tzinfo is not None:
                        pl_start_dt = pl_start_dt.replace(tzinfo=None)
                    total_secs = int((pl_end - pl_start_dt).total_seconds())
                    h, rem = divmod(total_secs, 3600)
                    m, s = divmod(rem, 60)
                    duration_hms = f"{h:02d}:{m:02d}:{s:02d}"
                    print(duration_hms)
            except Exception as e:
                logger.warning(f"[BATCH_CONTROL] Could not compute duration: {e}")

        print(duration_hms)

        set_map = {
            "pl_end":            F.lit(pl_end_str),
            "duration_hms":      F.lit(duration_hms),
            "batch_status":      F.lit(batch_status),
            "ingestion_version": F.lit(INGESTION_VERSION),
        }
        
        if error_message is not None:
            set_map["error_message"] = F.lit(str(error_message)[:2000])

        DeltaTable.forName(spark, "log.audit_batch_control").update(
            condition=f"batchid = {batchid}",
            set=set_map,
        )

        logger.info(
            f"[BATCH_CONTROL] Closed batchid={batchid}: "
            f"status={batch_status}, duration={duration_hms}, "
            f"ingestion_version={INGESTION_VERSION}"
        )

    except Exception as e:
        logger.error(f"[BATCH_CONTROL] Failed to update audit_batch_control for batchid={batchid}: {e}")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_audit_control")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
