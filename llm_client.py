"""
llm_client.py - LLM API client for SQL generation

This module handles communication with various LLM providers (Groq, Together, OpenAI)
to generate SQL queries from natural language prompts.

Supported providers:
- Groq (FREE tier available - recommended)
- Together AI (FREE tier available)
- OpenAI (paid)
"""

import os
import requests
import config
import logging
from typing import Optional, Dict

logger = logging.getLogger("dataverse.llm")


class LLMClient:
    """
    A client for interacting with LLM APIs.
    
    Supports multiple providers with a unified interface.
    API keys are read from environment variables for security.
    """
    
    def __init__(self, provider: str = None, model: str = None, api_key: str = None):
        """
        Initialize the LLM client.
        
        Args:
            provider: LLM provider name ("groq", "together", "openai")
                     If None, uses the default from config.py
            model: Specific model name to override default
            api_key: Explicit API key if not loading from env
        """
        self.provider = provider or config.LLM_PROVIDER
        self.model = model or config.MODEL_NAMES.get(self.provider)
        self.endpoint = config.API_ENDPOINTS.get(self.provider)
        self.api_key = api_key or self._get_api_key()
        self.last_usage = {}
        
        if not self.model:
            raise ValueError(f"Unknown provider: {self.provider}")
    
    def _get_api_key(self) -> str:
        """
        Get the API key from environment variables.
        
        Returns:
            API key string
        
        Raises:
            ValueError if API key is not set
        """
        env_var = config.API_KEY_ENV_VARS.get(self.provider)
        api_key = os.getenv(env_var)
        
        if not api_key:
            raise ValueError(
                f"API key not found! Please set the {env_var} environment variable.\n"
                f"Example: set {env_var}=your_api_key_here"
            )
        
        return api_key
    
    def generate_sql(self, prompt: str) -> str:
        """
        Send a prompt to the LLM and get the generated SQL.
        
        Args:
            prompt: The formatted prompt containing question and schema
        
        Returns:
            Generated SQL query string
        """
        # Prepare the request headers
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        # Prepare the request body (OpenAI-compatible format)
        # Most providers (Groq, Together) use this same format
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are an expert SQL generator. Only output valid SQL queries, nothing else."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "max_tokens": config.MAX_TOKENS,
            "temperature": config.TEMPERATURE,
        }
        
        try:
            # Make the API request
            import time
            start_time = time.time()
            logger.info(f"Sending SQL request to {self.provider} ({self.model}). Prompt length: {len(prompt)} chars.")
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=30  # 30 second timeout
            )
            
            # Check for errors
            response.raise_for_status()
            
            # Parse the response
            result = response.json()
            self.last_usage = result.get("usage", {})
            
            # Extract the generated text
            sql = result["choices"][0]["message"]["content"].strip()
            
            duration = round(time.time() - start_time, 2)
            logger.info(f"Received SQL response from {self.provider}. Duration: {duration}s. Payload length: {len(sql)} chars.")
            
            return sql
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling LLM API (SQL mode): {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"Response: {e.response.text}")
            raise

    def generate_json(self, prompt: str) -> dict:
        """
        Send a prompt to the LLM and get a structured JSON response.
        Uses response_format = {"type": "json_object"}.
        """
        import json
        import time
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        
        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a helpful data analyst. Always output valid JSON."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "response_format": {"type": "json_object"},
            "max_tokens": config.MAX_TOKENS * 2,  # Increase tokens for JSON payload
            "temperature": config.TEMPERATURE,
        }
        
        try:
            logger.info(f"Sending JSON request to {self.provider} ({self.model})...")
            response = requests.post(
                self.endpoint,
                headers=headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            
            result = response.json()
            self.last_usage = result.get("usage", {})
            content = result["choices"][0]["message"]["content"].strip()
            
            # Try to parse the JSON returned
            return json.loads(content)
            
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON: {e}\nContent was: {content}")
            raise ValueError("The LLM did not return a valid JSON object.")
        except requests.exceptions.RequestException as e:
            logger.error(f"Error calling LLM API: {e}")
            if hasattr(e, 'response') and e.response is not None:
                logger.error(f"{self.provider} HTTP Status: {e.response.status_code}")
                logger.error(f"{self.provider} Response Body: {e.response.text}")
            raise


def generate_sql_from_prompt(prompt: str, provider: str = None) -> str:
    """
    Convenience function to generate SQL without creating a client instance.
    
    Args:
        prompt: The formatted prompt
        provider: Optional provider override
    
    Returns:
        Generated SQL query string
    """
    client = LLMClient(provider=provider)
    return client.generate_sql(prompt)


# =============================================================================
# MAIN - For testing this module independently
# =============================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("Testing llm_client.py")
    print("=" * 60)
    
    # Test prompt
    test_prompt = """You are an expert SQL query generator.

Table columns: name, age, city

Question: What are the names of people older than 25?

SQL QUERY:"""
    
    try:
        client = LLMClient()
        print(f"\nProvider: {client.provider}")
        print(f"Model: {client.model}")
        print(f"\nTest Prompt:\n{test_prompt}")
        print("\nGenerating SQL...")
        
        sql = client.generate_sql(test_prompt)
        print(f"\nGenerated SQL:\n{sql}")
        
    except ValueError as e:
        print(f"\nConfiguration Error: {e}")
    except Exception as e:
        print(f"\nError: {e}")
