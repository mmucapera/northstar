"""Microsoft Fabric notebook generator."""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional
from textwrap import dedent
from xml.parsers.expat import model
from ..core.enums import LoadStrategy
from ..core.models import (
    BuildContext,
    LakehouseConfig,
    NotebookSettings,
    ResolvedModel,
)
from ..sql.generator import SparkSQLGenerator, qualify, qualify_model_name
from ..utils.helpers import escape_sql_string
from ..utils.logging import get_logger


logger = get_logger(__name__)


# Operation type mapping: UIX load_strategy -> logging operation_type
OPERATION_TYPE_MAP = {
    "bronze_to_silver": "MERGE",
    "bronze_to_silver_latest": "MERGE",
    "delete_insert": "DELETE_INSERT",
    "replace_latest": "REPLACE",
    "truncate_insert": "TRUNCATE_INSERT",
    "silver_to_gold": "TRANSFORM",
    "gold": "AGGREGATE",
    "scd2": "SCD2",
    "scd2_dim": "SCD2",
    "load_scd2": "SCD2",
}


def get_operation_type(load_strategy: str) -> str:
    """Map UIX load_strategy to logging operation_type."""
    return OPERATION_TYPE_MAP.get(load_strategy.lower(), load_strategy.upper())


class FabricNotebookGenerator:
    """Generate Microsoft Fabric notebooks for resolved models.

    This generator creates notebook cells that encapsulate:
    - Model metadata and context
    - Runtime parameters
    - Import statements
    - Framework import via %run
    - SQL execution logic (delegated to framework)
    - Data quality checks (delegated to framework)
    - Table optimization commands (delegated to framework)

    All customization is driven by model configuration (notebook_settings)
    rather than hardcoded model name checks.
    """

    def __init__(
        self,
        sql_generator: SparkSQLGenerator,
        default_lakehouse: LakehouseConfig | None = None,
        enable_logging: bool = False,
        logging_project: str | None = None,
    ) -> None:
        self.sql_generator = sql_generator
        self.default_lakehouse = default_lakehouse
        self.enable_logging = enable_logging
        self.logging_project = logging_project or "UnisonInsights"
        logger.debug("Notebook generator initialized")

    def generate(
        self,
        model: ResolvedModel,
        sql: str,
        context: BuildContext,
    ) -> Dict[str, Any]:
        logger.info(f"Generating notebook for {model.name}")
        return self._build_notebook(model, sql, context)

    def generate_all(
        self,
        models: Dict[str, ResolvedModel],
        sql_outputs: Dict[str, str],
        context: BuildContext,
    ) -> Dict[str, Dict[str, Any]]:
        results: Dict[str, Dict[str, Any]] = {}

        for name, model in models.items():
            if name not in sql_outputs:
                logger.warning(f"No SQL generated for {name}, skipping notebook")
                continue

            try:
                notebook = self.generate(model, sql_outputs[name], context)
                results[name] = notebook
                logger.info(f"Generated notebook for {name}")
            except Exception as e:
                logger.error(f"Failed to generate notebook for {name}: {e}")

        return results

    def _build_notebook(
        self,
        model: ResolvedModel,
        sql: str,
        context: BuildContext,
    ) -> Dict[str, Any]:
        # Get qualified table name using model's declared layer
        # qualify_model_name strips any stale directory-derived layer prefix so
        # that the YAML-declared layer always wins (e.g. file in gold/ but layer: interface)
        layer = getattr(model, "layer", None)
        model_name_q = qualify_model_name(model.name, layer)

        # Apply qualification to SQL if needed (negative lookbehind prevents double-prefix)
        if model.name and model_name_q != model.name:
            pattern = re.compile(rf"(?<!\.)\b{re.escape(model.name)}\b", re.IGNORECASE)
            sql = pattern.sub(model_name_q, sql)

        # Extract configuration from model
        settings = self._get_notebook_settings(model)
        strategy = self._get_load_strategy(model)
        merge_keys = self._get_merge_keys(model)
        delete_keys = self._get_delete_keys(model)
        derived_sql = getattr(model, "derived_sql", None)
        base_conversion_measures = self._get_base_conversion_measures(model)
        conversion_lkp_tbl = self._get_conversion_lkp_tbl(model)
        src_query_type = self._get_src_query_type(model)
        purge_domain = self._get_purge_domain(model)
        full_retention_months = self._get_full_retention_months(model)
        snapshot_months = self._get_snapshot_months(model)
        plan_over_plan = self._get_plan_over_plan(model)
        non_nulls = self._get_non_nulls(model)
        partition_by = self._get_partition_by(model)

        cells: List[Dict[str, Any]] = []

        cells.append(self._build_attach_lkh_cell())

        # Add imports section header
        # cells.append(self._build_markdown_cell("## Imports"))
        
        # 2. Framework import cell (%run)
        cells.append(self._build_logger_import_cell())
        cells.append(self._build_framework_import_cell())


        # 3. Imports cell
        cells.append(self._build_imports_cell(model))

        # 3b. Start log cell (only for SILVER/GOLD layers)
        start_log_cell = self._build_start_log_cell(model)
        if start_log_cell:
            cells.append(start_log_cell)

        # Add SQL section header
        # cells.append(self._build_markdown_cell("## SQL"))

        # 3b. Repair if corrupted (silver layer tables matching specific domains)
        repair_cell = self._build_repair_if_corrupted_cell(model, model_name_q)
        if repair_cell:
            cells.append(repair_cell)

        # Disable broadcast joins for gold tables known to exceed the 8 GiB threshold
        if "forecastaccuracy" in model.name or "pplprodlocinvfact_his" in model.name:
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {},
                    "outputs": [],
                    "source": [
                        "# Disable broadcast joins \u2014 table exceeds Spark broadcast threshold\n",
                        'spark.conf.set("spark.sql.autoBroadcastJoinThreshold", "-1")\n',
                    ],
                }
            )

        # 4. SQL execution cell (delegated to framework)
        # Bracket the src_sql cell with silver duplicate checks (before/after).
        pre_sql_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "pre-src_sql")
        if pre_sql_dup:
            cells.append(pre_sql_dup)

        cells.append(
            self._build_execute_sql_cell(
                model=model,
                sql=sql,
                model_name_q=model_name_q,
                strategy=strategy,
                merge_keys=merge_keys,
                delete_keys=delete_keys,
                derived_sql=derived_sql,
                base_conversion_measures=base_conversion_measures,
                conversion_lkp_tbl=conversion_lkp_tbl,
                src_query_type=src_query_type,
                purge_domain=purge_domain,
                full_retention_months=full_retention_months,
                snapshot_months=snapshot_months,
                plan_over_plan=plan_over_plan,
                partition_by=partition_by,
            )
        )

        post_sql_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "post-src_sql")
        if post_sql_dup:
            cells.append(post_sql_dup)

        # Add unit conversion section header
        # cells.append(self._build_markdown_cell("## Unit Conversion"))

        #will only run if there is unit conversion
        unit_conv_cell = self._build_execute_sql_cell_unit_conversion(
            model=model,
            sql=sql,
            model_name_q=model_name_q,
            strategy=strategy,
            merge_keys=merge_keys,
            delete_keys=delete_keys,
            derived_sql=derived_sql,
            base_conversion_measures=base_conversion_measures,
            conversion_lkp_tbl=conversion_lkp_tbl,
            src_query_type=src_query_type,
        )
        if unit_conv_cell:
            pre_uc_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "pre-unit_conversion")
            if pre_uc_dup:
                cells.append(pre_uc_dup)
            cells.append(unit_conv_cell)
            post_uc_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "post-unit_conversion")
            if post_uc_dup:
                cells.append(post_uc_dup)
        
        # Add Plan Over Plan section header (if configured)
        # if plan_over_plan == 1:
            # cells.append(self._build_markdown_cell("# Plan Over Plan"))
        
        # 5d. PlanOverPlan processing cell (if configured)
        if plan_over_plan == 1:
            domain = purge_domain
            pop_cell = self._build_plan_over_plan_cell(model_name_q, domain, merge_keys)
            if pop_cell:
                pre_pop_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "pre-plan_over_plan")
                if pre_pop_dup:
                    cells.append(pre_pop_dup)
                cells.append(pop_cell)
                post_pop_dup = self._build_check_silver_duplicates_cell(model, model_name_q, merge_keys, "post-plan_over_plan")
                if post_pop_dup:
                    cells.append(post_pop_dup)

        # Add Logging section header
        # cells.append(self._build_markdown_cell("## Logging"))

        # 5. Data quality checks cell (unless disabled)
        # if not settings.skip_dq_checks:
        #     cells.append(self._build_dq_checks_cell(model, model_name_q, merge_keys))

        # # Add Purging section header (if configured)
        # if (purge_domain and purge_domain.upper() in ["OPR", "FCT"] and 
        #     full_retention_months is not None and snapshot_months is not None):
            # cells.append(self._build_markdown_cell("## Purging"))

        # 5b. Purge cell for OPR tables (if retention policies configured)
        if purge_domain and purge_domain.upper() == "OPR" and full_retention_months is not None and snapshot_months is not None:
            purge_cell = self._build_purge_cell_opr(model_name_q, full_retention_months, snapshot_months)
            if purge_cell:
                cells.append(purge_cell)

        # 5c. Purge cell for FCT tables (if retention policies configured)
        if purge_domain and purge_domain.upper() == "FCT" and full_retention_months is not None and snapshot_months is not None:
            purge_cell = self._build_purge_cell_fct(model_name_q, full_retention_months, snapshot_months)
            if purge_cell:
                cells.append(purge_cell)

        # Add Optimize section header
        # cells.append(self._build_markdown_cell("## Optimize"))

        # 6. Optimize cell (unless disabled)
        if not settings.skip_optimize:
            optimize_cell = self._build_optimize_cell(model, model_name_q, settings)
            if optimize_cell:
                cells.append(optimize_cell)

        # 7. Validate source data (bronze layer - after optimize)
        validate_cell = self._build_check_source_duplicates_cell(model, model_name_q, merge_keys)
        if validate_cell:
            cells.append(validate_cell)

        # 7b. Validate non-nulls & partition keys (bronze layer - after optimize)
        validate_non_nulls_cell = self._build_validate_non_nulls_cell(model, model_name_q, non_nulls)
        if validate_non_nulls_cell:
            cells.append(validate_non_nulls_cell)

        # 8. Parallelism cell (optional – keep simple / no-op for now)
        parallelism_cell = self._build_parallelism_cell(model, model_name_q, settings)
        if parallelism_cell:
            cells.append(parallelism_cell)

        # 9. End log cell (only for SILVER/GOLD layers)
        end_log_cell = self._build_end_log_cell(model)
        if end_log_cell:
            cells.append(end_log_cell)

        # 10. Preview cell (bronze layer only — SELECT * LIMIT 10)
        if layer == "bronze":
            cells.append(self._build_preview_cell(model_name_q))

        return {
            "cells": cells,
            "metadata": self._build_notebook_metadata(),
            "nbformat": 4,
            "nbformat_minor": 5,
        }

    def _get_scd_logical_key(self, model: ResolvedModel) -> List[str]:
        return getattr(model, "scd_logical_key", None) or []

    def _get_scd_historical_fields(self, model: ResolvedModel) -> List[str]:
        return getattr(model, "scd_historical_fields", None) or []

    def _get_skip_historical(self, model: ResolvedModel) -> List[str]:
        return getattr(model, "skip_historical", None) or []

    def _get_notebook_settings(self, model: ResolvedModel) -> NotebookSettings:
        if hasattr(model, "notebook_settings") and model.notebook_settings:
            return model.notebook_settings
        return NotebookSettings()

    def _get_load_strategy(self, model: ResolvedModel) -> str:
        if model.merge_config and model.merge_config.load_strategy:
            return model.merge_config.load_strategy.lower()
        return LoadStrategy.REPLACE_LATEST.value

    def _get_merge_keys(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.merge_keys:
            return model.merge_config.merge_keys
        return []

    def _get_delete_keys(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.delete_keys:
            return model.merge_config.delete_keys
        return []

    def _get_partition_by(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.partition_by:
            return model.merge_config.partition_by
        return []
    
    def _get_non_nulls(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.non_nulls:
            return model.merge_config.non_nulls
        return []
    
    def _get_base_conversion_measures(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.base_conversion_measures:
            return model.merge_config.base_conversion_measures
        return []
    
    def _get_conversion_lkp_tbl(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.conversion_lkp_tbl:
            return model.merge_config.conversion_lkp_tbl
        return []
    
    def _get_src_query_type(self, model: ResolvedModel) -> List[str]:
        if model.merge_config and model.merge_config.src_query_type:
            return model.merge_config.src_query_type
        return []
    
    def _get_purge_domain(self, model: ResolvedModel) -> Optional[str]:
        if model.merge_config and model.merge_config.purge_domain:
            return model.merge_config.purge_domain
        return None
    
    def _get_full_retention_months(self, model: ResolvedModel) -> Optional[int]:
        if model.merge_config and model.merge_config.full_retention_months is not None:
            return model.merge_config.full_retention_months
        return None
    
    def _get_snapshot_months(self, model: ResolvedModel) -> Optional[int]:
        if model.merge_config and model.merge_config.snapshot_months is not None:
            return model.merge_config.snapshot_months
        return None
    
    def _get_plan_over_plan(self, model: ResolvedModel) -> Optional[int]:
        if model.merge_config and model.merge_config.plan_over_plan is not None:
            return model.merge_config.plan_over_plan
        return None
    
    def _build_check_silver_duplicates_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        merge_keys: List[str],
        stage: str,
    ) -> Optional[Dict[str, Any]]:
        """Build cell that checks for duplicates on the silver target table using merge keys.

        Emitted around the src_sql / unit-conversion / plan-over-plan cells so the
        target table is validated both before and after each transform step.
        Skipped when the table does not yet exist (e.g. first-time load) to avoid
        failing the pre-check.
        """
        layer = (getattr(model, "layer", "") or "").lower()
        if layer != "silver":
            return None
        if not merge_keys:
            return None

        content = [
            f"# Duplicate check on {model_name_q} ({stage})\n",
            f"if spark.catalog.tableExists('{model_name_q}'):\n",
            f"    _check_source_duplicates('{model_name_q}', {merge_keys})\n",
            f"else:\n",
            f"    logger.info(f'[DQ_DUPLICATES] {model_name_q} does not exist yet — skipping {stage} check')\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_check_source_duplicates_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        merge_keys: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Build cell that validates source data using merge keys.
        
        Only emitted for silver/gold layers with merge keys configured.
        Converts model_name_q from 'silver.' to 'bronze.' for source table reference.
        """
        layer = (getattr(model, "layer", "") or "").lower()
        
        if layer not in ("bronze"):
            return None
        
        # Only validate if merge keys exist
        if not merge_keys:
            return None
        
        # Convert target table to source table reference (silver. -> bronze., gold. -> silver.)
        source_table = model_name_q
        if layer == "silver":
            source_table = model_name_q.replace("silver.", "bronze.")
        elif layer == "gold":
            source_table = model_name_q.replace("gold.", "silver.")
        
        content = [
            # f"logger.info('Validating source data in {source_table} using primary keys: {merge_keys}')\n",
            f"_check_source_duplicates('{source_table}', {merge_keys})\n",
        ]
        
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }
    
    def _build_validate_non_nulls_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        non_nulls: List[str],
    ) -> Optional[Dict[str, Any]]:
        """Build cell that validates non-null columns in source data.
        
        Only emitted for bronze layer with non_nulls configured.
        Validates the bronze table directly.
        """
        layer = (getattr(model, "layer", "") or "").lower()
        
        # Only validate for bronze layer
        if layer not in ("bronze"):
            return None
        
        # Only validate if non_nulls exist
        if not non_nulls:
            return None
        
        source_table = model_name_q
        
        # Use delete_keys from the model, not a global DELETE_KEYS
        delete_keys = self._get_delete_keys(model)
        partition_keys = next((col for col in delete_keys if str(col).startswith("Partitionkeys_")), None)
        
        if partition_keys:
            content = [
                f"_validate_non_nulls('{source_table}', {non_nulls})\n\n",
                f"_validate_partition_keys('{source_table}', '{partition_keys}')\n",
            ]
        else:
            content = [
                f"_validate_non_nulls('{source_table}', {non_nulls})\n",
            ]
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }
    
    def _build_repair_if_corrupted_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
    ) -> Optional[Dict[str, Any]]:
        """Build cell that calls _repair_if_corrupted for specific silver tables.

        Only emitted when the model is in the silver layer and its name
        contains 'ppl', 'fact', or 'saleshistory'.
        """
        layer = (getattr(model, "layer", "") or "").lower()
        if layer != "silver":
            return None

        name_lower = (model.name or "").lower()
        if "script" in name_lower:
            return None
        if not any(kw in name_lower for kw in ("ppl", "fact", "saleshistory","scd")):
            return None

        content = [
            f"# Repair target table if corrupted\n",
            f"_repair_if_corrupted('{model_name_q}')\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_notebook_metadata(self) -> Dict[str, Any]:
        return {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.10.0",
                "mimetype": "text/x-python",
            },
        }

    def _build_metadata_cell(
        self,
        model: ResolvedModel,
        context: BuildContext,
    ) -> Dict[str, Any]:
        layer = (model.layer or "N/A").title()
        features = ", ".join(context.features) if context.features else "None"

        kind_val = None
        if hasattr(model, "kind") and model.kind:
            try:
                kind_val = model.kind.value
            except AttributeError:
                kind_val = str(model.kind)

        body = [
            f"# {layer} Layer Model: {model.name}",
            "",
            f"**Layer:** {model.layer or 'N/A'}",
            f"**Context:** Version={context.version}, Environment={context.environment}, Features={features}",
        ]

        if kind_val:
            body.append(f"**Kind:** {kind_val}")

        if model.description:
            body.append(f"**Description:** {model.description}")

        body.append("---")

        return {
            "cell_type": "markdown",
            "metadata": {},
            "source": [line + "\n" for line in body],
        }

    def _build_spark_settings_cells(
        self,
        settings: NotebookSettings,
    ) -> List[Dict[str, Any]]:
        cells: List[Dict[str, Any]] = []

        if settings.legacy_time_parser:
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {"tags": ["spark-config"]},
                    "outputs": [],
                    "source": [
                        "# Enable legacy time parser policy\n",
                        "%%sql\n",
                        "SET spark.sql.legacy.timeParserPolicy = LEGACY\n",
                    ],
                }
            )

        if settings.disable_broadcast_join:
            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {"tags": ["spark-config"]},
                    "outputs": [],
                    "source": [
                        "# Disable automatic broadcast joins\n",
                        'spark.conf.set("spark.sql.autoBroadcastJoinThreshold", -1)\n',
                    ],
                }
            )

        if settings.custom_spark_settings:
            lines = ["# Custom Spark settings\n"]
            for key, value in settings.custom_spark_settings.items():
                lines.append(f'spark.conf.set("{key}", "{value}")\n')

            cells.append(
                {
                    "cell_type": "code",
                    "execution_count": None,
                    "metadata": {"tags": ["spark-config"]},
                    "outputs": [],
                    "source": lines,
                }
            )

        return cells

    def _build_params_cell(
        self,
        model: ResolvedModel,
        context: BuildContext,
    ) -> Dict[str, Any]:
        lines = [
            "# Notebook parameters\n",
            'processing_date = spark.sql("SELECT current_date()").collect()[0][0]\n',
            f'version = "{context.version}"\n',
            f'environment = "{context.environment}"\n',
            "dry_run = False\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": lines,
        }

    def _build_imports_cell(self, model: ResolvedModel) -> Dict[str, Any]:
        lines = [
            "from pyspark.sql.functions import current_timestamp, lit\n",
            "from datetime import datetime\n",
            "import logging\n",
        ]

        # Add time import if logging enabled (needed for timing)
        lines.append("import time\n")

        lines.extend(
            [
                "\n",
                "logging.basicConfig(level=logging.INFO)\n",
                f'logger = logging.getLogger("{model.name}")\n',
            ]
        )

        # Add Fabric logging initialization if enabled
        lines.extend(
            [
                "\n",
                "# ---- FABRIC LOGGING FRAMEWORK ----\n",
                "try:\n",
                # "    import builtin.nb_utils_logging as nb_utils_logging\n",
                # "    from nb_utils_logging import FabricLogger\n",
                f'    _fabric_logger = FabricLogger("{self.logging_project}")\n',
                "    _logging_enabled = True\n",
                "except ImportError:\n",
                "    _logging_enabled = False\n",
                '    logger.warning("Fabric logging not available: {e}")\n',
            ]
        )

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": lines,
        }
    
    def _build_logger_import_cell(self) -> Dict[str, Any]:
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"tags": ["framework"]},
            "outputs": [],
            "source": [
                # "# Load shared Fabric merge / DQ / optimize framework\n",
                "%run nb_utils_logging",
            ],
        }
    
    def _build_framework_import_cell(self) -> Dict[str, Any]:
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"tags": ["framework"]},
            "outputs": [],
            "source": [
                # "# Load shared Fabric merge / DQ / optimize framework\n",
                "%run nb_utils_config",
            ],
        }
    
    def _build_markdown_cell(self, content: str) -> Dict[str, Any]:
        """Build a markdown cell with the given content."""
        return {
            "cell_type": "markdown",
            "metadata": {},
            "source": [content],
        }
    
    def _build_attach_lkh_cell(self) -> Dict[str, Any]:
        config = {
            "defaultLakehouse": {
                "name": self.logging_project,
            }
        }

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"tags": ["configure"]},
            "outputs": [],
            "source": [
                "%%configure\n",
                json.dumps(config, indent=2),
            ],
        }


    def _build_execute_sql_cell(
        self,
        model: ResolvedModel,
        sql: str,
        model_name_q: str,
        strategy: str,
        merge_keys: List[str],
        delete_keys: List[str],
        derived_sql: Optional[str],
        base_conversion_measures: Optional[List[str]] = None,
        conversion_lkp_tbl: Optional[str] = None,
        src_query_type: Optional[str] = None,
        purge_domain: Optional[str] = None,
        full_retention_months: Optional[int] = None,
        snapshot_months: Optional[int] = None,
        plan_over_plan: Optional[int] = None,
        partition_by: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        layer = (getattr(model, "layer", "") or "").lower()

        # Schema-only DDL (bronze) still executed inline
        if self._is_schema_only_ddl(sql, layer):
            return self._build_schema_ddl_cell(
                model_name_q=model_name_q,
                sql=derived_sql or sql,
            )

        # All-mode SCD2: override template SQL with SELECT T.* + explicit extra expressions
        _scd_fields = self._get_scd_historical_fields(model)
        _is_all_mode = _scd_fields in (['All'], ['all'], ['ALL'])
        if strategy == "load_scd2" and _is_all_mode:
            _source_tbl = model.source_table or ""
            _extra = [
                f"{col.expression} AS {col.name}"
                for col in model.columns
                if getattr(col, "expression", None) and col.expression != col.name
            ]
            if _extra:
                derived_sql = "SELECT DISTINCT\nT.*,\n" + ",\n".join(_extra) + f"\nFROM {_source_tbl} T"
            else:
                derived_sql = f"SELECT DISTINCT\nT.*\nFROM {_source_tbl} T"

        # Normal execution path: delegate to framework_execute
        return self._build_merge_execution_cell(
            model_name_q=model_name_q,
            sql=derived_sql or sql,
            strategy=strategy,
            merge_keys=merge_keys,
            delete_keys=delete_keys,
            base_conversion_measures=base_conversion_measures,
            conversion_lkp_tbl=conversion_lkp_tbl,
            src_query_type=src_query_type,
            purge_domain=purge_domain,
            full_retention_months=full_retention_months,
            snapshot_months=snapshot_months,
            plan_over_plan=plan_over_plan,
            partition_by=partition_by,
            scd_logical_key=self._get_scd_logical_key(model),
            scd_historical_fields=_scd_fields,
            skip_historical=self._get_skip_historical(model),
            source_table_override=model.source_table if strategy == "load_scd2" else None,
        )
    
    def _build_execute_sql_cell_unit_conversion(
        self,
        model: ResolvedModel,
        sql: str,
        model_name_q: str,
        strategy: str,
        merge_keys: List[str],
        delete_keys: List[str],
        derived_sql: Optional[str],
        base_conversion_measures: Optional[List[str]] = None,
        conversion_lkp_tbl: Optional[str] = None,
        src_query_type: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        layer = (getattr(model, "layer", "") or "").lower()

        # Normal execution path: delegate to framework_execute
        return self._build_merge_execution_cell_unit_conversion(
            model_name_q=model_name_q,
            sql=derived_sql or sql,
            strategy=strategy,
            merge_keys=merge_keys,
            delete_keys=delete_keys,
            base_conversion_measures=base_conversion_measures,
            conversion_lkp_tbl=conversion_lkp_tbl,
            src_query_type=src_query_type,
        )
    
    def _is_schema_only_ddl(self, sql: str, layer: str) -> bool:
        upper = sql.upper()
        return (
            layer == "bronze"
            and "CREATE OR REPLACE TABLE" in upper
            and " USING DELTA AS" not in upper
            and " AS SELECT" not in upper
            and not re.search(r"\bSELECT\b", upper)
        )

    def _build_schema_ddl_cell(
        self,
        model_name_q: str,
        sql: str,
    ) -> Dict[str, Any]:
        ddl = sql.strip().rstrip(";")
        escaped = escape_sql_string(ddl)

        content = [
            f"logger.info('Executing schema-only DDL for {model_name_q}')\n",
            f"target_tbl = '{model_name_q}'\n\n",
            f"# Check if source files exist for this model\n",
            f"check_for_model_files(domain, '{model_name_q.replace('bronze.', '')}', processing_date, extract_id)\n\n",
            f"spark.sql('DROP TABLE IF EXISTS {model_name_q}')\n\n",
            'ddl = """\n',
            escaped + "\n",
            '"""\n',
            "status = spark.sql(ddl)\n",
            "if status is not None:\n",
            "   status = 1\n\n",
            f"read_parquet_bulk(\n"
            f"    domain = domain, \n"
            f"    extract_id = extract_id, \n"
            f"    search_param = '_{model_name_q.replace('bronze.', '')}_', \n"
            f"    processing_date = processing_date, \n"
            f"    target_tbl = target_tbl, \n"
            f"    batchid = batchid\n"
            f")\n\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_merge_execution_cell(
        self,
        model_name_q: str,
        sql: str,
        strategy: str,
        merge_keys: List[str],
        delete_keys: List[str],
        base_conversion_measures: Optional[List[str]] = None,
        conversion_lkp_tbl: Optional[str] = None,
        src_query_type: Optional[str] = None,
        purge_domain: Optional[str] = None,
        full_retention_months: Optional[int] = None,
        snapshot_months: Optional[int] = None,
        plan_over_plan: Optional[int] = None,
        partition_by: Optional[List[str]] = None,
        scd_logical_key: Optional[List[str]] = None,
        scd_historical_fields: Optional[List[str]] = None,
        skip_historical: Optional[List[str]] = None,
        source_table_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build cell that delegates execution to framework_execute."""
        escaped_sql = sql.strip().rstrip(";")
        operation_type = get_operation_type(strategy)

        source_table = ""
        if "silver" in model_name_q:
            source_table = source_table_override or model_name_q.replace("silver.", "bronze.")
            content: List[str] = [
            "src_sql = '''\n",
            escaped_sql,
            "\n'''\n",
            "\n",
            "cfg = {\n",
            f"    'SOURCE_TABLE': '{source_table}',\n",
            f"    'TARGET_TABLE': '{model_name_q}',\n",
            "    'SOURCE_SQL': src_sql,\n",
            f"    'MERGE_KEYS': {merge_keys},\n",
            f"    'DELETE_KEYS': {delete_keys},\n",
            f"    'load_strategy': '{strategy}',\n",
        ]
        
        if "gold" in model_name_q or "interface" in model_name_q:
            source_table = source_table_override or (
                model_name_q.replace("gold.", "silver.") if "gold" in model_name_q
                else model_name_q.replace("interface.", "silver.")
            )
            
            content: List[str] = [
                "src_sql = '''\n",
                escaped_sql,
                "\n'''\n",
                "\n",
                "cfg = {\n",
                f"    'TARGET_TABLE': '{model_name_q}',\n",
                "    'SOURCE_SQL': src_sql,\n",
                f"    'MERGE_KEYS': {merge_keys},\n",
                f"    'DELETE_KEYS': {delete_keys},\n",
                f"    'load_strategy': '{strategy}',\n",
            ]
        
        # Add optional purge/retention configuration
        if purge_domain:
            content.append(f"    'purge_domain': '{purge_domain}',\n")
        if full_retention_months is not None:
            content.append(f"    'full_retention_months': {full_retention_months},\n")
        if snapshot_months is not None:
            content.append(f"    'snapshot_months': {snapshot_months},\n")
        if plan_over_plan is not None:
            content.append(f"    'plan_over_plan': {plan_over_plan},\n")
        if partition_by:
            content.append(f"    'PARTITION_BY': {partition_by},\n")
        # Add SCD2 configuration when present
        if scd_logical_key:
            content.append(f"    'LOGICAL_KEY': {scd_logical_key},\n")
            surrogate_key_col = '_'.join(scd_logical_key) + '_skey'
            content.append(f"    'SURROGATE_KEY_COL': '{surrogate_key_col}',\n")
        if scd_historical_fields:
            if scd_historical_fields in (['All'], ['all'], ['ALL']):
                content.append("    'HISTORICAL_FIELDS': 'All',\n")
            else:
                content.append(f"    'HISTORICAL_FIELDS': {scd_historical_fields},\n")
        if skip_historical:
            content.append(f"    'SKIP_HISTORICAL': {skip_historical},\n")
        
        content.extend(["}\n", "\n"])

        if 'script' in model_name_q:
            self.enable_logging = False
            # content.append("status = framework_execute(cfg)\n\n")
            if 'saleshistory_pre_load_script' in model_name_q:
                content.append(f"drop_rn('{model_name_q.replace('silver','bronze').replace('_pre_load_script','')}')\n\n")

            content.append("spark.sql(src_sql)\n\n")

            if 'saleshistory_pre_load_script' in model_name_q:
                content.append(f"drop_rn('{model_name_q.replace('silver','bronze').replace('_pre_load_script','')}')\n\n")

            logger.info(f"Model {model_name_q} identified as script. Executing SQL directly without logging or framework delegation.")

            content.append("from notebookutils import mssparkutils\n")
            content.append("mssparkutils.notebook.exit('Script detected. SQL executed directly. Exiting notebook to prevent further operations.')\n")

            # content.append("stop_notebook('Script detected. No further operations will be performed.')\n\n")

        # Static/functional tables or gold/interface layer: execute SQL directly, skip framework_execute
        if model_name_q.endswith('_functional') or model_name_q.endswith('_combinations') or 'gold' in model_name_q or 'interface' in model_name_q:
            self.enable_logging = True
            content.append("spark.sql(src_sql)\n")
            content.append(f"logger.info(f\"[DIRECT] Created {model_name_q} ({{spark.table('{model_name_q}').count()}} rows)\")\n")
            logger.info(f"Model {model_name_q} identified as static table. Executing SQL directly without framework_execute.")
            return {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": content,
            }
            
        self.enable_logging = True
        # Add logging instrumentation if enabled
        # if self.enable_logging:
        #     content.extend(
        #         [
        #             "# ---- CAPTURE BEFORE STATE (for logging) ----\n",
        #             f"_rows_before = spark.table('{model_name_q}').count() if spark.catalog.tableExists('{model_name_q}') else 0\n",
        #             "_op_start = time.time()\n",
        #             "\n",
        #         ]
        #     )

        content.append("status = framework_execute(cfg)\n")

        # Add logging after execution if enabled
        # if self.enable_logging:
        #     content.extend(
        #         [
        #             "\n",
        #             "# ---- LOG OPERATION ----\n",
        #             "_op_elapsed = time.time() - _op_start\n",
        #             f"_rows_after = spark.table('{model_name_q}').count() if status else _rows_before\n",
        #             "\n",
        #             "if _logging_enabled and status:\n",
        #             "    try:\n",
        #             "        _fabric_logger.log_operation(\n",
        #             f'            notebook_name="{model_name_q}",\n',
        #             f'            table_name="{model_name_q}",\n',
        #             f'            operation_type="{operation_type}",\n',
        #             "            rows_before=_rows_before,\n",
        #             "            rows_after=_rows_after,\n",
        #             "            execution_time=_op_elapsed,\n",
        #             "            message=\"Load completed successfully\"\n"
        #             "        )\n",
        #             "    except Exception as _log_err:\n",
        #             '        logger.warning(f"Failed to log operation: {_log_err}")\n',
        #         ]
        #     )

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_merge_execution_cell_unit_conversion(
        self,
        model_name_q: str,
        sql: str,
        strategy: str,
        merge_keys: List[str],
        delete_keys: List[str],
        base_conversion_measures: Optional[List[str]] = None,
        conversion_lkp_tbl: Optional[str] = None,
        src_query_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build cell that delegates execution to framework_execute."""
        escaped_sql = sql.strip().rstrip(";")
        operation_type = get_operation_type(strategy)

        if src_query_type:
            with_clause = "{with_clause}\nSELECT \n"
            final_select = "\t\t{final_select}\n"
            join_sql = "{join_sql}"
            escaped_sql = with_clause+final_select+"FROM "+model_name_q+ f" T\n{join_sql}"
            cta_sql = f"CREATE OR REPLACE TABLE {model_name_q} AS\n"+escaped_sql+"\n\n"

            content: List[str] = [
                f"logger.info(f'Table {model_name_q} will require unit conversion')\n\n",
                f"domain = '{model_name_q.split('.', 1)[1][:3]}'\n",
                f"main_tbl = '{model_name_q.split('.', 1)[1][4:]}'\n",
                f"conversion_lkp_tbl = '{conversion_lkp_tbl}'\n",
                f"base_measures = {base_conversion_measures}\n",
                f"rptmeasure_filter = None\n",
                "unit_filter = None\n\n\n",
                "with_clause, final_select, join_sql = build_unit_conversion_sql(\n"
                "    base_measures=base_measures,\n"
                "    domain=domain,\n"
                "    main_tbl=main_tbl,\n"
                "    rptmeasure_filter=rptmeasure_filter,\n"
                "    id_col=f'{conversion_lkp_tbl}id',\n",
                "    join_tbl=f'silver.{domain}_{conversion_lkp_tbl}',\n",
                "    join_tbl_key=f'{conversion_lkp_tbl}id',\n",
                "    unit_tbl=f'silver.{domain}_unit',\n",
                "    puc_tbl=f'silver.{domain}_productunitconversion',\n",
                "    guc_tbl=f'silver.{domain}_generalunitconversion',\n",
                "    filter=unit_filter,\n",
                "    unit_combos_tbl=f'silver.{domain}_unit_combinations'\n",
                ")\n\n\n"


                "src_sql = f'''\n",
                escaped_sql,
                "\n'''\n",
                "\n",
                
                
                f"if _show_fabric_logger_output:\n    print(f'''{cta_sql}''')\n\n",
                
                "print('Rows before unit conversion:')\n",
                f"print(spark.table(f'{model_name_q}').count())\n\n",
                f"spark.sql(f'''{cta_sql}''')\n\n",
                
                # "# ---- SAFE TABLE REPLACEMENT WITH BACKUP ----\n",
                # f"# Backup {model_name_q} before switch\n",
                # f"_backup_table = '{model_name_q}_backup'\n",
                # f"_tmp_table = '{model_name_q}_tmp'\n",
                # "try:\n",
                # f"    if spark.catalog.tableExists('{model_name_q}'):\n",
                # f"        spark.sql(f'DROP TABLE IF EXISTS {model_name_q}_backup')\n\n",
                # "        # Rename current table to backup\n",
                # f"        spark.sql(f'ALTER TABLE {model_name_q} RENAME TO {model_name_q}_backup')\n",
                # f"        logger.info(f'Backed up {model_name_q} to {model_name_q}_backup')\n",
                # "    \n",
                # f"    if spark.catalog.tableExists('{model_name_q}_tmp'):\n",
                # f"        spark.sql(f'ALTER TABLE {model_name_q}_tmp RENAME TO {model_name_q}')\n",
                # f"        logger.info(f'Switch {model_name_q}_tmp -> {model_name_q}')\n\n",
                # "    else:\n",
                # f"        raise Exception(f'Temporary table {model_name_q}_tmp does not exist. Restore from backup.')\n",
                # "    \n",
                # f"    _new_row_count = spark.table(f'{model_name_q}').count()\n",
                # "    if _new_row_count > 0:\n",
                # f"        if spark.catalog.tableExists('{model_name_q}_backup'):\n",
                # f"            spark.sql(f'DROP TABLE {model_name_q}_backup')\n",
                # f"            logger.info(f'Dropped backup table {model_name_q}_backup after successful replacement')\n",
                # "    else:\n",
                # f"        logger.warning(f'New table {model_name_q} is empty. Keeping backup {model_name_q}_backup for safety.')\n",
                # f"        spark.sql(f'DROP TABLE {model_name_q}')\n",
                # f"        spark.sql(f'ALTER TABLE {model_name_q}_backup RENAME TO {model_name_q}')\n\n",
                # f"        logger.warning(f'Restored {model_name_q} from backup due to invalid new table')\n",
                # f"        raise Exception(f'{model_name_q} failed validation. Restored from backup.')\n",
                # "\n",
                # "except Exception as _err:\n",
                # "    # Error handling: restore from backup if replacement failed\n",
                # "    logger.error(f'Error during table replacement: {_err}')\n",
                # f"    if spark.catalog.tableExists('{model_name_q}_backup'):\n",
                # "        try:\n",
                # f"            spark.sql(f'DROP TABLE IF EXISTS {model_name_q}')\n",
                # f"            spark.sql(f'ALTER TABLE {model_name_q}_backup RENAME TO {model_name_q}')\n",
                # f"            logger.info(f'Successfully restored {model_name_q} from backup {model_name_q}_backup')\n",
                # "        except Exception as _restore_err:\n",
                # "            logger.error(f'Failed to restore from backup: {_restore_err}')\n",
                # "    raise\n\n",
                
                "print('Rows after unit conversion:')\n",
                f"print(spark.table(f'{model_name_q}').count())\n\n",
            ]
        else:
            return None

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_merge_execution_cell_unit_conversion_v2(
        self,
        model_name_q: str,
        sql: str,
        strategy: str,
        merge_keys: List[str],
        delete_keys: List[str],
        base_conversion_measures: Optional[List[str]] = None,
        conversion_lkp_tbl: Optional[str] = None,
        src_query_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build cell for unit conversion using INSERT OVERWRITE with cached lookups."""

        if src_query_type:
            # Derive domain and main_tbl from model_name_q
            domain = model_name_q.split('.', 1)[1][:3]
            main_tbl = model_name_q.split('.', 1)[1][4:]

            content: List[str] = [
                f"logger.info(f'Table {model_name_q} will require unit conversion')\n\n",
                f"domain = '{domain}'\n",
                f"main_tbl = '{main_tbl}'\n",
                f"conversion_lkp_tbl = '{conversion_lkp_tbl}'\n",
                f"base_measures = {base_conversion_measures}\n",
                f"rptmeasure_filter = None\n",
                "unit_filter = None\n\n",
                "_uc_start = time.time()\n\n",
                "# ---- PERFORMANCE: Cache lookup tables to avoid repeated scans ----\n",
                "spark.sql(f\"CACHE TABLE silver.{domain}_{conversion_lkp_tbl}\")\n",
                "spark.sql(f\"CACHE TABLE silver.{domain}_unit\")\n",
                "spark.sql(f\"CACHE TABLE silver.{domain}_productunitconversion\")\n",
                "spark.sql(f\"CACHE TABLE silver.{domain}_generalunitconversion\")\n",
                "spark.sql(f\"CACHE TABLE silver.{domain}_unit_combinations\")\n\n",
                "with_clause, final_select, join_sql = build_unit_conversion_sql(\n"
                "    base_measures=base_measures,\n"
                "    domain=domain,\n"
                "    main_tbl=main_tbl,\n"
                "    rptmeasure_filter=rptmeasure_filter,\n"
                "    id_col=f'{conversion_lkp_tbl}id',\n",
                "    join_tbl=f'silver.{domain}_{conversion_lkp_tbl}',\n",
                "    join_tbl_key=f'{conversion_lkp_tbl}id',\n",
                "    unit_tbl=f'silver.{domain}_unit',\n",
                "    puc_tbl=f'silver.{domain}_productunitconversion',\n",
                "    guc_tbl=f'silver.{domain}_generalunitconversion',\n",
                "    filter=unit_filter,\n",
                "    unit_combos_tbl=f'silver.{domain}_unit_combinations'\n",
                ")\n\n",
                "src_sql = f'''\n",
                "{with_clause}\n",
                "SELECT \n",
                "\t\t{final_select}\n",
                f"FROM {model_name_q} T\n",
                "{join_sql}\n",
                "'''\n\n",
                "if _show_fabric_logger_output:\n",
                "    print(f'''Direct overwrite (no temp table):\n",
                "{src_sql}\n",
                "''')\n\n",
                f"_rows_before_uc = spark.table(f'{model_name_q}').count()\n",
                "print(f'Rows before unit conversion: {_rows_before_uc:,}')\n\n",
                "# ---- PERFORMANCE: Direct overwrite instead of CREATE + RENAME ----\n",
                f"spark.sql(f'''\nINSERT OVERWRITE TABLE {model_name_q}\n{{src_sql}}\n''')\n\n",
                f"_rows_after_uc = spark.table(f'{model_name_q}').count()\n",
                "print(f'Rows after unit conversion: {_rows_after_uc:,}')\n\n",
                "# ---- Cleanup caches ----\n",
                "try:\n",
                "    spark.sql(f\"UNCACHE TABLE silver.{domain}_{conversion_lkp_tbl}\")\n",
                "    spark.sql(f\"UNCACHE TABLE silver.{domain}_unit\")\n",
                "    spark.sql(f\"UNCACHE TABLE silver.{domain}_productunitconversion\")\n",
                "    spark.sql(f\"UNCACHE TABLE silver.{domain}_generalunitconversion\")\n",
                "    spark.sql(f\"UNCACHE TABLE silver.{domain}_unit_combinations\")\n",
                "except Exception:\n",
                "    pass\n\n",
                "_uc_elapsed = time.time() - _uc_start\n",
                "logger.info(f'Unit conversion completed in {_uc_elapsed:.1f} seconds ({_uc_elapsed/60:.1f} minutes)')\n",
            ]
        else:
            content: List[str] = [
                # f"logger.warning(f'No Unit conversion required for table {model_name_q}')\n",
            ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_dq_checks_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        merge_keys: List[str],
    ) -> Dict[str, Any]:
        """Call into framework DQ helper."""
        content = [
            # f"tbl = '{model_name_q}'\n",
            # f"merge_keys = {merge_keys}\n",
        ]

        # Add timing if logging enabled
        # if self.enable_logging:
        #     content.append("_dq_start = time.time()\n")

        

        # Add logging after DQ if enabled
        # if self.enable_logging:
        #     content.extend(
        #         [
        #             "\n",
        #             "# ---- LOG DQ CHECK ----\n",
        #             "_dq_elapsed = time.time() - _dq_start\n",
        #             "_row_cnt = spark.table(tbl).count() if status else 0\n",
        #             "\n",
        #             "if _logging_enabled and status:\n",
        #             "    try:\n",
        #             "        _fabric_logger.log_operation(\n",
        #             f'            notebook_name="{model_name_q}",\n',
        #             f'            table_name="{model_name_q}",\n',
        #             '            operation_type="DQ_CHECK",\n',
        #             "            rows_before=_row_cnt,\n",
        #             "            rows_after=_row_cnt,\n",
        #             "            execution_time=_dq_elapsed,\n",
        #             "            batchid=batchid,\n",
        #             '            message=f"DQ check completed: {_row_cnt:,} rows validated"\n',
        #             "        )\n",
        #             "    except Exception as _log_err:\n",
        #             '        logger.warning(f"Failed to log DQ check: {_log_err}")\n',
        #         ]
        #     )

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_purge_cell_opr(
        self,
        model_name_q: str,
        full_retention_months: int,
        snapshot_months: int,
    ) -> Dict[str, Any]:

        content = [
            "# Purge old versions (OPR table)\n",
            f"print(f'Starting purge for {model_name_q}')\n",
            "\n",
            # Get reference date at runtime
            f"_ref = spark.sql(\"SELECT MAX(Version_id) FROM {model_name_q}\").collect()[0][0]\n",
            "if _ref is None:\n",
            "    raise ValueError('No Version_id found. Aborting purge.')\n",
            "print(f'Reference Version_id (max): {_ref}')\n",
            "\n",
            # Count before
            f"_before = spark.sql(\"SELECT COUNT(*) FROM {model_name_q}\").collect()[0][0]\n",
            "print(f'Rows before purge: {_before:,}')\n",
            "\n",
            # Build delete SQL dynamically
            f"delete_sql = f\"\"\"\n"
            f"DELETE FROM {model_name_q}\n"
            f"WHERE NOT (\n"
            f"        Version_id BETWEEN add_months(date('{{_ref}}'), -{full_retention_months}) AND date('{{_ref}}')\n"
            f"    OR (\n"
            f"        Version_id BETWEEN add_months(date('{{_ref}}'), -{snapshot_months}) AND date('{{_ref}}')\n"
            f"        AND day(Version_id) = 1\n"
            f"    )\n"
            f")\n"
            f"\"\"\"\n",
            "\n",
            "print('\\nGenerated DELETE statement:')\n",
            "print(delete_sql)\n",
            "\n",
            # Execute delete
            "spark.sql(delete_sql)\n",
            "\n",
            # Count after
            f"_after = spark.sql(\"SELECT COUNT(*) FROM {model_name_q}\").collect()[0][0]\n",
            "print(f'Rows after purge: {_after:,}')\n",
            "print(f'Rows purged: {_before - _after:,}')\n",
            "\n",
            f"logger.info(f'Purged {{_before - _after:,}} rows from {model_name_q} "
            f"(retention: {full_retention_months} months full, {snapshot_months} months snapshots)')\n",
            "\n",
            # ---- FABRIC LOGGING ----
            # "_op_elapsed = 0  # Set to actual elapsed time if needed\n",
            # "if _logging_enabled:\n",
            # "    try:\n",
            # "        _fabric_logger.log_operation(\n",
            # f"            notebook_name=\"{model_name_q}\",\n",
            # f"            table_name=\"{model_name_q}\",\n",
            # "            operation_type=\"PURGE\",\n",
            # "            rows_before=_before,\n",
            # "            rows_after=_after,\n",
            # "            execution_time=_op_elapsed,\n",
            # "            message=f'Versions before: ' + str(spark.table(\"%s\").select(\"Version_id\").distinct().count()) + '\\n' + ' -> Versions after: ' + str(spark.table(\"%s\").select(\"Version_id\").distinct().count()),\n" % (model_name_q, model_name_q),
            # "            error_message=None,\n",
            # "            domain=None,\n",
            # "            deleted_combinations=delete_sql,\n",
            # "            source_file=None,\n",
            # "            status=None,\n",
            # "        )\n",
            # "    except Exception as _log_err:\n",
            # "        logger.warning(f'Failed to log operation: {_log_err}')\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_purge_cell_fct(
        self,
        model_name_q: str,
        full_retention_months: int,
        snapshot_months: int,
    ) -> Dict[str, Any]:

        content = [
            "# Purge old versions (FCT table)\n",
            "# Purge FOR SP not defined. This is just a placeholder\n",
            "# No execution will occur.\n\n\n",
            f"#print(f'Starting purge for {model_name_q}')\n",

            # Get reference date at runtime
            f"#_ref = spark.sql(\"SELECT MAX(Version_id) FROM {model_name_q}\").collect()[0][0]\n",
            "#if _ref is None:\n",
            "#    raise ValueError('No Version_id found. Aborting purge.')\n",
            "#print(f'Reference Version_id (max): {_ref}')\n",

            # Count before
            f"#_before = spark.sql(\"SELECT COUNT(*) FROM {model_name_q}\").collect()[0][0]\n",
            "#print(f'Rows before purge: {_before:,}')\n",

            # Build delete SQL dynamically
            f"#delete_sql = f\"\"\"\n"
            f"#DELETE FROM {model_name_q}\n"
            f"#WHERE NOT (\n"
            f"#        Version_id BETWEEN add_months(date('{{_ref}}'), -{full_retention_months}) AND date('{{_ref}}')\n"
            f"#    OR (\n"
            f"#        Version_id BETWEEN add_months(date('{{_ref}}'), -{snapshot_months}) AND date('{{_ref}}')\n"
            f"#        AND day(Version_id) = 1\n"
            f"#    )\n"
            f"#)\n"
            f"#\"\"\"\n",

            "#print('\\nGenerated DELETE statement:')\n",
            "#print(delete_sql)\n",

            # Execute delete
            "#spark.sql(delete_sql)\n",

            # Count after
            f"#_after = spark.sql(\"SELECT COUNT(*) FROM {model_name_q}\").collect()[0][0]\n",
            "#print(f'Rows after purge: {_after:,}')\n",

            "#print(f'Rows purged: {_before - _after:,}')\n",

            f"#logger.info(f'Purged {{_before - _after:,}} rows from {model_name_q} "
            f"#(retention: {full_retention_months} months full, {snapshot_months} months snapshots)')\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_plan_over_plan_cell(
        self,
        model_name_q: str,
        domain: str,
        merge_keys: List[str],
    ) -> Dict[str, Any]:
        """Build cell for PlanOverPlan processing."""
        content = [
            "# PlanOverPlan processing\n",
            f"logger.info(f'Starting PlanOverPlan processing for {model_name_q} in {domain} domain')\n",
            "\n",
            "try:\n",
            f"    build_PlanOverPlan('{model_name_q}', '{domain}', {merge_keys})\n",
            f"    logger.info(f'PlanOverPlan processing completed for {model_name_q}')\n",
            "except Exception:\n",
            f"    logger.error(f'PlanOverPlan processing failed for {model_name_q}')\n",
            "    raise\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_optimize_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        settings: NotebookSettings,
    ) -> Optional[Dict[str, Any]]:
        """Call into framework optimize helper."""
        # Runs OPTIMIZE + ZORDER + VACUUM via nb_config_optimize.run_optimize.
        # Skipped for script-only targets (name contains 'script').
        content = [
            f"tbl = '{model_name_q}'\n",
            "if 'script' not in tbl:\n",
            "    run_optimize(tbl)\n",
            "else:\n",
            "    logger.warning(f'Skipping optimize for script target {tbl}')\n",
        ]

        if not content:
            return None

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _build_parallelism_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
        settings: NotebookSettings,
    ) -> Optional[Dict[str, Any]]:
        """Optional hook for future parallelism logic.

        For now, keep notebooks simple and do nothing.
        """
        return None

    def _build_preview_cell(self, model_name_q: str) -> Dict[str, Any]:
        """Build a SELECT * LIMIT 10 preview cell appended to every bronze notebook."""
        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [
                f"# Preview — first 10 rows loaded into {model_name_q}\n",
                f'display(spark.sql("SELECT * FROM {model_name_q} LIMIT 10"))\n',
            ],
        }

    def _build_complete_cell(
        self,
        model: ResolvedModel,
        model_name_q: str,
    ) -> Dict[str, Any]:
        content = [
            f"logger.info('Completed {model_name_q}')\n",
        ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": content,
        }

    def _get_layer_name(self, model: ResolvedModel) -> str:
        """Extract layer name from model for logging purposes."""
        # Prefer explicit layer attribute if available
        if hasattr(model, "layer") and model.layer:
            return model.layer.upper()
        # Fallback to parsing model name
        model_name = (model.name or "").lower()
        if "silver" in model_name:
            return "SILVER"
        elif "gold" in model_name:
            return "GOLD"
        elif "bronze" in model_name:
            return "BRONZE"
        return "UNKNOWN"

    def _is_loggable_layer(self, model: ResolvedModel) -> bool:
        """Check if the model's layer supports logging (only SILVER and GOLD)."""
        layer = self._get_layer_name(model)
        return layer in ("SILVER", "GOLD", "INTERFACE")

    def _build_log_cell(
        self,
        model: ResolvedModel,
        log_type: str = "start",
    ) -> Optional[Dict[str, Any]]:
        """Build a logging cell for layer start or end.

        Only generates cells for SILVER and GOLD layers.
        Uses log_layer(layer, status) function from nb_utils_logging.

        Args:
            model: The resolved model
            log_type: Either 'start' or 'end'

        Returns:
            Cell dict or None if layer is not loggable (bronze/unknown)
        """
        layer = self._get_layer_name(model)

        # Only log for silver, gold, and interface layers
        if layer not in ("SILVER", "GOLD", "INTERFACE"):
            return None

        if log_type == "start":
            content = [
                f'log_layer(layer="{layer}", status="START")\n',
            ]
        else:
            content = [
                f'log_layer(layer="{layer}", status="SUCCESS")\n',
            ]

        return {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {"tags": ["logging"]},
            "outputs": [],
            "source": content,
        }

    def _build_start_log_cell(self, model: ResolvedModel) -> Optional[Dict[str, Any]]:
        """Build a logging cell for layer start (SILVER/GOLD only)."""
        return self._build_log_cell(model, log_type="start")

    def _build_end_log_cell(self, model: ResolvedModel) -> Optional[Dict[str, Any]]:
        """Build a logging cell for layer end (SILVER/GOLD only)."""
        return self._build_log_cell(model, log_type="end")
