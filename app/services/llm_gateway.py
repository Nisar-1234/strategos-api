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
from datetime import datetime, timezone, timedelta
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

    1. Checks response cache
    2. Enforces token budget (8,000 input tokens)
    3. Calls primary model (Claude), falls back to GPT-4o
    4. Strips emoji from response
    5. Logs token usage
    """
    model = settings.LLM_PRIMARY_MODEL
    cache_key = compute_cache_key(prompt + signal_context, model)

    # TODO: Check llm_response_cache table for cache hit < 4 hours old

    full_prompt = f"{system_prompt}\n\n{signal_context}\n\n{prompt}".strip()

    estimated_tokens = len(full_prompt.split()) * 1.3
    if estimated_tokens > settings.LLM_CONTEXT_TOKEN_BUDGET:
        # TODO: Implement signal ranking to reduce context
        pass

    # TODO: Call Anthropic API via LangChain with fallback to OpenAI
    raw_response = f"[Placeholder] Analysis for prompt: {prompt[:100]}..."

    cleaned = strip_emoji(raw_response)

    # TODO: Log to token_usage table
    # TODO: Cache the response

    return {
        "response": cleaned,
        "model": model,
        "cache_hit": False,
        "cache_key": cache_key,
        "input_tokens": int(estimated_tokens),
        "output_tokens": len(cleaned.split()),
    }
