"""Master configuration schema for Northstar Formation skeleton generation."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class HorizontalLayer(BaseModel):
    """Data processing stages (e.g., raw, staging, mart, or bronze, silver, gold)."""

    name: str = Field(..., description="Layer name")
    description: Optional[str] = Field(None, description="Layer description")
    order: Optional[int] = Field(None, description="Processing order")


class VerticalLayer(BaseModel):
    """Business domain layers (e.g., core/product, domain/industry, tenant/customer)."""

    name: str = Field(..., description="Layer name")
    description: Optional[str] = Field(None, description="Layer description")
    sublayers: Optional[Dict[str, str]] = Field(
        None, description="Nested sublayers with descriptions"
    )


class ModelDefinition(BaseModel):
    """Individual model definition within the layering system."""

    name: str = Field(..., description="Model name")
    horizontal_layer: str = Field(..., description="Which horizontal layer (raw, staging, etc.)")
    source_table: Optional[str] = Field(None, description="Source table reference")
    inherits_from: Optional[str] = Field(
        None,
        description="Full path: vertical.horizontal.model or vertical.sublayer.horizontal.model",
    )
    extends: Optional[str] = Field(None, description="Model to extend from")
    variants: Optional[List[str]] = Field(None, description="Partial/variant files to generate")
    kind: str = Field("VIEW", description="Model kind (VIEW, TABLE, etc.)")
    description: Optional[str] = Field(None, description="Model description")

    @field_validator("kind")
    def validate_kind(cls, v):
        """Validate model kind."""
        valid_kinds = ["VIEW", "TABLE", "INCREMENTAL", "EPHEMERAL", "MATERIALIZED"]
        if v.upper() not in valid_kinds:
            raise ValueError(f"Invalid kind: {v}. Must be one of {valid_kinds}")
        return v.upper()


class ProjectConfig(BaseModel):
    """Project configuration."""

    name: str = Field(..., description="Project name")
    version: str = Field("1.0.0", description="Project version")
    output_dir: str = Field(
        "./generated_models", description="Output directory for generated files"
    )
    description: Optional[str] = Field(None, description="Project description")


class MasterConfig(BaseModel):
    """Complete master configuration for skeleton generation."""

    project: ProjectConfig = Field(..., description="Project configuration")
    horizontal_layers: List[HorizontalLayer] = Field(
        ..., description="Horizontal layer definitions"
    )
    vertical_layers: List[VerticalLayer] = Field(..., description="Vertical layer definitions")
    variants: Optional[List[str]] = Field(None, description="Global variant definitions")
    models: Dict[str, Any] = Field(
        ..., description="Model definitions organized by vertical/horizontal"
    )

    @field_validator("horizontal_layers")
    def validate_horizontal_layers(cls, v):
        """Ensure horizontal layers have unique names."""
        names = [layer.name for layer in v]
        if len(names) != len(set(names)):
            raise ValueError("Horizontal layers must have unique names")
        return v

    @field_validator("vertical_layers")
    def validate_vertical_layers(cls, v):
        """Ensure vertical layers have unique names."""
        names = [layer.name for layer in v]
        if len(names) != len(set(names)):
            raise ValueError("Vertical layers must have unique names")
        return v

    def get_horizontal_layer(self, name: str) -> Optional[HorizontalLayer]:
        """Get horizontal layer by name."""
        for layer in self.horizontal_layers:
            if layer.name == name:
                return layer
        return None

    def get_vertical_layer(self, name: str) -> Optional[VerticalLayer]:
        """Get vertical layer by name."""
        for layer in self.vertical_layers:
            if layer.name == name:
                return layer
        return None

    def validate_model_references(self) -> List[str]:
        """Validate that all model references are valid."""
        errors = []

        # Collect all valid horizontal layer names
        horizontal_names = {layer.name for layer in self.horizontal_layers}

        # Collect all vertical layer names including sublayers
        vertical_names = {layer.name for layer in self.vertical_layers}
        for layer in self.vertical_layers:
            if layer.sublayers:
                for sublayer_name in layer.sublayers.keys():
                    vertical_names.add(f"{layer.name}.{sublayer_name}")

        # Validate each model
        for vertical_name, vertical_models in self.models.items():
            if vertical_name not in vertical_names:
                # Check if it's a valid vertical layer
                base_vertical = (
                    vertical_name.split(".")[0] if "." in vertical_name else vertical_name
                )
                if base_vertical not in {layer.name for layer in self.vertical_layers}:
                    errors.append(f"Unknown vertical layer: {vertical_name}")

            # Process models
            if isinstance(vertical_models, list):
                for model in vertical_models:
                    if isinstance(model, dict):
                        model_def = ModelDefinition(**model)
                        if model_def.horizontal_layer not in horizontal_names:
                            errors.append(
                                f"Model {model_def.name}: Unknown horizontal layer {model_def.horizontal_layer}"
                            )
            elif isinstance(vertical_models, dict):
                # Handle nested structure
                for sublayer_name, sublayer_models in vertical_models.items():
                    if isinstance(sublayer_models, list):
                        for model in sublayer_models:
                            if isinstance(model, dict):
                                model_def = ModelDefinition(**model)
                                if model_def.horizontal_layer not in horizontal_names:
                                    errors.append(
                                        f"Model {model_def.name}: Unknown horizontal layer {model_def.horizontal_layer}"
                                    )

        return errors


def load_master_config(config_path: str) -> MasterConfig:
    """Load and validate master configuration from YAML file."""
    from pathlib import Path

    import yaml

    config_file = Path(config_path)
    if not config_file.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(config_file) as f:
        data = yaml.safe_load(f)

    # Convert raw project dict to ProjectConfig if needed
    if isinstance(data.get("project"), dict):
        data["project"] = ProjectConfig(**data["project"])

    config = MasterConfig(**data)

    # Validate model references
    errors = config.validate_model_references()
    if errors:
        error_msg = "Configuration validation errors:\n" + "\n".join(f"  - {e}" for e in errors)
        raise ValueError(error_msg)

    return config


def filter_by_vertical(config: MasterConfig, vertical_filter: str) -> MasterConfig:
    """Filter models by vertical layer."""
    filtered_models = {}

    for vertical_name, vertical_models in config.models.items():
        # Check if this vertical matches the filter
        if vertical_name == vertical_filter or vertical_name.startswith(f"{vertical_filter}."):
            filtered_models[vertical_name] = vertical_models
        elif isinstance(vertical_models, dict):
            # Check sublayers
            filtered_sublayers = {}
            for sublayer_name, sublayer_models in vertical_models.items():
                full_path = f"{vertical_name}.{sublayer_name}"
                if vertical_name == vertical_filter or full_path.startswith(f"{vertical_filter}."):
                    filtered_sublayers[sublayer_name] = sublayer_models

            if filtered_sublayers:
                filtered_models[vertical_name] = filtered_sublayers

    config.models = filtered_models
    return config


def filter_by_horizontal(config: MasterConfig, horizontal_filter: str) -> MasterConfig:
    """Filter models by horizontal layer."""
    filtered_models = {}

    for vertical_name, vertical_models in config.models.items():
        if isinstance(vertical_models, list):
            # Filter direct models
            filtered = [
                m
                for m in vertical_models
                if isinstance(m, dict) and m.get("horizontal_layer") == horizontal_filter
            ]
            if filtered:
                filtered_models[vertical_name] = filtered
        elif isinstance(vertical_models, dict):
            # Filter sublayer models
            filtered_sublayers = {}
            for sublayer_name, sublayer_models in vertical_models.items():
                if isinstance(sublayer_models, list):
                    filtered = [
                        m
                        for m in sublayer_models
                        if isinstance(m, dict) and m.get("horizontal_layer") == horizontal_filter
                    ]
                    if filtered:
                        filtered_sublayers[sublayer_name] = filtered

            if filtered_sublayers:
                filtered_models[vertical_name] = filtered_sublayers

    config.models = filtered_models
    return config
