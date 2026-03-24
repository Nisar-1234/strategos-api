"""
L1 — Editorial Media Signal Layer

Sources:
  - GDELT Project: Global event database (free, real-time)
  - NewsAPI: Top headlines from major outlets

Ingestion schedule: every 300 seconds (5 minutes)
Weight: 0.6 (high bias risk — requires source credibility scoring)

Each article is enriched with:
  - NLP entity extraction (locations, organizations, persons)
  - Source bias score from the signal_sources registry
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals
from app.core.config import get_settings

logger = logging.getLogger("strategos.l1")
settings = get_settings()

cb_gdelt = CircuitBreaker("L1-GDELT")
cb_newsapi = CircuitBreaker("L1-NewsAPI")

CONFLICT_KEYWORDS = [
    "conflict", "war", "military", "attack", "strike", "sanctions",
    "nuclear", "escalation", "ceasefire", "troops", "missile",
    "invasion", "blockade", "embargo", "siege", "airstrike",
    "casualties", "deployment", "tensions", "hostilities",
]

SOURCE_BIAS_DEFAULTS = {
    "reuters.com": 8.5,
    "apnews.com": 8.3,
    "bbc.co.uk": 7.8,
    "aljazeera.com": 6.5,
    "cnn.com": 6.8,
    "foxnews.com": 5.5,
    "rt.com": 3.0,
    "xinhuanet.com": 3.5,
}


def _relevance_score(title: str, description: str) -> float:
    """Score 0-1 based on how many conflict-related keywords appear."""
    text = f"{title} {description}".lower()
    hits = sum(1 for kw in CONFLICT_KEYWORDS if kw in text)
    return min(1.0, hits / 5.0)


def _source_bias(url: str) -> float:
    """Lookup source credibility from defaults. 0=propaganda, 10=factual."""
    for domain, score in SOURCE_BIAS_DEFAULTS.items():
        if domain in url:
            return score
    return 5.0


def _ingest_gdelt() -> list[dict]:
    """Fetch latest geopolitical events from GDELT."""
    signals = []
    if cb_gdelt.is_open:
        logger.warning("Circuit breaker open for GDELT, skipping")
        return signals

    try:
        data = fetch_json_sync(
            "https://api.gdeltproject.org/api/v2/doc/doc",
            params={
                "query": "conflict OR war OR military OR sanctions",
                "mode": "artlist",
                "maxrecords": "30",
                "format": "json",
                "sort": "datedesc",
            },
        )

        articles = data.get("articles", [])
        for art in articles[:20]:
            title = art.get("title", "")
            url = art.get("url", "")
            source = art.get("domain", "unknown")
            tone = float(art.get("tone", 0))

            relevance = _relevance_score(title, art.get("seendate", ""))
            if relevance < 0.2:
                continue

            bias = _source_bias(url)
            score = (tone / 20.0) * (bias / 10.0)
            alert = abs(tone) > 8
            severity = "CRITICAL" if abs(tone) > 12 else ("WARNING" if alert else None)

            signals.append(SignalNormalizer.normalize(
                layer="L1",
                source_name=f"GDELT/{source}",
                raw_value=tone,
                normalized_score=max(-1.0, min(1.0, score)),
                content=title[:500],
                confidence=min(0.9, (bias / 10.0) * relevance),
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={
                    "url": url,
                    "source_domain": source,
                    "tone": tone,
                    "bias_score": bias,
                    "relevance": relevance,
                },
            ))

        cb_gdelt.record_success()
    except Exception as e:
        cb_gdelt.record_failure()
        logger.error("L1 GDELT error: %s", e)

    return signals


def _ingest_newsapi() -> list[dict]:
    """Fetch top conflict-related headlines from NewsAPI."""
    signals = []
    key = settings.NEWSAPI_KEY
    if not key:
        logger.warning("NEWSAPI_KEY not set, skipping NewsAPI")
        return signals

    if cb_newsapi.is_open:
        logger.warning("Circuit breaker open for NewsAPI, skipping")
        return signals

    try:
        data = fetch_json_sync(
            "https://newsapi.org/v2/everything",
            params={
                "q": "(conflict OR war OR military OR sanctions) AND (geopolitical OR international)",
                "sortBy": "publishedAt",
                "pageSize": "20",
                "language": "en",
                "apiKey": key,
            },
        )

        articles = data.get("articles", [])
        for art in articles:
            title = art.get("title", "")
            desc = art.get("description", "") or ""
            source_name = art.get("source", {}).get("name", "Unknown")
            url = art.get("url", "")

            relevance = _relevance_score(title, desc)
            if relevance < 0.2:
                continue

            bias = _source_bias(url)
            score = relevance * (bias / 10.0) - 0.5

            signals.append(SignalNormalizer.normalize(
                layer="L1",
                source_name=f"NewsAPI/{source_name}",
                raw_value=relevance,
                normalized_score=max(-1.0, min(1.0, score)),
                content=f"{title} -- {desc[:200]}",
                confidence=min(0.85, (bias / 10.0) * relevance),
                alert_flag=relevance > 0.7,
                alert_severity="WARNING" if relevance > 0.7 else None,
                raw_payload={
                    "url": url,
                    "source": source_name,
                    "bias_score": bias,
                    "relevance": relevance,
                    "published_at": art.get("publishedAt"),
                },
            ))

        cb_newsapi.record_success()
    except Exception as e:
        cb_newsapi.record_failure()
        logger.error("L1 NewsAPI error: %s", e)

    return signals


@celery_app.task(name="app.workers.l1_editorial.ingest")
def ingest():
    """L1 ingestion entrypoint — called by Celery beat every 5min."""
    all_signals = _ingest_gdelt() + _ingest_newsapi()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L1 Editorial: ingested %d signals", count)
    return len(all_signals)
