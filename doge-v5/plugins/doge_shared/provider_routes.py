from __future__ import annotations

from typing import Any


PREFERRED_DEEPSEEK_PROVIDER_IDS: tuple[str, ...] = (
    "deepseek/deepseek-v4-flash",
    "openrouter/~deepseek/deepseek-v4-flash-latest",
)


def dedicated_deepseek(context: Any):
    """Return an already-loaded DeepSeek chat provider without touching secrets.

    Prefer the direct DeepSeek source configured in AstrBot.  Fall back to an
    already-loaded OpenRouter DeepSeek model only when the direct provider is
    absent.  This deliberately does not fall back to the session-selected
    provider: callers use this helper because their behavior depends on a
    dedicated DeepSeek chain.
    """
    for provider_id in PREFERRED_DEEPSEEK_PROVIDER_IDS:
        try:
            provider = context.get_provider_by_id(provider_id)
        except Exception:
            provider = None
        if provider is not None:
            return provider, provider_id
    raise ValueError(
        "需要已配置的 DeepSeek provider（优先 deepseek/deepseek-v4-flash）；"
        "不会回退到当前会话的默认 Agent/provider。"
    )
