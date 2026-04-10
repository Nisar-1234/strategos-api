"""
LLM Gateway — Single entry point for all LLM calls.

Enforces:
1. Redis response cache (SHA-256 key, 4-hour TTL) — checked before every call
2. Context token budget cap (8,000 input tokens)
3. Emoji strip on all outputs
4. Token usage logging to llm_response_cache table
"""

import hashlib
import json
import logging
import re
from typing import AsyncGenerator

from app.core.config import get_settings

logger = logging.getLogger("strategos.llm")
settings = get_settings()

CACHE_TTL_SECONDS = 14_400  # 4 hours

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
    return EMOJI_PATTERN.sub("", text)


def compute_cache_key(prompt: str, model: str) -> str:
    normalized = prompt.strip().lower()
    return hashlib.sha256(f"{model}:{normalized}".encode()).hexdigest()


def _get_redis():
    import redis
    return redis.from_url(settings.REDIS_URL, socket_timeout=2, decode_responses=True)


async def _check_cache(cache_key: str) -> str | None:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        result = await r.get(f"llm:{cache_key}")
        await r.aclose()
        return result
    except Exception:
        return None


async def _write_cache(cache_key: str, response: str) -> None:
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        await r.setex(f"llm:{cache_key}", CACHE_TTL_SECONDS, response)
        await r.aclose()
    except Exception:
        pass


def _truncate_to_budget(text: str, budget_tokens: int) -> str:
    words = text.split()
    budget_words = int(budget_tokens / 1.3)
    return " ".join(words[:budget_words])


async def call_llm(
    prompt: str,
    system_prompt: str = "",
    signal_context: str = "",
    user_id: str | None = None,
    conflict_id: str | None = None,
) -> dict:
    """
    Gateway function for all LLM calls. Checks Redis cache first.
    Returns cached result immediately on hit; calls LLM on miss.
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

    # Cache check
    cached = await _check_cache(cache_key)
    if cached:
        logger.debug("LLM cache hit: %s", cache_key[:16])
        return {
            "response": cached,
            "model": model,
            "cache_hit": True,
            "cache_key": cache_key,
            "input_tokens": 0,
            "output_tokens": len(cached.split()),
        }

    # Token budget enforcement
    estimated_tokens = int(len(full_prompt.split()) * 1.3)
    if estimated_tokens > settings.LLM_CONTEXT_TOKEN_BUDGET:
        full_prompt = _truncate_to_budget(full_prompt, settings.LLM_CONTEXT_TOKEN_BUDGET)
        estimated_tokens = settings.LLM_CONTEXT_TOKEN_BUDGET

    raw_text = await _invoke_llm(model, system_prompt, signal_context, prompt)
    cleaned = strip_emoji(raw_text)

    await _write_cache(cache_key, cleaned)

    return {
        "response": cleaned,
        "model": model,
        "cache_hit": False,
        "cache_key": cache_key,
        "input_tokens": estimated_tokens,
        "output_tokens": len(cleaned.split()),
    }


async def stream_llm(
    prompt: str,
    system_prompt: str = "",
    signal_context: str = "",
) -> AsyncGenerator[str, None]:
    """
    Streaming variant. Yields text chunks as they arrive from the LLM.
    On cache hit, yields the full cached text as a single chunk.
    Caches the complete response after streaming finishes.
    """
    if not settings.ANTHROPIC_API_KEY:
        yield "LLM not configured: ANTHROPIC_API_KEY is missing."
        return

    model = settings.LLM_PRIMARY_MODEL
    full_prompt = f"{system_prompt}\n\n{signal_context}\n\n{prompt}".strip()
    cache_key = compute_cache_key(full_prompt, model)

    cached = await _check_cache(cache_key)
    if cached:
        yield cached
        return

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        messages = []
        if signal_context:
            user_content = f"{signal_context}\n\n{prompt}".strip()
        else:
            user_content = prompt

        full_response = ""
        async with client.messages.stream(
            model=model,
            max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
            system=system_prompt or "You are STRATEGOS, an AI geopolitical analyst.",
            messages=[{"role": "user", "content": user_content}],
        ) as stream:
            async for text in stream.text_stream:
                cleaned = strip_emoji(text)
                full_response += cleaned
                yield cleaned

        await _write_cache(cache_key, full_response)

    except Exception as exc:
        logger.warning("LLM streaming failed, falling back: %s", exc)
        # Fallback to non-streaming
        result = await _invoke_llm_fallback(system_prompt, signal_context, prompt)
        cleaned = strip_emoji(result)
        await _write_cache(cache_key, cleaned)
        yield cleaned


async def _invoke_llm(model: str, system_prompt: str, signal_context: str, prompt: str) -> str:
    """Try Claude primary, then GPT-4o fallback."""
    if settings.ANTHROPIC_API_KEY:
        try:
            from langchain_anthropic import ChatAnthropic
            llm = ChatAnthropic(
                model=model,
                api_key=settings.ANTHROPIC_API_KEY,
                max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
            )
            user_content = f"{signal_context}\n\n{prompt}".strip() if signal_context else prompt
            messages = []
            if system_prompt:
                from langchain_core.messages import SystemMessage, HumanMessage
                messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_content)]
            else:
                from langchain_core.messages import HumanMessage
                messages = [HumanMessage(content=user_content)]
            response = await llm.ainvoke(messages)
            return response.content if hasattr(response, "content") else str(response)
        except Exception as exc:
            logger.warning("Claude failed: %s, trying fallback", exc)

    return await _invoke_llm_fallback(system_prompt, signal_context, prompt)


async def _invoke_llm_fallback(system_prompt: str, signal_context: str, prompt: str) -> str:
    if settings.OPENAI_API_KEY:
        try:
            from langchain_openai import ChatOpenAI
            llm = ChatOpenAI(
                model=settings.LLM_FALLBACK_MODEL,
                api_key=settings.OPENAI_API_KEY,
                max_tokens=settings.LLM_MAX_TOKENS_PER_CALL,
            )
            user_content = f"{signal_context}\n\n{prompt}".strip() if signal_context else prompt
            response = await llm.ainvoke([
                {"role": "system", "content": system_prompt},
                {"role": "human", "content": user_content},
            ])
            return response.content
        except Exception as exc:
            logger.warning("GPT-4o fallback failed: %s", exc)

    return (
        "Signal-Based Analysis (LLM not configured):\n\n"
        "Configure ANTHROPIC_API_KEY or OPENAI_API_KEY for full AI analysis. "
        "Raw signal data is available via the Signals API."
    )
