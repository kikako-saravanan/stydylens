import logging
import os
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.exceptions import ModelError
from langchain_core.messages import BaseMessage
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


class AllProvidersUnavailableError(Exception):
    """Raised when every configured LLM provider has failed to respond."""


@lru_cache(maxsize=1)
def _primary_llm() -> ChatAnthropic:
    return ChatAnthropic(model=os.getenv("LLM_MODEL", "claude-sonnet-5"))


@lru_cache(maxsize=1)
def _fallback_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(model=os.getenv("LLM_FALLBACK_MODEL", "gemini-2.5-flash"))


def _extract_text(content) -> str:
    """Normalize a LangChain message's .content to plain text.

    Current-generation Claude models (e.g. Sonnet 5) have extended thinking
    on by default, so .content comes back as a LIST of blocks — a
    "thinking" block (the model's internal reasoning trace, opaque and not
    meant to be shown) plus one or more "text" blocks (the actual answer)
    — rather than a plain string. Older models / Gemini return a plain
    string. Handle both so callers always get just the answer text.
    """
    if isinstance(content, str):
        return content
    return "".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def generate(messages: list[BaseMessage]) -> str:
    """Invoke the primary LLM; fall back to a secondary provider on failure.

    `langchain_core.exceptions.ModelError` is LangChain's unified base class
    for classified provider failures — exhausted credit, rate limits,
    timeouts, overload, etc. Every LangChain chat-model integration
    (langchain-anthropic, langchain-google-genai, ...) raises subclasses of
    it, so this one except clause correctly triggers fallback regardless of
    *which* specific failure the primary provider hit, without needing to
    enumerate every provider-specific exception class by hand.
    """
    try:
        response = _primary_llm().invoke(messages)
        return _extract_text(response.content)
    except ModelError as e:
        logger.warning("Primary LLM (Anthropic) failed: %s. Falling back to Gemini.", e)

    try:
        response = _fallback_llm().invoke(messages)
        return _extract_text(response.content)
    except ModelError as e:
        logger.error("Fallback LLM (Gemini) also failed: %s", e)
        raise AllProvidersUnavailableError(
            "Both configured LLM providers (Anthropic and Gemini) are "
            "currently unavailable. Please try again later, or contact "
            "the administrator if this persists."
        ) from e
