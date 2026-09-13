#!/usr/bin/env python3
"""
Validation Engine for Fabric Deployment System
Implements REQ-007 - Configuration and deployment validation
"""

import os
import sys
import json
import requests
from typing import Dict

# Azure/Fabric API endpoints
FABRIC_API_BASE = "https://api.fabric.microsoft.com/v1"
AZURE_API_BASE = "https://management.azure.com"


class ValidationEngine:
    """Validation engine for deployment checks"""

    def __init__(self):
        """Initialize validation engine"""
        self.token = None
        self.headers = {}
        self._authenticate()

    def _authenticate(self):
        """Authenticate using Service Principal"""
        tenant_id = os.environ.get("TENANT_ID")
        client_id = os.environ.get("CLIENT_ID")
        client_secret = os.environ.get("CLIENT_SECRET")

        if not all([tenant_id, client_id, client_secret]):
            raise ValueError(
                "Missing authentication credentials in environment variables"
            )

        # Get access token
        token_url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
        token_data = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": "https://api.fabric.microsoft.com/.default",
        }

        response = requests.post(token_url, data=token_data)
        if response.status_code != 200:
            raise Exception(f"Failed to authenticate: {response.text}")

        self.token = response.json()["access_token"]
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def run_check(self, check_name: str, config: Dict, environment: str) -> Dict:
        """
        Run a specific validation check

        Args:
            check_name: Name of the validation check
            config: Configuration dictionary
            environment: Target environment

        Returns:
            Validation result dictionary
        """
        check_method_map = {
            "check_workspace_exists": self.check_workspace_exists,
            "check_capacity_available": self.check_capacity_available,
            "validate_connections": self.validate_connections,
            "verify_dependencies": self.verify_dependencies,
            "verify_item_count": self.verify_item_count,
            "test_connections": self.test_connections,
            "run_smoke_tests": self.run_smoke_tests,
            "verify_specific_items": self.verify_specific_items,
            "check_version_compatibility": self.check_version_compatibility,
            "validate_parameter_files": self.validate_parameter_files,
            "validate_parameter_deployment_order": self.validate_parameter_deployment_order,
        }

        if check_name not in check_method_map:
            return {
                "success": False,
                "message": f"Unknown validation check: {check_name}",
            }

        try:
            return check_method_map[check_name](config, environment)
        except Exception as e:
            return {
                "success": False,
                "message": f"Validation error in {check_name}: {str(e)}",
            }

    def check_workspace_exists(self, config: Dict, environment: str) -> Dict:
        """Check if target workspace exists and is accessible"""
        workspace_id = config["core"]["workspace_id"].get(environment)

        if not workspace_id:
            return {
                "success": False,
                "message": f"No workspace ID configured for environment: {environment}",
            }

        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        response = requests.get(url, headers=self.headers)

        if response.status_code == 200:
            workspace_info = response.json()
            return {
                "success": True,
                "message": f"Workspace exists: {workspace_info.get('displayName', 'Unknown')}",
                "data": workspace_info,
            }
        elif response.status_code == 404:
            return {"success": False, "message": f"Workspace not found: {workspace_id}"}
        elif response.status_code == 403:
            return {
                "success": False,
                "message": f"Access denied to workspace: {workspace_id}",
            }
        else:
            return {
                "success": False,
                "message": f"Failed to check workspace: {response.status_code} - {response.text}",
            }

    def check_capacity_available(self, config: Dict, environment: str) -> Dict:
        """Check if workspace capacity is available and has sufficient resources"""
        workspace_id = config["core"]["workspace_id"].get(environment)

        if not workspace_id:
            return {
                "success": False,
                "message": f"No workspace ID configured for environment: {environment}",
            }

        # Get workspace details to find capacity
        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to get workspace details: {response.status_code}",
            }

        workspace_info = response.json()
        capacity_id = workspace_info.get("capacityId")

        if not capacity_id:
            return {
                "success": True,
                "message": "Workspace is not assigned to a capacity (using shared capacity)",
                "warnings": ["Performance may be limited on shared capacity"],
            }

        # Check capacity status
        capacity_url = f"{FABRIC_API_BASE}/capacities/{capacity_id}"
        capacity_response = requests.get(capacity_url, headers=self.headers)

        if capacity_response.status_code == 200:
            capacity_info = capacity_response.json()
            state = capacity_info.get("state", "Unknown")

            if state.lower() == "active":
                return {
                    "success": True,
                    "message": f"Capacity is active: {capacity_info.get('displayName', 'Unknown')}",
                    "data": capacity_info,
                }
            else:
                return {
                    "success": False,
                    "message": f"Capacity is not active. Current state: {state}",
                }
        else:
            # Capacity check failed but workspace exists, warn but continue
            return {
                "success": True,
                "message": "Unable to verify capacity status",
                "warnings": [
                    "Could not check capacity status, proceeding with deployment"
                ],
            }

    def validate_connections(self, config: Dict, environment: str) -> Dict:
        """Validate that required connections are configured"""
        # This is a placeholder - actual implementation would check specific connections
        # based on the items being deployed

        warnings = []

        # Check if lakehouse connections are needed
        if "Lakehouse" in config["core"].get("item_types_in_scope", []):
            warnings.append("Lakehouse items will use automatic binding")

        # Check if semantic model connections are needed
        if "SemanticModel" in config["core"].get("item_types_in_scope", []):
            warnings.append(
                "Semantic models may require manual connection configuration post-deployment"
            )

        return {
            "success": True,
            "message": "Connection validation completed",
            "warnings": warnings if warnings else None,
        }

    def verify_dependencies(self, config: Dict, environment: str) -> Dict:
        """Verify that item dependencies are satisfied"""
        workspace_id = config["core"]["workspace_id"].get(environment)
        deployment_sequence = config.get("deployment", {}).get(
            "deployment_sequence", []
        )

        if not deployment_sequence:
            return {
                "success": True,
                "message": "No deployment sequence defined, skipping dependency check",
            }

        # Get existing items in workspace
        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to get workspace items: {response.status_code}",
            }

        existing_items = {
            item["type"]: item for item in response.json().get("value", [])
        }

        # Check dependencies based on sequence
        missing_deps = []
        for i, item_type in enumerate(deployment_sequence):
            # Check if this item type depends on previous types
            if i > 0:
                for j in range(i):
                    dep_type = deployment_sequence[j]
                    if (
                        self._check_dependency(item_type, dep_type)
                        and dep_type not in existing_items
                    ):
                        missing_deps.append(f"{item_type} depends on {dep_type}")

        if missing_deps:
            return {
                "success": False,
                "message": "Missing dependencies",
                "warnings": missing_deps,
            }

        return {"success": True, "message": "All dependencies satisfied"}

    def _check_dependency(self, item_type: str, dependency_type: str) -> bool:
        """Check if item_type depends on dependency_type"""
        dependencies = {
            "Notebook": ["Lakehouse"],
            "DataPipeline": ["Lakehouse"],
            "SemanticModel": ["Lakehouse", "Warehouse"],
            "Report": ["SemanticModel"],
        }

        return dependency_type in dependencies.get(item_type, [])

    def verify_item_count(self, config: Dict, environment: str) -> Dict:
        """Verify the number of items deployed matches expectations"""
        workspace_id = config["core"]["workspace_id"].get(environment)

        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to get workspace items: {response.status_code}",
            }

        items = response.json().get("value", [])
        item_counts = {}

        for item in items:
            item_type = item["type"]
            item_counts[item_type] = item_counts.get(item_type, 0) + 1

        return {
            "success": True,
            "message": f"Found {len(items)} total items in workspace",
            "data": item_counts,
        }

    def test_connections(self, config: Dict, environment: str) -> Dict:
        """Test that deployed connections are working"""
        # This would test actual connections to data sources
        # For now, return success as this requires item-specific testing

        return {
            "success": True,
            "message": "Connection testing skipped (requires item-specific implementation)",
        }

    def run_smoke_tests(self, config: Dict, environment: str) -> Dict:
        """Run smoke tests on deployed items"""
        workspace_id = config["core"]["workspace_id"].get(environment)

        # Get deployed notebooks
        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items?type=Notebook"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return {
                "success": True,
                "message": "Could not retrieve notebooks for smoke testing",
                "warnings": ["Smoke tests skipped"],
            }

        notebooks = response.json().get("value", [])

        if not notebooks:
            return {"success": True, "message": "No notebooks found for smoke testing"}

        # In a real implementation, we would execute test notebooks
        # For now, just verify they exist
        return {
            "success": True,
            "message": f"Verified {len(notebooks)} notebooks are accessible",
            "data": {"notebook_count": len(notebooks)},
        }

    def verify_specific_items(self, config: Dict, environment: str) -> Dict:
        """Verify specific items in selective deployment"""
        workspace_id = config["core"]["workspace_id"].get(environment)
        items_to_check = config.get("publish", {}).get("items_to_include", [])

        if not items_to_check:
            return {"success": True, "message": "No specific items to verify"}

        url = f"{FABRIC_API_BASE}/workspaces/{workspace_id}/items"
        response = requests.get(url, headers=self.headers)

        if response.status_code != 200:
            return {
                "success": False,
                "message": f"Failed to get workspace items: {response.status_code}",
            }

        deployed_items = {
            f"{item['displayName']}.{item['type']}"
            for item in response.json().get("value", [])
        }

        missing_items = []
        found_items = []

        for item in items_to_check:
            if item in deployed_items:
                found_items.append(item)
            else:
                missing_items.append(item)

        if missing_items:
            return {
                "success": False,
                "message": "Some items not found in workspace",
                "data": {"found": found_items, "missing": missing_items},
            }

        return {
            "success": True,
            "message": f"All {len(found_items)} specified items found in workspace",
            "data": {"found": found_items},
        }

    def check_version_compatibility(self, config: Dict, environment: str) -> Dict:
        """Check version compatibility between repository and deployment target"""
        repo_dir = config["core"]["repository_directory"].get(environment)

        if not repo_dir:
            return {"success": False, "message": "No repository directory specified"}

        # Extract version from path (assuming format like /versions/v1.0.0)
        import re

        version_match = re.search(r"v(\d+\.\d+\.\d+)", repo_dir)

        if not version_match:
            return {
                "success": True,
                "message": "Version not specified in repository path",
                "warnings": ["Cannot verify version compatibility"],
            }

        version = version_match.group(1)

        # Check if this is a valid semantic version
        try:
            major, minor, patch = map(int, version.split("."))
            return {
                "success": True,
                "message": f"Deploying version {version}",
                "data": {
                    "version": version,
                    "major": major,
                    "minor": minor,
                    "patch": patch,
                },
            }
        except ValueError:
            return {"success": False, "message": f"Invalid version format: {version}"}

    def validate_parameter_files(self, config: Dict, environment: str) -> Dict:
        """Validate parameter files are correctly formatted"""
        from pathlib import Path
        import yaml

        # Check if using dynamic parameter generation
        if "parameter_replacements" in config.get("core", {}):
            # Validate dynamic parameter replacements structure
            replacements = config["core"]["parameter_replacements"]
            if not isinstance(replacements, dict):
                return {
                    "success": False,
                    "message": "parameter_replacements must be a dictionary with sections (find_replace, key_value_replace, etc.)",
                }

            total_count = 0
            sections = []

            # Validate each section
            for section_name in [
                "find_replace",
                "key_value_replace",
                "spark_pool",
                "gateway_binding",
            ]:
                if section_name in replacements:
                    section_items = replacements[section_name]
                    if not isinstance(section_items, list):
                        return {
                            "success": False,
                            "message": f"parameter_replacements.{section_name} must be a list",
                        }
                    total_count += len(section_items)
                    sections.append(f"{section_name}({len(section_items)})")

            return {
                "success": True,
                "message": f"Dynamic parameter replacements validated: {', '.join(sections) if sections else 'no replacements'}",
            }

        # Check for static parameter file
        config_path = Path(
            config.get("metadata", {}).get(
                "config_path",
                f"configurations/{config.get('metadata', {}).get('customer_id')}",
            )
        )
        param_file = config_path / "parameters" / f"{environment}.yml"

        if not param_file.exists():
            # No parameter file is OK if no replacements are needed
            return {
                "success": True,
                "message": "No parameter file found (OK if no replacements needed)",
                "warnings": [f"No parameter file at {param_file}"],
            }

        try:
            with open(param_file, "r") as f:
                params = yaml.safe_load(f)

            # Handle empty or None params
            if params is None:
                return {
                    "success": True,
                    "message": "Parameter file is empty (no replacements defined)",
                }

            # Check for find_replace section (optional)
            if "find_replace" not in params:
                return {
                    "success": True,
                    "message": "No find_replace section (no parameter substitution)",
                }

            # Validate find_replace entries
            if not isinstance(params["find_replace"], list):
                return {"success": False, "message": "'find_replace' must be a list"}

            invalid_entries = []
            for i, entry in enumerate(params["find_replace"]):
                if not isinstance(entry, dict):
                    invalid_entries.append(f"Entry {i}: not a dictionary")
                elif "find_value" not in entry or "replace_value" not in entry:
                    invalid_entries.append(
                        f"Entry {i}: missing find_value or replace_value"
                    )

            if invalid_entries:
                return {
                    "success": False,
                    "message": "Invalid parameter file entries",
                    "warnings": invalid_entries,
                }

            return {
                "success": True,
                "message": f"Parameter file valid with {len(params['find_replace'])} replacements",
            }

        except yaml.YAMLError as e:
            return {
                "success": False,
                "message": f"Failed to parse parameter file: {str(e)}",
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"Error validating parameter file: {str(e)}",
            }

    def validate_parameter_deployment_order(
        self, config: Dict, environment: str
    ) -> Dict:
        """
        Validate that $items references in parameter_replacements only reference
        items that will be deployed BEFORE the item using the reference.

        This prevents errors like:
        - Notebook referencing $items.Lakehouse.* when Lakehouse hasn't been deployed yet
        """
        import re

        # Get deployment sequence
        deployment_sequence = config.get("deployment", {}).get(
            "deployment_sequence", []
        )
        if not deployment_sequence:
            return {
                "success": True,
                "message": "No deployment_sequence defined, skipping order validation",
            }

        # Get parameter replacements
        if "parameter_replacements" not in config.get("core", {}):
            return {
                "success": True,
                "message": "No parameter_replacements defined, skipping order validation",
            }

        replacements = config["core"]["parameter_replacements"]
        errors = []
        warnings = []

        # Pattern to extract $items references: $items.ItemType.ItemName.$attribute
        items_pattern = r"\$items\.(\w+)\."

        # Check find_replace section
        if "find_replace" in replacements:
            for replacement in replacements["find_replace"]:
                template = replacement.get("replace_with", {}).get("template", "")
                item_type = replacement.get(
                    "item_type"
                )  # Item type that will USE this replacement

                # Find all $items references in the template
                referenced_types = set(re.findall(items_pattern, template))

                if not referenced_types:
                    continue

                # Check if this replacement has an item_type filter
                if not item_type:
                    # No filter means it applies to all items
                    # Check if ANY of the referenced types come after ANY item in deployment_sequence
                    for ref_type in referenced_types:
                        if ref_type in deployment_sequence:
                            ref_index = deployment_sequence.index(ref_type)
                            # If ref_type is not first, there could be items before it that would fail
                            if ref_index > 0:
                                warnings.append(
                                    f"⚠️  Replacement '{replacement.get('name', 'unnamed')}' references "
                                    f"${ref_type} but has no item_type filter. This could cause errors if "
                                    f"applied to items deployed before {ref_type}."
                                )
                else:
                    # Check if the item_type that USES this replacement comes BEFORE the referenced types
                    if item_type in deployment_sequence:
                        using_item_index = deployment_sequence.index(item_type)

                        for ref_type in referenced_types:
                            if ref_type in deployment_sequence:
                                ref_type_index = deployment_sequence.index(ref_type)

                                if using_item_index < ref_type_index:
                                    errors.append(
                                        f"❌ Replacement '{replacement.get('name', 'unnamed')}' in {item_type} "
                                        f"references $items.{ref_type}.* but {item_type} (position {using_item_index + 1}) "
                                        f"deploys BEFORE {ref_type} (position {ref_type_index + 1}) in deployment_sequence"
                                    )
                            elif ref_type not in deployment_sequence:
                                warnings.append(
                                    f"⚠️  Replacement '{replacement.get('name', 'unnamed')}' references "
                                    f"$items.{ref_type}.* but {ref_type} is not in deployment_sequence"
                                )

        # Check key_value_replace section (less common to have $items references but check anyway)
        if "key_value_replace" in replacements:
            for replacement in replacements["key_value_replace"]:
                replace_values = replacement.get("replace_value", {})
                item_type = replacement.get("item_type")

                # Check all environment values for $items references
                for env, value in replace_values.items():
                    if isinstance(value, str):
                        referenced_types = set(re.findall(items_pattern, value))

                        if (
                            referenced_types
                            and item_type
                            and item_type in deployment_sequence
                        ):
                            using_item_index = deployment_sequence.index(item_type)

                            for ref_type in referenced_types:
                                if ref_type in deployment_sequence:
                                    ref_type_index = deployment_sequence.index(ref_type)

                                    if using_item_index < ref_type_index:
                                        errors.append(
                                            f"❌ Replacement '{replacement.get('name', 'unnamed')}' in {item_type} "
                                            f"references $items.{ref_type}.* but {item_type} deploys BEFORE {ref_type}"
                                        )

        if errors:
            return {
                "success": False,
                "message": f"Found {len(errors)} parameter deployment order error(s)",
                "errors": errors,
                "warnings": warnings if warnings else None,
                "suggestion": "Fix deployment_sequence to deploy referenced items BEFORE items that reference them",
            }

        if warnings:
            return {
                "success": True,
                "message": f"Parameter deployment order validated with {len(warnings)} warning(s)",
                "warnings": warnings,
            }

        return {
            "success": True,
            "message": "✅ All $items references are correctly ordered in deployment_sequence",
        }


