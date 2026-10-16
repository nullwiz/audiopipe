import sys
from pathlib import Path

import pytest


# Make sure the project root is in the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))


def pytest_addoption(parser):
    """Add options for integration and slow tests."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests",
    )
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )


def pytest_configure(config):
    """Register markers for our tests."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring integration with external systems",
    )
    config.addinivalue_line("markers", "slow: mark test as slow")


def pytest_collection_modifyitems(config, items):
    """Filter tests based on markers and command line options."""
    # Skip integration tests unless --integration is used
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="need --integration option to run")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)

    # Skip slow tests unless --runslow is used
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
