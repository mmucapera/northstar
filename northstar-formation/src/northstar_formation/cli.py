# src/northstar_formation/cli.py
"""Command-line interface for Northstar Formation."""

import copy
import json
import sys
from pathlib import Path
from typing import Any, Dict, Optional

import click
import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from .core.master_config import filter_by_horizontal, filter_by_vertical, load_master_config
from .core.models import BuildContext, LakehouseConfig
from .core.parser import YAMLParser
from .core.resolver import DependencyAnalyzer, ModelResolver
from .dummy_data import DummyDataGenerator
from .functions.registry import FunctionRegistry, FunctionResolver
from .generators.notebook import FabricNotebookGenerator
from .generators.library_copy import (
    copy_library_notebooks,
    copy_auth_files,
    copy_demo_data_files,
    write_lakehouse_placeholder,
)
from .generators.ddl_notebook import generate_ddl_notebook
from .generators.pipelines import build_manifest, load_notebook_ids_from_manifest, load_models, build_layer_pipeline, _read_yaml, _write_text, uuid_for_object_id, uuid_from_display_name
from .generators.semantic_model import generate_semantic_model, SemanticModelGenError
from .generators.report import generate_self_service_report, ReportGenError
from .generators.skeleton import SkeletonGenerator
from .sql.generator import SparkSQLGenerator
from .utils.errors import UIXTransformError
from .utils.logging import get_logger, setup_logging
from .validators.pipeline import ValidationPipeline


console = Console()
logger = get_logger(__name__)


def load_build_config(profile: Optional[str] = None) -> dict:
    """Load build configuration from build.yaml file."""
    # Look for build.yaml in current directory or config/ subdirectory
    config_paths = [
        Path.cwd() / "build.yaml",
        Path.cwd() / "config" / "build.yaml",
        Path.cwd() / "configs" / "build.yaml",
    ]

    config_file = None
    for path in config_paths:
        if path.exists():
            config_file = path
            break

    if not config_file:
        return {}

    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)

        # Start with default configuration
        build_config = config.get("default", {})

        # Apply profile if specified
        if profile and profile in config.get("profiles", {}):
            profile_config = config["profiles"][profile]
            build_config.update(profile_config)
            logger.info(f"Using build profile: {profile}")
        elif profile and profile in config:
            # Direct profile access (e.g., dev, prod_full)
            profile_config = config[profile]
            build_config.update(profile_config)
            logger.info(f"Using build profile: {profile}")
        elif profile:
            console.print(
                f"[yellow]Warning: Profile '{profile}' not found in build.yaml, using defaults[/yellow]"
            )

        if config_file:
            logger.info(f"Loaded build configuration from: {config_file}")

        return build_config
    except Exception as e:
        console.print(f"[yellow]Warning: Failed to load build.yaml: {e}[/yellow]")
        return {}


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging")
@click.option("--config", type=click.Path(exists=True), help="Configuration file")
@click.pass_context
def cli(ctx, debug, config):
    """Northstar Formation - YAML to Spark SQL transformation tool."""
    # Setup logging
    setup_logging(debug=debug)

    # Load configuration if provided
    ctx.ensure_object(dict)
    if config:
        with open(config) as f:
            ctx.obj["config"] = yaml.safe_load(f)
    else:
        ctx.obj["config"] = {}


@cli.command()
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base",
    "-b",
    type=click.Path(exists=True),
    help="Base models directory (models are merged with base)",
)
@click.option("--profile", "-p", help="Build profile from build.yaml")
@click.option("--output", "-o", type=click.Path(), help="Output directory")
@click.option("--customer", help="Customer identifier (overrides build.yaml)")
@click.option("--version", help="Version string (overrides build.yaml)")
@click.option("--features", help="Comma-separated feature flags (overrides build.yaml)")
@click.option("--environment", help="Target environment (overrides build.yaml)")
@click.option("--model", help="Transform specific model only")
@click.option("--dry-run", is_flag=True, help="Preview without generating files")
@click.option("--explain", is_flag=True, help="Show detailed execution plan")
@click.option(
    "--generate-notebooks",
    "generate_notebooks",
    type=str,
    default=None,
    help="Generate Fabric notebooks alongside SQL (optionally specify default lakehouse name)",
)
@click.option(
    "--notebook-output",
    type=click.Path(),
    help="Output directory for notebooks (defaults to output/notebooks)",
)
@click.option(
    "--output-format",
    type=click.Choice(["sql", "notebook", "all"]),
    help="Output format (overrides build.yaml)",
)
@click.option(
    "--lakehouse-name",
    help="Default lakehouse name for notebook generation",
)
@click.option(
    "--lakehouse-id",
    help="Default lakehouse GUID for notebook generation",
)
@click.option(
    "--lakehouse-workspace-id",
    help="Default lakehouse workspace GUID for notebook generation",
)
@click.option(
    "--enable-logging/--no-logging",
    default=False,
    help="Enable Fabric logging instrumentation in generated notebooks",
)
@click.option(
    "--logging-project",
    help="Logging project name (default: UnisonInsights-{customer})",
)
@click.option(
    "--config-version",
    "config_version",
    type=str,
    default=None,
    help="CONFIG functions version to copy (e.g. v1, v2). Defaults to the highest available under libraries/UTL/CONFIG/_functions/.",
)
@click.pass_context
def transform(
    ctx,
    models_dir,
    base,
    profile,
    output,
    customer,
    version,
    features,
    environment,
    model,
    dry_run,
    explain,
    generate_notebooks,
    notebook_output,
    output_format,
    lakehouse_name,
    lakehouse_id,
    lakehouse_workspace_id,
    enable_logging,
    logging_project,
    config_version,
):
    """Transform YAML models to Spark SQL."""
    console.print(f"[bold blue]Northstar Formation[/bold blue] - Transforming models from {models_dir}")

    # Load build configuration
    build_config = load_build_config(profile)

    # Use CLI options to override build config (CLI takes precedence)
    # Derive customer from models directory if not explicitly set
    _config_customer = build_config.get("customer", "STANDARD")
    if not customer and _config_customer == "STANDARD":
        # Try to infer from models_dir path (e.g. models/customers/customer0 -> customer0)
        _models_path = Path(models_dir)
        if _models_path.parent.name == "customers":
            _config_customer = _models_path.name
    final_customer = customer or _config_customer
    final_version = version or build_config.get("version", "1.0.0")
    final_environment = environment or build_config.get("environment", "production")
    final_output = output or build_config.get("output_dir")
    final_output_format = output_format or build_config.get("output_format", "sql")

    # Handle features - can be string from CLI or list from config
    if features:
        feature_list = features.split(",")
    elif build_config.get("features"):
        feature_list = (
            build_config["features"]
            if isinstance(build_config["features"], list)
            else build_config["features"].split(",")
        )
    else:
        feature_list = []

    # Build context
    context = BuildContext(
        customer=final_customer,
        version=final_version,
        features=feature_list,
        environment=final_environment,
    )

    console.print(
        f"[dim]Build Context: {final_customer} v{final_version} [{', '.join(feature_list) or 'no features'}][/dim]"
    )
    if profile:
        console.print(f"[dim]Using profile: {profile}[/dim]")

    # Backward compatibility: if generate_notebooks is used, include notebooks in output
    if generate_notebooks and final_output_format == "sql":
        final_output_format = "all"

    try:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            # Initialize components
            task = progress.add_task("Initializing...", total=None)

            parser = YAMLParser(models_dir)

            # Load dynamic functions
            progress.update(task, description="Loading functions...")
            registry = FunctionRegistry()
            config_dir = Path(models_dir) / "config"
            if config_dir.exists():
                registry.load_functions(config_dir, context)

            function_resolver = FunctionResolver(registry)
            resolver = ModelResolver(parser, function_resolver)
            generator = SparkSQLGenerator(function_resolver)

            # Determine default logging project name upfront (used for CTAS generation)
            if generate_notebooks and generate_notebooks.strip():
                # Value was provided to --generate-notebooks, use it as the default lakehouse
                final_logging_project = generate_notebooks
            else:
                # No value provided to --generate-notebooks, use the standard default
                final_logging_project = logging_project or f"UnisonInsights-{final_customer}"

            # Initialize notebook generator if requested
            notebook_generator = None
            if final_output_format in ["notebook", "all"] or generate_notebooks is not None:
                # Build default lakehouse config from CLI options
                default_lakehouse = None
                if lakehouse_name or lakehouse_id or lakehouse_workspace_id:
                    default_lakehouse = LakehouseConfig(
                        name=lakehouse_name,
                        id=lakehouse_id,
                        workspace_id=lakehouse_workspace_id,
                    )
                notebook_generator = FabricNotebookGenerator(
                    generator,
                    default_lakehouse=default_lakehouse,
                    enable_logging=enable_logging,
                    logging_project=final_logging_project,
                )

            # Load models
            progress.update(task, description="Loading models...")

            # If base directory is specified, load base models first then merge with customer models
            if base:
                base_parser = YAMLParser(base)
                base_models = base_parser.load_all_models(context)
                customer_models = parser.load_all_models(context)

                # Merge: customer models extend/override base models
                models = _merge_base_and_customer_models(base_models, customer_models)
                excluded_models = _load_excluded_models(Path(models_dir))
                if excluded_models:
                    models = {
                        name: model
                        for name, model in models.items()
                        if name.lower() not in excluded_models
                    }
                    console.print(
                        f"[dim]Excluded {len(excluded_models)} customer model(s)[/dim]"
                    )
                console.print(
                    f"[green]✓[/green] Loaded {len(base_models)} base model(s) + {len(customer_models)} customer model(s) = {len(models)} merged"
                )
            else:
                models = parser.load_all_models(context)
                console.print(f"[green]✓[/green] Loaded {len(models)} model(s)")

            if model:
                # Filter to specific model
                if model not in models:
                    console.print(f"[red]Model '{model}' not found[/red]")
                    sys.exit(1)
                models = {model: models[model]}

            # Validate models
            progress.update(task, description="Validating models...")
            validator = ValidationPipeline()
            validation_result = validator.validate(models)

            if not validation_result.is_valid:
                console.print("[red]Validation failed:[/red]")
                for error in validation_result.errors:
                    console.print(f"  {error}")
                sys.exit(1)

            if validation_result.warnings:
                console.print("[yellow]Warnings:[/yellow]")
                for warning in validation_result.warnings:
                    console.print(f"  {warning}")

            # Resolve models
            progress.update(task, description="Resolving dependencies...")
            resolved_models = resolver.resolve_all(models, context)

            # Show execution plan if requested
            if explain:
                _show_execution_plan(models, resolved_models)

            # Generate SQL
            progress.update(task, description="Generating SQL...")
            sql_outputs = generator.generate_all(resolved_models, context.__dict__)

            console.print(f"[green]✓[/green] Generated SQL for {len(sql_outputs)} model(s)")

            # Generate notebooks if requested
            notebook_outputs = {}
            if notebook_generator:
                progress.update(task, description="Generating notebooks...")
                notebook_outputs = notebook_generator.generate_all(
                    resolved_models, sql_outputs, context
                )
                console.print(
                    f"[green]✓[/green] Generated notebooks for {len(notebook_outputs)} model(s)"
                )

            # Output results
            if dry_run:
                console.print("\n[yellow]Dry run mode - SQL preview:[/yellow]")
                for name, sql in sql_outputs.items():
                    console.print(f"\n[bold]{name}:[/bold]")
                    console.print(sql)

                # Show notebook preview if generated
                if notebook_outputs:
                    console.print(
                        "\n[yellow]Notebook generation preview (Fabric .Notebook format):[/yellow]"
                    )
                    for name in notebook_outputs:
                        console.print(f"  📓 {name}.Notebook/")
            elif final_output:
                output_path = Path(final_output)
                # Only append /sql if the path doesn't already end with 'sql'
                if output_path.name.lower() == "sql":
                    sql_dir = output_path
                else:
                    sql_dir = output_path / "sql"
                _save_outputs(sql_outputs, sql_dir, models)
                console.print(f"[green]✓[/green] Saved SQL files to {sql_dir}")

                # Save notebooks if generated
                if notebook_outputs:
                    notebook_dir = (
                        Path(notebook_output)
                        if notebook_output
                        else Path(final_output) / "notebooks"
                    )
                    _save_notebook_outputs(
                        notebook_outputs, notebook_dir, models, customer=final_customer
                    )
                    console.print(f"[green]✓[/green] Saved Fabric notebooks to {notebook_dir}")

                    # Copy library notebooks from libraries/UTL into output, replacing lakehouse name
                    progress.update(task, description="Copying library notebooks...")
                    lib_count = copy_library_notebooks(
                        output_dir=Path(final_output),
                        lakehouse_name=final_logging_project,
                        config_version=config_version,
                    )
                    if lib_count > 0:
                        console.print(f"[green]✓[/green] Copied {lib_count} library notebook(s) to {notebook_dir / 'UTL'}")

                    # Copy auth/ (auth notebooks + pl_auth pipeline) as a sibling
                    # of this ENG output, not nested inside it
                    progress.update(task, description="Copying auth folder...")
                    auth_count = copy_auth_files(
                        output_dir=Path(final_output),
                        lakehouse_name=final_logging_project,
                    )
                    if auth_count > 0:
                        console.print(f"[green]✓[/green] Copied auth folder ({auth_count} notebook(s) + pl_auth pipeline) to {Path(final_output).parent / 'auth'}")

                    # Copy demo_data/ (nested inside this data_engineering
                    # output, unlike auth/ which is a sibling) - customer-
                    # specific, so resolved from this customer's own models dir.
                    progress.update(task, description="Copying demo_data folder...")
                    demo_data_count = copy_demo_data_files(
                        output_dir=Path(final_output),
                        lakehouse_name=final_logging_project,
                        demo_data_dir=Path(models_dir) / "demo_data",
                    )
                    if demo_data_count > 0:
                        console.print(f"[green]✓[/green] Copied demo_data folder ({demo_data_count} notebook(s)) to {Path(final_output) / 'demo_data'}")

                    # Reference-only Lakehouse placeholder (.platform, no
                    # definition/) for visibility in the output tree - NOT
                    # deployed via fabric-cicd, Lakehouse stays Terraform-managed.
                    progress.update(task, description="Writing lakehouse placeholder...")
                    lh_dir = write_lakehouse_placeholder(
                        output_dir=Path(final_output),
                        lakehouse_name=final_logging_project,
                    )
                    console.print(f"[green]✓[/green] Wrote lakehouse placeholder to {lh_dir}")

                    # Generate DDL notebook from SQL output files
                    progress.update(task, description="Generating DDL notebook...")
                    ddl_path = generate_ddl_notebook(
                        output_dir=Path(final_output),
                        lakehouse_name=final_logging_project,
                        customer=final_customer,
                    )
                    if ddl_path:
                        console.print(f"[green]✓[/green] Generated DDL notebook at {ddl_path}")
            # Print to stdout
            elif final_output_format in ["sql", "all"]:
                for name, sql in sql_outputs.items():
                    console.print(f"\n-- {name}")
                    console.print(sql)
                    console.print()

    except UIXTransformError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Unexpected error: {e}[/red]")
        if ctx.obj.get("debug"):
            console.print_exception()
        sys.exit(1)


