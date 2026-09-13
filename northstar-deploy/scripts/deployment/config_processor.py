#!/usr/bin/env python3
"""
Configuration Processor for Fabric Deployment System
Handles configuration loading, validation, and variable substitution
"""

import re
import yaml
from pathlib import Path
from typing import Dict, List, Optional
import copy


class ConfigProcessor:
    """Process and validate deployment configurations"""

    def __init__(self, config_path: Path):
        """
        Initialize configuration processor

        Args:
            config_path: Path to customer configuration directory
        """
        self.config_path = Path(config_path)
        self.main_config_file = self.config_path / "config.yml"
        self.parameters_dir = self.config_path / "parameters"
        self.overrides_dir = self.config_path / "overrides"

    def load_config(self) -> Dict:
        """Load main configuration file"""
        if not self.main_config_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.main_config_file}"
            )

        with open(self.main_config_file, "r") as f:
            config = yaml.safe_load(f)

        return self._validate_config_structure(config)

    def _validate_config_structure(self, config: Dict) -> Dict:
        """Validate configuration structure against requirements"""
        required_sections = ["metadata", "core", "features"]
        required_core_fields = [
            "workspace_id",
            "repository_directory",
            "item_types_in_scope",
        ]

        # Check required sections
        for section in required_sections:
            if section not in config:
                raise ValueError(f"Missing required configuration section: {section}")

        # Check core fields
        for field in required_core_fields:
            if field not in config["core"]:
                raise ValueError(f"Missing required core field: {field}")

        # Validate workspace IDs
        if not isinstance(config["core"]["workspace_id"], dict):
            raise ValueError("workspace_id must be a dictionary with environment keys")

        # Validate features
        if not isinstance(config["features"], list):
            raise ValueError("features must be a list")

        # Check for experimental features requirement
        if "enable_experimental_features" not in config["features"]:
            print("Warning: 'enable_experimental_features' not in features list")

        return config

    def load_parameters(self, environment: str) -> Dict:
        """Load environment-specific parameters"""
        param_file = self.parameters_dir / f"{environment}.yml"

        if not param_file.exists():
            print(f"Warning: Parameter file not found for {environment}: {param_file}")
            return {}

        with open(param_file, "r") as f:
            params = yaml.safe_load(f)

        return params

    def apply_variable_substitution(self, config: Dict, variables: Dict) -> Dict:
        """
        Apply variable substitution to configuration

        Args:
            config: Configuration dictionary
            variables: Variables to substitute

        Returns:
            Configuration with substituted variables
        """
        config_str = yaml.dump(config)

        # Replace variables in format ${VAR_NAME}
        for key, value in variables.items():
            pattern = f"\\$\\{{{key}\\}}"
            config_str = re.sub(pattern, str(value), config_str)

        return yaml.safe_load(config_str)

    def merge_configs(self, base: Dict, override: Dict) -> Dict:
        """
        Deep merge override configuration with base configuration

        Args:
            base: Base configuration
            override: Override configuration

        Returns:
            Merged configuration
        """
        result = copy.deepcopy(base)

        for key, value in override.items():
            if key in result:
                if isinstance(result[key], dict) and isinstance(value, dict):
                    result[key] = self.merge_configs(result[key], value)
                elif isinstance(result[key], list) and isinstance(value, list):
                    # For lists, replace rather than extend
                    result[key] = value
                else:
                    result[key] = value
            else:
                result[key] = value

        return result

    def create_deployment_config(
        self,
        environment: str,
        mode: str = "full",
        selective_items: Optional[List[str]] = None,
    ) -> Dict:
        """
        Create a complete deployment configuration for a specific environment

        Args:
            environment: Target environment
            mode: Deployment mode
            selective_items: List of items for selective deployment

        Returns:
            Complete deployment configuration
        """
        # Load base configuration
        config = self.load_config()

        # Load environment parameters
        params = self.load_parameters(environment)

        # Apply mode-specific overrides
        if mode == "selective":
            override_file = self.overrides_dir / "selective-deploy.yml"
            if override_file.exists():
                with open(override_file, "r") as f:
                    overrides = yaml.safe_load(f)
                config = self.merge_configs(config, overrides)

        # Add selective items if provided
        if selective_items and mode == "selective":
            if "publish" not in config:
                config["publish"] = {}
            config["publish"]["items_to_include"] = selective_items

        # Ensure features for selective deployment
        if mode == "selective" and "enable_items_to_include" not in config.get(
            "features", []
        ):
            config["features"].append("enable_items_to_include")

        # Set environment-specific values
        deployment_config = {
            "metadata": config.get("metadata", {}),
            "environment": environment,
            "mode": mode,
            "core": {
                "workspace_id": config["core"]["workspace_id"].get(environment),
                "repository_directory": config["core"]["repository_directory"].get(
                    environment
                ),
                "item_types_in_scope": config["core"]["item_types_in_scope"],
                "parameter": config["core"].get("parameter", {}).get(environment),
            },
            "deployment": config.get("deployment", {}),
            "publish": self._get_environment_config(
                config.get("publish", {}), environment
            ),
            "unpublish": self._get_environment_config(
                config.get("unpublish", {}), environment
            ),
            "features": config.get("features", []),
            "validation": config.get("validation", {}),
            "parameters": params,
        }

        return deployment_config

    def _get_environment_config(self, section: Dict, environment: str) -> Dict:
        """Extract environment-specific configuration from a section"""
        result = {}

        for key, value in section.items():
            if isinstance(value, dict) and environment in value:
                result[key] = value[environment]
            else:
                result[key] = value

        return result

    def create_fabric_cicd_config(
        self, deployment_config: Dict, item_type: str
    ) -> Dict:
        """
        Create a fabric-cicd compatible configuration for a specific item type

        Args:
            deployment_config: Complete deployment configuration
            item_type: Specific item type to deploy

        Returns:
            fabric-cicd compatible configuration
        """
        fabric_config = {
            "core": {
                "workspace_id": deployment_config["core"]["workspace_id"],
                "repository_directory": deployment_config["core"][
                    "repository_directory"
                ],
                "item_types_in_scope": [item_type],
            },
            "features": deployment_config["features"],
        }

        # Add parameter file if exists
        if deployment_config["core"].get("parameter"):
            fabric_config["core"]["parameter"] = deployment_config["core"]["parameter"]

        # Add publish configuration
        if deployment_config.get("publish"):
            fabric_config["publish"] = deployment_config["publish"]

        # Add unpublish configuration
        if deployment_config.get("unpublish"):
            fabric_config["unpublish"] = deployment_config["unpublish"]

        return fabric_config

    def validate_parameter_file(self, param_file: Path) -> bool:
        """
        Validate parameter file structure

        Args:
            param_file: Path to parameter file

        Returns:
            True if valid, raises exception if not
        """
        if not param_file.exists():
            raise FileNotFoundError(f"Parameter file not found: {param_file}")

        with open(param_file, "r") as f:
            params = yaml.safe_load(f)

        # Check for find_replace section
        if "find_replace" not in params:
            print(f"Warning: No find_replace section in {param_file}")
            return True

        # Validate find_replace structure
        if not isinstance(params["find_replace"], list):
            raise ValueError("find_replace must be a list")

        for item in params["find_replace"]:
            if not isinstance(item, dict):
                raise ValueError("Each find_replace item must be a dictionary")
            if "find_value" not in item or "replace_value" not in item:
                raise ValueError(
                    "Each find_replace item must have 'find_value' and 'replace_value'"
                )

        return True

    def get_deployment_sequence(self, config: Dict) -> List[str]:
        """
        Get the deployment sequence for items

        Args:
            config: Configuration dictionary

        Returns:
            List of item types in deployment order
        """
        # Check for custom deployment sequence
        if "deployment" in config and "deployment_sequence" in config["deployment"]:
            return config["deployment"]["deployment_sequence"]

        # Default to items in scope
        return config["core"].get("item_types_in_scope", [])

    def get_retry_config(self, config: Dict) -> Dict:
        """
        Get retry configuration

        Args:
            config: Configuration dictionary

        Returns:
            Retry configuration
        """
        default_retry = {
            "max_attempts": 3,
            "backoff_seconds": 30,
            "retriable_errors": [
                "TooManyRequests",
                "ServiceUnavailable",
                "GatewayTimeout",
            ],
        }

        if "deployment" in config and "retry" in config["deployment"]:
            return config["deployment"]["retry"]

        return default_retry


# Utility functions for external use
def load_customer_config(customer_id: str, environment: str) -> Dict:
    """
    Load configuration for a specific customer and environment

    Args:
        customer_id: Customer identifier
        environment: Target environment

    Returns:
        Complete configuration dictionary
    """
    config_path = Path(f"configurations/{customer_id}")
    processor = ConfigProcessor(config_path)
    return processor.create_deployment_config(environment)


def validate_all_customer_configs(customer_ids: List[str]) -> Dict[str, bool]:
    """
    Validate configurations for multiple customers

    Args:
        customer_ids: List of customer IDs

    Returns:
        Dictionary of customer_id -> validation status
    """
    results = {}

    for customer_id in customer_ids:
        config_path = Path(f"configurations/{customer_id}")
        processor = ConfigProcessor(config_path)

        try:
            processor.load_config()
            results[customer_id] = True
        except Exception as e:
            print(f"Validation failed for {customer_id}: {str(e)}")
            results[customer_id] = False

    return results
