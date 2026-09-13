#!/usr/bin/env python3
"""
Deployment Orchestrator for Fabric Multi-Customer Deployment System
Implements REQ-006, REQ-008, REQ-016, REQ-019
"""

import os
import sys
import json
import yaml
import argparse
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import copy
import re
from fabric_cicd import (
    FabricWorkspace,
    publish_all_items,
    unpublish_all_orphan_items,
    deploy_with_config,
)
from azure.identity import ClientSecretCredential

# Add project root to path
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

from scripts.auth.auth_spn import setup_fabric_auth  # noqa: E402
from scripts.deployment.config_models import validate_config  # noqa: E402
from scripts.deployment.config_processor import ConfigProcessor  # noqa: E402
from scripts.deployment.notebook_executor import (  # noqa: E402
    execute_notebooks_after_deployment,
)
from scripts.deployment.retry_handler import create_retry_handler_from_config  # noqa: E402
from scripts.deployment.validation import ValidationEngine  # noqa: E402
from scripts.utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


class DeploymentOrchestrator:
    """Main orchestrator for Fabric deployments"""

    def __init__(self, customer_id: str, environment: str, mode: str = "full"):
        """
        Initialize the deployment orchestrator

        Args:
            customer_id: Customer identifier
            environment: Target environment (dev, test, uat, prod)
            mode: Deployment mode (full, incremental, selective)
        """
        self.customer_id = customer_id
        self.environment = environment
        self.mode = mode
        self.config_path = Path(f"configurations/{customer_id}")
        self.config_processor = ConfigProcessor(self.config_path)
        self.validation = ValidationEngine()
        self.retry_handler = None  # Will be initialized after config is loaded
        self.credential = None  # Will be initialized with authentication
        self.temp_parameter_file = None  # Track temporary parameter file for cleanup
        self.deployment_report = {
            "customer": customer_id,
            "environment": environment,
            "mode": mode,
            "start_time": datetime.now().isoformat(),
            "items_succeeded": [],  # Individual items that deployed successfully
            "items_failed": [],  # Individual items that failed to deploy
            "item_types_attempted": [],  # Item types that were attempted
            "errors": [],
            "warnings": [],
        }

    def load_configuration(self) -> Dict:
        """Load and process customer configuration with Pydantic validation"""
        logger.info(f"Loading configuration for {self.customer_id}/{self.environment}")

        # Load main config
        config_file = self.config_path / "config.yml"
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")

        with open(config_file, "r") as f:
            config = yaml.safe_load(f)

        # Validate configuration with Pydantic
        try:
            validated_config = validate_config(config)
            logger.info(
                f"Configuration validated: customer={validated_config.metadata.customer_id}, "
                f"item_types={validated_config.core.item_types_in_scope}"
            )
        except Exception as e:
            logger.error(f"Configuration validation failed: {e}")
            raise ValueError(f"Invalid configuration: {e}")

        # Load environment-specific parameters
        param_file = self.config_path / "parameters" / f"{self.environment}.yml"
        if param_file.exists():
            with open(param_file, "r") as f:
                params = yaml.safe_load(f)
                config["parameters"] = params

        # Apply mode-specific overrides
        if self.mode == "selective":
            override_file = self.config_path / "overrides" / "selective-deploy.yml"
            if override_file.exists():
                with open(override_file, "r") as f:
                    overrides = yaml.safe_load(f)
                    config = self._merge_configs(config, overrides)

        # Initialize retry handler with config
        if self.retry_handler is None:
            self.retry_handler = create_retry_handler_from_config(config)
            logger.info(
                f"Retry handler initialized: max_attempts={self.retry_handler.max_attempts}, "
                f"backoff_seconds={self.retry_handler.backoff_seconds}"
            )

        return config

    def _merge_configs(self, base: Dict, override: Dict) -> Dict:
        """Merge override configuration with base configuration"""
        result = copy.deepcopy(base)
        for key, value in override.items():
            if (
                key in result
                and isinstance(result[key], dict)
                and isinstance(value, dict)
            ):
                result[key] = self._merge_configs(result[key], value)
            else:
                result[key] = value
        return result

    def validate_pre_deployment(self, config: Dict) -> bool:
        """Run pre-deployment validation checks (REQ-007)"""
        logger.info("Running pre-deployment validation")

        if self.mode == "selective" and config.get("validation", {}).get(
            "skip_for_selective"
        ):
            logger.info("Skipping validation for selective deployment")
            return True

        validation_checks = config.get("validation", {}).get("pre_deployment", [])

        for check in validation_checks:
            logger.info(f"Running validation: {check}")
            result = self.validation.run_check(check, config, self.environment)

            if not result["success"]:
                logger.error(f"Validation failed: {check} - {result['message']}")
                self.deployment_report["errors"].append(
                    {"check": check, "message": result["message"]}
                )
                return False

            if result.get("warnings"):
                self.deployment_report["warnings"].extend(result["warnings"])

        logger.info("Pre-deployment validation completed successfully")
        return True

    def _resolve_repository_path(self, repo_dir: str) -> str:
        """
        Resolve repository path for both local and Azure DevOps environments

        Args:
            repo_dir: Repository directory from config (may be relative)

        Returns:
            Absolute path to repository directory
        """
        # Check if running in Azure DevOps
        if os.environ.get("BUILD_SOURCESDIRECTORY") or os.environ.get(
            "SYSTEM_DEFAULTWORKINGDIRECTORY"
        ):
            # Azure DevOps environment
            base_path = os.environ.get("BUILD_SOURCESDIRECTORY", "/home/vsts/work/1/s")
            # Clean up the path - remove any relative prefixes
            repo_dir = re.sub(r"^\.\./", "", repo_dir)
            repo_dir = re.sub(r"^\./", "", repo_dir)
            full_path = os.path.join(base_path, repo_dir)
            logger.info(f"Azure DevOps environment detected, base path: {base_path}")
        else:
            # Local environment - resolve relative to config path
            if not os.path.isabs(repo_dir):
                full_path = str((self.config_path / repo_dir).resolve())
            else:
                full_path = repo_dir
            logger.info("Local environment detected")

        # Verify path exists
        if not os.path.exists(full_path):
            logger.warning(f"Repository path does not exist: {full_path}")

        return full_path

    def deploy_items(
        self, config: Dict, selective_items: Optional[List[str]] = None
    ) -> str:
        """
        Deploy items to target workspace (REQ-008, REQ-016)

        Returns:
            Deployment status: 'SUCCESS', 'PARTIAL_SUCCESS', or 'FAILED'
        """
        # logger.info(f"Starting deployment in {self.mode} mode")

        # # Get workspace ID and repository path
        workspace_id = config["core"]["workspace_id"][self.environment]
        repo_dir = config["core"]["repository_directory"][self.environment]

        # # Resolve repository path
        # repo_dir = self._resolve_repository_path(repo_dir)
        # logger.info(f"Repository directory: {repo_dir}")

        # Convert relative to absolute path if needed
        # if not os.path.isabs(repo_dir):
        #     repo_dir = str((self.config_path / repo_dir).resolve())

        #####################################3######
        print("\nBEFORE replacement \n" + str(Path(repo_dir).resolve()))
        repo_dir = re.sub(r"^(.*?/s/)[^/]+/[^/]+/", r"\1", repo_dir)
        print(repo_dir)

        # print("\nBEFORE : Expand Azure DevOps variables \n"+ str(Path(repo_dir).resolve()))

        # Expand Azure DevOps variables
        repo_dir = os.path.expandvars(repo_dir)

        print("\nAFTER : Expand Azure DevOps variables \n" + repo_dir)
        repo_dir = "/home/vsts/work/1/s/" + repo_dir
        # # Resolve to absolute path
        # repo_dir = str(Path(repo_dir).resolve())

        print("\nAFTER : Resolve to absolute path \n" + repo_dir)
        ##################################################

        # Get deployment sequence
        deployment_sequence = config.get("deployment", {}).get(
            "deployment_sequence", config["core"]["item_types_in_scope"]
        )

        # Prepare parameter file (generate dynamically or use existing)
        # NOTE: For dynamic $items resolution, we DEFER parameter file generation
        # until AFTER Lakehouse is deployed. This allows us to query the Fabric API
        # to get the actual Lakehouse ID before generating the parameter file.
        param_file = None
        has_dynamic_items_vars = False

        if "parameter_replacements" in config.get("core", {}):
            # Check if config uses $items variables that need API resolution
            replacements = config["core"]["parameter_replacements"]
            for fr in replacements.get("find_replace", []):
                replace_with = fr.get("replace_with", {})
                for env_val in replace_with.values():
                    if isinstance(env_val, str) and (
                        "$items." in env_val or "$workspace.$id" in env_val
                    ):
                        has_dynamic_items_vars = True
                        break
                if has_dynamic_items_vars:
                    break

            if has_dynamic_items_vars:
                # DEFER parameter file generation - will be done after Lakehouse deploys
                logger.info(
                    "Deferring parameter file generation - config uses $items variables that require API resolution"
                )
            else:
                # No dynamic variables - safe to generate now
                param_file = self._generate_parameter_file(config, self.environment)
                self.temp_parameter_file = param_file
                logger.info(f"Generated dynamic parameter file: {param_file}")
        elif "parameter" in config.get("core", {}):
            # Use fabric-cicd native parameter file from repository
            param_file_name = config["core"]["parameter"]
            param_file_path = Path(repo_dir) / param_file_name
            if param_file_path.exists():
                param_file = str(param_file_path.resolve())
                logger.info(f"Using static parameter file: {param_file}")
            else:
                logger.warning(
                    f"Parameter file specified in config but not found: {param_file_path}"
                )
        else:
            # Fall back to environment-specific parameter file
            param_file_path = (
                self.config_path / "parameters" / f"{self.environment}.yml"
            )
            if param_file_path.exists():
                with open(param_file_path, "r") as f:
                    params = yaml.safe_load(f)
                # Only use parameter file if it has find_replace entries
                if params and params.get("find_replace"):
                    param_file = str(param_file_path.resolve())
                else:
                    param_file = None
                    logger.info(
                        "No parameter replacements defined, deploying without parameter file"
                    )
            else:
                param_file = None
                logger.info(
                    "No parameter file found, deploying without parameter substitution"
                )

        has_failures = False
        items_resolved = False  # Track if we've resolved $items variables

        # Deploy items in sequence
        for item_type in deployment_sequence:
            logger.info(f"Deploying {item_type} items")

            # Track this item type
            self.deployment_report["item_types_attempted"].append(item_type)

            # Resolve $items variables before deploying items that reference other items
            # - Notebook: references Lakehouse (default_lakehouse, known_lakehouses)
            # - SemanticModel/Report: references Lakehouse (OneLake URL)
            # This happens AFTER Lakehouse is deployed so we can query the API for IDs
            if (
                item_type in ["Notebook", "SemanticModel", "Report"]
                and not items_resolved
            ):
                if "parameter_replacements" in config.get("core", {}):
                    logger.info(
                        f"Resolving $items variables via Fabric API before {item_type} deployment..."
                    )
                    config_resolved = copy.deepcopy(config)
                    config_resolved = self._resolve_items_variables(
                        config_resolved, workspace_id
                    )

                    # Generate (or regenerate) parameter file with resolved values
                    if param_file and os.path.exists(param_file):
                        os.remove(param_file)
                        logger.info(
                            "Removed old parameter file, regenerating with resolved $items..."
                        )
                    else:
                        logger.info(
                            "Generating parameter file with resolved $items (was deferred until now)..."
                        )

                    param_file = self._generate_parameter_file(
                        config_resolved, self.environment
                    )
                    self.temp_parameter_file = param_file
                    logger.info(f"Parameter file with resolved $items: {param_file}")
                    items_resolved = True

            try:
                if self._should_use_native_deployment(config):
                    # Use native fabric-cicd deployment with config
                    self._deploy_with_native_config(config, item_type)
                else:
                    # Use programmatic deployment
                    self._deploy_programmatically(
                        workspace_id,
                        repo_dir,
                        item_type,
                        param_file,
                        selective_items,
                        config,
                    )

                # Query workspace to get deployed items of this type
                items_deployed = self._get_deployed_items(workspace_id, item_type)
                for item_name in items_deployed:
                    self.deployment_report["items_succeeded"].append(
                        {
                            "name": f"{item_name}.{item_type}",
                            "type": item_type,
                            "timestamp": datetime.now().isoformat(),
                        }
                    )

            except Exception as e:
                error_msg = str(e)
                logger.error(f"Failed to deploy {item_type}: {error_msg}")
                has_failures = True

                # Add to failed items
                self.deployment_report["items_failed"].append(
                    {
                        "type": item_type,
                        "error": error_msg,
                        "timestamp": datetime.now().isoformat(),
                    }
                )

                self.deployment_report["errors"].append(
                    {"item_type": item_type, "error": error_msg}
                )

                if self.mode == "full":
                    return "FAILED"  # Stop on error in full mode
                # In incremental mode, continue with next item type

        # Determine final status
        if has_failures:
            return (
                "PARTIAL_SUCCESS"
                if self.deployment_report["items_succeeded"]
                else "FAILED"
            )
        return "SUCCESS"

    def _generate_parameter_file(self, config: Dict, environment: str) -> str:
        """
        Generate parameter.yml dynamically from config.yml
        Supports: find_replace, key_value_replace, spark_pool, gateway_binding

        Args:
            config: Configuration dictionary
            environment: Target environment

        Returns:
            Path to generated parameter file
        """
        replacements = config["core"]["parameter_replacements"]

        # Build fabric-cicd parameter.yml structure
        parameter_config = {}
        replacement_count = 0

        # ========== FIND/REPLACE SECTION ==========
        if "find_replace" in replacements:
            parameter_config["find_replace"] = []

            for replacement in replacements["find_replace"]:
                # Get template (may use {lakehouse_name} placeholder)
                template = replacement["replace_with"].get("template")

                # If template uses environment-specific values
                if (
                    isinstance(replacement["replace_with"], dict)
                    and "dev" in replacement["replace_with"]
                ):
                    replace_value = replacement["replace_with"]
                else:
                    # Use same template for all environments
                    replace_value = {
                        "dev": template,
                        "test": template,
                        "uat": template,
                        "prod": template,
                    }

                # Build find_replace entry
                find_replace_entry = {
                    "find_value": replacement["find_value"],
                    "replace_value": replace_value,
                    "is_regex": str(replacement.get("is_regex", False)).lower(),
                }

                # Add optional filters
                if "item_type" in replacement:
                    find_replace_entry["item_type"] = replacement["item_type"]
                if "item_name" in replacement:
                    find_replace_entry["item_name"] = replacement["item_name"]
                if "file_path" in replacement:
                    find_replace_entry["file_path"] = replacement["file_path"]

                parameter_config["find_replace"].append(find_replace_entry)
                replacement_count += 1

        # ========== KEY/VALUE REPLACE SECTION ==========
        if "key_value_replace" in replacements:
            parameter_config["key_value_replace"] = []

            for replacement in replacements["key_value_replace"]:
                key_value_entry = {
                    "find_key": replacement["find_key"],
                    "replace_value": replacement["replace_value"],
                }

                # Add optional filters
                if "item_type" in replacement:
                    key_value_entry["item_type"] = replacement["item_type"]
                if "item_name" in replacement:
                    key_value_entry["item_name"] = replacement["item_name"]
                if "file_path" in replacement:
                    key_value_entry["file_path"] = replacement["file_path"]

                parameter_config["key_value_replace"].append(key_value_entry)
                replacement_count += 1

        # ========== SPARK POOL SECTION ==========
        if "spark_pool" in replacements:
            parameter_config["spark_pool"] = []

            for replacement in replacements["spark_pool"]:
                spark_pool_entry = {
                    "instance_pool_id": replacement["instance_pool_id"],
                    "replace_value": replacement["replace_value"],
                }

                # Add optional filters
                if "item_name" in replacement:
                    spark_pool_entry["item_name"] = replacement["item_name"]

                parameter_config["spark_pool"].append(spark_pool_entry)
                replacement_count += 1

        # ========== GATEWAY BINDING SECTION ==========
        if "gateway_binding" in replacements:
            parameter_config["gateway_binding"] = []

            for replacement in replacements["gateway_binding"]:
                gateway_entry = {
                    "gateway_id": replacement["gateway_id"],
                    "dataset_name": replacement["dataset_name"],
                }

                parameter_config["gateway_binding"].append(gateway_entry)
                replacement_count += 1

        # Write to temporary file
        temp_file = tempfile.NamedTemporaryFile(
            mode="w",
            suffix=".yml",
            prefix="parameter_",
            delete=False,
            dir=self.config_path,
        )

        with temp_file as f:
            yaml.dump(parameter_config, f, default_flow_style=False, sort_keys=False)

        logger.info(
            f"Generated parameter file with {replacement_count} total replacements"
        )
        logger.info(
            f"  - find_replace: {len(parameter_config.get('find_replace', []))}"
        )
        logger.info(
            f"  - key_value_replace: {len(parameter_config.get('key_value_replace', []))}"
        )
        logger.info(f"  - spark_pool: {len(parameter_config.get('spark_pool', []))}")
        logger.info(
            f"  - gateway_binding: {len(parameter_config.get('gateway_binding', []))}"
        )

        return temp_file.name

    def _should_use_native_deployment(self, config: Dict) -> bool:
        """Check if we should use native fabric-cicd config deployment"""
        features = config.get("features", [])
        return (
            "enable_config_deploy" in features
            and "enable_experimental_features" in features
        )

    def _deploy_with_native_config(self, config: Dict, item_type: str):
        """Deploy using native fabric-cicd config deployment"""
        # Create temporary config with only the current item type
        temp_config = copy.deepcopy(config)
        temp_config["core"]["item_types_in_scope"] = [item_type]

        # fabric-cicd resolves relative repository_directory paths relative
        # to the config file it's given - but that's about to be a temp file
        # under /tmp, not our real configurations/<customer>/ directory, so
        # any relative path (the template default, e.g. "./versions/v1.0.0")
        # would resolve to a nonexistent path under /tmp instead of the real
        # one. Rewrite to absolute paths (resolved against self.config_path,
        # the actual config directory) before writing the temp config.
        repo_dirs = temp_config.get("core", {}).get("repository_directory", {})
        for env, repo_dir in repo_dirs.items():
            if repo_dir and not os.path.isabs(repo_dir):
                repo_dirs[env] = str((self.config_path / repo_dir).resolve())

        # Write temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
            yaml.dump(temp_config, f)
            temp_config_path = f.name

        try:
            # Deploy with retry logic (REQ-019)
            def deploy_operation():
                logger.info(f"Deploying {item_type} using config: {temp_config_path}")
                deploy_with_config(
                    config_file_path=temp_config_path,
                    environment=self.environment,
                    token_credential=self.credential,
                )

            self.retry_handler.execute_with_retry(
                deploy_operation, context=f"deploy_{item_type}_with_config"
            )

        finally:
            # Clean up temporary config
            if os.path.exists(temp_config_path):
                os.remove(temp_config_path)

    def _deploy_programmatically(
        self,
        workspace_id: str,
        repo_dir: str,
        item_type: str,
        param_file: str,
        selective_items: Optional[List[str]] = None,
        config: Optional[Dict] = None,
    ):
        """Deploy using programmatic fabric-cicd API"""

        # Create FabricWorkspace instance with our credential
        workspace_args = {
            "workspace_id": workspace_id,
            "repository_directory": repo_dir,
            "item_type_in_scope": [item_type],
            "environment": self.environment,
            "token_credential": self.credential,  # Pass our ClientSecretCredential
        }

        # Only add parameter_file_path if we have one
        if param_file:
            workspace_args["parameter_file_path"] = param_file

        # Add publish/unpublish configuration from config.yml
        if config:
            publish_config = config.get("publish", {})
            unpublish_config = config.get("unpublish", {})

            # Add exclude_regex for publish
            if "exclude_regex" in publish_config:
                exclude_pattern = publish_config["exclude_regex"]
                # Handle both single string and environment-specific dict
                if isinstance(exclude_pattern, dict):
                    exclude_pattern = exclude_pattern.get(self.environment)
                if exclude_pattern:
                    workspace_args["exclude_regex"] = exclude_pattern
                    logger.info(f"Applied exclude_regex: {exclude_pattern}")

            # Add folder_exclude_regex for publish
            if "folder_exclude_regex" in publish_config:
                folder_exclude_pattern = publish_config["folder_exclude_regex"].get(
                    self.environment
                )
                if folder_exclude_pattern:
                    workspace_args["folder_exclude_regex"] = folder_exclude_pattern

            # Add unpublish_exclude_regex for cleanup
            if "exclude_regex" in unpublish_config:
                workspace_args["unpublish_exclude_regex"] = unpublish_config[
                    "exclude_regex"
                ]

        workspace = FabricWorkspace(**workspace_args)

        # Apply selective items filter if provided
        if selective_items and self.mode == "selective":
            # Filter items based on selective list
            workspace.items_to_include = [
                item for item in selective_items if item.endswith(f".{item_type}")
            ]

        # Deploy with retry logic (REQ-019)
        def publish_operation():
            logger.info(f"Publishing {item_type} items to workspace {workspace_id}")
            publish_all_items(workspace)

        def cleanup_operation():
            logger.info(f"Cleaning up orphaned {item_type} items")
            unpublish_all_orphan_items(workspace)

        # Publish items with retry
        self.retry_handler.execute_with_retry(
            publish_operation, context=f"publish_{item_type}_items"
        )

        # Clean up orphans in full mode (if enabled in config)
        cleanup_orphans = (
            config.get("deployment", {})
            .get("modes", {})
            .get("full", {})
            .get("cleanup_orphans", True)
        )
        if self.mode == "full" and cleanup_orphans:
            self.retry_handler.execute_with_retry(
                cleanup_operation, context=f"cleanup_orphan_{item_type}_items"
            )

    def _get_deployed_items(self, workspace_id: str, item_type: str) -> List[str]:
        """
        Query workspace to get list of deployed items of a specific type

        Args:
            workspace_id: Target workspace ID
            item_type: Type of items to query (e.g., 'Notebook', 'Lakehouse')

        Returns:
            List of item display names
        """
        import requests

        try:
            # Use Fabric API to get items in workspace
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type={item_type}"
            headers = {
                "Authorization": f"Bearer {os.environ.get('FABRIC_BEARER_TOKEN')}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                items = response.json().get("value", [])
                return [item["displayName"] for item in items]
            else:
                logger.warning(f"Could not query items: {response.status_code}")
                return []

        except Exception as e:
            logger.warning(f"Error querying deployed items: {str(e)}")
            return []

    def _get_item_id_by_name(
        self, workspace_id: str, item_type: str, item_name: str
    ) -> Optional[str]:
        """
        Query Fabric API to get an item's ID by its display name and type.

        This is used to resolve $items.<ItemType>.<name>.$id variables dynamically
        before generating the parameter file.

        Args:
            workspace_id: Target workspace GUID
            item_type: Type of item (e.g., 'Lakehouse', 'Notebook', 'SemanticModel')
            item_name: Display name of the item

        Returns:
            Item GUID if found, None otherwise
        """
        import requests

        try:
            url = f"https://api.fabric.microsoft.com/v1/workspaces/{workspace_id}/items?type={item_type}"
            headers = {
                "Authorization": f"Bearer {os.environ.get('FABRIC_BEARER_TOKEN')}",
                "Content-Type": "application/json",
            }

            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                items = response.json().get("value", [])
                for item in items:
                    if item["displayName"] == item_name:
                        logger.info(f"Resolved {item_type}.{item_name} -> {item['id']}")
                        return item["id"]
                logger.warning(f"Item not found: {item_type}.{item_name}")
                return None
            else:
                logger.warning(
                    f"Could not query {item_type} items: {response.status_code}"
                )
                return None

        except Exception as e:
            logger.warning(f"Error querying item ID: {str(e)}")
            return None

    def _resolve_items_variables(self, config: Dict, workspace_id: str) -> Dict:
        """
        Resolve dynamic variables in parameter replacements:
        - $workspace.$id -> actual workspace GUID
        - $items.<ItemType>.<name>.$id -> actual item GUID (via Fabric API)

        This allows semantic models to reference lakehouses dynamically without
        requiring all item types to be in the same deployment scope.

        Args:
            config: Configuration dictionary (will be modified in place)
            workspace_id: Target workspace GUID

        Returns:
            Modified config with resolved variables
        """
        replacements = config.get("core", {}).get("parameter_replacements", {})
        find_replace = replacements.get("find_replace", [])

        # Pattern to match $items.<ItemType>.<name>.$id
        # Example: $items.Lakehouse.lh_uix_deploy.$id
        items_pattern = re.compile(r"\$items\.(\w+)\.([^.$]+)\.\$id")

        resolved_count = 0

        for replacement in find_replace:
            replace_with = replacement.get("replace_with", {})

            for env_key, value in replace_with.items():
                if not isinstance(value, str):
                    continue

                # First, resolve $workspace.$id with actual workspace ID
                if "$workspace.$id" in value:
                    replace_with[env_key] = replace_with[env_key].replace(
                        "$workspace.$id", workspace_id
                    )
                    resolved_count += 1
                    logger.info(
                        f"Resolved $workspace.$id -> {workspace_id} for environment '{env_key}'"
                    )

                # Then find all $items references in this value
                matches = items_pattern.findall(replace_with[env_key])

                for item_type, item_name in matches:
                    # Query API to get actual ID
                    item_id = self._get_item_id_by_name(
                        workspace_id, item_type, item_name
                    )

                    if item_id:
                        # Replace the variable with actual ID
                        old_var = f"$items.{item_type}.{item_name}.$id"
                        replace_with[env_key] = replace_with[env_key].replace(
                            old_var, item_id
                        )
                        resolved_count += 1
                        logger.info(
                            f"Resolved {old_var} -> {item_id} for environment '{env_key}'"
                        )
                    else:
                        logger.warning(
                            f"Could not resolve {item_type}.{item_name} - item may not exist yet"
                        )

        if resolved_count > 0:
            logger.info(f"Resolved {resolved_count} $items variable(s) via Fabric API")

        return config

    def deploy_phased(self, config: Dict, single_phase: Optional[str] = None) -> str:
        """
        Execute phased deployment with notebook execution between phases

        This supports:
        1. Deploy infrastructure (Lakehouse, Notebooks)
        2. Execute notebooks to create tables
        3. Deploy semantic layer (SemanticModel, Report) - only if notebook succeeds

        Args:
            config: Customer configuration
            single_phase: If provided, only run this specific phase (for pipeline steps)

        Returns:
            Deployment status: 'SUCCESS', 'PARTIAL_SUCCESS', or 'FAILED'
        """
        phases = config.get("deployment", {}).get("phases", [])

        if not phases:
            logger.info("No phases defined, using standard deployment sequence")
            return self.deploy_items(config)

        # If single_phase specified, filter to only that phase
        if single_phase:
            phase_names = [p.get("name") for p in phases]
            if single_phase not in phase_names:
                raise ValueError(
                    f"Phase '{single_phase}' not found. Available phases: {phase_names}"
                )
            phases = [p for p in phases if p.get("name") == single_phase]
            logger.info(f"Running single phase: {single_phase}")

        workspace_id = config["core"]["workspace_id"][self.environment]
        repo_dir = config["core"]["repository_directory"][self.environment]

        # Resolve repository path (works for both local and Azure DevOps)
        repo_dir = self._resolve_repository_path(repo_dir)
        logger.info(f"Repository directory: {repo_dir}")

        # Parameter file will be generated per-phase to support $items resolution
        # After Lakehouse is deployed, we can resolve $items.Lakehouse.<name>.$id
        param_file = None

        phase_results = {}
        has_failures = False

        for phase in phases:
            phase_name = phase.get("name", "unnamed")
            phase_type = phase.get("type", "deployment")

            logger.info(f"\n{'=' * 60}")
            logger.info(f"PHASE: {phase_name} - {phase.get('description', '')}")
            logger.info(f"{'=' * 60}")

            # Check dependencies (skip check when running single phase - assume deps satisfied)
            depends_on = phase.get("depends_on")
            if depends_on and not single_phase:
                if depends_on not in phase_results:
                    logger.warning(
                        f"Phase {phase_name} depends on {depends_on} which hasn't run"
                    )
                    phase_results[phase_name] = {"success": False, "skipped": True}
                    continue
                if not phase_results[depends_on].get("success", False):
                    logger.warning(
                        f"Skipping phase {phase_name} - dependency {depends_on} failed"
                    )
                    phase_results[phase_name] = {"success": False, "skipped": True}
                    self.deployment_report["warnings"].append(
                        {
                            "phase": phase_name,
                            "message": f"Skipped due to failed dependency: {depends_on}",
                        }
                    )
                    continue
            elif depends_on and single_phase:
                logger.info(
                    f"Single phase mode: assuming dependency '{depends_on}' is satisfied"
                )

            try:
                if phase_type == "notebook_execution":
                    # Execute notebooks
                    result = self._execute_phase_notebooks(phase, workspace_id)
                    phase_results[phase_name] = result

                    if result["success"]:
                        logger.info(f"Phase {phase_name} completed successfully")
                        self.deployment_report["items_succeeded"].append(
                            {
                                "name": f"Phase: {phase_name}",
                                "type": "notebook_execution",
                                "notebooks_executed": result.get(
                                    "notebooks_executed", []
                                ),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )
                    else:
                        has_failures = True
                        logger.error(f"Phase {phase_name} failed")
                        self.deployment_report["items_failed"].append(
                            {
                                "name": f"Phase: {phase_name}",
                                "type": "notebook_execution",
                                "error": result.get(
                                    "error", "Notebook execution failed"
                                ),
                                "timestamp": datetime.now().isoformat(),
                            }
                        )

                else:
                    # Standard deployment phase
                    item_types = phase.get("item_types", [])

                    # Check if this phase needs $items resolution
                    # Resolve $items variables if phase contains items that reference other items:
                    # - Notebook: references Lakehouse (default_lakehouse, known_lakehouses)
                    # - SemanticModel/Report: references Lakehouse (OneLake URL)
                    needs_items_resolution = phase.get("resolve_items", False) or any(
                        t in ["Notebook", "SemanticModel", "Report"] for t in item_types
                    )

                    # Check if config uses $items or $workspace variables
                    has_dynamic_vars = False
                    if "parameter_replacements" in config.get("core", {}):
                        replacements = config["core"]["parameter_replacements"]
                        for fr in replacements.get("find_replace", []):
                            replace_with = fr.get("replace_with", {})
                            for env_val in replace_with.values():
                                if isinstance(env_val, str) and (
                                    "$items." in env_val or "$workspace.$id" in env_val
                                ):
                                    has_dynamic_vars = True
                                    break
                            if has_dynamic_vars:
                                break

                    if (
                        needs_items_resolution
                        and "parameter_replacements" in config.get("core", {})
                    ):
                        logger.info("Resolving $items variables via Fabric API...")
                        # Make a deep copy to avoid modifying original config
                        config_resolved = copy.deepcopy(config)
                        config_resolved = self._resolve_items_variables(
                            config_resolved, workspace_id
                        )

                        # Generate parameter file with resolved values
                        if param_file and os.path.exists(param_file):
                            os.remove(param_file)  # Remove old param file
                        param_file = self._generate_parameter_file(
                            config_resolved, self.environment
                        )
                        self.temp_parameter_file = param_file
                        logger.info(
                            f"Generated parameter file with resolved $items: {param_file}"
                        )
                    elif not param_file and "parameter_replacements" in config.get(
                        "core", {}
                    ):
                        # First time generating parameter file
                        if has_dynamic_vars and not needs_items_resolution:
                            # Defer generation - will be done when deploying Notebook/SemanticModel/Report
                            logger.info(
                                "Deferring parameter file generation - $items variables need resolution after Lakehouse deploys"
                            )
                        else:
                            # No dynamic variables - safe to generate now
                            param_file = self._generate_parameter_file(
                                config, self.environment
                            )
                            self.temp_parameter_file = param_file
                            logger.info(
                                f"Generated dynamic parameter file: {param_file}"
                            )

                    for item_type in item_types:
                        logger.info(f"Deploying {item_type} items")
                        self.deployment_report["item_types_attempted"].append(item_type)

                        try:
                            self._deploy_programmatically(
                                workspace_id,
                                repo_dir,
                                item_type,
                                param_file,
                                None,
                                config,
                            )

                            items_deployed = self._get_deployed_items(
                                workspace_id, item_type
                            )
                            for item_name in items_deployed:
                                self.deployment_report["items_succeeded"].append(
                                    {
                                        "name": f"{item_name}.{item_type}",
                                        "type": item_type,
                                        "phase": phase_name,
                                        "timestamp": datetime.now().isoformat(),
                                    }
                                )

                        except Exception as e:
                            has_failures = True
                            logger.error(f"Failed to deploy {item_type}: {str(e)}")
                            self.deployment_report["items_failed"].append(
                                {
                                    "type": item_type,
                                    "phase": phase_name,
                                    "error": str(e),
                                    "timestamp": datetime.now().isoformat(),
                                }
                            )

                    phase_results[phase_name] = {"success": not has_failures}

            except Exception as e:
                has_failures = True
                logger.error(f"Phase {phase_name} failed with error: {str(e)}")
                phase_results[phase_name] = {"success": False, "error": str(e)}
                self.deployment_report["errors"].append(
                    {"phase": phase_name, "error": str(e)}
                )

        # Determine final status
        if has_failures:
            return (
                "PARTIAL_SUCCESS"
                if self.deployment_report["items_succeeded"]
                else "FAILED"
            )
        return "SUCCESS"

    def _execute_phase_notebooks(self, phase: Dict, workspace_id: str) -> Dict:
        """
        Execute notebooks as part of a deployment phase

        Args:
            phase: Phase configuration dict
            workspace_id: Target workspace GUID

        Returns:
            Dict with execution results
        """
        notebooks = phase.get("notebooks", [])
        lakehouse_name = phase.get("lakehouse")
        workspace_name = phase.get("workspace_name")  # Required for fabric-cli
        timeout = phase.get("timeout", 600)
        stop_on_failure = phase.get("stop_on_failure", True)

        if not notebooks:
            logger.warning("No notebooks specified in phase")
            return {"success": True, "notebooks_executed": []}

        if not workspace_name:
            logger.warning(
                "No workspace_name specified in phase config - fabric-cli requires workspace name, not ID"
            )

        logger.info(
            f"Executing {len(notebooks)} notebook(s) in workspace '{workspace_name}'"
        )

        result = execute_notebooks_after_deployment(
            workspace_id=workspace_id,
            workspace_name=workspace_name,
            notebooks=notebooks,
            bearer_token=os.environ.get("FABRIC_BEARER_TOKEN"),
            lakehouse_name=lakehouse_name,
            timeout=timeout,
            stop_on_failure=stop_on_failure,
        )

        return result

    def validate_post_deployment(self, config: Dict) -> bool:
        """Run post-deployment validation checks"""
        logger.info("Running post-deployment validation")

        validation_checks = config.get("validation", {}).get("post_deployment", [])

        for check in validation_checks:
            logger.info(f"Running validation: {check}")
            result = self.validation.run_check(check, config, self.environment)

            if not result["success"]:
                logger.error(f"Post-deployment validation failed: {check}")
                self.deployment_report["warnings"].append(
                    {"check": check, "message": result["message"]}
                )

        return True

    def generate_report(self):
        """Generate deployment report and print summary to console"""
        self.deployment_report["end_time"] = datetime.now().isoformat()

        # Calculate duration
        start = datetime.fromisoformat(self.deployment_report["start_time"])
        end = datetime.fromisoformat(self.deployment_report["end_time"])
        duration = (end - start).total_seconds()
        self.deployment_report["duration_seconds"] = duration

        # Status is already set in deploy_items(), but add warnings check
        if "status" not in self.deployment_report:
            if self.deployment_report["errors"]:
                self.deployment_report["status"] = "FAILED"
            elif self.deployment_report["warnings"]:
                self.deployment_report["status"] = "SUCCESS_WITH_WARNINGS"
            else:
                self.deployment_report["status"] = "SUCCESS"

        # Add warnings to status if needed
        if (
            self.deployment_report.get("status") == "SUCCESS"
            and self.deployment_report["warnings"]
        ):
            self.deployment_report["status"] = "SUCCESS_WITH_WARNINGS"
        elif (
            self.deployment_report.get("status") == "PARTIAL_SUCCESS"
            and self.deployment_report["warnings"]
        ):
            self.deployment_report["status"] = "PARTIAL_SUCCESS_WITH_WARNINGS"

        # Print console summary
        self._print_deployment_summary()

        # Save report
        report_file = f"deployment_report_{self.customer_id}_{self.environment}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(report_file, "w") as f:
            json.dump(self.deployment_report, f, indent=2)

        logger.info(f"Deployment report saved: {report_file}")
        return report_file

    def _print_deployment_summary(self):
        """Print detailed deployment summary to console"""
        status = self.deployment_report.get("status", "UNKNOWN")
        succeeded = self.deployment_report.get("items_succeeded", [])
        failed = self.deployment_report.get("items_failed", [])
        errors = self.deployment_report.get("errors", [])
        warnings = self.deployment_report.get("warnings", [])

        print("\n" + "=" * 80)
        print(" DEPLOYMENT SUMMARY")
        print("=" * 80)
        print(f"Customer:     {self.deployment_report['customer']}")
        print(f"Environment:  {self.deployment_report['environment']}")
        print(f"Mode:         {self.deployment_report['mode']}")
        print(f"Status:       {status}")
        print(f"Duration:     {self.deployment_report.get('duration_seconds', 0):.2f}s")
        print("=" * 80)

        # Items succeeded
        if succeeded:
            print(f"\n[OK] SUCCEEDED ({len(succeeded)} items):")
            for item in succeeded:
                print(f"   - {item['name']}")

        # Items failed
        if failed:
            print(f"\n[FAIL] FAILED ({len(failed)} items):")
            for item in failed:
                print(
                    f"   - {item.get('type', 'Unknown')}: {item.get('error', 'Unknown error')}"
                )

        # Errors
        if errors:
            print(f"\n[ERROR] ERRORS ({len(errors)}):")
            for error in errors:
                if isinstance(error, dict):
                    print(
                        f"   - {error.get('item_type', 'Unknown')}: {error.get('error', str(error))}"
                    )
                else:
                    print(f"   - {error}")

        # Warnings
        if warnings:
            print(f"\n[WARN] WARNINGS ({len(warnings)}):")
            for warning in warnings:
                if isinstance(warning, dict):
                    print(
                        f"   - {warning.get('check', 'Unknown')}: {warning.get('message', str(warning))}"
                    )
                else:
                    print(f"   - {warning}")

        print("\n" + "=" * 80)

        # Final status message
        if status == "SUCCESS":
            print("[OK] All items deployed successfully")
        elif status == "SUCCESS_WITH_WARNINGS":
            print("[OK] All items deployed successfully (with warnings)")
        elif status == "PARTIAL_SUCCESS":
            print(
                f"[WARN] Partial deployment: {len(succeeded)} succeeded, {len(failed)} failed"
            )
        elif status == "PARTIAL_SUCCESS_WITH_WARNINGS":
            print(
                f"[WARN] Partial deployment with warnings: {len(succeeded)} succeeded, {len(failed)} failed"
            )
        elif status == "FAILED":
            print("[FAIL] Deployment failed")

        print("=" * 80 + "\n")

    def run(
        self, selective_items: Optional[str] = None, single_phase: Optional[str] = None
    ):
        """Execute the deployment orchestration

        Args:
            selective_items: Comma-separated list of items for selective deployment
            single_phase: Run only this specific phase (for pipeline step-by-step execution)
        """
        try:
            logger.info(
                f"Starting deployment for {self.customer_id} to {self.environment}"
            )
            logger.info(f"Deployment mode: {self.mode}")
            if single_phase:
                logger.info(f"Running single phase: {single_phase}")

            # Authenticate with Fabric API first
            logger.info("Authenticating with Fabric API...")
            try:
                # Set up bearer token for validation API calls
                setup_fabric_auth()

                # Create ClientSecretCredential for fabric-cicd
                tenant_id = os.environ.get("TENANT_ID")
                client_id = os.environ.get("CLIENT_ID")
                client_secret = os.environ.get("CLIENT_SECRET")

                if not all([tenant_id, client_id, client_secret]):
                    raise ValueError(
                        "Missing authentication credentials in environment variables"
                    )

                self.credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                    authority="https://login.microsoftonline.com",
                )
                logger.info("Authentication successful")
            except Exception as e:
                logger.error(f"Authentication failed: {str(e)}")
                raise

            # Load configuration
            config = self.load_configuration()

            # Check deployment mode settings
            mode_config = (
                config.get("deployment", {}).get("modes", {}).get(self.mode, {})
            )
            if not mode_config.get("enabled", True):
                raise ValueError(
                    f"Deployment mode '{self.mode}' is not enabled for {self.customer_id}"
                )

            # Pre-deployment validation
            if not self.validate_pre_deployment(config):
                raise Exception("Pre-deployment validation failed")

            # Parse selective items if provided
            selective_items_list = None
            if selective_items:
                selective_items_list = [
                    item.strip() for item in selective_items.split(",")
                ]
                logger.info(f"Selective deployment for items: {selective_items_list}")

            # Deploy items - use phased deployment if phases are defined
            if config.get("deployment", {}).get("phases"):
                logger.info("Using phased deployment with notebook execution")
                deployment_status = self.deploy_phased(
                    config, single_phase=single_phase
                )
            else:
                if single_phase:
                    logger.warning(
                        f"--phase '{single_phase}' ignored: no phases defined in config"
                    )
                deployment_status = self.deploy_items(config, selective_items_list)

            # Store status in report
            self.deployment_report["status"] = deployment_status

            # Post-deployment validation
            self.validate_post_deployment(config)

            # Log appropriate message based on status
            if deployment_status == "SUCCESS":
                logger.info("Deployment completed successfully")
            elif deployment_status in [
                "PARTIAL_SUCCESS",
                "PARTIAL_SUCCESS_WITH_WARNINGS",
            ]:
                logger.warning(
                    f"Deployment completed with {deployment_status}: some items failed"
                )
            elif deployment_status == "SUCCESS_WITH_WARNINGS":
                logger.info("Deployment completed successfully with warnings")
            else:
                logger.error(f"Deployment failed with status: {deployment_status}")

        except Exception as e:
            logger.error(f"Deployment failed: {str(e)}")
            self.deployment_report["errors"].append(
                {"type": "fatal", "message": str(e)}
            )
            raise

        finally:
            # Cleanup temporary parameter file
            if self.temp_parameter_file and os.path.exists(self.temp_parameter_file):
                try:
                    os.remove(self.temp_parameter_file)
                    logger.info(
                        f"Cleaned up temporary parameter file: {self.temp_parameter_file}"
                    )
                except Exception as e:
                    logger.warning(f"Could not cleanup temporary parameter file: {e}")

            # Add retry statistics to report
            if self.retry_handler:
                self.deployment_report["retry_stats"] = self.retry_handler.get_stats()

            # Generate report
            self.generate_report()


def main():
    """Main entry point for deployment orchestrator"""
    parser = argparse.ArgumentParser(description="Fabric Deployment Orchestrator")
    parser.add_argument("--customer", required=True, help="Customer ID")
    parser.add_argument("--environment", required=True, help="Target environment")
    parser.add_argument(
        "--mode",
        default="full",
        choices=["full", "incremental", "selective"],
        help="Deployment mode",
    )
    parser.add_argument(
        "--phase",
        help="Run specific phase only (e.g., lakehouse, notebooks, table_creation, semantic_layer)",
    )
    parser.add_argument(
        "--selective-items",
        help="Comma-separated list of items for selective deployment",
    )
    parser.add_argument("--build-id", help="Build ID for tracking")
    parser.add_argument("--user", help="User who triggered deployment")

    args = parser.parse_args()

    # Load environment variables from .env file (for local development)
    from scripts.utils.load_env import load_env_file

    loaded_vars = load_env_file()
    if loaded_vars:
        logger.info(f"Loaded {len(loaded_vars)} environment variables from .env file")

    # Set build metadata
    if args.build_id:
        os.environ["BUILD_ID"] = args.build_id
    if args.user:
        os.environ["DEPLOYMENT_USER"] = args.user

    # Create and run orchestrator
    orchestrator = DeploymentOrchestrator(
        customer_id=args.customer, environment=args.environment, mode=args.mode
    )

    try:
        orchestrator.run(selective_items=args.selective_items, single_phase=args.phase)
        logger.info("Deployment completed successfully")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Deployment failed: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
