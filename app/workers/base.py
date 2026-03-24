"""
Base ingestion framework shared by all signal layer workers.

Provides:
- CircuitBreaker: trips after N consecutive failures, auto-resets after cooldown
- SignalNormalizer: maps raw API data to standard Signal schema
- Retry-aware HTTP client with timeout
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

logger = logging.getLogger("strategos.ingest")


class CircuitBreaker:
    """
    Trips open after `threshold` consecutive failures.
    While open, calls short-circuit immediately.
    Resets after `cooldown_seconds`.
    """

    def __init__(self, name: str, threshold: int = 3, cooldown_seconds: int = 300):
        self.name = name
        self.threshold = threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures = 0
        self._open_since: float | None = None

    @property
    def is_open(self) -> bool:
        if self._open_since is None:
            return False
        elapsed = time.time() - self._open_since
        if elapsed >= self.cooldown_seconds:
            self.reset()
            return False
        return True

    def record_success(self):
        self._failures = 0
        self._open_since = None

    def record_failure(self):
        self._failures += 1
        if self._failures >= self.threshold:
            self._open_since = time.time()
            logger.warning("Circuit breaker OPEN for %s after %d failures", self.name, self._failures)

    def reset(self):
        self._failures = 0
        self._open_since = None
        logger.info("Circuit breaker RESET for %s", self.name)


class SignalNormalizer:
    """Maps raw API data to the standard Signal schema dict."""

    @staticmethod
    def normalize(
        layer: str,
        source_name: str,
        raw_value: float | None,
        normalized_score: float,
        content: str | None = None,
        conflict_id: str | None = None,
        confidence: float = 0.5,
        alert_flag: bool = False,
        alert_severity: str | None = None,
        raw_payload: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "id": str(uuid4()),
            "layer": layer,
            "source_name": source_name,
            "raw_value": raw_value,
            "normalized_score": max(-1.0, min(1.0, normalized_score)),
            "content": content,
            "conflict_id": conflict_id,
            "confidence": max(0.0, min(1.0, confidence)),
            "alert_flag": alert_flag,
            "alert_severity": alert_severity,
            "raw_payload": raw_payload,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def detect_alert(value: float, baseline: float, threshold_pct: float = 15.0) -> tuple[bool, str | None]:
        """Check if a value deviates from baseline enough to trigger an alert."""
        if baseline == 0:
            return False, None
        pct_change = abs((value - baseline) / baseline) * 100
        if pct_change >= 30:
            return True, "CRITICAL"
        if pct_change >= threshold_pct:
            return True, "WARNING"
        return False, None

    @staticmethod
    def pct_change_score(current: float, baseline: float, cap: float = 50.0) -> float:
        """
        Convert a % change to a -1..+1 score.
        Positive = price/value went up, negative = went down.
        Capped at `cap`% for normalization.
        """
        if baseline == 0:
            return 0.0
        pct = ((current - baseline) / abs(baseline)) * 100
        clamped = max(-cap, min(cap, pct))
        return clamped / cap


async def fetch_json(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 30.0) -> dict:
    """Shared HTTP GET with timeout and error handling."""
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()


def fetch_json_sync(url: str, params: dict | None = None, headers: dict | None = None, timeout: float = 30.0) -> dict:
    """Synchronous version for Celery workers (which aren't async)."""
    with httpx.Client(timeout=timeout) as client:
        resp = client.get(url, params=params, headers=headers)
        resp.raise_for_status()
        return resp.json()