@cli.command()
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base",
    "-b",
    type=click.Path(exists=True),
    help="Base models directory (models are merged with base)",
)
@click.option("--customer", default="STANDARD", help="Customer identifier")
@click.option("--version", default="1.0.0", help="Version string")
@click.option("--features", help="Comma-separated feature flags")
@click.option("--strict", is_flag=True, help="Treat warnings as errors")
def validate(models_dir, base, customer, version, features, strict):
    """Validate YAML models without generating SQL."""
    console.print(f"[bold blue]Northstar Formation[/bold blue] - Validating models from {models_dir}")

    # Build context
    feature_list = features.split(",") if features else []
    context = BuildContext(customer=customer, version=version, features=feature_list)

    try:
        # Initialize components
        parser = YAMLParser(models_dir)

        # Load models (with base merge if specified)
        if base:
            base_parser = YAMLParser(base)
            base_models = base_parser.load_all_models(context)
            customer_models = parser.load_all_models(context)
            models = _merge_base_and_customer_models(base_models, customer_models)
            console.print(
                f"[dim]Loaded {len(base_models)} base + {len(customer_models)} customer = {len(models)} merged[/dim]"
            )
        else:
            models = parser.load_all_models(context)
            console.print(f"[dim]Loaded {len(models)} model(s)[/dim]")

        # Validate
        validator = ValidationPipeline()
        result = validator.validate(models)

        # Show results
        if result.errors:
            console.print("\n[red]Errors:[/red]")
            for error in result.errors:
                console.print(f"  {error}")

        if result.warnings:
            console.print("\n[yellow]Warnings:[/yellow]")
            for warning in result.warnings:
                console.print(f"  {warning}")

        if result.is_valid and not (strict and result.warnings):
            console.print("\n[green]✓ Validation passed[/green]")
            sys.exit(0)
        else:
            console.print("\n[red]✗ Validation failed[/red]")
            sys.exit(1)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("models_dir", type=click.Path(exists=True))
@click.option("--customer", default="STANDARD", help="Customer identifier")
@click.option("--format", type=click.Choice(["text", "json", "yaml"]), default="text")
def plan(models_dir, customer, format):
    """Show execution plan for models."""
    console.print(f"[bold blue]Northstar Formation[/bold blue] - Analyzing {models_dir}")

    context = BuildContext(customer=customer)

    try:
        # Load models
        parser = YAMLParser(models_dir)
        models = parser.load_all_models(context)

        # Analyze dependencies
        analyzer = DependencyAnalyzer(models)

        # Get resolution order
        order = analyzer.get_resolution_order()

        if format == "json":
            # JSON output
            plan = {"models": len(models), "resolution_order": order, "dependencies": {}}

            for model_name in models:
                plan["dependencies"][model_name] = {
                    "depends_on": list(analyzer.get_dependencies(model_name)),
                    "depended_by": list(analyzer.get_dependents(model_name)),
                }

            console.print(json.dumps(plan, indent=2))

        elif format == "yaml":
            # YAML output
            import yaml

            plan = {"models": len(models), "resolution_order": order, "dependencies": {}}

            for model_name in models:
                plan["dependencies"][model_name] = {
                    "depends_on": list(analyzer.get_dependencies(model_name)),
                    "depended_by": list(analyzer.get_dependents(model_name)),
                }

            console.print(yaml.dump(plan, default_flow_style=False))

        else:
            # Text output
            table = Table(title="Model Execution Plan")
            table.add_column("Order", style="cyan")
            table.add_column("Model", style="green")
            table.add_column("Layer", style="yellow")
            table.add_column("Dependencies", style="blue")

            for i, model_name in enumerate(order, 1):
                if model_name in models:
                    model = models[model_name]
                    deps = analyzer.get_dependencies(model_name)
                    deps_str = ", ".join(deps) if deps else "None"

                    table.add_row(
                        str(i), model_name, model.layer.value if model.layer else "N/A", deps_str
                    )

            console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("models_dir", type=click.Path(exists=True))
@click.option("--customer", default="STANDARD", help="Customer identifier")
def functions(models_dir, customer):
    """List available dynamic functions."""
    console.print("[bold blue]Northstar Formation[/bold blue] - Dynamic Functions")

    context = BuildContext(customer=customer)

    try:
        # Load functions
        registry = FunctionRegistry()
        config_dir = Path(models_dir) / "config"

        if not config_dir.exists():
            console.print("[yellow]No config directory found[/yellow]")
            return

        registry.load_functions(config_dir, context)

        # Display functions
        table = Table(title=f"Available Functions ({customer})")
        table.add_column("Function", style="cyan")
        table.add_column("Parameters", style="yellow")
        table.add_column("Description", style="white")

        for func_name in sorted(registry.list_functions()):
            func = registry.get_function(func_name)
            params = ", ".join(func.parameters) if func.parameters else "None"
            desc = func.description or "N/A"

            table.add_row(func_name, params, desc)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("master_config", type=click.Path(exists=True))
