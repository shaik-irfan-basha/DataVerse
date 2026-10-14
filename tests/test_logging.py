import pytest
import logging
import os
import sys
from logger import setup_logging, SecretScrubbingFormatter
import config

@pytest.fixture(autouse=True)
def inject_mock_secret(monkeypatch):
    """Ensure a specific mock secret is always present for testing."""
    monkeypatch.setenv("MOCK_API_KEY", "gsk_SUPER_SECRET_KEY_12345")

def test_secret_scrubbing_formatter():
    formatter = SecretScrubbingFormatter('%(message)s')
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=0,
        msg="Connecting using API key: gsk_SUPER_SECRET_KEY_12345 to db.",
        args=(), exc_info=None
    )
    
    formatted = formatter.format(record)
    assert "gsk_SUPER_SECRET_KEY_12345" not in formatted
    assert "***REDACTED***" in formatted

def test_secret_scrubbing_traceback():
    formatter = SecretScrubbingFormatter('%(message)s')
    
    # Create an exception with the secret in the message
    exc_info = None
    try:
        raise ValueError("Failed with token gsk_SUPER_SECRET_KEY_12345 !")
    except ValueError:
        exc_info = sys.exc_info()
        
    record = logging.LogRecord(
        name="test", level=logging.ERROR, pathname="", lineno=0,
        msg="An error occurred",
        args=(), exc_info=exc_info
    )
    
    formatted = formatter.format(record)
    
    # Both the log message and the traceback should be scrubbed
    assert "gsk_SUPER_SECRET_KEY_12345" not in formatted
    assert "***REDACTED***" in formatted

def test_setup_logging_is_idempotent():
    # Force reset if it was already called by something else
    import logger as logger_module
    logger_module._logging_initialized = False
    
    root = logging.getLogger()
    root.handlers.clear()
    
    # Call once
    setup_logging()
    initial_handlers = len(root.handlers)
    assert initial_handlers == 2 # Console and File
    
    # Call twice
    setup_logging()
    assert len(root.handlers) == initial_handlers # Should not have duplicated
