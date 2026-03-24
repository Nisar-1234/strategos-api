"""Tests for LLM Gateway utilities."""

import pytest
from app.services.llm_gateway import strip_emoji, compute_cache_key


class TestStripEmoji:
    def test_removes_emoji(self):
        assert strip_emoji("Hello World") == "Hello World"

    def test_removes_flag_emoji(self):
        result = strip_emoji("Analysis complete")
        assert result == "Analysis complete"

    def test_preserves_normal_text(self):
        text = "Convergence Score: 8.4/10 -- HIGH confidence"
        assert strip_emoji(text) == text

    def test_removes_mixed_emoji(self):
        result = strip_emoji("Score is great!")
        assert "great" in result

    def test_handles_empty_string(self):
        assert strip_emoji("") == ""


class TestComputeCacheKey:
    def test_produces_hex_string(self):
        key = compute_cache_key("test prompt", "claude-sonnet-4-6")
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)

    def test_same_input_same_key(self):
        k1 = compute_cache_key("test", "claude-sonnet-4-6")
        k2 = compute_cache_key("test", "claude-sonnet-4-6")
        assert k1 == k2

    def test_different_prompts_different_keys(self):
        k1 = compute_cache_key("prompt A", "claude-sonnet-4-6")
        k2 = compute_cache_key("prompt B", "claude-sonnet-4-6")
        assert k1 != k2

    def test_different_models_different_keys(self):
        k1 = compute_cache_key("test", "claude-sonnet-4-6")
        k2 = compute_cache_key("test", "gpt-4o")
        assert k1 != k2

    def test_normalizes_whitespace(self):
        k1 = compute_cache_key("  test  ", "claude-sonnet-4-6")
        k2 = compute_cache_key("test", "claude-sonnet-4-6")
        assert k1 == k2

    def test_case_insensitive(self):
        k1 = compute_cache_key("Test Prompt", "claude-sonnet-4-6")
        k2 = compute_cache_key("test prompt", "claude-sonnet-4-6")
        assert k1 == k2
