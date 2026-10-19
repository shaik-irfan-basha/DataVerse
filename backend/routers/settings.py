"""
backend/routers/settings.py - AI Provider & BYOK Configuration Router
"""

import os
import requests
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status

from backend.config import ALLOW_SERVER_ENV_KEY, SUPPORTED_AI_PROVIDERS
from backend.schemas import (
    ProviderConfigResponse,
    ProviderOption,
    ModelOption,
    ProviderSaveRequest,
    ProviderSaveResponse,
    ProviderTestRequest,
    ProviderTestResponse,
    GenericMessageResponse
)
from backend.session_manager import UserSession, get_current_session

logger = logging.getLogger("dataverse.api.settings")
router = APIRouter(prefix="/settings", tags=["AI Provider Settings (BYOK)"])


def _build_provider_options():
    options = []
    for pid, pdata in SUPPORTED_AI_PROVIDERS.items():
        models = [ModelOption(id=m["id"], name=m["name"]) for m in pdata.get("models", [])]
        options.append(
            ProviderOption(
                id=pid,
                name=pdata.get("name", pid),
                default_model=pdata.get("default_model", ""),
                models=models,
                key_prefix=pdata.get("key_prefix"),
                docs_url=pdata.get("docs_url")
            )
        )
    return options


def _test_provider_connectivity(provider: str, model: str, api_key: str) -> tuple[bool, str]:
    """
    Core connectivity test logic shared between Test Connection and Save & Apply.
    Executes a minimal test request with strict timeouts without exposing secrets.
    """
    provider = provider.lower().strip()
    if provider not in SUPPORTED_AI_PROVIDERS:
        return False, f"Unsupported provider '{provider}'."

    pdata = SUPPORTED_AI_PROVIDERS[provider]
    endpoint = pdata["endpoint"]
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    test_payload = {
        "model": model,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": 2
    }

    try:
        res = requests.post(endpoint, headers=headers, json=test_payload, timeout=10)
        if res.status_code == 200:
            return True, f"Authentication successful! Connected to {pdata['name']} ({model})."
        elif res.status_code == 401:
            return False, "Authentication failed: Invalid API key. Please check your key at console.groq.com."
        elif res.status_code == 429:
            return False, "Rate limit or quota exceeded on this Groq account. Please check your plan limits."
        elif res.status_code == 404:
            return False, f"Model '{model}' not found on provider. Please select a different model."
        else:
            return False, f"Provider returned HTTP {res.status_code}. Please verify settings."
    except requests.exceptions.Timeout:
        return False, "Connection timed out while reaching Groq API. Please check your internet connection."
    except requests.exceptions.RequestException as e:
        logger.warning(f"Network error testing provider connection: {type(e).__name__}")
        return False, "Network error reaching AI provider. Please verify your connection."


@router.get("/ai-provider", response_model=ProviderConfigResponse, summary="Get Session AI Provider Configuration")
def get_provider_config(session: UserSession = Depends(get_current_session)) -> ProviderConfigResponse:
    """
    Returns the current session's AI provider configuration.
    Never exposes full API keys (only masked key preview).
    Falls back gracefully if session model is invalid or unavailable.
    """
    server_key_present = bool(os.getenv("GROQ_API_KEY"))
    active_prov = session.llm_provider or "groq"
    pdata = SUPPORTED_AI_PROVIDERS.get(active_prov, SUPPORTED_AI_PROVIDERS["groq"])
    prov_model_ids = [m["id"] for m in pdata.get("models", [])]

    # Gracefully handle unavailable or stale models in session
    active_model = session.llm_model if (session.llm_model and session.llm_model in prov_model_ids) else pdata["default_model"]

    return ProviderConfigResponse(
        provider=active_prov,
        model=active_model,
        has_key=bool(session.llm_api_key),
        masked_key=session.get_masked_key(),
        allow_server_env_key=ALLOW_SERVER_ENV_KEY,
        server_key_available=bool(ALLOW_SERVER_ENV_KEY and server_key_present),
        supported_providers=_build_provider_options()
    )


@router.post("/ai-provider", response_model=ProviderSaveResponse, summary="Save or Update Session AI API Key")
def save_provider_config(
    payload: ProviderSaveRequest,
    session: UserSession = Depends(get_current_session)
) -> ProviderSaveResponse:
    """
    Configures the user's isolated API key and model for their current session.
    Stored in memory only for the lifetime of this session; never persisted to disk or logged.
    If api_key is omitted, preserves the existing session key and updates the model.
    If validate_connection is True, validates against provider before saving.
    """
    clean_provider = payload.provider.lower().strip()
    if clean_provider not in SUPPORTED_AI_PROVIDERS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported AI provider '{payload.provider}'. Supported: {list(SUPPORTED_AI_PROVIDERS.keys())}"
        )

    pdata = SUPPORTED_AI_PROVIDERS[clean_provider]
    valid_model_ids = [m["id"] for m in pdata.get("models", [])]
    clean_model = (payload.model or pdata["default_model"]).strip()
    if clean_model not in valid_model_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported model '{clean_model}' for provider '{clean_provider}'. Supported models: {valid_model_ids}"
        )

    # Determine effective key: provided key or existing session key
    if payload.api_key and payload.api_key.strip():
        clean_key = payload.api_key.strip()
        if len(clean_key) < 10:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key is too short. Please provide a valid API key."
            )
    else:
        clean_key = session.llm_api_key
        if not clean_key:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="API key is required. Please enter your Groq API key."
            )

    # Validate against provider if requested (preserves existing key on failure)
    if payload.validate_connection:
        is_valid, err_msg = _test_provider_connectivity(clean_provider, clean_model, clean_key)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=err_msg
            )

    try:
        session.set_provider_config(
            provider=clean_provider,
            model=clean_model,
            api_key=clean_key
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve)
        )

    return ProviderSaveResponse(
        status="success",
        message="AI provider and API key configured for your active session.",
        provider=session.llm_provider,
        model=session.llm_model,
        has_key=True,
        masked_key=session.get_masked_key()
    )


@router.delete("/ai-provider", response_model=GenericMessageResponse, summary="Remove Session API Key")
def remove_provider_config(session: UserSession = Depends(get_current_session)) -> GenericMessageResponse:
    """
    Clears the configured API key and custom provider from the active session.
    """
    session.clear_provider_config()
    return GenericMessageResponse(
        success=True,
        message="API key and custom provider configuration removed from active session."
    )


@router.post("/ai-provider/test", response_model=ProviderTestResponse, summary="Test Provider API Key Connection")
def test_provider_connection(
    payload: ProviderTestRequest,
    session: UserSession = Depends(get_current_session)
) -> ProviderTestResponse:
    """
    Verifies that the provided or saved API key can successfully authenticate with the AI provider.
    Executes a minimal test request with strict timeouts without exposing secrets.
    """
    provider = (payload.provider or session.llm_provider or "groq").lower().strip()
    if provider not in SUPPORTED_AI_PROVIDERS:
        return ProviderTestResponse(
            success=False,
            message=f"Unsupported provider '{provider}'."
        )

    pdata = SUPPORTED_AI_PROVIDERS[provider]
    model = (payload.model or session.llm_model or pdata["default_model"]).strip()
    api_key = (payload.api_key or session.llm_api_key or "").strip()

    if not api_key:
        return ProviderTestResponse(
            success=False,
            message="No API key provided to test. Please enter a key or save one first."
        )

    success, message = _test_provider_connectivity(provider, model, api_key)
    return ProviderTestResponse(success=success, message=message)
