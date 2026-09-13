#!/usr/bin/env python3
"""
Load environment variables from .env file
Useful for local development and testing
"""

import os
import sys
from pathlib import Path
from typing import Optional


def load_env_file(env_file: Optional[str] = None) -> dict:
    """
    Load environment variables from .env file

    Args:
        env_file: Path to .env file (defaults to .env in project root)

    Returns:
        Dictionary of environment variables loaded
    """
    # Find project root
    if env_file is None:
        project_root = Path(__file__).parent.parent.parent
        env_file = project_root / ".env"
    else:
        env_file = Path(env_file)

    if not env_file.exists():
        print(f"Warning: .env file not found at {env_file}")
        print("Create one by copying .env.example:")
        print(f"  cp {env_file.parent}/.env.example {env_file}")
        return {}

    loaded_vars = {}

    with open(env_file, "r") as f:
        for line_num, line in enumerate(f, 1):
            # Skip empty lines and comments
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse KEY=VALUE format
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()

                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]

                # Set environment variable
                os.environ[key] = value
                loaded_vars[key] = value
            else:
                print(f"Warning: Invalid format on line {line_num}: {line}")

    return loaded_vars


def check_required_vars(required_vars: list) -> bool:
    """
    Check if required environment variables are set

    Args:
        required_vars: List of required variable names

    Returns:
        True if all required variables are set
    """
    missing_vars = []

    for var in required_vars:
        if not os.environ.get(var):
            missing_vars.append(var)

    if missing_vars:
        print("❌ Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print("\nPlease set these in your .env file or environment")
        return False

    return True


def display_loaded_vars(loaded_vars: dict, mask_secrets: bool = True):
    """
    Display loaded environment variables

    Args:
        loaded_vars: Dictionary of loaded variables
        mask_secrets: Whether to mask sensitive values
    """
    if not loaded_vars:
        print("No environment variables loaded")
        return

    print(f"\n✓ Loaded {len(loaded_vars)} environment variables:")

    secret_keys = ["SECRET", "PASSWORD", "TOKEN", "KEY", "CREDENTIAL"]

    for key, value in sorted(loaded_vars.items()):
        # Check if this is a secret
        is_secret = mask_secrets and any(
            secret in key.upper() for secret in secret_keys
        )

        if is_secret and value:
            # Mask the value
            if len(value) > 8:
                masked_value = value[:4] + "*" * (len(value) - 8) + value[-4:]
            else:
                masked_value = "*" * len(value)
            print(f"  {key}: {masked_value}")
        else:
            print(f"  {key}: {value}")


def main():
    """Main entry point for loading environment variables"""
    import argparse

    parser = argparse.ArgumentParser(
        description="Load environment variables from .env file"
    )
    parser.add_argument("--file", help="Path to .env file", default=None)
    parser.add_argument(
        "--check", nargs="+", help="Check if required variables are set"
    )
    parser.add_argument("--show", action="store_true", help="Display loaded variables")
    parser.add_argument(
        "--no-mask", action="store_true", help="Do not mask secret values"
    )

    args = parser.parse_args()

    # Load environment variables
    print("Loading environment variables...")
    loaded_vars = load_env_file(args.file)

    if loaded_vars:
        print(f"✓ Successfully loaded {len(loaded_vars)} variables")

    # Display loaded variables if requested
    if args.show:
        display_loaded_vars(loaded_vars, mask_secrets=not args.no_mask)

    # Check required variables if requested
    if args.check:
        print("\nChecking required variables...")
        if check_required_vars(args.check):
            print("✓ All required variables are set")
            sys.exit(0)
        else:
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
