#!/usr/bin/env python3
"""
Notebook Executor for Fabric Deployment System
Executes notebooks after deployment using fabric-cli or Fabric REST API
"""

import os
import subprocess
import json
import time
import requests
from typing import Dict, Optional, List
from pathlib import Path

import sys

project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
sys.path.insert(0, project_root)

from scripts.utils.logger import setup_logger  # noqa: E402

logger = setup_logger(__name__)


class NotebookExecutor:
    """Execute notebooks after deployment using fabric-cli or REST API"""

    def __init__(self, workspace_id: str, bearer_token: Optional[str] = None):
        """
        Initialize notebook executor

        Args:
            workspace_id: Target workspace GUID
            bearer_token: Optional bearer token for REST API calls
        """
        self.workspace_id = workspace_id
        self.bearer_token = bearer_token or os.environ.get("FABRIC_BEARER_TOKEN")
        self.api_base = "https://api.fabric.microsoft.com/v1"
        self._fab_executable = None  # Cache for fab executable path

    def _find_fab_executable(self) -> str:
        """
        Find the fab executable path

        Checks:
        1. Same directory as current Python executable (venv)
        2. System PATH

        Returns:
            Path to fab executable
        """
        if self._fab_executable:
            return self._fab_executable

        import sys
        import shutil

        # Check venv Scripts directory (same as current Python)
        python_dir = Path(sys.executable).parent
        if os.name == "nt":  # Windows
            fab_venv = python_dir / "fab.exe"
        else:  # Linux/Mac
            fab_venv = python_dir / "fab"

        if fab_venv.exists():
            self._fab_executable = str(fab_venv)
            logger.info(f"Found fab in venv: {self._fab_executable}")
            return self._fab_executable

        # Fall back to system PATH
        fab_system = shutil.which("fab")
        if fab_system:
            self._fab_executable = fab_system
            logger.info(f"Found fab in PATH: {self._fab_executable}")
            return self._fab_executable

        # Default to 'fab' and let subprocess handle the error
        logger.warning("fab executable not found in venv or PATH, using 'fab'")
        return "fab"

    def _authenticate_fab_cli(self) -> bool:
        """
        Authenticate fabric-cli using Service Principal credentials from environment

        Returns:
            True if authentication successful
        """
        fab_cmd = self._find_fab_executable()

        # Get credentials from environment
        client_id = os.environ.get("CLIENT_ID")
        client_secret = os.environ.get("CLIENT_SECRET")
        tenant_id = os.environ.get("TENANT_ID")

        if not all([client_id, client_secret, tenant_id]):
            logger.error(
                "Missing SERVICE PRINCIPAL credentials (CLIENT_ID, CLIENT_SECRET, TENANT_ID)"
            )
            return False

        # Authenticate with fabric-cli
        auth_cmd = [
            fab_cmd,
            "auth",
            "login",
            "-u",
            client_id,
            "-p",
            client_secret,
            "--tenant",
            tenant_id,
        ]

        logger.info("Authenticating fabric-cli with Service Principal...")

        try:
            result = subprocess.run(
                auth_cmd, capture_output=True, text=True, timeout=60
            )

            if result.returncode == 0:
                logger.info("fabric-cli authentication successful")
                logger.info(f"Auth output: {result.stdout}")
                return True
            else:
                logger.error(
                    f"fabric-cli authentication failed (return code: {result.returncode})"
                )
                logger.error(f"Auth STDOUT: {result.stdout}")
                logger.error(f"Auth STDERR: {result.stderr}")
                return False

        except Exception as e:
            logger.error(f"Error during fabric-cli authentication: {str(e)}")
            return False

    def execute_notebook_cli(
        self,
        notebook_name: str,
        workspace_name: Optional[str] = None,
        parameters: Optional[Dict] = None,
        timeout: int = 600,
        lakehouse_config: Optional[Dict] = None,
    ) -> Dict:
        """
        Execute notebook using fabric-cli (synchronous, waits for completion)

        Args:
            notebook_name: Name of the notebook (without .Notebook extension)
            workspace_name: Workspace name (optional, uses ID if not provided)
            parameters: Optional parameters to pass to notebook
            timeout: Timeout in seconds (default 600 = 10 minutes)
            lakehouse_config: Optional lakehouse configuration dict

        Returns:
            Dict with success status and output
        """
        # Authenticate first
        if not self._authenticate_fab_cli():
            return {
                "success": False,
                "notebook": notebook_name,
                "error": "fabric-cli authentication failed",
            }

        # Build the item path - fabric-cli uses format: WorkspaceName.Workspace/NotebookName.Notebook
        if workspace_name:
            # Use workspace name with .Workspace suffix
            item_path = f"{workspace_name}.Workspace/{notebook_name}.Notebook"
        else:
            # Fall back to workspace ID (may not work with all fab commands)
            logger.warning(
                "No workspace_name provided, using workspace_id - this may not work with fabric-cli"
            )
            item_path = f"{self.workspace_id}/{notebook_name}.Notebook"

        # Find fab executable - check venv first, then system PATH
        fab_cmd = self._find_fab_executable()

        # Build command
        cmd = [fab_cmd, "job", "run", item_path, "--timeout", str(timeout)]

        # Add parameters if provided
        if parameters:
            param_str = ",".join([f"{k}:string={v}" for k, v in parameters.items()])
            cmd.extend(["-P", param_str])

        # Add lakehouse configuration if provided
        if lakehouse_config:
            config_json = json.dumps({"defaultLakehouse": lakehouse_config})
            cmd.extend(["-C", config_json])

        logger.info(f"Executing notebook: {notebook_name}")
        logger.info(f"Command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout + 60,  # Add buffer to subprocess timeout
            )

            success = result.returncode == 0

            if success:
                logger.info(f"Notebook {notebook_name} completed successfully")
                logger.info(f"Output: {result.stdout}")
            else:
                logger.error(
                    f"Notebook {notebook_name} failed with return code: {result.returncode}"
                )
                logger.error(f"STDOUT: {result.stdout}")
                logger.error(f"STDERR: {result.stderr}")

            return {
                "success": success,
                "notebook": notebook_name,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }

        except subprocess.TimeoutExpired:
            logger.error(f"Notebook {notebook_name} timed out after {timeout} seconds")
            return {
                "success": False,
                "notebook": notebook_name,
                "error": f"Timeout after {timeout} seconds",
            }
        except Exception as e:
            logger.error(f"Error executing notebook {notebook_name}: {str(e)}")
            return {"success": False, "notebook": notebook_name, "error": str(e)}

    def execute_notebook_api(
        self,
        notebook_id: str,
        parameters: Optional[Dict] = None,
        lakehouse_config: Optional[Dict] = None,
        timeout: int = 600,
        poll_interval: int = 10,
    ) -> Dict:
        """
        Execute notebook using Fabric REST API (with polling for completion)

        Args:
            notebook_id: Notebook item GUID
            parameters: Optional parameters to pass to notebook
            lakehouse_config: Optional lakehouse configuration
            timeout: Timeout in seconds
            poll_interval: Polling interval in seconds

        Returns:
            Dict with job status and details
        """
        if not self.bearer_token:
            raise ValueError("Bearer token required for REST API calls")

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

        # Start the job
        url = f"{self.api_base}/workspaces/{self.workspace_id}/items/{notebook_id}/jobs/instances?jobType=RunNotebook"

        body = {}
        if parameters or lakehouse_config:
            body["executionData"] = {}
            if parameters:
                body["executionData"]["parameters"] = parameters
            if lakehouse_config:
                body["executionData"]["configuration"] = {
                    "defaultLakehouse": lakehouse_config
                }

        logger.info(f"Starting notebook job via API: {notebook_id}")

        try:
            response = requests.post(url, headers=headers, json=body if body else None)

            if response.status_code not in [200, 202]:
                logger.error(
                    f"Failed to start notebook job: {response.status_code} - {response.text}"
                )
                return {
                    "success": False,
                    "notebook_id": notebook_id,
                    "error": f"API error: {response.status_code}",
                    "details": response.text,
                }

            # Get job instance ID from response
            job_data = response.json()
            job_id = job_data.get("id")

            if not job_id:
                # Check Location header for async operations
                location = response.headers.get("Location")
                if location:
                    job_id = location.split("/")[-1]

            logger.info(f"Job started with ID: {job_id}")

            # Poll for completion
            return self._poll_job_status(
                notebook_id, job_id, headers, timeout, poll_interval
            )

        except Exception as e:
            logger.error(f"Error executing notebook via API: {str(e)}")
            return {"success": False, "notebook_id": notebook_id, "error": str(e)}

    def _poll_job_status(
        self,
        notebook_id: str,
        job_id: str,
        headers: Dict,
        timeout: int,
        poll_interval: int,
    ) -> Dict:
        """Poll job status until completion or timeout"""
        url = f"{self.api_base}/workspaces/{self.workspace_id}/items/{notebook_id}/jobs/instances/{job_id}"

        start_time = time.time()
        last_status = None

        while time.time() - start_time < timeout:
            try:
                response = requests.get(url, headers=headers)

                if response.status_code != 200:
                    logger.warning(f"Status check failed: {response.status_code}")
                    time.sleep(poll_interval)
                    continue

                job_data = response.json()
                status = job_data.get("status")

                if status != last_status:
                    logger.info(f"Job status: {status}")
                    last_status = status

                if status == "Completed":
                    logger.info("Notebook job completed successfully")
                    return {
                        "success": True,
                        "notebook_id": notebook_id,
                        "job_id": job_id,
                        "status": status,
                        "details": job_data,
                    }
                elif status in ["Failed", "Cancelled"]:
                    failure_reason = job_data.get("failureReason", "Unknown")
                    logger.error(f"Notebook job {status}: {failure_reason}")
                    return {
                        "success": False,
                        "notebook_id": notebook_id,
                        "job_id": job_id,
                        "status": status,
                        "error": failure_reason,
                        "details": job_data,
                    }

                time.sleep(poll_interval)

            except Exception as e:
                logger.warning(f"Error polling job status: {str(e)}")
                time.sleep(poll_interval)

        logger.error(f"Job timed out after {timeout} seconds")
        return {
            "success": False,
            "notebook_id": notebook_id,
            "job_id": job_id,
            "status": "Timeout",
            "error": f"Job did not complete within {timeout} seconds",
        }

    def get_notebook_id(self, notebook_name: str) -> Optional[str]:
        """
        Get notebook ID by name from workspace

        Args:
            notebook_name: Display name of the notebook

        Returns:
            Notebook GUID or None if not found
        """
        if not self.bearer_token:
            # Try using fabric-cli
            return self._get_notebook_id_cli(notebook_name)

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/workspaces/{self.workspace_id}/items?type=Notebook"

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                items = response.json().get("value", [])
                for item in items:
                    if item["displayName"] == notebook_name:
                        return item["id"]

            logger.warning(f"Notebook {notebook_name} not found in workspace")
            return None

        except Exception as e:
            logger.error(f"Error getting notebook ID: {str(e)}")
            return None

    def _get_notebook_id_cli(self, notebook_name: str) -> Optional[str]:
        """Get notebook ID using fabric-cli"""
        try:
            cmd = [
                "fab",
                "api",
                "-X",
                "GET",
                f"/workspaces/{self.workspace_id}/items?type=Notebook",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                for item in data.get("value", []):
                    if item["displayName"] == notebook_name:
                        return item["id"]

            return None

        except Exception as e:
            logger.error(f"Error getting notebook ID via CLI: {str(e)}")
            return None

    def get_lakehouse_info(self, lakehouse_name: str) -> Optional[Dict]:
        """
        Get lakehouse ID and details by name

        Args:
            lakehouse_name: Display name of the lakehouse

        Returns:
            Dict with lakehouse info or None
        """
        if not self.bearer_token:
            return self._get_lakehouse_info_cli(lakehouse_name)

        headers = {
            "Authorization": f"Bearer {self.bearer_token}",
            "Content-Type": "application/json",
        }

        url = f"{self.api_base}/workspaces/{self.workspace_id}/items?type=Lakehouse"

        try:
            response = requests.get(url, headers=headers)

            if response.status_code == 200:
                items = response.json().get("value", [])
                for item in items:
                    if item["displayName"] == lakehouse_name:
                        return {
                            "id": item["id"],
                            "name": item["displayName"],
                            "type": item["type"],
                        }

            logger.warning(f"Lakehouse {lakehouse_name} not found in workspace")
            return None

        except Exception as e:
            logger.error(f"Error getting lakehouse info: {str(e)}")
            return None

    def _get_lakehouse_info_cli(self, lakehouse_name: str) -> Optional[Dict]:
        """Get lakehouse info using fabric-cli"""
        try:
            cmd = [
                "fab",
                "api",
                "-X",
                "GET",
                f"/workspaces/{self.workspace_id}/items?type=Lakehouse",
            ]

            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                data = json.loads(result.stdout)
                for item in data.get("value", []):
                    if item["displayName"] == lakehouse_name:
                        return {
                            "id": item["id"],
                            "name": item["displayName"],
                            "type": item["type"],
                        }

            return None

        except Exception as e:
            logger.error(f"Error getting lakehouse info via CLI: {str(e)}")
            return None


def execute_notebooks_after_deployment(
    workspace_id: str,
    notebooks: List[str],
    bearer_token: Optional[str] = None,
    lakehouse_name: Optional[str] = None,
    workspace_name: Optional[str] = None,
    timeout: int = 600,
    stop_on_failure: bool = True,
) -> Dict:
    """
    Execute multiple notebooks after deployment

    Args:
        workspace_id: Target workspace GUID
        notebooks: List of notebook names to execute
        bearer_token: Optional bearer token
        lakehouse_name: Optional lakehouse to configure
        workspace_name: Workspace name for fabric-cli (required for fab job run)
        timeout: Timeout per notebook
        stop_on_failure: Stop execution if a notebook fails

    Returns:
        Dict with execution results
    """
    executor = NotebookExecutor(workspace_id, bearer_token)

    results = {
        "success": True,
        "notebooks_executed": [],
        "notebooks_failed": [],
        "notebooks_skipped": [],
    }

    # Get lakehouse config if specified
    lakehouse_config = None
    if lakehouse_name:
        lakehouse_info = executor.get_lakehouse_info(lakehouse_name)
        if lakehouse_info:
            lakehouse_config = {
                "name": lakehouse_info["name"],
                "id": lakehouse_info["id"],
            }
            logger.info(f"Using lakehouse: {lakehouse_name} ({lakehouse_info['id']})")

    for notebook in notebooks:
        logger.info(f"Executing notebook: {notebook}")

        result = executor.execute_notebook_cli(
            notebook_name=notebook,
            workspace_name=workspace_name,
            timeout=timeout,
            lakehouse_config=lakehouse_config,
        )

        if result["success"]:
            results["notebooks_executed"].append(notebook)
        else:
            results["notebooks_failed"].append(
                {
                    "name": notebook,
                    "error": result.get("error", result.get("stderr", "Unknown error")),
                }
            )
            results["success"] = False

            if stop_on_failure:
                # Mark remaining as skipped
                remaining_idx = notebooks.index(notebook) + 1
                results["notebooks_skipped"] = notebooks[remaining_idx:]
                break

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Execute Fabric notebooks")
    parser.add_argument("--workspace-id", required=True, help="Workspace GUID")
    parser.add_argument("--notebook", required=True, help="Notebook name")
    parser.add_argument("--timeout", type=int, default=600, help="Timeout in seconds")
    parser.add_argument("--lakehouse", help="Lakehouse name for configuration")

    args = parser.parse_args()

    executor = NotebookExecutor(args.workspace_id)

    lakehouse_config = None
    if args.lakehouse:
        lakehouse_info = executor.get_lakehouse_info(args.lakehouse)
        if lakehouse_info:
            lakehouse_config = {
                "name": lakehouse_info["name"],
                "id": lakehouse_info["id"],
            }

    result = executor.execute_notebook_cli(
        notebook_name=args.notebook,
        timeout=args.timeout,
        lakehouse_config=lakehouse_config,
    )

    print(json.dumps(result, indent=2))
    exit(0 if result["success"] else 1)
