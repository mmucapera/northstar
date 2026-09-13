# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   }
# META }

# MARKDOWN ********************

# # nb_config_paths
# > Loaded by `nb_utils_config`. Do NOT %run this notebook directly.
# > Contents: check_for_model_files, _path_exists, _resolve_orchestrator_base_path
# > Versioning: keep older impls as `<fn>_vN` in this file; expose the current one via `fn = fn_vN`.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# MARKDOWN ********************


# ## Source File Discovery using Regex
# Validates that Parquet source files exist for a given model and date partition before triggering a load.

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


import re

def check_for_model_files(model_name_q: str, date_part) -> None:
    """
    Legacy 2-param signature kept for backward compatibility.
    Reads 'domain' and 'extract_id' from the notebook's global variables
    (they are always injected as pipeline parameters) and delegates to
    the orchestrator-aware path resolver that includes extract_id.
    """
    import builtins
    _g = {**globals(), **vars(builtins)}
    _domain     = _g.get("domain")     or None
    _extract_id = _g.get("extract_id") or None

    if _domain and _extract_id:
        # Forward to orchestrator version — path will be Files/bronze/{domain}/{date}/{extract_id}
        _check_for_model_files_orchestrator(_domain, model_name_q, date_part, _extract_id)
    else:
        fail_notebook(
            f"[REGENERATE REQUIRED] check_for_model_files called without domain/extract_id "
            f"for {model_name_q}. Run 'northstar-formation build' to regenerate the notebook."
        )

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************


import re

def _path_exists(path: str) -> bool:
    try:
        mssparkutils.fs.ls(path)
        return True
    except Exception:
        return False


def _resolve_orchestrator_base_path(domain, date_part, extract_id) -> str:
    """
    Resolve the bronze source base path for orchestrator loads.
    Uses ONLY the exact domain/date/extract_id path provided.
    Returns None if the exact path does not exist.
    """
    domain_raw = str(domain or "").strip()
    date_clean = str(date_part or "").strip("/")
    extract_id_str = str(int(extract_id))

    exact = f"Files/bronze/{domain_raw}/{date_clean}/{extract_id_str}"
    if date_clean and _path_exists(exact):
        return exact

    logger.warning(
        f"[ORCHESTRATOR_PATH] Exact path not found for "
        f"domain={domain_raw}, date={date_clean}, extract_id={extract_id_str}. Skipping."
    )
    return None

if USE_ORCHESTRATOR:
    def _check_for_model_files_orchestrator(domain, model_name_q: str, date_part, extract_id) -> None:
        try:
            source_path = _resolve_orchestrator_base_path(domain, date_part, extract_id)
            if not source_path:
                _msg = (
                    f"No source path found for {model_name_q}: "
                    f"Files/bronze/{domain}/{date_part}/{extract_id} does not exist."
                )
                if _dev_mode_allow_missing_source():
                    logger.warning(
                        f"[DEV_MODE] {_msg} Continuing — bronze DDL will create an empty table."
                    )
                    return None
                fail_notebook(
                    f"{_msg} Check that extract_id={extract_id} was processed for "
                    f"domain={domain} on {date_part}."
                )

            # Accept both 'layer.domain_entity' and 'domain_entity'
            parts = model_name_q.split('.', 1)
            tbl = parts[1] if len(parts) == 2 else parts[0]

            # Extract domain + entity
            tbl_domain, entity = tbl.split('_', 1)
            tbl_domain = tbl_domain.lower()
            entity = entity.lower()

            # Matching logic (same as read_parquet_bulk matches_model_file)
            def matches_model_file(name: str) -> bool:
                name = name.lower()

                # SAFETY CHECK: entity must be present in filename
                if entity not in name:
                    return False

                # DOMAIN BOUNDARY CHECK
                if tbl_domain == 'fct' and '_sp_full' in name:
                    return False
                if tbl_domain == 'opr' and '_fct_' in name:
                    return False

                # Old format: 20260409_162015_OPR_PPLProdLocInvFact_*.parquet
                old_pattern = re.compile(
                    rf"^\d{{8}}_\d{{6}}_{tbl_domain}_{entity}(?:_|[^a-z0-9]).*\.parquet$", re.IGNORECASE
                )
                # SP format (OPR/SP): PPLProdLocInvFact_SP_Full_*_20260409_093914.parquet
                new_pattern = re.compile(
                    rf"^{entity}(?:_|[^a-z0-9])sp_.*_\d{{8}}_\d{{6}}\.parquet$", re.IGNORECASE
                ) if tbl_domain in ['opr', 'sp'] else None
                # DP format (FCT/DP): Location_DP_Central_Full_20260728_070408.parquet
                dp_pattern = re.compile(
                    rf"^{entity}(?:_|[^a-z0-9])dp_.*_\d{{8}}_\d{{6}}\.parquet$", re.IGNORECASE
                ) if tbl_domain in ['fct', 'dp'] else None

                matched = (
                    bool(old_pattern.match(name))
                    or bool(new_pattern and new_pattern.match(name))
                    or bool(dp_pattern and dp_pattern.match(name))
                )
                return matched

            # Recursive file walk (same as read_parquet_bulk)
            data_files = []

            def walk(path, depth=0, max_depth=3):
                try:
                    items = mssparkutils.fs.ls(path)
                except Exception:
                    return
                for it in items:
                    full = f"{path}/{it.name}"
                    if it.isDir and depth < max_depth:
                        walk(full, depth + 1, max_depth)
                    elif it.isDir:
                        continue
                    elif (
                        it.name.lower().endswith(".parquet")
                        and matches_model_file(it.name)
                    ):
                        data_files.append(it)

            walk(source_path)

            if not data_files:
                _msg = f"No source files found for {model_name_q} in {date_part} (searched: {source_path})"
                if _dev_mode_allow_missing_source():
                    logger.warning(
                        f"[DEV_MODE] {_msg} Continuing — bronze DDL will create an empty table."
                    )
                    return None
                logger.error(f"No data found for {model_name_q} at {source_path} (date={date_part}, domain={tbl_domain}, entity={entity})")
                fail_notebook(_msg)
            else:
                logger.info(f"Found {len(data_files)} source file(s) for {model_name_q} at {source_path}")
                logger.info("Matched files:")
                for f in data_files:
                    logger.info(f" -> {f.name}")

        except Exception as e:
            if "[NOTEBOOK_FAIL]" in str(e):
                raise  # Don't double-wrap fail_notebook exceptions
            logger.error(f"Error checking source files for {model_name_q}: {e}")
            fail_notebook(f"Error checking source files for {model_name_q}: {e}")

    def check_for_model_files(domain, model_name_q: str, date_part, extract_id) -> None:
        _check_for_model_files_orchestrator(domain, model_name_q, date_part, extract_id)

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }

# CELL ********************

# [LOAD_CONFIRM]
print("[CONFIG] loaded nb_config_paths")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
