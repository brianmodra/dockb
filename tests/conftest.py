# tests/conftest.py
import logging

import pytest


@pytest.fixture(scope="session", autouse=True)
def set_test_logging():
    # Force the root logger to DEBUG level for the entire test session
    logging.getLogger().setLevel(logging.DEBUG)

    # Optional: If you use a specific named logger in your app, change it here:
    # logging.getLogger("your_app_name").setLevel(logging.DEBUG)
