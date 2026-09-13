"""YAML parser with partial file support."""

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from pydantic import ValidationError as PydanticValidationError

from ..utils.errors import FileNotFoundError, ParsingError
from ..utils.logging import get_logger
from .models import BuildContext, Model, YAMLConfig


logger = get_logger(__name__)


class YAMLParser:
    """Parse YAML files with partial file support."""

    def __init__(self, base_directory: str):
        self.base_directory = Path(base_directory)
        if not self.base_directory.exists():
            raise FileNotFoundError(f"Directory not found: {base_directory}")

        self.loaded_files: Dict[str, YAMLConfig] = {}
        self.model_groups: Dict[str, List[Path]] = defaultdict(list)

    # Directories under a customer/base tree that never contain model YAMLs
    # (they hold config, external references, or generator-specific configs like
    # data-quality/validation notebook definitions and framework contract files).
    _NON_MODEL_DIRS = ("config", "external", "data_quality", "framework")

    def discover_files(self) -> None:
        logger.info("Discovering YAML files in %s", self.base_directory)
        yaml_files = []
        for pattern in ["*.yaml", "*.yml"]:
            for file_path in self.base_directory.rglob(pattern):
                if not any(part in self._NON_MODEL_DIRS for part in file_path.parts):
                    yaml_files.append(file_path)
        for file_path in yaml_files:
            model_name = self._extract_model_name(file_path)
            if model_name:
                self.model_groups[model_name].append(file_path)
                logger.debug(f"  Found: {file_path.name} → {model_name}")
        logger.info("Discovered %d files for %d models", len(yaml_files), len(self.model_groups))

    def _extract_model_name(self, file_path: Path) -> Optional[str]:
        """Extract model name from file path.

        For models in layer directories (bronze/silver/gold), use layer-qualified
        names internally to ensure uniqueness (e.g., 'bronze.fct_customer').
        """
        filename = file_path.stem
        parts = filename.split(".")
        base_name = parts[0] if parts else None

        if not base_name:
            return None

        # Check if file is in a layer directory and qualify the name
        path_parts = file_path.parts
        for part in path_parts:
            if part in ("bronze", "silver", "gold", "interface"):
                # Use layer-qualified name for internal uniqueness
                return f"{part}.{base_name}"

        return base_name

    def _is_partial_file(self, data: Dict[str, Any], file_path: Path) -> bool:
        # INCLUDE new keys in partial detection
        partial_indicators = [
            "transformations",
            "filters",
            "metadata",
            "ctes",
            "aggregations",
            "relationships",
            "audits",
            "optimization",
        ]
        has_partial_content = any(key in data for key in partial_indicators)
        has_no_model = "model" not in data
        filename = file_path.stem
        has_variant = "." in filename
        return has_partial_content and has_no_model and has_variant

    def load_file(self, file_path: Path) -> Optional[YAMLConfig]:
        if str(file_path) in self.loaded_files:
            return self.loaded_files[str(file_path)]

        try:
            with open(file_path) as f:
                data = yaml.safe_load(f)

            if not data:
                logger.warning(f"  Empty YAML file: {file_path.name}")
                return None

            # Create minimal model for partials
            if "model" not in data and self._is_partial_file(data, file_path):
                model_name = self._extract_model_name(file_path)
                metadata = data.pop("metadata", None)
                model_data = {"name": model_name}
                if metadata:
                    model_data["metadata"] = metadata
                for key in [
                    "transformations",
                    "filters",
                    "aggregations",
                    "ctes",
                    "relationships",
                    "audits",
                    "optimization",
                ]:
                    if key in data:
                        model_data[key] = data[key]
                data = {"model": model_data}

            # Merge root-level sections into model
            if "model" in data:
                model_data = data["model"]
                for key in [
                    "source",
                    "transformations",
                    "filters",
                    "aggregations",
                    "ctes",
                    "relationships",
                    "audits",
                    "optimization",
                ]:
                    if key in data and key not in model_data:
                        model_data[key] = data[key]
                data["model"] = model_data

            try:
                config = YAMLConfig(**data)
                self.loaded_files[str(file_path)] = config
                logger.debug(f"  Loaded: {file_path.name}")
                return config
            except PydanticValidationError as e:
                errors = []
                for error in e.errors():
                    field = ".".join(str(x) for x in error["loc"])
                    msg = error["msg"]
                    errors.append(f"{field}: {msg}")
                raise ParsingError(
                    f"Invalid YAML structure in {file_path.name}:\n"
                    + "\n".join(f"  - {err}" for err in errors)
                )
        except yaml.YAMLError as e:
            raise ParsingError(f"Failed to parse YAML {file_path.name}: {e}")
        except ParsingError:
            raise
        except Exception as e:
            raise ParsingError(f"Error loading {file_path.name}: {e}")

    def load_model(self, model_name: str, context: BuildContext) -> Optional[Model]:
        if model_name not in self.model_groups:
            raise FileNotFoundError(f"No files found for model: {model_name}")

        files = self.model_groups[model_name]
        logger.info("Loading model '%s' from %d file(s)", model_name, len(files))
        sorted_files = self._sort_files_for_loading(files)

        base_model: Optional[Model] = None
        applied_files = []
        partial_configs = []

        for file_path in sorted_files:
            try:
                config = self.load_file(file_path)
                if not config:
                    continue
                if self._should_apply_file(config, file_path, context):
                    if base_model is None:
                        base_model = config.model
                        applied_files.append(file_path.name)
                    else:
                        base_model = base_model.merge_with(config.model)
                        applied_files.append(file_path.name)
            except ParsingError as e:
                if "." in file_path.stem:
                    logger.warning(f"  Skipping partial file {file_path.name}: {e}")
                    partial_configs.append((file_path, e))
                else:
                    raise

        if base_model is None:
            if partial_configs:
                logger.error(f"Could not load model {model_name}: base file missing or invalid")
                logger.error("Partial files found but no valid base file:")
                for path, error in partial_configs:
                    logger.error(f"  - {path.name}: {error}")
            raise ParsingError(
                f"No applicable files found for model {model_name} with context {context}"
            )

        # Update the model name to use the layer-qualified name for internal consistency
        if base_model and "." in model_name:
            base_model.name = model_name

        logger.info("Loaded model '%s' from: %s", model_name, ", ".join(applied_files))
        return base_model

    def _sort_files_for_loading(self, files: List[Path]) -> List[Path]:
        def sort_key(path: Path) -> Tuple[int, str]:
            filename = path.stem
            parts = filename.split(".")
            if len(parts) == 1:
                return (0, filename)
            elif "v" in parts[1] or "version" in parts[1]:
                return (1, filename)
            elif any(keyword in parts[1] for keyword in ["feature", "analytics", "premium"]):
                return (2, filename)
            elif any(keyword in parts[1] for keyword in ["tenant", "customer", "client"]):
                return (3, filename)
            else:
                return (4, filename)

        return sorted(files, key=sort_key)

    def _should_apply_file(
        self, config: YAMLConfig, file_path: Path, context: BuildContext
    ) -> bool:
        filename = file_path.stem
        if "." not in filename:
            return True
        if config.model.metadata and config.model.metadata.applies_when:
            return context.matches_condition(config.model.metadata.applies_when)
        parts = filename.split(".")
        if len(parts) > 1:
            variant = parts[1].lower()
            if variant == context.customer.lower():
                return True
            if variant in [f.lower() for f in context.features]:
                return True
            if variant.startswith("v"):
                version_match = re.search(r"v(\d+)", variant)
                if version_match:
                    file_version = version_match.group(1)
                    context_version = context.version.split(".")[0]
                    if file_version == context_version:
                        return True
        return "." not in filename

    def load_all_models(self, context: BuildContext) -> Dict[str, Model]:
        self.discover_files()
        models = {}
        for model_name in self.model_groups:
            try:
                model = self.load_model(model_name, context)
                models[model_name] = model
            except Exception as e:
                logger.warning("Failed to load model %s: %s", model_name, e)
        return models

    def load_dynamic_functions(self, context: BuildContext) -> Dict[str, Any]:
        functions = {}
        core_functions_path = self.base_directory / "config" / "dynamic_functions.yaml"
        if core_functions_path.exists():
            with open(core_functions_path) as f:
                data = yaml.safe_load(f)
                if data and "dynamic_functions" in data:
                    functions["core"] = data["dynamic_functions"].get("core", [])
        customer_functions_path = (
            self.base_directory / "config" / f"dynamic_functions.{context.customer.lower()}.yaml"
        )
        if customer_functions_path.exists():
            with open(customer_functions_path) as f:
                data = yaml.safe_load(f)
                if data and "dynamic_functions" in data:
                    custom = data["dynamic_functions"].get("custom", {})
                    if custom.get("customer") == context.customer:
                        functions["custom"] = custom.get("functions", [])
        return functions


class PartialFileMerger:
    """Handles merging of partial YAML files."""

    @staticmethod
    def deep_merge(base: Dict[str, Any], overlay: Dict[str, Any]) -> Dict[str, Any]:
        result = base.copy()
        for key, value in overlay.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = PartialFileMerger.deep_merge(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    result[key] = result[key] + value
                else:
                    result[key] = value
            else:
                result[key] = value
        return result

    @staticmethod
    def merge_models(models: List[Model]) -> Model:
        if not models:
            raise ValueError("No models to merge")
        if len(models) == 1:
            return models[0]
        base_model = models[0]
        for model in models[1:]:
            base_model = base_model.merge_with(model)
        return base_model
