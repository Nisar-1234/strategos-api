"""Tests for the base signal normalizer and circuit breaker."""

import time
import pytest
from app.workers.base import CircuitBreaker, SignalNormalizer


class TestCircuitBreaker:
    def test_starts_closed(self):
        cb = CircuitBreaker("test", threshold=3, cooldown_seconds=10)
        assert not cb.is_open

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker("test", threshold=3)
        cb.record_failure()
        cb.record_failure()
        assert not cb.is_open

    def test_opens_at_threshold(self):
        cb = CircuitBreaker("test", threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_failure()
        assert cb.is_open

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker("test", threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        cb.record_failure()
        assert not cb.is_open

    def test_resets_after_cooldown(self):
        cb = CircuitBreaker("test", threshold=1, cooldown_seconds=1)
        cb.record_failure()
        assert cb.is_open
        cb._open_since = time.time() - 2  # simulate 2 seconds elapsed
        assert not cb.is_open

    def test_manual_reset(self):
        cb = CircuitBreaker("test", threshold=1, cooldown_seconds=999)
        cb.record_failure()
        assert cb.is_open
        cb.reset()
        assert not cb.is_open


class TestSignalNormalizer:
    def test_normalize_basic(self):
        sig = SignalNormalizer.normalize(
            layer="L5",
            source_name="Gold API",
            raw_value=2847.50,
            normalized_score=0.65,
            content="Gold at $2847.50",
        )
        assert sig["layer"] == "L5"
        assert sig["source_name"] == "Gold API"
        assert sig["raw_value"] == 2847.50
        assert sig["normalized_score"] == 0.65
        assert sig["content"] == "Gold at $2847.50"
        assert sig["id"] is not None
        assert sig["timestamp"] is not None

    def test_normalize_clamps_score(self):
        sig = SignalNormalizer.normalize(
            layer="L1", source_name="test", raw_value=None,
            normalized_score=5.0,
        )
        assert sig["normalized_score"] == 1.0

        sig2 = SignalNormalizer.normalize(
            layer="L1", source_name="test", raw_value=None,
            normalized_score=-5.0,
        )
        assert sig2["normalized_score"] == -1.0

    def test_normalize_clamps_confidence(self):
        sig = SignalNormalizer.normalize(
            layer="L1", source_name="test", raw_value=None,
            normalized_score=0.0, confidence=2.0,
        )
        assert sig["confidence"] == 1.0

        sig2 = SignalNormalizer.normalize(
            layer="L1", source_name="test", raw_value=None,
            normalized_score=0.0, confidence=-0.5,
        )
        assert sig2["confidence"] == 0.0

    def test_normalize_alert_fields(self):
        sig = SignalNormalizer.normalize(
            layer="L10", source_name="IODA", raw_value=15.0,
            normalized_score=-0.9, alert_flag=True, alert_severity="CRITICAL",
        )
        assert sig["alert_flag"] is True
        assert sig["alert_severity"] == "CRITICAL"

    def test_detect_alert_no_alert(self):
        flag, severity = SignalNormalizer.detect_alert(100, 100)
        assert flag is False
        assert severity is None

    def test_detect_alert_warning(self):
        flag, severity = SignalNormalizer.detect_alert(120, 100)
        assert flag is True
        assert severity == "WARNING"

    def test_detect_alert_critical(self):
        flag, severity = SignalNormalizer.detect_alert(140, 100)
        assert flag is True
        assert severity == "CRITICAL"

    def test_detect_alert_negative_change(self):
        flag, severity = SignalNormalizer.detect_alert(60, 100)
        assert flag is True
        assert severity == "CRITICAL"

    def test_detect_alert_zero_baseline(self):
        flag, severity = SignalNormalizer.detect_alert(50, 0)
        assert flag is False
        assert severity is None

    def test_pct_change_score_positive(self):
        score = SignalNormalizer.pct_change_score(110, 100)
        assert 0.15 < score < 0.25

    def test_pct_change_score_negative(self):
        score = SignalNormalizer.pct_change_score(90, 100)
        assert -0.25 < score < -0.15

    def test_pct_change_score_no_change(self):
        score = SignalNormalizer.pct_change_score(100, 100)
        assert score == 0.0

    def test_pct_change_score_capped(self):
        score = SignalNormalizer.pct_change_score(200, 100, cap=50)
        assert score == 1.0

        score_neg = SignalNormalizer.pct_change_score(10, 100, cap=50)
        assert score_neg == -1.0

    def test_pct_change_score_zero_baseline(self):
        score = SignalNormalizer.pct_change_score(100, 0)
        assert score == 0.0
