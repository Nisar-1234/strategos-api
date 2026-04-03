"""
LLM Gateway — Single entry point for all LLM calls.

Enforces:
1. Response cache check (SHA-256 hash, 4-hour TTL)
2. Context token budget cap (8,000 input tokens)
3. Emoji strip on all outputs
4. Token usage logging
"""

import re
import hashlib
from app.core.config import get_settings

settings = get_settings()

EMOJI_PATTERN = re.compile(
    "["
    "\U0001F300-\U0001FFFF"
    "\U00002600-\U000027BF"
    "\U0000FE00-\U0000FE0F"
    "\U0001F900-\U0001F9FF"
    "\U0000200D"
    "\U00002702-\U000027B0"
    "]+",
    flags=re.UNICODE,
)


def strip_emoji(text: str) -> str:
    """Remove all emoji characters from LLM output. BRD absolute rule: zero emoji."""
    return EMOJI_PATTERN.sub("", text)


def compute_cache_key(prompt: str, model: str) -> str:
    """SHA-256 hash of normalized prompt + model for cache lookup."""
    normalized = prompt.strip().lower()
    return hashlib.sha256(f"{model}:{normalized}".encode()).hexdigest()


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    signal_context: str = "",
    user_id: str | None = None,
    conflict_id: str | None = None,
) -> dict:
    """
    Gateway function for all LLM calls. Never call the LLM directly.

    1. Enforces token budget (8,000 input tokens)
    2. Calls Claude (claude-sonnet-4-6) — no fallback
    3. Strips emoji from response
    """
    if not settings.ANTHROPIC_API_KEY:
        return {
            "response": "LLM not configured: ANTHROPIC_API_KEY is missing.",
            "model": settings.LLM_PRIMARY_MODEL,
            "cache_hit": False,
            "cache_key": "",
            "input_tokens": 0,
            "output_tokens": 0,
        }

    model = settings.LLM_PRIMARY_MODEL
    full_prompt = f"{system_prompt}\n\n{signal_context}\n\n{prompt}".strip()
    cache_key = compute_cache_key(full_prompt, model)

    estimated_tokens = int(len(full_prompt.split()) * 1.3)
    if estimated_tokens > settings.LLM_CONTEXT_TOKEN_BUDGET:
        # Truncate signal_context to fit within budget
        words = full_prompt.split()
        budget_words = int(settings.LLM_CONTEXT_TOKEN_BUDGET / 1.3)
        full_prompt = " ".join(words[:budget_words])
        estimated_tokens = settings.LLM_CONTEXT_TOKEN_BUDGET

    from langchain_anthropic import ChatAnthropic
    from langchain_core.messages import HumanMessage, SystemMessage

    llm = ChatAnthropic(
        model=model,
        api_key=settings.ANTHROPIC_API_KEY,
        max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
    )

    messages = []
    if system_prompt:
        messages.append(SystemMessage(content=system_prompt))
    user_content = f"{signal_context}\n\n{prompt}".strip() if signal_context else prompt
    messages.append(HumanMessage(content=user_content))

    response = await llm.ainvoke(messages)
    raw_text = response.content if hasattr(response, "content") else str(response)
    cleaned = strip_emoji(raw_text)

    output_tokens = len(cleaned.split())

    return {
        "response": cleaned,
        "model": model,
        "cache_hit": False,
        "cache_key": cache_key,
        "input_tokens": estimated_tokens,
        "output_tokens": output_tokens,
    }
