#!/usr/bin/env python3
"""
Pydantic Configuration Models for Fabric Deployment System
Provides type-safe configuration validation with clear error messages
"""

from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, field_validator, model_validator
import re


# =============================================================================
# ENVIRONMENT VALUES
# =============================================================================
class EnvironmentValues(BaseModel):
    """Environment-specific values (dev, test, uat, prod)"""

    dev: str
    test: Optional[str] = None
    uat: Optional[str] = None
    prod: Optional[str] = None

    @field_validator("dev")
    @classmethod
    def dev_must_not_be_empty(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("dev environment value cannot be empty")
        return v


class OptionalEnvironmentValues(BaseModel):
    """Environment-specific values where all are optional"""

    dev: Optional[str] = None
    test: Optional[str] = None
    uat: Optional[str] = None
    prod: Optional[str] = None


# =============================================================================
# FIND/REPLACE RULES
# =============================================================================
class FindReplaceRule(BaseModel):
    """A single find/replace rule for parameter substitution"""

    name: str = Field(..., description="Unique identifier for this rule")
    find_value: str = Field(..., description="Value or regex pattern to find")
    replace_with: Dict[str, str] = Field(
        ..., description="Environment-specific replacement values"
    )
    is_regex: bool = Field(
        default=False, description="Whether find_value is a regex pattern"
    )
    file_path: Optional[str] = Field(
        default=None, description="Glob pattern to limit files"
    )
    item_type: Optional[str] = Field(
        default=None, description="Limit to specific item type"
    )
    item_name: Optional[str] = Field(
        default=None, description="Limit to specific item name"
    )

    @field_validator("find_value")
    @classmethod
    def validate_find_value(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("find_value cannot be empty")
        return v

    @field_validator("replace_with")
    @classmethod
    def validate_replace_with(cls, v: Dict[str, str]) -> Dict[str, str]:
        if "dev" not in v:
            raise ValueError(
                'replace_with must have at least a "dev" environment value'
            )
        return v

    @model_validator(mode="after")
    def validate_regex_pattern(self) -> "FindReplaceRule":
        """Validate regex pattern has exactly one capturing group"""
        if self.is_regex:
            try:
                pattern = re.compile(self.find_value)
                if pattern.groups != 1:
                    raise ValueError(
                        f"Regex pattern must have exactly ONE capturing group, "
                        f"found {pattern.groups}. Pattern: {self.find_value}"
                    )
            except re.error as e:
                raise ValueError(f"Invalid regex pattern: {e}")
        return self


class ParameterReplacements(BaseModel):
    """Parameter replacement configuration"""

    find_replace: List[FindReplaceRule] = Field(default_factory=list)
    key_value_replace: Optional[List[Dict[str, Any]]] = None
    spark_pool: Optional[List[Dict[str, Any]]] = None
    gateway_binding: Optional[List[Dict[str, Any]]] = None


# =============================================================================
# DEPLOYMENT PHASES
# =============================================================================
class DeploymentPhase(BaseModel):
    """A single deployment phase"""

    name: str = Field(..., description="Unique phase identifier")
    description: Optional[str] = None
    item_types: Optional[List[str]] = Field(
        default=None, description="Item types to deploy"
    )
    type: Optional[str] = Field(
        default=None, description="Phase type (deployment or notebook_execution)"
    )
    depends_on: Optional[str] = Field(default=None, description="Phase dependency")

    # Notebook execution specific fields
    workspace_name: Optional[str] = None
    notebooks: Optional[List[str]] = None
    lakehouse: Optional[str] = None
    timeout: Optional[int] = Field(default=600, ge=60, le=3600)
    stop_on_failure: Optional[bool] = True

    @model_validator(mode="after")
    def validate_phase_type(self) -> "DeploymentPhase":
        """Validate phase has required fields based on type"""
        if self.type == "notebook_execution":
            if not self.notebooks:
                raise ValueError('notebook_execution phase requires "notebooks" list')
            if not self.workspace_name:
                raise ValueError('notebook_execution phase requires "workspace_name"')
        elif self.type is None or self.type == "deployment":
            if not self.item_types:
                raise ValueError('deployment phase requires "item_types" list')
        return self


class DeploymentModes(BaseModel):
    """Deployment mode configurations"""

    full: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"enabled": True, "cleanup_orphans": False}
    )
    incremental: Optional[Dict[str, Any]] = None
    selective: Optional[Dict[str, Any]] = None