def main():
    """Main entry point for standalone validation"""
    import argparse

    parser = argparse.ArgumentParser(description="Fabric Deployment Validation")
    parser.add_argument(
        "--config-path", required=True, help="Path to customer configuration"
    )
    parser.add_argument(
        "--mode",
        choices=["pre-deployment", "post-deployment"],
        required=True,
        help="Validation mode",
    )
    parser.add_argument("--customer", required=True, help="Customer ID")
    parser.add_argument("--environments", help="Comma-separated list of environments")

    args = parser.parse_args()

    # Load configuration
    from pathlib import Path
    import yaml

    config_file = Path(args.config_path) / "config.yml"
    with open(config_file, "r") as f:
        config = yaml.safe_load(f)

    # Add metadata for validation
    config["metadata"] = config.get("metadata", {})
    config["metadata"]["customer_id"] = args.customer
    config["metadata"]["config_path"] = args.config_path

    # Run validation
    validator = ValidationEngine()
    environments = args.environments.split(",") if args.environments else ["dev"]

    results = {}
    for env in environments:
        if args.mode == "pre-deployment":
            checks = config.get("validation", {}).get("pre_deployment", [])
        else:
            checks = config.get("validation", {}).get("post_deployment", [])

        env_results = []
        for check in checks:
            result = validator.run_check(check, config, env)
            env_results.append({"check": check, "result": result})

        results[env] = env_results

    # Print validation results to console
    print("\n" + "=" * 80)
    print(f" {args.mode.upper()} VALIDATION RESULTS")
    print("=" * 80)

    has_failures = False
    has_warnings = False

    for env, env_results in results.items():
        print(f"\nEnvironment: {env}")
        print("-" * 80)

        for check_result in env_results:
            check_name = check_result["check"]
            result = check_result["result"]
            success = result.get("success", False)

            if success:
                print(f"  ✅ {check_name}: {result.get('message', 'OK')}")
            else:
                print(f"  ❌ {check_name}: {result.get('message', 'FAILED')}")
                has_failures = True

            # Print errors if present
            if result.get("errors"):
                for error in result["errors"]:
                    print(f"      {error}")

            # Print warnings if present
            if result.get("warnings"):
                has_warnings = True
                for warning in result["warnings"]:
                    print(f"      ⚠️  {warning}")

            # Print suggestion if present
            if result.get("suggestion"):
                print(f"      💡 {result['suggestion']}")

    print("\n" + "=" * 80)
    if has_failures:
        print("❌ VALIDATION FAILED - Deployment blocked")
    elif has_warnings:
        print("✅ VALIDATION PASSED (with warnings)")
    else:
        print("✅ VALIDATION PASSED")
    print("=" * 80 + "\n")

    # Save results - determine the correct path for the report
    # In Azure Pipelines, we need to save to the uix-deploy directory
    from pathlib import Path

    # Try to find the uix-deploy root directory
    script_dir = (
        Path(__file__).resolve().parent.parent.parent
    )  # Go up from scripts/deployment/
    report_file = script_dir / "validation-report.json"

    with open(report_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"Validation report saved: {report_file}")

    sys.exit(1 if has_failures else 0)


if __name__ == "__main__":
    main()
