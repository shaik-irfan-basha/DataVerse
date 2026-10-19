"""
config.py - Configuration settings for DataVerse

This file contains all configuration parameters for the LLM client.
API keys should be stored in environment variables, NOT hardcoded here.
"""

# =============================================================================
# LLM PROVIDER CONFIGURATION
# =============================================================================

# Supported providers: "groq", "together", "openai"
# Default is "groq" (free tier available)
LLM_PROVIDER = "groq"

# Model names per provider
MODEL_NAMES = {
    "groq": "openai/gpt-oss-20b",      # Verified Groq model supporting json_mode for this key
    "together": "meta-llama/Llama-3-8b-chat-hf",  # Together AI model
    "openai": "gpt-3.5-turbo",            # OpenAI (paid)
}

# Phase 5: SQL Recovery
MAX_SQL_RETRIES = 2

# Environment variable names for API keys
API_KEY_ENV_VARS = {
    "groq": "GROQ_API_KEY",
    "together": "TOGETHER_API_KEY",
    "openai": "OPENAI_API_KEY",
}

# API endpoints
API_ENDPOINTS = {
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
}

# =============================================================================
# LLM GENERATION PARAMETERS
# =============================================================================

# Maximum tokens in the generated response
MAX_TOKENS = 256

# Temperature controls randomness (0 = deterministic, 1 = creative)
# Lower temperature is better for SQL generation (we want precise output)
TEMPERATURE = 0.1

# =============================================================================
# DATASET CONFIGURATION
# =============================================================================

# Supported file types for universal data loading
SUPPORTED_FILE_TYPES = [".csv", ".xlsx", ".xls", ".json", ".db", ".sqlite", ".sqlite3", ".pdf", ".docx", ".doc", ".pptx", ".ppt"]

# Number of sample rows to include in LLM prompt for context
MAX_SAMPLE_ROWS = 3

# =============================================================================
# Logging Configuration
# =============================================================================
from paths import get_log_file_path, get_history_db_path, get_metadata_db_path

LOG_LEVEL = "INFO"
LOG_FILE = str(get_log_file_path())

# Maximum rows to display in the results table
MAX_DISPLAY_ROWS = 500

# =============================================================================
# HISTORY & VISUALIZATION CONFIGURATION
# =============================================================================
HISTORY_DB_PATH = str(get_history_db_path())
METADATA_DB_PATH = str(get_metadata_db_path())
MAX_HISTORY_ENTRIES = 100
DEFAULT_CHART_DPI = 150

# =============================================================================
# LEGACY - WikiSQL (kept for backward compatibility)
# =============================================================================

DATASET_NAME = "wikisql"
DATASET_SPLIT = "train"