@click.option("--dry-run", is_flag=True, help="Preview without creating files")
@click.option("--force", is_flag=True, help="Overwrite existing files")
@click.option("--filter-vertical", help="Generate only specific vertical layer")
@click.option("--filter-horizontal", help="Generate only specific horizontal layer")
@click.option("--filter-sublayer", help="Generate only specific sublayer within vertical")
@click.option("--show-summary", is_flag=True, help="Show generation summary")
def generate_skeleton(
    master_config, dry_run, force, filter_vertical, filter_horizontal, filter_sublayer, show_summary
):
    """Generate skeleton YAML files from master configuration.

    Creates a complete directory structure with base YAML files and variant/partial files
    based on the vertical/horizontal layering system defined in the master config.

    Examples:
        # Generate all skeletons
        northstar-formation generate-skeleton master_config.yaml

        # Preview what would be created
        northstar-formation generate-skeleton master_config.yaml --dry-run

        # Generate only tenant vertical layer
        northstar-formation generate-skeleton master_config.yaml --filter-vertical tenant

        # Generate only staging horizontal layer
        northstar-formation generate-skeleton master_config.yaml --filter-horizontal staging

        # Generate only a specific sublayer within tenant vertical
        northstar-formation generate-skeleton master_config.yaml --filter-vertical tenant --filter-sublayer my_tenant

        # Force overwrite existing files
        northstar-formation generate-skeleton master_config.yaml --force
    """
    console.print(
        f"[bold blue]Northstar Formation[/bold blue] - Generating skeletons from {master_config}"
    )

    try:
        # Load and validate master config
        config = load_master_config(master_config)
        console.print(
            f"[green]✓[/green] Loaded master configuration for project: {config.project.name}"
        )

        # Apply filters if specified
        original_models_count = len(config.models)

        if filter_vertical:
            config = filter_by_vertical(config, filter_vertical)
            console.print(f"[dim]Filtered to vertical layer: {filter_vertical}[/dim]")

        if filter_horizontal:
            config = filter_by_horizontal(config, filter_horizontal)
            console.print(f"[dim]Filtered to horizontal layer: {filter_horizontal}[/dim]")

        if filter_sublayer and not filter_vertical:
            console.print(
                "[yellow]Warning: --filter-sublayer requires --filter-vertical to be effective[/yellow]"
            )

        # Additional sublayer filtering if specified
        if filter_sublayer and filter_vertical:
            filtered_models = {}
            for vertical_name, vertical_models in config.models.items():
                if isinstance(vertical_models, dict) and filter_sublayer in vertical_models:
                    filtered_models[vertical_name] = {
                        filter_sublayer: vertical_models[filter_sublayer]
                    }
                elif isinstance(vertical_models, list) and vertical_name == filter_sublayer:
                    # Handle case where sublayer name matches vertical name
                    filtered_models[vertical_name] = vertical_models
            config.models = filtered_models
            console.print(f"[dim]Filtered to sublayer: {filter_sublayer}[/dim]")

        filtered_models_count = len(config.models)
        if filtered_models_count != original_models_count:
            console.print(
                f"[dim]Filtered from {original_models_count} to {filtered_models_count} vertical layers[/dim]"
            )

        # Initialize progress tracking
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            # Generate skeletons
            task = progress.add_task("Generating skeleton files...", total=len(config.models))
            generator = SkeletonGenerator(config)

            if dry_run:
                console.print("\n[yellow]Dry run mode - showing what would be created:[/yellow]")

            stats = generator.generate_all(
                dry_run=dry_run, force=force, progress=progress, task_id=task
            )
            progress.remove_task(task)

        # Show results
        if dry_run:
            console.print("\n[yellow]Dry run completed - no files created[/yellow]")
            console.print(f"[dim]Would have created {stats['created']} files[/dim]")
        else:
            console.print("\n[green]✓ Skeleton generation completed[/green]")
            console.print(f"[green]Files created: {stats['created']}[/green]")
            if stats["skipped"] > 0:
                console.print(
                    f"[yellow]Files skipped: {stats['skipped']}[/yellow] [dim](already existed)[/dim]"
                )
            console.print(f"[dim]Output directory: {config.project.output_dir}[/dim]")

        # Show generation summary if requested
        if show_summary or dry_run:
            summary = generator.get_generation_summary()

            console.print("\n[bold]Generation Summary:[/bold]")

            summary_table = Table(
                title="Project Overview", show_header=True, header_style="bold blue"
            )
            summary_table.add_column("Metric", style="cyan")
            summary_table.add_column("Value", style="white")

            summary_table.add_row("Project Name", summary["project_name"])
            summary_table.add_row("Output Directory", summary["output_directory"])
            summary_table.add_row("Vertical Layers", str(summary["total_verticals"]))
            summary_table.add_row("Horizontal Layers", str(summary["total_horizontals"]))
            summary_table.add_row("Total Models", str(summary["total_models"]))
            summary_table.add_row("Total Variants", str(summary["total_variants"]))
            summary_table.add_row("Files Created", str(summary["files_created"]))

            if summary["files_skipped"] > 0:
                summary_table.add_row("Files Skipped", str(summary["files_skipped"]))

            console.print(summary_table)

            # Show layer overview
            layers_table = Table(
                title="Layer Configuration", show_header=True, header_style="bold green"
            )
            layers_table.add_column("Type", style="yellow")
            layers_table.add_column("Name", style="cyan")
            layers_table.add_column("Description", style="white")
            layers_table.add_column("Order/Sublayers", style="dim")

            # Add horizontal layers
            for layer in config.horizontal_layers:
                layers_table.add_row(
                    "Horizontal",
                    layer.name,
                    layer.description or "N/A",
                    str(layer.order) if layer.order else "N/A",
                )

            # Add vertical layers
            for layer in config.vertical_layers:
                sublayer_info = (
                    f"{len(layer.sublayers)} sublayers" if layer.sublayers else "No sublayers"
                )
                layers_table.add_row(
                    "Vertical", layer.name, layer.description or "N/A", sublayer_info
                )

            console.print(layers_table)

    except Exception as e:
        console.print(f"[red]Error generating skeletons: {e}[/red]")
        if "--debug" in sys.argv:
            console.print_exception()
        sys.exit(1)


def _show_execution_plan(models, resolved_models):
    """Display execution plan details."""
    console.print("\n[bold]Execution Plan:[/bold]")

    analyzer = DependencyAnalyzer(models)
    order = analyzer.get_resolution_order()

    for i, model_name in enumerate(order, 1):
        if model_name in models:
            model = models[model_name]
            console.print(f"\n{i}. [cyan]{model_name}[/cyan]")
            console.print(f"   Layer: {model.layer.value if model.layer else 'N/A'}")
            console.print(f"   Kind: {model.kind.value}")

            deps = analyzer.get_dependencies(model_name)
            if deps:
                console.print(f"   Dependencies: {', '.join(deps)}")

            if model.ctes:
                cte_names = [cte.name for cte in model.ctes]
                console.print(f"   CTEs: {', '.join(cte_names)}")


def _merge_base_and_customer_models(
    base_models: Dict[str, Any], customer_models: Dict[str, Any]
) -> Dict[str, Any]:
    """Merge base models with customer models.

    Customer models can:
    1. Override base models completely (same name)
    2. Extend base models (inherit_columns: true merges columns)
    3. Add new models not in base

    Args:
        base_models: Dictionary of base model name -> model
        customer_models: Dictionary of customer model name -> model

    Returns:
        Merged dictionary of models
    """

    def _normalize_inheritance_ref(ref: str | None) -> str | None:
        """Normalize inheritance refs like '_base.fct.bronze.fct_customer' to 'bronze.fct_customer'."""
        if not ref:
            return ref
        parts = str(ref).split(".")
        for idx, part in enumerate(parts):
            if part in ("bronze", "silver", "gold", "interface"):
                # Keep the layer-qualified model reference from the layer token onward.
                return ".".join(parts[idx:])
        return parts[-1]

    merged = {}

    # Start with base models
    for name, base_model in base_models.items():
        merged[name] = copy.deepcopy(base_model)
        if hasattr(merged[name], "extends"):
            merged[name].extends = _normalize_inheritance_ref(merged[name].extends)
        if hasattr(merged[name], "inherits_from"):
            merged[name].inherits_from = _normalize_inheritance_ref(
                merged[name].inherits_from
            )

    # Process customer models
    for name, customer_model in customer_models.items():
        if name in merged:
            # Customer model overrides/extends base model
            base_model = merged[name]

            # Check if customer model wants to inherit columns from base
            inherit_columns = False
            if hasattr(customer_model, "transformations") and customer_model.transformations:
                inherit_columns = getattr(customer_model.transformations, "inherit_columns", False)

            if (
                inherit_columns
                and hasattr(base_model, "transformations")
                and base_model.transformations
            ):
                # Merge columns: base columns + customer columns
                base_columns = []
                if (
                    hasattr(base_model.transformations, "columns")
                    and base_model.transformations.columns
                ):
                    base_columns = list(base_model.transformations.columns)

                customer_columns = []
                if (
                    hasattr(customer_model.transformations, "columns")
                    and customer_model.transformations.columns
                ):
                    customer_columns = list(customer_model.transformations.columns)

                # Get column names from customer to check for overrides
                customer_column_names = {
                    col.name.lower() for col in customer_columns if hasattr(col, "name")
                }

                # Merge: base columns (not overridden) + customer columns
                merged_columns = []
                for col in base_columns:
                    if hasattr(col, "name") and col.name.lower() not in customer_column_names:
                        merged_columns.append(col)

                merged_columns.extend(customer_columns)

                # Update customer model with merged columns
                customer_model.transformations.columns = merged_columns
                logger.info(
                    f"Merged {name}: {len(base_columns)} base + {len(customer_columns)} customer = {len(merged_columns)} columns"
                )

            # Column merge already handled inheritance; clear any _base. ref to avoid
            # the customer model pointing at itself (since it shares the same key as the
            # base model it was derived from).
            if hasattr(customer_model, "extends") and customer_model.extends:
                if str(customer_model.extends).startswith("_base."):
                    customer_model.extends = None
            if hasattr(customer_model, "inherits_from") and customer_model.inherits_from:
                if str(customer_model.inherits_from).startswith("_base."):
                    customer_model.inherits_from = None

            # Use customer model (with potentially merged columns)
            merged[name] = customer_model
        else:
            # New model from customer, add directly
            if hasattr(customer_model, "extends"):
                customer_model.extends = _normalize_inheritance_ref(customer_model.extends)
            if hasattr(customer_model, "inherits_from"):
                customer_model.inherits_from = _normalize_inheritance_ref(
                    customer_model.inherits_from
                )
            merged[name] = customer_model

    return merged


