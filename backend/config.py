"""
backend/config.py - Backend Configuration Settings for DataVerse API
"""

import os
from typing import List, Set
from pathlib import Path
from dotenv import load_dotenv

from paths import (
    get_bundle_dir,
    get_user_data_dir,
    get_temp_session_dir,
    get_metadata_db_path
)

# Base Paths
BASE_DIR = get_bundle_dir()
USER_DATA_DIR = get_user_data_dir()
load_dotenv(BASE_DIR / ".env")
load_dotenv(USER_DATA_DIR / ".env")
TEMP_SESSION_DIR = get_temp_session_dir()
METADATA_DB_PATH = get_metadata_db_path()


# API Specifications
API_TITLE = "DataVerse Intelligence API"
API_DESCRIPTION = "Secure enterprise REST & WebSocket backend for Natural Language to SQL analytics"
API_VERSION = "1.0.0"
API_PREFIX = "/api/v1"

# Session & Security Parameters
SESSION_TTL_SECONDS: int = int(os.getenv("DATAVERSE_SESSION_TTL", "3600"))  # 1 hour
SESSION_CLEANUP_INTERVAL_SECONDS: int = int(os.getenv("DATAVERSE_CLEANUP_INTERVAL", "300"))  # 5 min
MAX_UPLOAD_SIZE_BYTES: int = int(os.getenv("DATAVERSE_MAX_UPLOAD_SIZE", str(25 * 1024 * 1024)))  # 25 MB

ALLOWED_EXTENSIONS: Set[str] = {
    ".csv",
    ".xlsx",
    ".xls",
    ".json",
    ".db",
    ".sqlite",
    ".sqlite3"
}

# CORS Configuration (Restricted by default)
DEFAULT_CORS_ORIGINS: List[str] = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    "http://localhost:5173",
    "http://127.0.0.1:5173"
]

CORS_ORIGINS: List[str] = [
    origin.strip()
    for origin in os.getenv("DATAVERSE_CORS_ORIGINS", "").split(",")
    if origin.strip()
] or DEFAULT_CORS_ORIGINS

# Rate Limiting
RATE_LIMIT_REQUESTS_PER_MINUTE: int = int(os.getenv("DATAVERSE_RATE_LIMIT_RPM", "120"))

# =============================================================================
# Bring Your Own Key (BYOK) Configuration
# =============================================================================

# Server-level environment key fallback:
# In production/public deployment, this defaults to False so public users cannot consume server keys.
# Set DATAVERSE_ALLOW_SERVER_ENV_KEY=true only for local developer testing.
ALLOW_SERVER_ENV_KEY: bool = os.getenv(
    "DATAVERSE_ALLOW_SERVER_ENV_KEY",
    "true" if os.getenv("PYTEST_CURRENT_TEST") else "false"
).lower() in ("true", "1", "yes")

SUPPORTED_AI_PROVIDERS = {
    "groq": {
        "id": "groq",
        "name": "Groq Cloud (Fast AI Inference)",
        "default_model": "openai/gpt-oss-20b",
        "key_prefix": "gsk_",
        "models": [
            {"id": "openai/gpt-oss-20b", "name": "GPT-OSS 20B (Recommended / Verified)"},
            {"id": "openai/gpt-oss-120b", "name": "GPT-OSS 120B (High Capacity)"},
            {"id": "qwen/qwen3.8-27b", "name": "Qwen 3.8 27B (Instruction / Versatile)"},
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B (Versatile - Account Permitted)"},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B (Instant - Account Permitted)"},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B (32k Context - Account Permitted)"}
        ],
        "endpoint": "https://api.groq.com/openai/v1/chat/completions",
        "docs_url": "https://console.groq.com/keys"
    }
}
