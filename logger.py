import logging
from logging.handlers import RotatingFileHandler
import os
import config

import re

_logging_initialized = False
_DYNAMIC_SECRETS = set()

def register_secret_to_scrub(secret: str):
    """Register an in-memory session key or secret to redact in logs."""
    if secret and len(secret) > 5:
        _DYNAMIC_SECRETS.add(secret)

class SecretScrubbingFormatter(logging.Formatter):
    """
    A custom formatter that redacts configured API keys and secrets from the final
    formatted log string, including from exception tracebacks.
    """
    def __init__(self, fmt=None, datefmt=None, style='%', validate=True):
        super().__init__(fmt, datefmt, style, validate)
        self._secrets = []
        self._refresh_secrets()

    def _refresh_secrets(self):
        """Dynamically fetch secrets from environment to scrub."""
        self._secrets = list(_DYNAMIC_SECRETS)
        # Check standard known API key environment variables
        keys_to_check = ["GROQ_API_KEY", "TOGETHER_API_KEY", "OPENAI_API_KEY", "MOCK_API_KEY"]
        for k in keys_to_check:
            val = os.getenv(k)
            if val and len(val) > 5: # Basic sanity check to avoid matching short common strings
                if val not in self._secrets:
                    self._secrets.append(val)

    def format(self, record):
        # Let the standard formatter do its work, which includes appending exception tracebacks
        formatted = super().format(record)

        # Ensure we have the latest secrets (in case dotenv loaded late)
        self._refresh_secrets()

        # Replace exact matches of secrets with redaction string
        for secret in self._secrets:
            formatted = formatted.replace(secret, "***REDACTED***")

        # Pattern-based redaction for Groq keys (gsk_...)
        formatted = re.sub(r'gsk_[A-Za-z0-9_-]{12,}', '***REDACTED***', formatted)

        return formatted


def setup_logging():
    """
    Idempotent function to configure root logger.
    Creates the necessary logs directory and attaches handlers.
    """
    global _logging_initialized
    if _logging_initialized:
        return

    # Ensure log directory exists
    log_dir = os.path.dirname(config.LOG_FILE)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    root_logger = logging.getLogger()

    # Safely parse log level
    log_level_str = getattr(config, "LOG_LEVEL", "INFO").upper()
    level = getattr(logging, log_level_str, logging.INFO)
    root_logger.setLevel(level)

    # Clear any existing handlers to prevent duplicates during testing or reloads
    if root_logger.handlers:
        root_logger.handlers.clear()

    formatter = SecretScrubbingFormatter('%(asctime)s | %(name)-15s | %(levelname)-8s | %(message)s')

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    # Rotating File Handler (5MB max size, keep 3 backups)
    file_handler = RotatingFileHandler(config.LOG_FILE, maxBytes=5*1024*1024, backupCount=3)
    file_handler.setFormatter(formatter)

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    _logging_initialized = True
