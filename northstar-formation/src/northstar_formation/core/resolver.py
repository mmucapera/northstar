"""Model resolver for inheritance and references."""

from typing import Dict, List, Optional, Set

import networkx as nx

from ..utils.errors import CircularDependencyError, ResolutionError
from ..utils.logging import get_logger
from .models import (
    BuildContext,
    Column,
    ColumnAction,
    FilterCondition,
    JoinSpec,
    MergeConfig,
    Model,
    ModelKind,
    NotebookSettings,
    ResolvedModel,
)
from .parser import YAMLParser


logger = get_logger(__name__)


class ModelResolver:
    """Resolve models with inheritance and references."""

    def __init__(self, parser: YAMLParser, function_resolver=None):
        self.parser = parser
        self.function_resolver = function_resolver
        self.resolved_models: Dict[str, ResolvedModel] = {}
        self.dependency_graph = nx.DiGraph()

    def resolve_all(
        self, models: Dict[str, Model], context: BuildContext
    ) -> Dict[str, ResolvedModel]:
        """Resolve all models in dependency order.

        Args:
            models: Dictionary of model name to Model.
            context: Build context.

        Returns:
            Dictionary of model name to ResolvedModel.

        Raises:
            CircularDependencyError: If circular dependencies are detected.
        """
        logger.info(f"Resolving {len(models)} models")
        self._build_dependency_graph(models)
        if not nx.is_directed_acyclic_graph(self.dependency_graph):
            cycles = list(nx.simple_cycles(self.dependency_graph))
            raise CircularDependencyError(f"Circular dependencies detected: {cycles}")
        resolution_order = list(nx.topological_sort(self.dependency_graph))
        for model_name in resolution_order:
            if model_name in models:
                resolved = self.resolve_model(models[model_name], models, context)
                self.resolved_models[model_name] = resolved
                logger.debug(f"Resolved: {model_name}")
        logger.info(f"Successfully resolved {len(self.resolved_models)} models")
        return self.resolved_models

    def resolve_model(
        self, model: Model, all_models: Dict[str, Model], context: BuildContext
    ) -> ResolvedModel:
        logger.debug(f"Resolving model: {model.name}")
        logger.debug(f"Model source: {model.source}")
        logger.debug(f"Model has {len(model.transformations.columns)} columns")
        logger.debug(f"  Original source: {model.source.base_table if model.source else 'None'}")

        if model.extends or model.inherits_from:
            model = self._apply_inheritance(model, all_models)
            logger.debug(
                f"  After inheritance source: {model.source.base_table if model.source else 'None'}"
            )

        columns = self._resolve_columns(model)
        logger.debug(f"  Resolved {len(columns)} columns")

        source_table = self._resolve_source_table(model)
        logger.debug(f"  Resolved source table: {source_table}")

        cte_definitions, cte_models = self._resolve_ctes(model, all_models, context)
        where_clause = self._build_where_clause(model)

        group_by_clause = None
        having_clause = None
        if model.aggregations:
            group_by_clause = model.aggregations.group_by
            having_clause = model.aggregations.having

        base_alias = "T"
        joins: List[JoinSpec] = []
        if model.relationships:
            # Process foreign_keys (legacy format)
            if model.relationships.foreign_keys:
                for i, fk in enumerate(model.relationships.foreign_keys, start=1):
                    ref_alias = fk.alias or f"t{i}"
                    if fk.on_expression:
                        on_clause = fk.on_expression
                    else:
                        on_clause = (
                            f'{base_alias}."{fk.local_column}" = {ref_alias}."{fk.references_column}"'
                        )
                    joins.append(
                        JoinSpec(
                            join_type=fk.join_type,
                            ref_table=fk.references_table,
                            ref_alias=ref_alias,
                            on_clause=on_clause,
                        )
                    )
            # Process direct joins (new format)
            if model.relationships.joins:
                for join_def in model.relationships.joins:
                    joins.append(
                        JoinSpec(
                            join_type=join_def.join_type,
                            ref_table=join_def.ref_table,
                            ref_alias=join_def.ref_alias,
                            on_clause=join_def.on_clause,
                        )
                    )

        # Extract merge_config from source if available
        merge_config = None
        if model.source and model.source.merge_keys:
            merge_config = model.source.merge_keys

        # If source has an explicit load_strategy, ensure it is reflected in merge_config
        if model.source and model.source.load_strategy:
            if merge_config is None:
                merge_config = MergeConfig(load_strategy=model.source.load_strategy)
            elif not merge_config.load_strategy:
                merge_config = MergeConfig(
                    merge_keys=merge_config.merge_keys,
                    load_strategy=model.source.load_strategy,
                    delete_keys=merge_config.delete_keys,
                    non_nulls=merge_config.non_nulls,
                    partition_by=merge_config.partition_by,
                    base_conversion_measures=merge_config.base_conversion_measures,
                    conversion_lkp_tbl=merge_config.conversion_lkp_tbl,
                    src_query_type=merge_config.src_query_type,
                    purge_domain=merge_config.purge_domain,
                    full_retention_months=merge_config.full_retention_months,
                    snapshot_months=merge_config.snapshot_months,
                    plan_over_plan=merge_config.plan_over_plan,
                )
        scd_logical_key: List[str] = []
        scd_historical_fields: List[str] = []
        skip_historical: List[str] = []
        if model.source:
            scd_logical_key = model.source.scd_logical_key or []
            scd_historical_fields = model.source.scd_historical_fields or []
            skip_historical = getattr(model.source, "skip_historical", []) or []

        # Get notebook_settings from model (defaults to empty NotebookSettings)
        notebook_settings = getattr(model, "notebook_settings", None) or NotebookSettings()

        resolved_model = ResolvedModel(
            name=model.name,
            kind=model.kind,
            layer=model.layer,
            columns=columns,
            source_table=source_table,
            cte_definitions=cte_definitions,
            where_clause=where_clause,
            group_by_clause=group_by_clause,
            having_clause=having_clause,
            base_alias=base_alias,
            joins=joins,
            description=model.description,
            audits=model.audits,
            relationships=model.relationships,
            optimization=model.optimization,
            filters=model.filters,
            merge_config=merge_config,
            notebook_settings=notebook_settings,
            customer=model.customer,
            scd_logical_key=scd_logical_key,
            scd_historical_fields=scd_historical_fields,
            skip_historical=skip_historical,
        )
        resolved_model.derived_sql = getattr(model, "derived_sql", None)
        resolved_model._cte_models = cte_models
        return resolved_model

    def _build_dependency_graph(self, models: Dict[str, Model]) -> None:
        for model_name, model in models.items():
            self.dependency_graph.add_node(model_name)
            if model.extends:
                parent_name = self._extract_model_name(model.extends)
                self.dependency_graph.add_edge(parent_name, model_name)
            if model.inherits_from:
                parent_name = self._extract_model_name(model.inherits_from)
                self.dependency_graph.add_edge(parent_name, model_name)
            for cte in model.ctes:
                self.dependency_graph.add_edge(cte.name, model_name)
            if model.source and not self._is_raw_table(model.source.base_table):
                if model.source.base_table in models:
                    self.dependency_graph.add_edge(model.source.base_table, model_name)

    def _extract_model_name(self, reference: str) -> str:
        """Extract model name from reference.

        If reference is layer-qualified (e.g., 'bronze.fct_customer'), keep it as-is.
        Otherwise, return just the last part for backward compatibility.
        """
        parts = reference.split(".")
        for idx, part in enumerate(parts):
            if part in ("bronze", "silver", "gold", "interface"):
                return ".".join(parts[idx:])
        return parts[-1]

    def _is_raw_table(self, table_name: str) -> bool:
        if "." not in table_name:
            return False
        return True

    def _apply_inheritance(self, model: Model, all_models: Dict[str, Model]) -> Model:
        parent_ref = model.extends or model.inherits_from
        if not parent_ref:
            return model
        parent_name = self._extract_model_name(parent_ref)
        if parent_name not in all_models:
            raise ResolutionError(f"Parent model not found: {parent_name}")
        parent = all_models[parent_name]
        if parent.extends or parent.inherits_from:
            parent = self._apply_inheritance(parent, all_models)

        adjusted_parent_filters = parent.filters
        if model.transformations.inherit_columns and parent_name in self.resolved_models:
            parent_resolved = self.resolved_models[parent_name]
            column_mapping = {}
            for col in parent.transformations.columns:
                if col.expression and col.expression != col.name:
                    column_mapping[col.expression] = col.name
            from .models import Filters

            adjusted_conditions = []
            for cond in parent.filters.where_conditions:
                adjusted_condition = cond.condition
                import re

                def replace_with_output_name(match):
                    col_name = match.group(1)
                    return column_mapping.get(col_name, col_name)

                adjusted_condition = re.sub(
                    r"\b([a-z_][a-z0-9_]*)\b", replace_with_output_name, adjusted_condition
                )
                adjusted_conditions.append(
                    FilterCondition(
                        id=cond.id,
                        condition=adjusted_condition,
                        operation=cond.operation,
                        description=cond.description,
                    )
                )
            adjusted_parent_filters = Filters(where_conditions=adjusted_conditions)

        inherited_model = Model(
            name=model.name,
            description=model.description or parent.description,
            layer=model.layer or parent.layer,
            kind=model.kind,
            source=model.source if model.source else parent.source,
            transformations=parent.transformations.merge_with(model.transformations),
            filters=adjusted_parent_filters.merge_with(model.filters),
            aggregations=model.aggregations or parent.aggregations,
            ctes=parent.ctes + [cte for cte in model.ctes if cte not in parent.ctes],
            audits=model.audits or parent.audits,
            relationships=model.relationships or parent.relationships,
            optimization=model.optimization or parent.optimization,
        )
        return inherited_model

    def _resolve_columns(self, model: Model) -> List[Column]:
        columns: List[Column] = []
        processed_names = set()
        logger.debug(f"  Starting column resolution for {model.name}")
        logger.debug(
            f"    Input columns count: {len(model.transformations.columns) if model.transformations.columns else 0}"
        )
        if not model.transformations.columns:
            logger.warning(f"Model {model.name} has no columns defined")
            return columns
        for col in model.transformations.columns:
            logger.debug(f"    Processing column: {col.name} (action: {col.action})")
            if not col.action:
                resolved_expression = col.expression or col.name
                if self.function_resolver and resolved_expression and "@" in resolved_expression:
                    expanded_expression = self.function_resolver.resolve_expression(
                        resolved_expression
                    )
                    logger.debug(
                        f"      Function expansion: '{resolved_expression}' -> '{expanded_expression}'"
                    )
                    resolved_expression = expanded_expression
                columns.append(
                    Column(
                        name=col.name,
                        expression=resolved_expression,
                        data_type=col.data_type,
                        description=col.description,
                        nullable=col.nullable,
                    )
                )
                processed_names.add(col.name)
                logger.debug(f"      Added regular column: {col.name}")
                continue
            if col.action == ColumnAction.REMOVE:
                logger.debug(f"      Removing column: {col.name}")
                continue
            final_name = col.new_name if col.action == ColumnAction.RENAME else col.name
            if final_name in processed_names:
                logger.debug(f"      Skipping duplicate: {final_name}")
                continue
            resolved_expression = col.expression or col.name
            if self.function_resolver and resolved_expression and "@" in resolved_expression:
                expanded_expression = self.function_resolver.resolve_expression(resolved_expression)
                logger.debug(
                    f"      Function expansion: '{resolved_expression}' -> '{expanded_expression}'"
                )
                resolved_expression = expanded_expression
            columns.append(
                Column(
                    name=final_name,
                    expression=resolved_expression,
                    data_type=col.data_type,
                    description=col.description,
                    nullable=col.nullable,
                    action=col.action,
                )
            )
            processed_names.add(final_name)
            logger.debug(f"      Added action column: {final_name}")
        logger.debug(f"    Final column count: {len(columns)}")
        logger.debug(f"    Column names: {[c.name for c in columns]}")
        return columns

    def _resolve_source_table(self, model: Model) -> str:
        if not model.source:
            if model.inherits_from:
                parent_name = self._extract_model_name(model.inherits_from)
                logger.debug(f"Model {model.name} using inherited source: {parent_name}")
                return parent_name
            raise ResolutionError(f"Model {model.name} has no source defined")
        if not model.source.base_table:
            raise ResolutionError(f"Model {model.name} source has no base_table defined")
        base_table = model.source.base_table
        if base_table == model.name:
            logger.warning(
                f"Model {model.name} references itself as source - checking for inheritance"
            )
            if model.inherits_from:
                parent_name = self._extract_model_name(model.inherits_from)
                logger.debug(f"Using inherited parent {parent_name} as source instead")
                return parent_name
        if hasattr(model.source, "table_schema") and model.source.table_schema:
            base_table = f"{model.source.table_schema}.{base_table}"
        if hasattr(model.source, "database") and model.source.database:
            base_table = f"{model.source.database}.{base_table}"
        return base_table

    def _resolve_ctes(
        self, model: Model, all_models: Dict[str, Model], context: BuildContext
    ) -> tuple[Dict[str, str], Dict[str, "ResolvedModel"]]:
        cte_definitions: Dict[str, str] = {}
        cte_models: Dict[str, ResolvedModel] = {}
        for cte_ref in model.ctes:
            if cte_ref.name in all_models:
                cte_model = all_models[cte_ref.name]
                if cte_model.kind != ModelKind.CTE:
                    logger.warning(f"Referenced model {cte_ref.name} is not a CTE")
                    continue
                resolved_cte = self.resolve_model(cte_model, all_models, context)
                cte_sql = self._generate_cte_sql(resolved_cte)
                cte_definitions[cte_ref.alias] = cte_sql
                cte_models[cte_ref.alias] = resolved_cte
            else:
                logger.warning(f"CTE {cte_ref.name} not found")
        return cte_definitions, cte_models

    def _generate_cte_sql(self, model: ResolvedModel) -> str:
        if not model.columns:
            logger.warning(f"CTE {model.name} has no columns")
            return f"SELECT * FROM {model.source_table}"
        columns = model.columns
        if self.function_resolver:
            for column in columns:
                if column.expression and "@" in column.expression:
                    column.expression = self.function_resolver.resolve_expression(column.expression)
        columns_sql = ", ".join(
            [
                f"{col.expression} AS {col.name}" if col.expression != col.name else col.name
                for col in columns
            ]
        )
        sql = f"SELECT {columns_sql} FROM {model.source_table}"
        where_clause = model.where_clause
        if where_clause and self.function_resolver and "@" in where_clause:
            where_clause = self.function_resolver.resolve_expression(where_clause)
        if where_clause:
            sql += f" WHERE {where_clause}"
        if model.group_by_clause:
            sql += f" GROUP BY {', '.join(model.group_by_clause)}"
        having_clause = model.having_clause
        if having_clause and self.function_resolver:
            expanded_having = []
            for clause in having_clause:
                expanded_having.append(
                    self.function_resolver.resolve_expression(clause) if "@" in clause else clause
                )
            having_clause = expanded_having
        if having_clause:
            sql += f" HAVING {' AND '.join(having_clause)}"
        return sql

    def _build_where_clause(self, model: Model) -> Optional[str]:
        if not model.filters.where_conditions:
            return None
        conditions = []
        for filter_cond in model.filters.where_conditions:
            condition = filter_cond.condition
            if model.source and model.source.base_table and "" not in model.source.base_table:
                import re

                sql_keywords = {
                    "AND",
                    "OR",
                    "NOT",
                    "IS",
                    "NULL",
                    "IN",
                    "BETWEEN",
                    "LIKE",
                    "EXISTS",
                    "DISTINCT",
                    "ALL",
                    "ANY",
                    "SOME",
                    "TRUE",
                    "FALSE",
                    "CASE",
                    "WHEN",
                    "THEN",
                    "ELSE",
                    "END",
                    "ASC",
                    "DESC",
                }

                def replace_column_names(match):
                    word = match.group(1)
                    if word.upper() in sql_keywords or word.isdigit() or "." in word:
                        return word
                    if match.start() > 1 and condition[match.start() - 2 : match.start()] == "T.":
                        return word
                    return f"T.{word}"

                condition = re.sub(
                    r'\b([A-Za-z_][A-Za-z0-9_]*)\b(?![.\'"()])', replace_column_names, condition
                )
            conditions.append(f"({condition})")
        return " AND ".join(conditions) if conditions else None