def _load_excluded_models(models_dir: Path) -> set[str]:
    """Load optional customer-specific model exclusions."""
    exclusions_path = models_dir / "config" / "model_exclusions.yaml"
    if not exclusions_path.exists():
        return set()

    with exclusions_path.open(encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    excluded = config.get("excluded_models", [])
    if not isinstance(excluded, list):
        raise click.ClickException(
            f"excluded_models must be a list in {exclusions_path}"
        )

    return {str(name).strip().lower() for name in excluded if str(name).strip()}


def _save_outputs(sql_outputs: dict, output_dir: str, models: dict = None):
    """Save SQL outputs to files, organized by layer.

    Args:
        sql_outputs: Dictionary of model_name -> SQL string.
        output_dir: Base output directory.
        models: Optional dictionary of models to get layer information.
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    for model_name, sql in sql_outputs.items():
        # Determine the layer subdirectory
        layer = None
        if models and model_name in models:
            model = models[model_name]
            if hasattr(model, "layer") and model.layer:
                layer = model.layer.value if hasattr(model.layer, "value") else str(model.layer)

        # Strip the layer prefix from filename if present (e.g., "bronze.fct_customer" -> "fct_customer")
        # Also handles mismatched prefixes (parser keys by folder name, model may declare a different layer).
        filename = model_name
        for _prefix in ([f"{layer}."] if layer else []) + ["bronze.", "silver.", "gold.", "interface."]:
            if model_name.lower().startswith(_prefix.lower()):
                filename = model_name[len(_prefix):]
                break

        # Build output path: layer
        target_dir = output_path
        if layer:
            target_dir = target_dir / layer
        target_dir.mkdir(parents=True, exist_ok=True)

        file_path = target_dir / f"{filename}.sql"

        with open(file_path, "w") as f:
            f.write(sql)


def _save_notebook_outputs(
    notebook_outputs: dict,
    output_dir: Path,
    models: dict = None,
    customer: str = "",
):
    """Save notebook outputs as Fabric .Notebook directories, organized by layer.

    Args:
        notebook_outputs: Dictionary of model_name -> notebook dict.
        output_dir: Base output directory.
        models: Optional dictionary of models to get layer information.
        customer: Customer name for deterministic logicalId generation.
            If not provided, attempts to extract from model's customer field.

    Output structure:
        output_dir/
        ├── bronze/
        │   └── model_name.Notebook/
        │       ├── .platform
        │       └── notebook-content.py
        ├── silver/
        │   └── ...
        └── gold/
            └── ...
    """
    from .generators.fabric_format import FabricFormatExporter

    output_dir.mkdir(parents=True, exist_ok=True)
    exporter = FabricFormatExporter()

    def _get_customer_from_model(model) -> str:
        """Extract customer from model if available."""
        # Try to get customer from model's customer attribute
        if hasattr(model, "customer") and model.customer:
            return model.customer
        # Try to get from raw_data if available
        if hasattr(model, "raw_data") and isinstance(model.raw_data, dict):
            model_section = model.raw_data.get("model", {})
            if isinstance(model_section, dict) and model_section.get("customer"):
                return model_section["customer"]
        return ""

    for model_name, notebook in notebook_outputs.items():
        # Determine the layer subdirectory
        layer = None
        if models and model_name in models:
            model = models[model_name]
            if hasattr(model, "layer") and model.layer:
                layer = model.layer.value if hasattr(model.layer, "value") else str(model.layer)

        # Strip the layer prefix from filename if present (e.g., "bronze.fct_customer" -> "fct_customer")
        # Also handles mismatched prefixes (parser keys by folder name, model may declare a different layer).
        filename = model_name
        for _prefix in ([f"{layer}."] if layer else []) + ["bronze.", "silver.", "gold.", "interface."]:
            if model_name.lower().startswith(_prefix.lower()):
                filename = model_name[len(_prefix):]
                break

        # Build output path: layer
        target_dir = output_dir
        if layer:
            target_dir = target_dir / layer
        target_dir.mkdir(parents=True, exist_ok=True)

        # Get lakehouse config and customer from model if available
        lakehouse_config = None
        model_customer = ""  # Will be extracted from model or fall back to CLI param
        model_layer = layer or ""  # Use already extracted layer
        if models and model_name in models:
            model = models[model_name]
            if hasattr(model, "notebook_settings") and model.notebook_settings:
                lakehouse_config = getattr(model.notebook_settings, "lakehouse", None)
            # Extract customer from model - prefer model's customer over CLI default
            model_customer = _get_customer_from_model(model)

        # Fall back to CLI-provided customer if model doesn't have one
        if not model_customer:
            model_customer = customer

        # Export as Fabric .Notebook format
        exporter.export(
            model_name=filename,
            cells=notebook.get("cells", []),
            output_dir=target_dir,
            lakehouse_config=lakehouse_config,
            description=f"Generated notebook for {model_name}",
            customer=model_customer,
            layer=model_layer,
        )


@cli.command()
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base",
    "-b",
    type=click.Path(exists=True),
    help="Base models directory (models are merged with base)",
)
@click.option("--output", "-o", type=click.Path(), help="Output file path")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["dot", "json"]),
    default="dot",
    help="Output format (default: dot)",
)
@click.option("--table", help="Generate lineage for specific table only")
@click.option("--column", help="Generate column-level lineage for specific column")
@click.option("--layer", help="Filter to specific layer (bronze, silver, gold)")
@click.option("--impact-of", "impact_table", help="Show impact analysis for table")
@click.option(
    "--render",
    type=click.Choice(["png", "svg", "pdf"]),
    help="Render DOT to image (requires graphviz installed)",
)
@click.option("--show-columns/--no-columns", default=True, help="Show columns in table nodes")
@click.option("--show-types/--no-types", default=False, help="Show column data types")
@click.option("--customer", default="STANDARD", help="Customer identifier")
@click.option("--version", default="1.0.0", help="Version string")
@click.option("--features", help="Comma-separated feature flags")
def lineage(
    models_dir,
    base,
    output,
    output_format,
    table,
    column,
    layer,
    impact_table,
    render,
    show_columns,
    show_types,
    customer,
    version,
    features,
):
    r"""Generate data lineage graph from YAML models.

    Creates a visual representation of data flow through the bronze, silver,
    and gold layers, showing table dependencies and column transformations.

    \b
    Examples:
        # Full lineage graph
        northstar-formation lineage ./models --output lineage.dot

        # Lineage for specific table
        northstar-formation lineage ./models --table dim_customer -o customer.dot

        # Render to PNG
        northstar-formation lineage ./models -o lineage.dot --render png

        # Impact analysis
        northstar-formation lineage ./models --impact-of bronze.customer

        # Column-level lineage
        northstar-formation lineage ./models --table dim_customer --column customer_id_key

        # JSON output for programmatic use
        northstar-formation lineage ./models --format json -o lineage.json
    """
    from .lineage import DotExporter, JsonExporter, LineageAnalyzer

    console.print("[bold blue]Northstar Formation[/bold blue] - Data Lineage Analysis")

    # Build context
    feature_list = features.split(",") if features else []
    context = BuildContext(customer=customer, version=version, features=feature_list)

    try:
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            # Load and analyze models
            task = progress.add_task("Loading models...", total=None)

            parser = YAMLParser(models_dir)

            # If base directory is specified, load base models first then merge
            if base:
                base_parser = YAMLParser(base)
                base_models = base_parser.load_all_models(context)
                customer_models = parser.load_all_models(context)
                models = _merge_base_and_customer_models(base_models, customer_models)
                console.print(
                    f"[green]✓[/green] Loaded {len(base_models)} base + {len(customer_models)} customer = {len(models)} merged"
                )
            else:
                models = parser.load_all_models(context)
                console.print(f"[green]✓[/green] Loaded {len(models)} model(s)")

            # Resolve models for better column information
            progress.update(task, description="Resolving models...")
            resolver = ModelResolver(parser)
            resolved_models = resolver.resolve_all(models, context)

            # Build lineage graph
            progress.update(task, description="Analyzing lineage...")
            analyzer = LineageAnalyzer()
            graph = analyzer.analyze(models, resolved_models)

            console.print(
                f"[green]✓[/green] Analyzed lineage: {len(graph.tables)} tables, "
                f"{len(graph.edges)} edges"
            )

            # Handle impact analysis
            if impact_table:
                progress.update(task, description="Analyzing impact...")
                _show_impact_analysis(graph, impact_table)
                return

            # Filter graph if requested
            if table:
                graph = graph.filter_by_table(table)
                console.print(f"[dim]Filtered to table: {table}[/dim]")

            if layer:
                graph = graph.filter_by_layer(layer)
                console.print(f"[dim]Filtered to layer: {layer}[/dim]")

            # Determine output path
            if not output:
                ext = "json" if output_format == "json" else "dot"
                output = Path(f"lineage.{ext}")
            else:
                output = Path(output)

            # Export based on format
            progress.update(task, description=f"Exporting to {output_format}...")

            if output_format == "json":
                exporter = JsonExporter()
                if column and table:
                    # Column-level lineage
                    exporter.export_column_lineage(graph, table, column, output)
                else:
                    exporter.export(graph, output, title=f"Lineage: {models_dir}")
            else:
                # DOT format
                exporter = DotExporter(
                    show_columns=show_columns,
                    show_column_types=show_types,
                )

                if column and table:
                    # Column-level lineage
                    exporter.export_column_lineage(
                        graph, table, column, output, title=f"Column Lineage: {table}.{column}"
                    )
                else:
                    exporter.export(graph, output, title=f"Data Lineage: {models_dir}")

                # Render to image if requested
                if render:
                    progress.update(task, description=f"Rendering to {render}...")
                    try:
                        rendered_path = exporter.render(output, render)
                        console.print(f"[green]✓[/green] Rendered to: {rendered_path}")
                    except RuntimeError as e:
                        console.print(f"[yellow]Warning: {e}[/yellow]")

            console.print(f"[green]✓[/green] Lineage exported to: {output}")

            # Show summary statistics
            stats = analyzer.get_statistics()
            _show_lineage_summary(stats)

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        logger.exception("Lineage analysis failed")
        sys.exit(1)


def _show_impact_analysis(graph, table_name: str):
    """Display impact analysis for a table."""
    console.print(f"\n[bold]Impact Analysis: {table_name}[/bold]")

    if table_name not in graph.tables:
        console.print(f"[red]Table '{table_name}' not found in lineage graph[/red]")
        return

    # Get upstream and downstream
    upstream = graph.get_upstream(table_name)
    downstream = graph.get_downstream(table_name)
    direct_downstream = graph.get_direct_downstream(table_name)

    # Upstream dependencies
    console.print(f"\n[cyan]Upstream Dependencies ({len(upstream)}):[/cyan]")
    if upstream:
        for dep in sorted(upstream):
            table = graph.get_table(dep)
            layer = table.layer if table else "unknown"
            console.print(f"  ← {dep} [{layer}]")
    else:
        console.print("  [dim]None[/dim]")

    # Direct downstream
    console.print(f"\n[yellow]Direct Downstream ({len(direct_downstream)}):[/yellow]")
    if direct_downstream:
        for dep in sorted(direct_downstream):
            table = graph.get_table(dep)
            layer = table.layer if table else "unknown"
            console.print(f"  → {dep} [{layer}]")
    else:
        console.print("  [dim]None[/dim]")

    # All downstream (indirect)
    indirect = [t for t in downstream if t not in direct_downstream]
    if indirect:
        console.print(f"\n[dim]Indirect Downstream ({len(indirect)}):[/dim]")
        for dep in sorted(indirect):
            table = graph.get_table(dep)
            layer = table.layer if table else "unknown"
            console.print(f"  ⤳ {dep} [{layer}]")

    # Summary
    console.print("\n[bold]Summary:[/bold]")
    console.print(f"  Total tables that would be affected: {len(downstream)}")


def _show_lineage_summary(stats: dict):
    """Display lineage summary statistics."""
    console.print("\n[bold]Lineage Summary:[/bold]")

    summary_table = Table(show_header=True, header_style="bold blue")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="white")

    summary_table.add_row("Total Tables", str(stats.get("total_tables", 0)))
    summary_table.add_row("Total Edges", str(stats.get("total_edges", 0)))
    summary_table.add_row("Column Edges", str(stats.get("column_edges", 0)))
    summary_table.add_row("External Tables", str(stats.get("external_tables", 0)))

    if "max_depth" in stats:
        summary_table.add_row("Max Depth", str(stats["max_depth"]))

    # Layer breakdown
    layers = stats.get("layers", {})
    for layer, count in sorted(layers.items()):
        summary_table.add_row(f"  {layer.title()} Layer", str(count))

    console.print(summary_table)


@cli.command()
@click.option(
    "--models-dir",
    "-m",
    type=click.Path(exists=True),
    required=True,
    help="Directory containing model YAML files",
)
@click.option(
    "--notebooks-root",
    "-n",
    type=click.Path(exists=True),
    required=True,
    help="Root directory containing generated notebooks",
)
@click.option(
    "--pipelines-yaml-dir",
    "-p",
    type=click.Path(exists=True),
    required=True,
    help="Directory containing pipeline YAML definitions",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output directory for generated pipelines",
)
@click.option(
    "--workspace-id",
    "-w",
    required=True,
    help="Microsoft Fabric workspace ID (GUID)",
)
@click.option(
    "--filter",
    "file_filter",
    default="*.yaml",
    show_default=True,
    help="Glob pattern applied to pipeline YAML filenames (e.g. '*customer*').",
)
def pipelines(models_dir, notebooks_root, pipelines_yaml_dir, output, workspace_id, file_filter):
    """Generate Microsoft Fabric Data Pipelines from YAML definitions.

    This command generates Fabric Data Pipeline artifacts based on pipeline
    YAML definitions, model metadata, and generated notebooks.

    \b
    Examples:
        # Generate pipelines for a customer
        northstar-formation pipelines \\
            --models-dir models/customers/customer0 \\
            --notebooks-root output/notebooks \\
            --pipelines-yaml-dir pipelines/customers/customer0 \\
            --output output/pipelines \\
            --workspace-id <workspace-id>

        # Only pipelines matching a name pattern
        northstar-formation pipelines ... --filter '*customer*'
    """
    import fnmatch

    models_path = Path(models_dir)
    notebooks_path = Path(notebooks_root)
    pipelines_path = Path(pipelines_yaml_dir)
    out_path = Path(output)

    manifest_path = out_path / "manifest" / "notebooks_manifest.yaml"

    console.print("[bold blue]Northstar Formation[/bold blue] - Generating Fabric Data Pipelines")
    console.print(f"  Models: {models_path}")
    console.print(f"  Notebooks: {notebooks_path}")
    console.print(f"  Pipeline definitions: {pipelines_path}")
    console.print(f"  Output: {out_path}")
    console.print(f"  Workspace ID: {workspace_id}")
    console.print(f"  File filter: {file_filter}")

    console.print("\n[cyan]Step 1:[/cyan] Building notebook manifest...")
    build_manifest(notebooks_path, manifest_path)
    console.print("  ✔ Manifest built")

    notebook_ids = load_notebook_ids_from_manifest(manifest_path)
    models = load_models(models_path)

    console.print("\n[cyan]Step 2:[/cyan] Generating pipelines...")

    # Match filter against filename OR stem so both '*customer*' and '*customer*.yaml' work.
    def _matches(path: Path) -> bool:
        return (
            fnmatch.fnmatch(path.name, file_filter)
            or fnmatch.fnmatch(path.stem, file_filter)
        )

    yaml_files = [f for f in pipelines_path.rglob("*.yaml") if _matches(f)]
    if not yaml_files:
        console.print(
            f"[yellow]No pipeline YAML files matched filter '{file_filter}' "
            f"under {pipelines_path}[/yellow]"
        )

    generated_count = 0
    for yaml_file in yaml_files:
        doc = _read_yaml(yaml_file)
        if "pipeline" not in doc:
            continue

        p = doc["pipeline"]
        name = p["name"]

        afm = p["auto_from_models"]
        layer = afm["layer"]
        domain_prefix = afm["domain_prefix"]
        pass_params = afm.get("pass_parameters")
        
        # Check for explicit notebooks configuration
        notebooks_config = p.get("notebooks")

        pipeline_json = build_layer_pipeline(
            pipeline_name=name,
            layer=layer,
            domain_prefix=domain_prefix,
            models=models,
            notebook_ids=notebook_ids,
            workspace_id=workspace_id,
            pass_parameters=pass_params,
            notebooks_config=notebooks_config,
        )

        import json as json_module
        dp_dir = out_path / f"{name}.DataPipeline"
        dp_dir.mkdir(parents=True, exist_ok=True)

        _write_text(
            dp_dir / "pipeline-content.json",
            json_module.dumps(pipeline_json, indent=2),
        )

        _write_text(
            dp_dir / ".platform",
            json_module.dumps({
                "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                "metadata": {"type": "DataPipeline", "displayName": name},
                "config": {
                    "version": "2.0",
                    "objectId": uuid_for_object_id(name),
                    "logicalId": uuid_from_display_name(name),
                },
            }, indent=2),
        )

        console.print(f"  ✔ Generated [green]{name}[/green]")
        generated_count += 1

    # Clean up manifest folder
    import shutil
    manifest_dir = manifest_path.parent
    if manifest_dir.exists():
        shutil.rmtree(manifest_dir)

    # Copy shared pipelines from _c000 sibling folder if it exists
    c000_path = pipelines_path.parent / "_c000"
    if c000_path.exists() and c000_path.is_dir():
        console.print("\n[cyan]Step 3:[/cyan] Copying shared pipelines from _c000...")
        for item in c000_path.iterdir():
            if item.is_dir():
                dest = out_path / item.name
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(item, dest)
                console.print(f"  ✔ Copied [green]{item.name}[/green]")

    console.print(f"\n[bold green]✔ All pipelines generated successfully ({generated_count} total)[/bold green]")


@cli.command(name="semantic-model")
@click.option(
    "--models-dir",
    "-m",
    type=click.Path(exists=True),
    required=True,
    help="Customer models directory (must contain a gold/ subfolder)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output directory - the .SemanticModel folder is created here "
         "(pass output_<customer>/semantic_model, a sibling of ENG/ and auth/)",
)
@click.option(
    "--name",
    "semantic_model_name",
    required=True,
    help="Semantic model display name (e.g. sm_customer0)",
)
@click.option(
    "--sql-endpoint",
    required=True,
    help="Lakehouse SQL analytics endpoint FQDN "
         "(GET /v1/workspaces/{id}/lakehouses/{id} -> properties.sqlEndpointProperties.connectionString)",
)
@click.option(
    "--database-id",
    required=True,
    help="Lakehouse SQL analytics endpoint database id "
         "(same response -> properties.sqlEndpointProperties.id)",
)
def semantic_model(models_dir, output, semantic_model_name, sql_endpoint, database_id):
    """Generate a Fabric SemanticModel (TMDL, DirectLake) from gold/*.yaml models.

    Tables, columns, and dim<->fact relationships are all inferred from the
    same gold-layer model metadata the gold notebooks are generated from - no
    manual relationship wiring. Relationships are inferred by matching a
    fact's column name against a dim table's own natural-key column (its
    first declared column), which is the convention every model in this repo
    already follows (e.g. PartnerId is dim_partner's key and the FK on every
    fact referencing it).

    \b
    Example:
        northstar-formation semantic-model \\
            --models-dir models/customers/customer0 \\
            --output output_customer0/data_modelling/semantic_models \\
            --name sm_customer0 \\
            --sql-endpoint abc123-xyz.datawarehouse.fabric.microsoft.com \\
            --database-id 99ee579a-2855-41f4-a1d1-bd610f44ee34
    """
    models_path = Path(models_dir)
    gold_dir = models_path / "gold"
    if not gold_dir.exists():
        raise click.ClickException(f"No gold/ directory found under {models_path}")
    out_path = Path(output)

    console.print("[bold blue]Northstar Formation[/bold blue] - Generating Fabric Semantic Model")
    console.print(f"  Gold models: {gold_dir}")
    console.print(f"  Output: {out_path}")
    console.print(f"  Name: {semantic_model_name}")

    try:
        result = generate_semantic_model(
            gold_dir=gold_dir,
            output_dir=out_path,
            semantic_model_name=semantic_model_name,
            sql_endpoint=sql_endpoint,
            database_id=database_id,
        )
    except SemanticModelGenError as exc:
        raise click.ClickException(str(exc))

    console.print(f"\n  ✔ Tables ({len(result['tables'])}): {', '.join(result['tables'])}")
    console.print(f"  ✔ Relationships inferred ({len(result['relationships'])}):")
    for fact, col, dim in result["relationships"]:
        console.print(f"      {fact}.{col} -> {dim}.{col}")
    console.print(f"\n[bold green]✔ Semantic model generated at {result['output_dir']}[/bold green]")

    # reports/ is a sibling of semantic_models/ under data_modelling/ - real
    # Report content is generated separately (`northstar-formation report`), this
    # just guarantees the standard tree is always visible even before that's run.
    reports_dir = out_path.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / ".gitkeep").touch()
    console.print(f"[green]✓[/green] Ensured reports/ placeholder at {reports_dir}")


@cli.command(name="report")
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Output directory - the .Report folder is created here "
         "(pass output_<customer>/data_modelling/reports, a sibling of semantic_models/)",
)
@click.option(
    "--name",
    "report_name",
    required=True,
    help="Report display name (e.g. sr_customer0)",
)
@click.option(
    "--semantic-model-id",
    required=True,
    help="Real Fabric item ID (GUID) of the deployed SemanticModel this report binds to "
         "(GET /v1/workspaces/{id}/items?type=SemanticModel). Bound live via byConnection - "
         "no data copy, works regardless of where the semantic model's files live.",
)
def report(output, report_name, semantic_model_id):
    """Generate a minimal self-service Fabric Report (PBIR) bound to an
    existing SemanticModel.

    A small, real starting point - 4 KPI cards, a period/partner slicer
    pair, a trend chart and a detail table, all on one page - for users to
    duplicate and extend themselves in the Fabric portal. Not a replica of
    any custom app UI.

    \b
    Example:
        northstar-formation report \\
            --output output_customer0/data_modelling/reports \\
            --name sr_customer0 \\
            --semantic-model-id 6a37ffac-5e14-4c38-9183-2ea6877efd17
    """
    out_path = Path(output)

    console.print("[bold blue]Northstar Formation[/bold blue] - Generating Self-Service Report")
    console.print(f"  Output: {out_path}")
    console.print(f"  Name: {report_name}")
    console.print(f"  Semantic model: {semantic_model_id}")

    try:
        result = generate_self_service_report(
            output_dir=out_path,
            report_name=report_name,
            semantic_model_id=semantic_model_id,
        )
    except ReportGenError as exc:
        raise click.ClickException(str(exc))

    console.print(f"  ✔ Page: {result['page']}")
    console.print(f"  ✔ Visuals ({len(result['visuals'])}): {', '.join(result['visuals'])}")
    console.print(f"\n[bold green]✔ Report generated at {result['output_dir']}[/bold green]")


@cli.command()
@click.argument("tmdl_path", type=click.Path(exists=True))
@click.option(
    "--output", "-o", 
    type=click.Path(), 
    help="Output directory for the validation notebook"
)
@click.option(
    "--notebook-name",
    default="audit_relationship_validator",
    help="Name for the validation notebook (default: audit_relationship_validator)"
)
@click.option(
    "--lakehouse-name",
    default="lkh_customer0_schema_enabled",
    help="Lakehouse name for configuration"
)
@click.pass_context
def validate_relationships(ctx, tmdl_path, output, notebook_name, lakehouse_name):
    """Generate relationship validation notebook from TMDL semantic models.
    
    Scans a directory containing semantic models and generates a validation notebook
    that checks if all foreign key values in fact tables exist in their related
    dimension tables. Results are logged to log.tmdl_validation_results.
    
    Supports two modes:
    1. Multiple semantic models: Pass parent "Semantic Models" directory - all relationships
       from all semantic models are validated in a single notebook
    2. Single semantic model: Pass specific "SM_XXX.SemanticModel/definition" directory
    
    Usage:
        northstar-formation validate-relationships "path/to/Semantic Models" -o output/
        northstar-formation validate-relationships "path/to/SM_FCT.SemanticModel/definition" -o output/
    """
    console.print(f"[bold blue]Northstar Formation[/bold blue] - Validating semantic model relationships")
    console.print(f"[dim]Scanning: {tmdl_path}[/dim]")
    
    try:
        from pathlib import Path
        from .generators.audit_relationship_validator import TMDLParser, ValidationNotebookGenerator
        
        tmdl_dir = Path(tmdl_path)
        
        # Determine if this is a multiple semantic models directory or single semantic model
        is_semantic_models_dir = any(
            d.is_dir() and d.name.endswith('.SemanticModel') 
            for d in tmdl_dir.iterdir()
        )
        
        # Parse TMDL files
        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Parsing TMDL files...", total=None)
            parser = TMDLParser()
            
            if is_semantic_models_dir:
                console.print(f"[dim]Detected multiple semantic models directory[/dim]")
                tables, relationships = parser.parse_semantic_models_directory(tmdl_dir)
            else:
                console.print(f"[dim]Detected single semantic model[/dim]")
                tables, relationships = parser.parse_directory(tmdl_dir)
            
            progress.update(task, description=f"Found {len(tables)} tables, {len(relationships)} relationships")
            
            # Generate notebook
            task = progress.add_task("Generating validation notebook...", total=None)
            generator = ValidationNotebookGenerator(tables, relationships, lakehouse_name)
            notebook = generator.generate_notebook()
            progress.update(task, completed=True, description="Validation notebook generated")
        
        # Save the notebook if output directory specified
        if output:
            output_dir = Path(output)
            # Create the validators subdirectory structure
            validators_dir = output_dir / "notebooks" / "UTL"
            validators_dir.mkdir(parents=True, exist_ok=True)
            
            # Save as Fabric .Notebook format for direct deployment (creates .Notebook directory)
            from .generators.fabric_format import FabricFormatExporter
            from .core.models import LakehouseConfig
            
            exporter = FabricFormatExporter()
            cells = notebook.get("cells", [])
            
            try:
                lakehouse_config = LakehouseConfig(name=lakehouse_name)
                notebook_dir = exporter.export(
                    model_name=notebook_name,
                    cells=cells,
                    output_dir=validators_dir,
                    lakehouse_config=lakehouse_config,
                    description="Semantic Model Relationship Validation Notebook - Results logged to log.tmdl_validation_results",
                )
                console.print(f"[green]✓[/green] Saved Fabric .Notebook format to {notebook_dir}")
                
                # Also save Jupyter .ipynb format inside the .Notebook directory
                ipynb_path = notebook_dir / f"{notebook_name}.ipynb"
                with open(ipynb_path, 'w', encoding='utf-8') as f:
                    json.dump(notebook, f, indent=2)
                console.print(f"[green]✓[/green] Saved Jupyter notebook to {ipynb_path}")
                
            except Exception as e:
                console.print(f"[yellow]⚠[/yellow] Could not save notebook: {e}")
        else:
            # Print to stdout
            console.print(json.dumps(notebook, indent=2))
        
        console.print("[green]✓ Validation notebook generated successfully[/green]")
        
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        if ctx.obj.get("debug"):
            console.print_exception()
        sys.exit(1)


@cli.command("generate-validation-notebook")
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base",
    "-b",
    type=click.Path(exists=True),
    help="Base models directory (customer models are merged on top of base for key resolution)",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(),
    required=True,
    help="Root output directory (notebook is written under <output>/notebooks/UTL/VALIDATION/)",
)
@click.option(
    "--lakehouse-name",
    required=True,
    help="Default lakehouse name for the %%configure cell",
)
@click.option("--lakehouse-id", help="Optional default lakehouse GUID")
@click.option("--lakehouse-workspace-id", help="Optional default lakehouse workspace GUID")
@click.option(
    "--customer",
    help="Customer identifier (default: inferred from models_dir name)",
)
@click.option(
    "--validation-config",
    type=click.Path(exists=True),
    help="Path to validation.yaml (default: <models_dir>/validation.yaml)",
)
@click.pass_context
def generate_validation_notebook_cmd(
    ctx,
    models_dir,
    base,
    output,
    lakehouse_name,
    lakehouse_id,
    lakehouse_workspace_id,
    customer,
    validation_config,
):
    """Generate a silver-layer data-quality validation notebook.

    Reads test definitions from ``<models_dir>/validation.yaml`` and produces a
    single Fabric ``.Notebook`` where each test module is an independent,
    freezable Python cell that runs SQL checks against every applicable table.
    The notebook is intended to run before the gold pipelines.

    Example:

        northstar-formation generate-validation-notebook models/customers/customer0 \\
            --base models/_base \\
            -o output_customer0/ENG/ \\
            --lakehouse-name lkh_001
    """
    from .generators.validation_notebook import generate_validation_notebook

    models_path = Path(models_dir)
    base_path = Path(base) if base else None
    output_path = Path(output)
    cfg_path = Path(validation_config) if validation_config else None

    inferred_customer = customer
    if not inferred_customer:
        # models/customers/<customer> -> <customer>
        if models_path.parent.name == "customers":
            inferred_customer = models_path.name
        else:
            inferred_customer = models_path.name

    console.print(
        f"[bold blue]Northstar Formation[/bold blue] - Generating validation notebook for "
        f"[green]{inferred_customer}[/green]"
    )
    console.print(f"[dim]Models dir: {models_path}[/dim]")
    if base_path:
        console.print(f"[dim]Base dir:   {base_path}[/dim]")
    console.print(f"[dim]Output dir: {output_path}[/dim]")

    try:
        result = generate_validation_notebook(
            models_dir=models_path,
            base_dir=base_path,
            output_dir=output_path,
            lakehouse_name=lakehouse_name,
            lakehouse_id=lakehouse_id,
            lakehouse_workspace_id=lakehouse_workspace_id,
            customer=inferred_customer,
            validation_config_path=cfg_path,
        )
    except Exception as exc:
        console.print(f"[red]Error: {exc}[/red]")
        if ctx.obj.get("debug"):
            console.print_exception()
        sys.exit(1)

    if not result:
        console.print(
            "[red]✗ Notebook was not generated (missing validation.yaml or no tests defined)[/red]"
        )
        sys.exit(1)

    console.print(f"[green]✓[/green] Validation notebook written to [cyan]{result}[/cyan]")


# Framework/audit column names that are expected to be "dead ends" at every
# layer and should not be reported as downstream orphans.
_ORPHAN_FRAMEWORK_COLS: set[str] = {
    "valid_from", "valid_to", "is_current",
    "ins_batchid", "upd_batchid",
    "sourcefile", "manifest_file", "manifest_package",
    "load_date", "load_timestamp",
    "exportdate", "partitionkey", "version_id",
    "scd_hash",
}


@cli.command(name="check-framework")
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base", "-b", type=click.Path(exists=True),
    help="Base models directory (models are merged with base before checking)",
)
@click.option(
    "--contract", type=click.Path(exists=True),
    help="Path to required_columns.yaml (default: models/_base/framework/required_columns.yaml)",
)
@click.option("--customer", default="STANDARD", help="Customer identifier for build context")
@click.option(
    "--strict/--no-strict", default=True,
    help="Exit non-zero on any missing required column (default: strict)",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.option(
    "--only",
    type=click.Choice(["all", "nok", "fail", "warn"]),
    default="all",
    show_default=True,
    help="Filter rows: all | nok (fail+warn) | fail | warn.",
)
@click.pass_context
def check_framework_cmd(ctx, models_dir, base, contract, customer, strict, output_format, only):
    """Check every bronze/silver model has the framework-mandatory columns.

    Loads customer models, merges with base (if --base given), then verifies each
    merged model contains the required columns declared in the framework contract
    yaml. Type mismatches are reported as warnings; missing columns fail the check
    in strict mode (default).

    Example:

        northstar-formation check-framework models/customers/customer0 --base models/_base
    """
    from .validators.framework_columns import (
        check_all_models, _load_contract,
    )

    try:
        contract_data = _load_contract(Path(contract) if contract else None)
    except FileNotFoundError as exc:
        console.print(f"[red]✗ {exc}[/red]")
        sys.exit(2)

    ctx_obj = BuildContext(customer=customer)
    customer_parser = YAMLParser(models_dir)
    customer_models = customer_parser.load_all_models(ctx_obj)

    if base:
        base_parser = YAMLParser(base)
        base_models = base_parser.load_all_models(ctx_obj)
        merged = _merge_base_and_customer_models(base_models, customer_models)
    else:
        merged = customer_models

    results = check_all_models(merged, contract_data)

    def _keep(r) -> bool:
        if only == "all":
            return True
        if only == "fail":
            return not r.ok
        if only == "warn":
            return r.ok and bool(r.type_mismatches)
        # nok = fail + warn
        return (not r.ok) or bool(r.type_mismatches)

    filtered = [r for r in results if _keep(r)]

    if output_format == "json":
        console.print_json(data=[
            {
                "model": r.model_name,
                "layer": r.layer,
                "kind": r.kind,
                "missing": r.missing,
                "type_mismatches": [
                    {"column": n, "expected": e, "actual": a} for n, e, a in r.type_mismatches
                ],
                "ok": r.ok,
            }
            for r in filtered
        ])
    else:
        table = Table(show_header=True, header_style="bold")
        table.add_column("Model")
        table.add_column("Layer")
        table.add_column("Kind")
        table.add_column("Status")
        table.add_column("Missing / Mismatches")
        for r in filtered:
            if r.ok and not r.type_mismatches:
                table.add_row(r.model_name, r.layer, r.kind, "[green]OK[/green]", "")
            elif not r.missing:
                mm = "\n".join(f"[yellow]type[/yellow] {n}: expected {e}, got {a}" for n, e, a in r.type_mismatches)
                table.add_row(r.model_name, r.layer, r.kind, "[yellow]warn[/yellow]", mm)
            else:
                missing_str = ", ".join(r.missing)
                mm = "\n".join(f"[yellow]type[/yellow] {n}: expected {e}, got {a}" for n, e, a in r.type_mismatches)
                detail = f"missing: {missing_str}" + (f"\n{mm}" if mm else "")
                table.add_row(r.model_name, r.layer, r.kind, "[red]FAIL[/red]", detail)
        console.print(table)

        n_ok = sum(1 for r in results if r.ok and not r.type_mismatches)
        n_warn = sum(1 for r in results if r.ok and r.type_mismatches)
        n_fail = sum(1 for r in results if not r.ok)
        shown_note = "" if only == "all" else f"   [dim](showing {len(filtered)} / {len(results)} filtered by --only {only})[/dim]"
        console.print(
            f"\n[bold]Summary:[/bold] {n_ok} OK · {n_warn} warn · {n_fail} fail   ({len(results)} checked){shown_note}"
        )

    if strict and any(not r.ok for r in results):
        sys.exit(1)


@cli.command(name="inspect")
@click.argument("model_name")
@click.option(
    "--models-dir", "models_dir", type=click.Path(exists=True), required=True,
    help="Customer models directory (e.g. models/customers/customer0)",
)
@click.option(
    "--base", "-b", type=click.Path(exists=True),
    help="Base models directory (models are merged with base before inspection)",
)
@click.option("--customer", default="STANDARD", help="Customer identifier for build context")
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json"]),
    default="table",
    show_default=True,
)
@click.pass_context
def inspect_cmd(ctx, model_name, models_dir, base, customer, output_format):
    """Show a resolved model with each column annotated by its origin (base / customer).

    MODEL_NAME must be layer-qualified: `bronze.productlocation`,
    `silver.customer_scd`, `interface.dim_hierarchy`.

    Example:

        northstar-formation inspect bronze.productlocation \\
            --models-dir models/customers/customer0 --base models/_base
    """
    from .validators.framework_columns import (
        _build_source_index, inspect_model, check_model, _load_contract,
    )

    ctx_obj = BuildContext(customer=customer)
    customer_parser = YAMLParser(models_dir)
    customer_models = customer_parser.load_all_models(ctx_obj)

    base_path = Path(base) if base else None
    if base_path:
        base_parser = YAMLParser(str(base_path))
        base_models = base_parser.load_all_models(ctx_obj)
        merged = _merge_base_and_customer_models(base_models, customer_models)
    else:
        merged = customer_models

    if model_name not in merged:
        console.print(f"[red]Model '{model_name}' not found. Available:[/red]")
        for n in sorted(merged.keys())[:20]:
            console.print(f"  {n}")
        if len(merged) > 20:
            console.print(f"  … +{len(merged) - 20} more")
        sys.exit(1)

    source_index = _build_source_index(base_path, Path(models_dir), ctx_obj)
    rows = inspect_model(model_name, merged, source_index)

    try:
        contract_data = _load_contract(None)
        check = check_model(model_name, merged[model_name], contract_data)
    except FileNotFoundError:
        check = None

    if output_format == "json":
        payload = {
            "model": model_name,
            "columns": [
                {"name": r.name, "data_type": r.data_type, "expression": r.expression, "source": r.source}
                for r in rows
            ],
        }
        if check:
            payload["framework_check"] = {
                "missing": check.missing,
                "type_mismatches": [
                    {"column": n, "expected": e, "actual": a} for n, e, a in check.type_mismatches
                ],
                "ok": check.ok,
            }
        console.print_json(data=payload)
        return

    console.print(f"[bold blue]{model_name}[/bold blue]  ({customer})")
    console.print(f"[dim]{len(rows)} column(s) after merge[/dim]\n")

    table = Table(show_header=True, header_style="bold")
    table.add_column("Column")
    table.add_column("Type")
    table.add_column("Source", style="cyan")
    table.add_column("Expression", overflow="ellipsis", max_width=60)
    for r in rows:
        colour = {"base": "dim white", "customer": "green", "framework": "magenta"}.get(r.source, "yellow")
        table.add_row(r.name, r.data_type, f"[{colour}]{r.source}[/{colour}]", r.expression or "")
    console.print(table)

    if check is not None:
        console.print("\n[bold]Framework check[/bold]")
        if not check.missing and not check.type_mismatches:
            console.print("  [green]all required framework columns present[/green]")
        else:
            for name in check.missing:
                console.print(f"  [red]MISSING[/red] {name}")
            for name, exp, act in check.type_mismatches:
                console.print(f"  [yellow]TYPE[/yellow]    {name}: expected {exp}, got {act}")


@cli.command(name="orphans")
@click.argument("models_dir", type=click.Path(exists=True))
@click.option(
    "--base", "-b", type=click.Path(exists=True),
    help="Base models directory (models are merged with base)",
)
@click.option("--customer", default="STANDARD", help="Customer identifier")
@click.option(
    "--kind",
    type=click.Choice(["downstream", "upstream", "both"]),
    default="both",
    show_default=True,
    help="downstream=cols nothing uses; upstream=cols with broken source refs",
)
@click.option(
    "--layer",
    help="Filter to a specific layer (bronze/silver/gold/interface). "
         "Terminal layer is always excluded from downstream orphan reporting unless "
         "--include-terminal is set.",
)
@click.option("--table", help="Filter to a specific table.")
@click.option(
    "--include-terminal/--no-include-terminal", default=False,
    help="Include gold/interface layer in downstream orphans "
         "(they're expected leaves; only flag them if you know they shouldn't be).",
)
@click.option(
    "--include-framework/--no-include-framework", default=False,
    help="Include framework/audit columns (valid_from, load_timestamp, ...).",
)
@click.option(
    "--format", "output_format",
    type=click.Choice(["table", "json", "csv"]),
    default="table",
    show_default=True,
)
@click.option(
    "--mode",
    type=click.Choice(["show_orphans", "show_all", "trace"]),
    default="show_orphans",
    show_default=True,
    help="show_orphans=detailed report of just orphans (default). "
         "show_all=flat table|layer|column|orphan(1/0) row for every column. "
         "trace=per-column upstream trace (table | <layer> | silver | bronze); "
         "requires --layer.",
)
@click.option(
    "--only-missing/--no-only-missing", default=False,
    help="trace mode only: keep only rows with a 'missing' upstream cell.",
)
@click.option("--output", "-o", type=click.Path(), help="Write report to file instead of stdout.")
def orphans(
    models_dir, base, customer, kind, layer, table, include_terminal,
    include_framework, output_format, mode, only_missing, output,
):
    """Find orphan columns in the lineage graph.

    \b
    - downstream orphans: columns declared in a table that no downstream column
      references. Candidates for removal.
    - upstream orphans: column expressions that reference a source column
      which doesn't exist in the upstream table. Broken lineage / typos.

    Bronze is the starting point of the graph and has no upstream by design.
    Gold/interface tables are the endpoints (terminal) and by default are not
    flagged as orphans -- pass --include-terminal to flag them anyway.

    \b
    Examples:
        # Every orphan in the whole graph (detailed report)
        northstar-formation orphans models/customers/customer0 --base models/_base

        # Flat per-column view: table | layer | column | orphan (1/0)
        northstar-formation orphans models/customers/customer0 --base models/_base \\
            --mode show_all --format csv -o orphans.csv

        # Only bronze orphans that nothing downstream uses
        northstar-formation orphans models/customers/customer0 --base models/_base \\
            --kind downstream --layer bronze

        # One table
        northstar-formation orphans models/customers/customer0 --base models/_base \\
            --table productlocation

        # Broken column references (typos, missing sources)
        northstar-formation orphans models/customers/customer0 --base models/_base --kind upstream
    """
    from .lineage import LineageAnalyzer
    import json as _json

    console.print("[bold blue]Northstar Formation[/bold blue] - Orphan Column Analysis")

    context = BuildContext(customer=customer, version="1.0.0", features=[])
    parser = YAMLParser(models_dir)
    if base:
        base_parser = YAMLParser(base)
        base_models = base_parser.load_all_models(context)
        customer_models = parser.load_all_models(context)
        models = _merge_base_and_customer_models(base_models, customer_models)
    else:
        models = parser.load_all_models(context)
    console.print(f"[green]✓[/green] Loaded {len(models)} model(s)")

    resolver = ModelResolver(parser)
    resolved = resolver.resolve_all(models, context)
    graph = LineageAnalyzer().analyze(models, resolved)
    console.print(
        f"[green]✓[/green] Graph: {len(graph.tables)} tables, "
        f"{len(graph.column_edges)} column edges"
    )

    # Build fast lookup: for each (table, column) → does any column_edge start here?
    used_as_source: set[tuple[str, str]] = {
        (e.source_table.lower(), e.source_column.lower()) for e in graph.column_edges
    }
    # And a set of all declared (table, column) — for upstream broken-ref checks.
    declared: dict[str, set[str]] = {
        t.name.lower(): {c.name.lower() for c in t.columns} for t in graph.tables.values()
    }

    def is_terminal(node) -> bool:
        # Terminal = no downstream table depends on this one.
        return not any(e.source == node.name for e in graph.edges)

    def _table_matches(tname: str) -> bool:
        # Accept full "layer.table" or bare "table" for --table filter.
        if not table:
            return True
        t = table.lower()
        n = tname.lower()
        return n == t or n.split(".", 1)[-1] == t

    # --- trace mode: per-column upstream trace (table | <layer> | silver | bronze) ---
    if mode == "trace":
        if not layer:
            console.print("[red]--mode trace requires --layer (gold, interface, or silver).[/red]")
            sys.exit(1)
        start_layer = layer.lower()
        if start_layer not in {"gold", "interface", "silver"}:
            console.print(
                f"[red]--mode trace: unsupported --layer '{layer}'. "
                "Use gold, interface, or silver.[/red]"
            )
            sys.exit(1)

        # Group column edges by target (table, column) for fast reverse lookup.
        incoming: dict[tuple[str, str], list] = {}
        for e in graph.column_edges:
            incoming.setdefault(
                (e.target_table.lower(), e.target_column.lower()), []
            ).append(e)

        def _hop(tname_l: str, cname_l: str, want_layer: str) -> list[str]:
            """Find column names at `want_layer` upstream of (tname_l, cname_l).

            Returns list of strings: real column names, or 'missing' if the edge
            points to a non-existent source column, or 'computed' for literals.
            Empty list means no upstream edge at all.
            """
            edges = incoming.get((tname_l, cname_l), [])
            if not edges:
                return []
            out: list[str] = []
            for e in edges:
                src_t = e.source_table.lower()
                src_c = e.source_column
                src_node = graph.tables.get(e.source_table)
                src_layer = (src_node.layer or "").lower() if src_node else ""
                if src_c == "<computed>":
                    if src_layer == want_layer or not want_layer:
                        out.append("computed")
                    continue
                if src_layer != want_layer:
                    # Skip edges that don't land at the requested layer.
                    continue
                if src_t in declared and src_c.lower() not in declared[src_t]:
                    out.append("missing")
                else:
                    out.append(src_c)
            # Dedup while preserving order.
            seen = set()
            uniq = []
            for x in out:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            return uniq

        # Bronze is a hop off any silver column; walk silver->bronze even if the
        # source_column ends up on a bronze table via a different silver name.
        def _to_bronze(silver_val: str, silver_tables: list[str]) -> list[str]:
            if silver_val in ("", "missing", "computed"):
                return [""]
            hits: list[str] = []
            for st in silver_tables:
                hits.extend(_hop(st.lower(), silver_val.lower(), "bronze"))
            if not hits:
                # Not resolvable on any silver source-table. Empty passthrough.
                return [""]
            seen = set()
            uniq = []
            for x in hits:
                if x not in seen:
                    seen.add(x)
                    uniq.append(x)
            return uniq

        # Determine start-layer tables to iterate.
        start_tables = [
            (tname, node) for tname, node in graph.tables.items()
            if (node.layer or "").lower() == start_layer and _table_matches(tname)
        ]

        # Column headers for output.
        if start_layer == "silver":
            headers = ["table", "silver", "bronze"]
        else:
            headers = ["table", start_layer, "silver", "bronze"]

        trace_rows: list[dict] = []
        for tname, node in start_tables:
            for col in node.columns:
                if not include_framework and col.name.lower() in _ORPHAN_FRAMEWORK_COLS:
                    continue
                if start_layer == "silver":
                    bronze_vals = _hop(tname.lower(), col.name.lower(), "bronze") or [""]
                    for bv in bronze_vals:
                        trace_rows.append({
                            "table": tname, "silver": col.name, "bronze": bv,
                        })
                    continue

                # gold or interface: hop to silver, then to bronze.
                silver_vals = _hop(tname.lower(), col.name.lower(), "silver")
                # Also allow gold->bronze direct (rare but possible).
                bronze_direct = _hop(tname.lower(), col.name.lower(), "bronze")

                if not silver_vals and not bronze_direct:
                    trace_rows.append({
                        "table": tname, start_layer: col.name,
                        "silver": "", "bronze": "",
                    })
                    continue

                if silver_vals:
                    # For each silver name, resolve possible source tables at silver.
                    silver_tables = [
                        e.source_table for e in incoming.get(
                            (tname.lower(), col.name.lower()), []
                        )
                        if (graph.tables.get(e.source_table).layer or "").lower() == "silver"
                        if e.source_table in graph.tables
                    ]
                    for sv in silver_vals:
                        bronze_vals = _to_bronze(sv, silver_tables)
                        for bv in bronze_vals:
                            trace_rows.append({
                                "table": tname, start_layer: col.name,
                                "silver": sv, "bronze": bv,
                            })
                for bv in bronze_direct:
                    trace_rows.append({
                        "table": tname, start_layer: col.name,
                        "silver": "", "bronze": bv,
                    })

        trace_rows.sort(key=lambda r: (r["table"], r.get(start_layer, r.get("silver", ""))))

        if only_missing:
            trace_rows = [r for r in trace_rows if "missing" in r.values()]

        if output_format == "json":
            _emit(_json.dumps(trace_rows, indent=2, default=str), output)
        elif output_format == "csv":
            import csv, io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=headers)
            w.writeheader()
            for r in trace_rows:
                w.writerow({k: r.get(k, "") for k in headers})
            _emit(buf.getvalue(), output)
        else:
            t = Table(
                title=f"Column trace from {start_layer} to bronze",
                show_header=True, header_style="bold blue",
            )
            for c in headers:
                t.add_column(c, style="white", overflow="fold", no_wrap=False)
            for r in trace_rows:
                vals = [str(r.get(c, "")) for c in headers]
                style = "yellow" if "missing" in vals else None
                t.add_row(*vals, style=style)
            console.print(t, soft_wrap=True)
            n_missing = sum(1 for r in trace_rows if "missing" in r.values())
            console.print(
                f"\n[bold]Total:[/bold] {len(trace_rows)} rows, "
                f"{n_missing} with missing upstream"
            )
        return

    # --- show_all mode: flat per-column report with 0/1 orphan flag ---
    if mode == "show_all":
        layer_order = {"gold": 0, "interface": 1, "silver": 2, "bronze": 3}
        terminal_layers = {"gold", "interface"}
        flat_rows: list[dict] = []
        for tname, node in graph.tables.items():
            if not _table_matches(tname):
                continue
            node_layer = (node.layer or "").lower() or "other"
            if layer and node_layer != layer.lower():
                continue
            table_is_terminal = is_terminal(node) or node_layer in terminal_layers
            for col in node.columns:
                cname_l = col.name.lower()
                is_framework = cname_l in _ORPHAN_FRAMEWORK_COLS
                has_downstream = (tname.lower(), cname_l) in used_as_source
                if has_downstream:
                    is_orphan = 0
                elif is_framework and not include_framework:
                    is_orphan = 0
                elif table_is_terminal and not include_terminal:
                    is_orphan = 0
                else:
                    is_orphan = 1
                flat_rows.append({
                    "table": tname,
                    "layer": node_layer,
                    "column": col.name,
                    "orphan": is_orphan,
                })
        flat_rows.sort(key=lambda r: (
            layer_order.get(r["layer"], 99), r["table"], r["column"],
        ))

        if output_format == "json":
            payload = _json.dumps(flat_rows, indent=2, default=str)
            _emit(payload, output)
        elif output_format == "csv":
            import csv, io
            buf = io.StringIO()
            w = csv.DictWriter(buf, fieldnames=["table", "layer", "column", "orphan"])
            w.writeheader()
            for r in flat_rows:
                w.writerow(r)
            _emit(buf.getvalue(), output)
        else:
            t = Table(title="Columns (orphan = 1 means no downstream consumer)",
                      show_header=True, header_style="bold blue")
            for c in ["table", "layer", "column", "orphan"]:
                t.add_column(c, style="white")
            for r in flat_rows:
                style = "yellow" if r["orphan"] == 1 else None
                t.add_row(r["table"], r["layer"], r["column"], str(r["orphan"]),
                          style=style)
            console.print(t)
            n_orph = sum(1 for r in flat_rows if r["orphan"] == 1)
            console.print(
                f"\n[bold]Total:[/bold] {len(flat_rows)} columns, "
                f"{n_orph} orphan"
            )
        return

    downstream_rows: list[dict] = []
    upstream_rows: list[dict] = []

    for tname, node in graph.tables.items():
        if not _table_matches(tname):
            continue
        if layer and (node.layer or "").lower() != layer.lower():
            continue

        # --- downstream orphans (columns nothing uses) ---
        if kind in ("downstream", "both"):
            skip_this_table_for_downstream = (
                not include_terminal
                and (
                    is_terminal(node)
                    or (node.layer or "").lower() in {"gold", "interface"}
                )
            )
            if not skip_this_table_for_downstream:
                for col in node.columns:
                    if not include_framework and col.name.lower() in _ORPHAN_FRAMEWORK_COLS:
                        continue
                    if (tname.lower(), col.name.lower()) not in used_as_source:
                        downstream_rows.append({
                            "kind": "downstream",
                            "table": tname,
                            "layer": node.layer or "",
                            "column": col.name,
                            "data_type": col.data_type or "",
                            "expression": (col.expression or "")[:80],
                            "reason": "no downstream column references it",
                        })

        # --- upstream orphans (broken source refs) ---
        if kind in ("upstream", "both"):
            # For every column_edge whose target is this column of this table,
            # verify that the source column actually exists in the source table's
            # declared columns. Skip <computed> pseudo-source and external tables.
            for edge in graph.column_edges:
                if edge.target_table.lower() != tname.lower():
                    continue
                if edge.source_column == "<computed>":
                    continue
                src = edge.source_table.lower()
                if src not in declared:
                    # External source (bronze/raw) — nothing to check locally.
                    continue
                if edge.source_column.lower() not in declared[src]:
                    upstream_rows.append({
                        "kind": "upstream",
                        "table": tname,
                        "layer": node.layer or "",
                        "column": edge.target_column,
                        "missing_source": f"{edge.source_table}.{edge.source_column}",
                        "expression": (edge.transformation or "")[:80],
                    })

    rows = downstream_rows + upstream_rows

    # Emit
    if output_format == "json":
        payload = _json.dumps(rows, indent=2, default=str)
        _emit(payload, output)
    elif output_format == "csv":
        import csv, io
        keys = ["kind", "table", "layer", "column", "data_type", "missing_source", "expression", "reason"]
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=keys)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in keys})
        _emit(buf.getvalue(), output)
    else:
        if downstream_rows:
            _print_orphan_table(
                "Downstream orphans (no consumer)", downstream_rows,
                ["table", "layer", "column", "data_type", "expression"],
            )
        if upstream_rows:
            _print_orphan_table(
                "Upstream orphans (broken source refs)", upstream_rows,
                ["table", "layer", "column", "missing_source", "expression"],
            )
        if not rows:
            console.print("[green]✓ no orphans found[/green]")
        console.print(
            f"\n[bold]Total:[/bold] {len(downstream_rows)} downstream, "
            f"{len(upstream_rows)} upstream"
        )


def _print_orphan_table(title: str, rows: list[dict], cols: list[str]) -> None:
    t = Table(title=title, show_header=True, header_style="bold blue")
    for c in cols:
        t.add_column(c, style="white")
    for r in rows:
        t.add_row(*[str(r.get(c, "")) for c in cols])
    console.print(t)


@cli.command("generate-dummy-data")
@click.option(
    "--customers-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=Path("models/customers"),
    show_default=True,
    help="Directory containing customer model folders.",
)
@click.option(
    "--output",
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("demo_data"),
    show_default=True,
    help="Directory where customer CSV data and manifests are written.",
)
@click.option("--rows", type=click.IntRange(min=1), default=100, show_default=True)
@click.option("--seed", type=int, default=42, show_default=True)
@click.option("--customer", "customer_name", help="Generate one customer; default is all customers.")
@click.pass_context
def generate_dummy_data(ctx, customers_dir, output_dir, rows, seed, customer_name):
    """Generate deterministic demo CSV data from customer gold models."""
    del ctx
    generator = DummyDataGenerator(seed=seed)
    customers = [customer_name] if customer_name else generator.discover_customers(customers_dir)
    if customer_name and not (customers_dir / customer_name).is_dir():
        raise click.ClickException(f"Customer directory not found: {customers_dir / customer_name}")

    for customer in customers:
        result = generator.generate_customer(customers_dir / customer, output_dir, rows)
        console.print(
            f"[green]✓[/green] {result.customer}: {result.models} models, "
            f"{result.rows} rows -> {result.output_dir}"
        )


def _emit(payload: str, output: Optional[str]) -> None:
    if output:
        Path(output).write_text(payload, encoding="utf-8")
        console.print(f"[green]✓[/green] Wrote {output}")
    else:
        console.print(payload)


def main():
    """Main entry point."""
    cli(obj={})


if __name__ == "__main__":
    main()
