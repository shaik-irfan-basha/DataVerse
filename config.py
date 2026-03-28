"""
config.py - Configuration settings for NL to SQL project

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
    "groq": "llama-3.1-8b-instant",      # Free, fast Groq model
    "together": "meta-llama/Llama-3-8b-chat-hf",  # Together AI model
    "openai": "gpt-3.5-turbo",            # OpenAI (paid)
}

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

# WikiSQL dataset configuration
# Note: Using standard 'wikisql' as WikiSQL_VALUE uses deprecated scripts
DATASET_NAME = "wikisql"
DATASET_SPLIT = "train"   # Using train split
