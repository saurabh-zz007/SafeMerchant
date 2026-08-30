"""
LLM factory for the dispute-resolution agent.

Creates a ChatOpenAI instance pointed at OpenRouter.
Extracted as a shared helper so every node file can import it
without circular dependencies.
"""

from __future__ import annotations

from app.core.config import settings


def get_llm():
    """
    Create a ChatOpenAI instance pointed at OpenRouter.
    OpenRouter is OpenAI-compatible, so we reuse langchain-openai
    with a custom base_url.
    """
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(
        model=settings.openrouter_model_name,
        openai_api_key=settings.openrouter_api_key,
        openai_api_base=settings.openrouter_base_url,
        default_headers={
            "HTTP-Referer": "https://safemerchant.dev",
            "X-Title": "SafeMerchant Risk Agent",
        },
    )
