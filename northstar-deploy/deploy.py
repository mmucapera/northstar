#!/usr/bin/env python3
"""
Simple deployment wrapper that loads .env and runs deployment
"""

import os
import sys
from pathlib import Path

# Load .env file
env_file = Path(__file__).parent / ".env"
if env_file.exists():
    print("Loading environment variables from .env...")
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ[key] = value
    print("✓ Environment variables loaded\n")
else:
    print("Warning: .env file not found. Using environment variables from shell.\n")

# Add scripts to path
sys.path.insert(0, str(Path(__file__).parent / "scripts"))

# Now import and run
from deployment.deploy_orchestrator import main  # noqa: E402

if __name__ == "__main__":
    main()
