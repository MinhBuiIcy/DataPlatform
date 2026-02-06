"""
Pytest configuration for test suite

Markers:
- unit: Fast unit tests (no external dependencies)
- integration: Integration tests (requires Docker services)
- binance: Tests that fetch from Binance API (requires internet)
- slow: Slow-running tests (>10 seconds)
"""

import pytest


def pytest_configure(config):
    """Register custom markers"""
    config.addinivalue_line("markers", "unit: Fast unit tests (no dependencies)")
    config.addinivalue_line(
        "markers", "integration: Integration tests (requires Docker)"
    )
    config.addinivalue_line(
        "markers", "binance: Tests using Binance API (requires internet)"
    )
    config.addinivalue_line("markers", "slow: Slow tests (>10 seconds)")
