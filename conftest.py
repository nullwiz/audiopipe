import pytest
import os
from pathlib import Path


# Note: Main pytest options are defined in test/conftest.py
# This file only contains project-wide fixtures and setup


@pytest.fixture(scope="session", autouse=True)
def ensure_output_dir():
    """Ensure output directory exists"""
    os.makedirs("output", exist_ok=True)
    # Add a .gitkeep file if it doesn't exist
    gitkeep = Path("output/.gitkeep")
    if not gitkeep.exists():
        gitkeep.touch()
