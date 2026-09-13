#!/usr/bin/env python3
"""
Service Principal Authentication for Fabric API
"""

import os
import sys
import requests
from datetime import datetime, timedelta
from typing import Optional, Dict


class FabricAuthentication:
    """Handle authentication with Microsoft Fabric using Service Principal"""

    def __init__(self):
        """Initialize authentication handler"""
        self.tenant_id = os.environ.get("TENANT_ID")
        self.client_id = os.environ.get("CLIENT_ID")
        self.client_secret = os.environ.get("CLIENT_SECRET")
        self.token = None
        self.token_expiry = None

        if not all([self.tenant_id, self.client_id, self.client_secret]):
            raise ValueError(
                "Missing authentication credentials. Please set TENANT_ID, CLIENT_ID, and CLIENT_SECRET environment variables"
            )

    def get_token(self, force_refresh: bool = False) -> str:
        """
        Get access token for Fabric API

        Args:
            force_refresh: Force token refresh even if current token is valid

        Returns:
            Access token string
        """
        if not force_refresh and self.token and self._is_token_valid():
            return self.token

        self._authenticate()
        return self.token

    def _authenticate(self):
        """Authenticate with Azure AD and get access token"""
        print(f"Authenticating with tenant: {self.tenant_id}")

        # Azure AD token endpoint
        token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        )

        # Token request data
        token_data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": "https://api.fabric.microsoft.com/.default",
        }

        try:
            response = requests.post(token_url, data=token_data)
            response.raise_for_status()

            token_response = response.json()
            self.token = token_response["access_token"]

            # Calculate token expiry (typically 1 hour, but we'll refresh after 50 minutes)
            expires_in = token_response.get("expires_in", 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in - 600)

            print("Authentication successful")

            # Set environment variable for fabric-cicd
            os.environ["FABRIC_BEARER_TOKEN"] = self.token

        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: {str(e)}")
            if hasattr(e, "response") and e.response is not None:
                print(f"Response: {e.response.text}")
            raise

    def _is_token_valid(self) -> bool:
        """Check if current token is still valid"""
        if not self.token or not self.token_expiry:
            return False

        return datetime.now() < self.token_expiry

    def get_headers(self) -> Dict[str, str]:
        """
        Get headers for API requests

        Returns:
            Dictionary with authorization headers
        """
        return {
            "Authorization": f"Bearer {self.get_token()}",
            "Content-Type": "application/json",
        }

    def test_connection(self) -> bool:
        """
        Test connection to Fabric API

        Returns:
            True if connection successful, False otherwise
        """
        try:
            headers = self.get_headers()
            response = requests.get(
                "https://api.fabric.microsoft.com/v1/workspaces", headers=headers
            )

            if response.status_code == 200:
                workspaces = response.json().get("value", [])
                print(
                    f"Connection successful. Found {len(workspaces)} accessible workspaces"
                )
                return True
            else:
                print(f"Connection test failed with status: {response.status_code}")
                return False

        except Exception as e:
            print(f"Connection test failed: {str(e)}")
            return False

    def list_workspaces(self) -> Optional[list]:
        """
        List all accessible workspaces

        Returns:
            List of workspace dictionaries or None if failed
        """
        try:
            headers = self.get_headers()
            response = requests.get(
                "https://api.fabric.microsoft.com/v1/workspaces", headers=headers
            )

            if response.status_code == 200:
                return response.json().get("value", [])
            else:
                print(f"Failed to list workspaces: {response.status_code}")
                return None

        except Exception as e:
            print(f"Error listing workspaces: {str(e)}")
            return None


def setup_fabric_auth():
    """
    Setup authentication for fabric-cicd library
    This function should be called before using fabric-cicd functions
    """
    auth = FabricAuthentication()
    token = auth.get_token()

    # Set the token for fabric-cicd to use
    os.environ["FABRIC_BEARER_TOKEN"] = token

    # Verify connection
    if not auth.test_connection():
        raise ConnectionError("Failed to connect to Fabric API")

    return auth


def main():
    """Main entry point for authentication testing"""
    print("Testing Fabric authentication...")

    try:
        auth = FabricAuthentication()

        # Test authentication
        token = auth.get_token()
        print(f"Token obtained: {token[:20]}...")

        # Test connection
        if auth.test_connection():
            print("✓ Authentication successful")

            # List workspaces
            workspaces = auth.list_workspaces()
            if workspaces:
                print(f"\nAccessible workspaces ({len(workspaces)}):")
                for ws in workspaces[:5]:  # Show first 5
                    print(
                        f"  - {ws.get('displayName', 'Unknown')} ({ws.get('id', 'Unknown')})"
                    )
                if len(workspaces) > 5:
                    print(f"  ... and {len(workspaces) - 5} more")

            sys.exit(0)
        else:
            print("✗ Authentication failed")
            sys.exit(1)

    except Exception as e:
        print(f"Authentication error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