class RetryConfig(BaseModel):
    """Retry configuration for transient failures"""

    max_attempts: int = Field(default=3, ge=1, le=10)
    backoff_seconds: int = Field(default=30, ge=5, le=300)
    max_backoff_seconds: Optional[int] = Field(default=300, ge=60, le=600)


class DeploymentConfig(BaseModel):
    """Deployment configuration section"""

    phases: Optional[List[DeploymentPhase]] = None
    deployment_sequence: Optional[List[str]] = None
    modes: Optional[DeploymentModes] = None
    retry: Optional[RetryConfig] = None


# =============================================================================
# CORE CONFIGURATION
# =============================================================================
class CoreConfig(BaseModel):
    """Core configuration section"""

    workspace_id: Dict[str, str] = Field(
        ..., description="Workspace IDs per environment"
    )
    repository_directory: Dict[str, str] = Field(
        ..., description="Repository paths per environment"
    )
    item_types_in_scope: List[str] = Field(..., description="Item types to deploy")
    parameter_replacements: Optional[ParameterReplacements] = None
    parameter: Optional[str] = None

    @field_validator("workspace_id")
    @classmethod
    def validate_workspace_id(cls, v: Dict[str, str]) -> Dict[str, str]:
        if "dev" not in v:
            raise ValueError('workspace_id must have at least a "dev" environment')
        # Validate GUID format for each workspace ID
        guid_pattern = re.compile(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
        for env, ws_id in v.items():
            if ws_id and not ws_id.startswith("x") and not guid_pattern.match(ws_id):
                raise ValueError(f"Invalid workspace ID format for {env}: {ws_id}")
        return v

    @field_validator("item_types_in_scope")
    @classmethod
    def validate_item_types(cls, v: List[str]) -> List[str]:
        valid_types = {
            "Lakehouse",
            "Notebook",
            "SemanticModel",
            "Report",
            "DataPipeline",
            "Warehouse",
            "Environment",
            "MLModel",
            "MLExperiment",
            "Eventhouse",
            "KQLDatabase",
            "KQLQueryset",
            "Eventstream",
            "Reflex",
            "Dashboard",
            "SparkJobDefinition",
            "SQLEndpoint",
        }
        for item_type in v:
            if item_type not in valid_types:
                raise ValueError(
                    f"Invalid item type: {item_type}. Valid types: {valid_types}"
                )
        return v


# =============================================================================
# METADATA
# =============================================================================
class Metadata(BaseModel):
    """Configuration metadata"""

    customer_id: str = Field(..., description="Unique customer identifier")
    customer_name: Optional[str] = None
    description: Optional[str] = None
    version: Optional[str] = None

    @field_validator("customer_id")
    @classmethod
    def validate_customer_id(cls, v: str) -> str:
        if not v or v.strip() == "":
            raise ValueError("customer_id cannot be empty")
        # Only allow alphanumeric, hyphens, and underscores
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError(
                "customer_id can only contain letters, numbers, hyphens, and underscores"
            )
        return v


# =============================================================================
# VALIDATION CONFIGURATION
# =============================================================================
class ValidationConfig(BaseModel):
    """Validation checks configuration"""

    pre_deployment: List[str] = Field(default_factory=list)
    post_deployment: List[str] = Field(default_factory=list)
    skip_for_selective: Optional[bool] = False


# =============================================================================
# MAIN CONFIGURATION MODEL
# =============================================================================
class CustomerConfig(BaseModel):
    """
    Complete customer configuration model.

    This is the root model that validates the entire config.yml file.
    Use CustomerConfig.model_validate(config_dict) to validate a configuration.
    """

    metadata: Metadata
    core: CoreConfig
    deployment: Optional[DeploymentConfig] = None
    validation: Optional[ValidationConfig] = None
    features: List[str] = Field(default_factory=list)
    publish: Optional[Dict[str, Any]] = None
    unpublish: Optional[Dict[str, Any]] = None

    @model_validator(mode="after")
    def validate_deployment_phases_dependencies(self) -> "CustomerConfig":
        """Validate phase dependencies exist"""
        if self.deployment and self.deployment.phases:
            phase_names = {p.name for p in self.deployment.phases}
            for phase in self.deployment.phases:
                if phase.depends_on and phase.depends_on not in phase_names:
                    raise ValueError(
                        f'Phase "{phase.name}" depends on "{phase.depends_on}" '
                        f"which does not exist. Available phases: {phase_names}"
                    )
        return self

    @model_validator(mode="after")
    def validate_items_resolution_order(self) -> "CustomerConfig":
        """
        Validate that $items references in find_replace rules only reference
        item types that are deployed BEFORE the item using the reference.
        """
        if not self.deployment or not self.deployment.phases:
            return self

        if not self.core.parameter_replacements:
            return self

        # Build ordered list of item types from phases
        item_type_order = []
        for phase in self.deployment.phases:
            if phase.item_types:
                item_type_order.extend(phase.item_types)

        # Pattern to extract $items references
        items_pattern = re.compile(r"\$items\.(\w+)\.")

        for rule in self.core.parameter_replacements.find_replace:
            for env, value in rule.replace_with.items():
                if not isinstance(value, str):
                    continue

                # Find all $items references
                referenced_types = set(items_pattern.findall(value))

                if not referenced_types:
                    continue

                # If rule targets specific item type, check order
                if rule.item_type and rule.item_type in item_type_order:
                    using_index = item_type_order.index(rule.item_type)

                    for ref_type in referenced_types:
                        if ref_type in item_type_order:
                            ref_index = item_type_order.index(ref_type)
                            if using_index < ref_index:
                                raise ValueError(
                                    f'Rule "{rule.name}" in {rule.item_type} references '
                                    f"$items.{ref_type} but {rule.item_type} deploys BEFORE {ref_type}"
                                )

        return self


# =============================================================================
# VALIDATION HELPER FUNCTIONS
# =============================================================================
def validate_config(config_dict: Dict[str, Any]) -> CustomerConfig:
    """
    Validate a configuration dictionary.

    Args:
        config_dict: Configuration dictionary (from yaml.safe_load)

    Returns:
        Validated CustomerConfig model

    Raises:
        pydantic.ValidationError: If validation fails
    """
    return CustomerConfig.model_validate(config_dict)


def validate_config_file(config_path: str) -> CustomerConfig:
    """
    Load and validate a configuration file.

    Args:
        config_path: Path to config.yml file

    Returns:
        Validated CustomerConfig model

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML parsing fails
        pydantic.ValidationError: If validation fails
    """
    import yaml
    from pathlib import Path

    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    with open(path, "r") as f:
        config_dict = yaml.safe_load(f)

    return validate_config(config_dict)


# =============================================================================
# CLI ENTRY POINT
# =============================================================================
if __name__ == "__main__":
    import argparse
    import yaml
    import sys

    parser = argparse.ArgumentParser(
        description="Validate Fabric deployment configuration"
    )
    parser.add_argument("config_file", help="Path to config.yml file")
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed output"
    )

    args = parser.parse_args()

    try:
        config = validate_config_file(args.config_file)
        print(f"[OK] Configuration is valid: {args.config_file}")

        if args.verbose:
            print(f"\nCustomer: {config.metadata.customer_id}")
            print(f"Item types: {config.core.item_types_in_scope}")
            if config.deployment and config.deployment.phases:
                print(f"Phases: {[p.name for p in config.deployment.phases]}")
            if config.core.parameter_replacements:
                print(
                    f"Find/replace rules: {len(config.core.parameter_replacements.find_replace)}"
                )

        sys.exit(0)

    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    except yaml.YAMLError as e:
        print(f"[ERROR] YAML parsing error: {e}")
        sys.exit(1)

    except Exception as e:
        print("[ERROR] Validation failed:")
        # Pydantic errors have detailed messages
        error_msg = str(e)
        # Clean up pydantic error formatting
        for line in error_msg.split("\n"):
            if line.strip():
                print(f"  {line}")
        sys.exit(1)
