"""
Configuration utility functions
"""

from pathlib import Path
from typing import Any

import yaml


def load_yaml(filepath: str) -> dict[str, Any]:
    """
    Load YAML file and return as dictionary

    Args:
        filepath: Path to YAML file (relative or absolute)

    Returns:
        Dictionary with YAML data

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If YAML is invalid

    Example:
        >>> config = load_yaml("config/providers/streaming.yaml")
        >>> print(config['kafka']['bootstrap_servers'])
        kafka:9092
    """
    path = Path(filepath)

    if not path.exists():
        raise FileNotFoundError(f"YAML file not found: {filepath}")

    with open(path) as f:
        return yaml.safe_load(f)


def load_yaml_safe(filepath: str) -> dict[str, Any]:
    """
    Load YAML file with fallback to empty dict if file doesn't exist

    Args:
        filepath: Path to YAML file

    Returns:
        Dictionary with YAML data, or empty dict if file not found

    Example:
        >>> config = load_yaml_safe("config/optional.yaml")
        >>> # Returns {} if file doesn't exist
    """
    try:
        return load_yaml(filepath)
    except (FileNotFoundError, yaml.YAMLError):
        return {}
