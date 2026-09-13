"""Skeleton generator for creating YAML model files with vertical/horizontal layering."""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from rich.console import Console
from rich.progress import Progress, TaskID

from ..core.master_config import MasterConfig, ModelDefinition


console = Console()


class SkeletonGenerator:
    """Generator for creating skeleton YAML files from master configuration."""

    def __init__(self, config: MasterConfig):
        """Initialize the skeleton generator.

        Args:
            config: Master configuration containing all layer and model definitions
        """
        self.config = config
        self.output_dir = Path(config.project.output_dir)
        self.files_created = 0
        self.files_skipped = 0

    def generate_all(
        self,
        dry_run: bool = False,
        force: bool = False,
        progress: Optional[Progress] = None,
        task_id: Optional[TaskID] = None,
    ) -> Dict[str, int]:
        """Generate all skeleton files including variants.

        Args:
            dry_run: Preview without creating files
            force: Overwrite existing files
            progress: Optional progress tracker
            task_id: Optional task ID for progress updates

        Returns:
            Dictionary with creation statistics
        """
        self.files_created = 0
        self.files_skipped = 0

        # Process each vertical layer
        for vertical_name, vertical_models in self.config.models.items():
            if isinstance(vertical_models, list):
                # Direct models under vertical
                self._process_models(vertical_name, None, vertical_models, dry_run, force)
            elif isinstance(vertical_models, dict):
                # Nested structure (e.g., domain->retail)
                for sublayer_name, sublayer_models in vertical_models.items():
                    if isinstance(sublayer_models, list):
                        self._process_models(
                            vertical_name, sublayer_name, sublayer_models, dry_run, force
                        )

            if progress and task_id:
                progress.advance(task_id)

        # Generate build.yaml configuration file
        self._generate_build_config(dry_run, force)

        return {"created": self.files_created, "skipped": self.files_skipped}

    def _process_models(
        self,
        vertical: str,
        sublayer: Optional[str],
        models: List[Dict[str, Any]],
        dry_run: bool,
        force: bool,
    ):
        """Process models for a specific vertical/sublayer.

        Args:
            vertical: Vertical layer name
            sublayer: Optional sublayer name
            models: List of model definitions
            dry_run: Preview mode
            force: Overwrite existing files
        """
        for model_dict in models:
            # Convert dict to ModelDefinition
            model = ModelDefinition(**model_dict)

            # Determine output path
            path_parts = [self.output_dir, vertical]
            if sublayer:
                path_parts.append(sublayer)
            path_parts.append(model.horizontal_layer)

            output_path = Path(*path_parts)

            # Generate base file
            self._generate_base_file(model, output_path, vertical, sublayer, dry_run, force)

            # Generate variant files
            if model.variants:
                for variant in model.variants:
                    self._generate_variant_file(
                        model, variant, output_path, vertical, sublayer, dry_run, force
                    )

    def _generate_base_file(
        self,
        model: ModelDefinition,
        output_path: Path,
        vertical: str,
        sublayer: Optional[str],
        dry_run: bool,
        force: bool,
    ):
        """Generate base model skeleton file.

        Args:
            model: Model definition
            output_path: Directory path for output
            vertical: Vertical layer name
            sublayer: Optional sublayer name
            dry_run: Preview mode
            force: Overwrite existing files
        """
        file_path = output_path / f"{model.name}.yaml"

        # Build the YAML content
        content = self._build_base_content(model, vertical, sublayer)

        # Write or display
        self._write_file(file_path, content, dry_run, force, is_variant=False)

    def _generate_variant_file(
        self,
        model: ModelDefinition,
        variant: str,
        output_path: Path,
        vertical: str,
        sublayer: Optional[str],
        dry_run: bool,
        force: bool,
    ):
        """Generate variant/partial file skeleton.

        Args:
            model: Base model definition
            variant: Variant name
            output_path: Directory path for output
            vertical: Vertical layer name
            sublayer: Optional sublayer name
            dry_run: Preview mode
            force: Overwrite existing files
        """
        file_path = output_path / f"{model.name}.{variant}.yaml"

        # Build variant content
        content = self._build_variant_content(model, variant, vertical, sublayer)

        # Write or display
        self._write_file(file_path, content, dry_run, force, is_variant=True)

    def _build_base_content(
        self, model: ModelDefinition, vertical: str, sublayer: Optional[str]
    ) -> Dict[str, Any]:
        """Build content for base model file.

        Args:
            model: Model definition
            vertical: Vertical layer name
            sublayer: Optional sublayer name

        Returns:
            Dictionary containing YAML structure
        """
        # Map model kinds to valid Northstar Formation kinds
        kind_mapping = {"MATERIALIZED": "TABLE", "INCREMENTAL": "TABLE", "EPHEMERAL": "VIEW"}
        valid_kind = kind_mapping.get(model.kind, model.kind)

        # Build the core model definition
        model_config = {
            "name": model.name,
            "description": model.description or f"# TODO: Add description for {model.name}",
            "layer": model.horizontal_layer,
            "kind": valid_kind,
        }

        # Add inheritance if specified
        if model.inherits_from:
            model_config["inherits_from"] = model.inherits_from

        # Add extends if specified
        if model.extends:
            model_config["extends"] = model.extends

        content = {"model": model_config}

        # Add source configuration
        if model.inherits_from:
            # Extract parent information from inheritance path
            parent_parts = model.inherits_from.split(".")
            parent_name = parent_parts[-1]  # Last part is the model name
            content["source"] = {"base_table": parent_name}
        elif model.source_table:
            content["source"] = {"base_table": model.source_table}
        else:
            content["source"] = {"base_table": "# TODO: Specify source table"}

        # Add transformation skeleton with proper Northstar Formation format
        transformations = {}

        if model.inherits_from:
            transformations["inherit_columns"] = True

        # Add sample columns in the correct format
        transformations["columns"] = [
            {
                "name": "ID",
                "expression": "ID",  # Use expression, not transformation
                "data_type": "INTEGER",
            }
            # Add more columns as needed - see test-models for examples
        ]

        # Add commented example for additional columns
        transformations["# example_columns"] = [
            "# Add more columns like this:",
            "# - name: COLUMN_NAME",
            '#   expression: "column_name" or "@function()"',
            "#   data_type: VARCHAR(100)",
            "#   action: add  # optional: add, transform, rename, etc.",
        ]

        content["transformations"] = transformations

        # Add filters in correct format - must be objects with id and condition
        content["filters"] = {
            "where_conditions": [
                {
                    "id": "example_filter",
                    "condition": '# TODO: Add WHERE condition like status != "DELETED"',
                }
                # Add more filter conditions as needed
            ]
        }

        # Add aggregations if this might be an aggregated model
        if model.horizontal_layer in ["mart", "gold", "analytics"]:
            content["aggregations"] = {
                "group_by": ["# TODO: List columns to group by"],
                "having": ["# TODO: Add HAVING conditions if needed"],
            }

        # Add CTEs reference example
        content["# ctes"] = [
            "# Example CTE reference:",
            "# - name: quality_metrics_cte",
            "#   alias: QUALITY",
        ]

        return content

    def _build_variant_content(
        self, model: ModelDefinition, variant: str, vertical: str, sublayer: Optional[str]
    ) -> Dict[str, Any]:
        """Build content for variant/partial file.

        Args:
            model: Base model definition
            variant: Variant name
            vertical: Vertical layer name
            sublayer: Optional sublayer name

        Returns:
            Dictionary containing variant YAML structure
        """
        content = {"metadata": {"applies_when": self._determine_variant_conditions(variant)}}

        # Add variant-specific transformations in Northstar Formation format
        # Only add example comments, not actual invalid columns
        content["# transformations_example"] = [
            "# Add variant-specific transformations like this:",
            "# transformations:",
            "#   columns:",
            f"#     - name: {variant.upper()}_COLUMN",
            '#       expression: "some_expression"',
            "#       data_type: VARCHAR(100)",
            "#       action: add",
            "#     - name: EXISTING_COLUMN",
            "#       action: transform",
            f'#       expression: "{variant}-specific transformation"',
        ]

        # Add variant-specific filters as comments to avoid parsing errors
        content["# filters_example"] = [
            "# Add variant-specific filters like this:",
            "# filters:",
            "#   where_conditions:",
            f"#     - id: {variant}_filter",
            f"#       condition: \"column_name = '{variant}'\"",
        ]

        return content

    def _determine_variant_conditions(self, variant: str) -> Dict[str, str]:
        """Determine appropriate conditions for a variant.

        Args:
            variant: Variant name

        Returns:
            Dictionary with condition configuration
        """
        # Heuristics for common variant patterns
        if any(term in variant.lower() for term in ["customer", "client", "tenant"]):
            return {"customer": variant, "condition_type": "customer_specific"}
        elif any(term in variant.lower() for term in ["analytics", "ml", "ai", "features"]):
            return {"feature_set": variant, "condition_type": "feature_specific"}
        elif any(char.isdigit() for char in variant) and "v" in variant.lower():
            return {"version": f">= {variant}", "condition_type": "version_specific"}
        elif any(term in variant.lower() for term in ["region", "geo", "location"]):
            return {"region": variant, "condition_type": "geographical"}
        else:
            return {"# TODO": f"Define conditions for {variant}", "condition_type": "custom"}

    def _write_file(
        self,
        file_path: Path,
        content: Dict[str, Any],
        dry_run: bool,
        force: bool,
        is_variant: bool = False,
    ):
        """Write content to file or display in dry run mode.

        Args:
            file_path: Path to write file
            content: Content to write
            dry_run: Preview mode
            force: Overwrite existing files
            is_variant: Whether this is a variant file
        """
        if dry_run:
            variant_text = " (variant)" if is_variant else ""
            console.print(f"[blue]Would create{variant_text}:[/blue] {file_path}")
            # Show abbreviated content
            yaml_content = yaml.dump(content, default_flow_style=False, sort_keys=False)
            lines = yaml_content.split("\n")[:10]  # First 10 lines
            preview = "\n".join(lines)
            if len(lines) >= 10:
                preview += "\n  ... (truncated)"
            console.print(f"[dim]  Content preview:\n{preview}[/dim]")
            return

        # Check if file exists
        if file_path.exists() and not force:
            console.print(
                f"[yellow]Skipping existing file:[/yellow] {file_path} [dim](use --force to overwrite)[/dim]"
            )
            self.files_skipped += 1
            return

        # Create directory structure
        file_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        try:
            with open(file_path, "w") as f:
                yaml.dump(
                    content,
                    f,
                    default_flow_style=False,
                    sort_keys=False,
                    allow_unicode=True,
                    indent=2,
                )

            variant_text = " (variant)" if is_variant else ""
            if file_path.exists() and force:
                console.print(f"[green]Overwritten{variant_text}:[/green] {file_path}")
            else:
                console.print(f"[green]Created{variant_text}:[/green] {file_path}")

            self.files_created += 1

        except Exception as e:
            console.print(f"[red]Error writing file[/red] {file_path}: {e}")

    def get_generation_summary(self) -> Dict[str, Any]:
        """Get summary of generation process.

        Returns:
            Dictionary with generation statistics
        """
        total_verticals = len(self.config.models)
        total_horizontals = len(self.config.horizontal_layers)

        # Count total models and variants
        total_models = 0
        total_variants = 0

        for vertical_models in self.config.models.values():
            if isinstance(vertical_models, list):
                for model_dict in vertical_models:
                    model = ModelDefinition(**model_dict)
                    total_models += 1
                    if model.variants:
                        total_variants += len(model.variants)
            elif isinstance(vertical_models, dict):
                for sublayer_models in vertical_models.values():
                    if isinstance(sublayer_models, list):
                        for model_dict in sublayer_models:
                            model = ModelDefinition(**model_dict)
                            total_models += 1
                            if model.variants:
                                total_variants += len(model.variants)

        return {
            "project_name": self.config.project.name,
            "output_directory": str(self.output_dir),
            "total_verticals": total_verticals,
            "total_horizontals": total_horizontals,
            "total_models": total_models,
            "total_variants": total_variants,
            "files_created": self.files_created,
            "files_skipped": self.files_skipped,
        }

    def _generate_build_config(self, dry_run: bool, force: bool):
        """Generate build.yaml configuration file from master config.

        Args:
            dry_run: Preview mode
            force: Overwrite existing files
        """
        build_path = self.output_dir / "build.yaml"

        if build_path.exists() and not force:
            if not dry_run:
                console.print(f"[yellow]⚠[/yellow] Skipped existing build.yaml at {build_path}")
            self.files_skipped += 1
            return

        build_config = self._build_yaml_content()

        if dry_run:
            console.print(f"[dim]Would create:[/dim] {build_path}")
        else:
            build_path.parent.mkdir(parents=True, exist_ok=True)
            with open(build_path, "w") as f:
                yaml.dump(build_config, f, default_flow_style=False, sort_keys=False)
            console.print(f"[green]✓[/green] Created build.yaml at {build_path}")

        self.files_created += 1

    def _build_yaml_content(self) -> Dict[str, Any]:
        """Build the content for build.yaml based on master config.

        Returns:
            Dictionary containing the build configuration
        """
        # Extract unique variants from all models
        all_variants = set()
        customer_variants = set()

        for vertical_models in self.config.models.values():
            if isinstance(vertical_models, list):
                for model_dict in vertical_models:
                    model = ModelDefinition(**model_dict)
                    if model.variants:
                        all_variants.update(model.variants)
            elif isinstance(vertical_models, dict):
                for sublayer_models in vertical_models.values():
                    if isinstance(sublayer_models, list):
                        for model_dict in sublayer_models:
                            model = ModelDefinition(**model_dict)
                            if model.variants:
                                all_variants.update(model.variants)

        # Separate customers from features based on naming patterns
        feature_variants = set()
        for variant in all_variants:
            # Check if it looks like a customer name (from vertical layer names)
            is_customer = False
            for vertical_name, vertical_data in self.config.models.items():
                if isinstance(vertical_data, dict):
                    # Check sublayers - these are often customer names
                    if variant in vertical_data.keys():
                        customer_variants.add(variant)
                        is_customer = True
                        break

            if not is_customer:
                feature_variants.add(variant)

        # Extract customers from vertical layers with sublayers (tenant layer)
        for vertical_name, vertical_data in self.config.models.items():
            if isinstance(vertical_data, dict) and vertical_name.lower() in [
                "tenant",
                "customer",
                "client",
            ]:
                customer_variants.update(vertical_data.keys())

        # Build configuration
        build_config = {
            "# Generated build configuration from master_config.yaml": None,
            "default": {
                "customer": "STANDARD",
                "version": getattr(self.config.project, "version", "1.0.0"),
                "features": [],
                "environment": "production",
                "output_format": "notebook",
                "output_dir": "./results",
                "workspace_id": "YOUR_FABRIC_WORKSPACE_ID",
                "fabric_conn_id": "fabric_conn",
            },
        }

        # Add customer profiles
        if customer_variants:
            build_config["profiles"] = {}
            for customer in sorted(customer_variants):
                # Create sample feature combinations for each customer
                customer_features = (
                    list(feature_variants)[:3]
                    if len(feature_variants) >= 3
                    else list(feature_variants)
                )

                build_config["profiles"][customer.lower()] = {
                    "customer": customer.upper(),
                    "features": customer_features,
                    "output_dir": f"./results/{customer.lower()}",
                }

        # Add environment profiles
        build_config["dev"] = {
            "environment": "development",
            "features": list(feature_variants)[:1] if feature_variants else ["analytics"],
            "output_dir": "./results/dev",
            "output_format": "sql",
        }

        # Add full production profile with all features
        if feature_variants:
            build_config["prod_full"] = {
                "environment": "production",
                "output_format": "all",
                "features": sorted(list(feature_variants)),
                "output_dir": "./results/production",
            }

        # Clean up None values (from comments)
        return {k: v for k, v in build_config.items() if v is not None}
