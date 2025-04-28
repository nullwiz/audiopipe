import pytest
import os
from pathlib import Path

def pytest_addoption(parser):
    parser.addoption(
        "--runslow", action="store_true", default=False, help="run slow tests"
    )
    parser.addoption(
        "--integration", action="store_true", default=False, help="run integration tests"
    )
    
def pytest_configure(config):
    config.addinivalue_line("markers", "slow: mark test as slow to run")
    config.addinivalue_line("markers", "integration: mark test as an integration test")
    
def pytest_collection_modifyitems(config, items):
    # Handle slow tests
    if not config.getoption("--runslow"):
        skip_slow = pytest.mark.skip(reason="need --runslow option to run")
        for item in items:
            if "slow" in item.keywords:
                item.add_marker(skip_slow)
                
    # Handle integration tests
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="need --integration option to run")
        for item in items:
            if "integration" in item.keywords and "test_integration" in item.parent.name:
                item.add_marker(skip_integration)

@pytest.fixture(scope="session", autouse=True)
def ensure_output_dir():
    """Ensure output directory exists"""
    os.makedirs("output", exist_ok=True)
    # Add a .gitkeep file if it doesn't exist
    gitkeep = Path("output/.gitkeep")
    if not gitkeep.exists():
        gitkeep.touch() 