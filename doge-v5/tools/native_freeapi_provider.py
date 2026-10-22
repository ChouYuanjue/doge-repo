"""Doge v5: configure native AstrBot providers for existing free gateways.

No extra router, thinking-token tier, prompt rewriting or FreeLLMAPI policy
changes. Existing AstrBot Agent Runner owns system prompts, history, tools,
message filtering, persona and fallback_chat_models.
"""
from __future__ import annotations
from copy import deepcopy

WORKBUDDY_ID = "workbuddy"
WORKBUDDY_BASE = "http://127.0.0.1:16302/v1"
FREELLM_ID = "freellmapi"
FREELLM_BASE = "http://127.0.0.1:16301/v1"
WORKBUDDY_PRIMARY = "workbuddy/deepseek-v4.1-flash"

# All four models have been checked with real small text/tool calls, rather
# than assumed equivalent from their provider naming conventions.
WORKBUDDY_MODELS = (
    ("workbuddy/glm-5.3", "glm-5.3"),
    ("workbuddy/deepseek-v4.1-flash", "deepseek-v4.1-flash"),
    ("workbuddy/kimi-k2.7", "kimi-k2.7"),
)
FREELLM_MODEL = ("freellmapi/auto", "auto")


def _validate_secret(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) < 24 or any(c.isspace() for c in value):
        raise ValueError(f"{name}: missing or malformed local API key")


def _install_source(sources: list, template: dict, *, id: str,
                    base: str, key: str) -> None:
    matching = [source for source in sources if source.get("id") == id]
    if len(matching) > 1:
        raise ValueError(f"Duplicate AstrBot source: {id}")
    if matching:
        source = matching[0]
        if source.get("type") != "openai_chat_completion" or source.get("api_base") != base:
            raise ValueError(f"Conflicting source: {id}")
    else:
        source = deepcopy(template)
        sources.append(source)
    source.update({
        "id": id,
        "type": "openai_chat_completion",
        "provider": "openai",
        "provider_type": "chat_completion",
        "api_base": base,
        "key": key,
        "proxy": "",
        "custom_headers": {},  # no Doge-specific extensions inside FreeLLMAPI
        "enable": True,
    })


def _install_model(models: list, template: dict, *,
                   model_id: str, source_id: str, upstream: str) -> None:
    matching = [model for model in models if model.get("id") == model_id]
    if len(matching) > 1:
        raise ValueError(f"Duplicate model: {model_id}")
    if matching:
        entry = matching[0]
        if entry.get("provider_source_id") != source_id or entry.get("model") != upstream:
            raise ValueError(f"Conflicting model: {model_id}")
        return
    entry = deepcopy(template)
    entry.update({
        "id": model_id,
        "provider_source_id": source_id,
        "model": upstream,
        "modalities": ["text", "tool_use"],
        "custom_extra_body": {},  # no forced reasoning_effort or arbitrary limits
        "enable": True,
    })
    # Deliberately retain the original, already deployed model's context/output
    # settings. The native AstrBot provider and persona own those decisions.
    models.append(entry)


def configure_native_freeapi(original: dict, *, unified_key: str,
                             workbuddy_key: str | None = None,
                             activate: bool = False) -> dict:
    """Return an independent AstrBot config copy; no live mutation by itself.

    WorkBuddy is first based on actual text+tool-call tests. Native FreeLLMAPI
    auto uses its own existing scoring/rate limit/fallback, and direct DeepSeek
    remains the first paid fallback. Previous fallbacks are retained.
    """
    _validate_secret(unified_key, "FreeLLMAPI")
    if activate and workbuddy_key is None:
        raise ValueError("WorkBuddy key required to activate this provider order")
    if workbuddy_key is not None:
        _validate_secret(workbuddy_key, "WorkBuddy")
    result = deepcopy(original)
    sources = result.get("provider_sources")
    providers = result.get("provider")
    settings = result.get("provider_settings")
    if not isinstance(sources, list) or not isinstance(providers, list) or not isinstance(settings, dict):
        raise ValueError("AstrBot provider configuration is incomplete")
    ds_source = next((item for item in sources if item.get("id") == "deepseek"), None)
    ds_model = next((item for item in providers if item.get("id") == "deepseek/deepseek-v4-flash"), None)
    if ds_source is None or ds_model is None:
        raise ValueError("Original direct DeepSeek provider is required for fallback")

    _install_source(sources, ds_source, id=FREELLM_ID, base=FREELLM_BASE, key=unified_key)
    _install_model(providers, ds_model, model_id=FREELLM_MODEL[0],
                   source_id=FREELLM_ID, upstream=FREELLM_MODEL[1])

    if workbuddy_key:
        _install_source(sources, ds_source, id=WORKBUDDY_ID,
                        base=WORKBUDDY_BASE, key=workbuddy_key)
        for model_id, upstream in WORKBUDDY_MODELS:
            _install_model(providers, ds_model, model_id=model_id,
                           source_id=WORKBUDDY_ID, upstream=upstream)

    if activate:
        old_default = str(settings.get("default_provider_id") or "").strip()
        old_fallbacks = list(settings.get("fallback_chat_models") or [])
        if not old_default:
            raise ValueError("Missing original AstrBot default provider")
        order = [
            WORKBUDDY_PRIMARY,
            "workbuddy/glm-5.3",
            FREELLM_MODEL[0],
            old_default,
            *old_fallbacks,
        ]
        unique = []
        for model_id in order:
            if isinstance(model_id, str) and model_id and model_id not in unique:
                unique.append(model_id)
        settings["default_provider_id"] = unique[0]
        settings["fallback_chat_models"] = unique[1:]

    return result