# Keep this: CLI imports it
class DependencyAnalyzer:
    """Analyze dependencies between models."""

    def __init__(self, models: Dict[str, Model]):
        self.models = models
        self.graph = nx.DiGraph()
        self._build_graph()

    def _build_graph(self):
        for name, model in self.models.items():
            self.graph.add_node(name, layer=model.layer)
            if model.extends:
                parent = self._extract_model_name(model.extends)
                if parent in self.models:
                    self.graph.add_edge(parent, name, type="extends")
            if model.inherits_from:
                parent = self._extract_model_name(model.inherits_from)
                if parent in self.models:
                    self.graph.add_edge(parent, name, type="inherits")
            for cte in model.ctes:
                if cte.name in self.models:
                    self.graph.add_edge(cte.name, name, type="cte")
            if model.source and "." not in model.source.base_table:
                ref = model.source.base_table
                if ref in self.models:
                    self.graph.add_edge(ref, name, type="source")

    def _extract_model_name(self, reference: str) -> str:
        """Extract model name from reference.

        If reference is layer-qualified (e.g., 'bronze.fct_customer'), keep it as-is.
        Otherwise, return just the last part for backward compatibility.
        """
        parts = reference.split(".")
        for idx, part in enumerate(parts):
            if part in ("bronze", "silver", "gold", "interface"):
                return ".".join(parts[idx:])
        return parts[-1]

    def get_dependencies(self, model_name: str) -> Set[str]:
        if model_name not in self.graph:
            return set()
        return set(nx.ancestors(self.graph, model_name))

    def get_dependents(self, model_name: str) -> Set[str]:
        if model_name not in self.graph:
            return set()
        return set(nx.descendants(self.graph, model_name))

    def get_resolution_order(self) -> List[str]:
        if not nx.is_directed_acyclic_graph(self.graph):
            cycles = list(nx.simple_cycles(self.graph))
            raise CircularDependencyError(f"Circular dependencies: {cycles}")
        return list(nx.topological_sort(self.graph))

    def validate_layer_hierarchy(self) -> List[str]:
        return []
