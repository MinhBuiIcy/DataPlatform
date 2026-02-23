"""
Pytest configuration for integration tests

This conftest patches YAML loading at MODULE LEVEL to replace Docker hostnames
with localhost for tests running on the host machine.
"""

import os
from unittest import mock

# ============================================================================
# CRITICAL: Patch YAML loading at MODULE LEVEL
# This runs BEFORE any test modules are imported by pytest
# ============================================================================
# Import original function
from core.utils.config import load_yaml_safe as _original_load_yaml_safe


def _patched_load_yaml_safe(path):
    """Load YAML and replace Docker hostnames with localhost for integration tests"""
    config = _original_load_yaml_safe(path)

    # Patch databases.yaml - replace Docker hostnames/ports with localhost values
    if "databases.yaml" in path:
        if "clickhouse" in config:
            config["clickhouse"]["host"] = "localhost"
        if "redis" in config:
            config["redis"]["host"] = "localhost"
        if "postgres" in config:
            config["postgres"]["host"] = "localhost"
            config["postgres"]["port"] = 5433  # Docker exposes 5433→5432 on host

    return config


# Apply global patch
mock.patch("core.utils.config.load_yaml_safe", side_effect=_patched_load_yaml_safe).start()

# Also set environment variables as backup
os.environ["CLICKHOUSE_HOST"] = "localhost"
os.environ["REDIS_HOST"] = "localhost"
os.environ["POSTGRES_HOST"] = "localhost"

# Reset Settings singleton to force reload with patched YAML loader
from config.settings import Settings

if hasattr(Settings, "_yaml_loaded"):
    delattr(Settings, "_yaml_loaded")

# ============================================================================
# Now all test files will use localhost when they load Settings/YAML configs
# ============================================================================
