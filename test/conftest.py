import os
import sys
import warnings
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

    # Add option to set HF token
    parser.addoption(
        "--hf-token",
        action="store",
        help="Hugging Face token for API access during tests",
    )


def pytest_configure(config):
    """Register markers for our tests."""
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring integration with external systems",
    )
    config.addinivalue_line("markers", "slow: mark test as slow")
    config.addinivalue_line(
        "markers", "requires_token: mark test as requiring Hugging Face token"
    )

    # Set Hugging Face token if provided
    hf_token = config.getoption("--hf-token")
    if hf_token:
        os.environ["HUGGING_FACE_TOKEN"] = hf_token
        print("Using provided Hugging Face token for tests")
    elif os.environ.get("HUGGING_FACE_TOKEN"):
        print("Using Hugging Face token from environment for tests")
    else:
        warnings.warn(
            "No Hugging Face token available. Some tests may be skipped. "
            "For full testing, provide a token with --hf-token or set HUGGING_FACE_TOKEN environment variable.",
            stacklevel=2,
        )


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

    # Skip token-requiring tests if no token is provided
    if not os.environ.get("HUGGING_FACE_TOKEN"):
        skip_token = pytest.mark.skip(reason="need Hugging Face token to run")
        for item in items:
            if "requires_token" in item.keywords:
                item.add_marker(skip_token)


@pytest.fixture
def has_hf_token():
    """Fixture to check if Hugging Face token is available."""
    token = os.environ.get("HUGGING_FACE_TOKEN")
    return token is not None
