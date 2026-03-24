"""
L2 — Social Media Signal Layer

Sources:
  - Reddit: Geopolitics and conflict subreddits via public JSON API
  - YouTube: Conflict-related video metrics via YouTube Data API

Ingestion schedule: every 300 seconds (5 minutes) — via L1 beat schedule
Weight: 0.6 (high noise — requires bot/spam filtering)

Key signals:
  - Volume spikes in conflict-related subreddits
  - Sentiment shifts in social discourse
  - Viral conflict content indicating public attention
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals
from app.core.config import get_settings

logger = logging.getLogger("strategos.l2")
settings = get_settings()

cb_reddit = CircuitBreaker("L2-Reddit")

TRACKED_SUBREDDITS = [
    "worldnews",
    "geopolitics",
    "CredibleDefense",
    "UkrainianConflict",
    "IsraelPalestine",
    "syriancivilwar",
]

CONFLICT_KEYWORDS = {
    "escalation", "ceasefire", "military", "attack", "missile",
    "troops", "sanctions", "nuclear", "invasion", "blockade",
    "casualties", "strike", "drone", "airstrike", "deployment",
}


def _estimate_relevance(title: str) -> float:
    """Quick keyword-based relevance for filtering noise."""
    words = set(title.lower().split())
    hits = len(words & CONFLICT_KEYWORDS)
    return min(1.0, hits / 3.0)


def _ingest_reddit() -> list[dict]:
    """Fetch hot posts from geopolitics subreddits via Reddit JSON API (no auth needed)."""
    signals = []
    if cb_reddit.is_open:
        logger.warning("Circuit breaker open for Reddit, skipping")
        return signals

    try:
        for sub in TRACKED_SUBREDDITS:
            try:
                data = fetch_json_sync(
                    f"https://www.reddit.com/r/{sub}/hot.json",
                    params={"limit": "10", "raw_json": "1"},
                    headers={"User-Agent": "STRATEGOS/1.0 (intelligence platform)"},
                )

                posts = data.get("data", {}).get("children", [])
                for post in posts:
                    d = post.get("data", {})
                    title = d.get("title", "")
                    score = d.get("score", 0)
                    num_comments = d.get("num_comments", 0)
                    upvote_ratio = d.get("upvote_ratio", 0.5)

                    relevance = _estimate_relevance(title)
                    if relevance < 0.3:
                        continue

                    engagement = min(1.0, (score + num_comments * 2) / 5000)
                    controversy = 1.0 - abs(upvote_ratio - 0.5) * 2

                    norm_score = (relevance * 0.4 + engagement * 0.4 + controversy * 0.2) - 0.5
                    alert = engagement > 0.7 and relevance > 0.5

                    signals.append(SignalNormalizer.normalize(
                        layer="L2",
                        source_name=f"Reddit/r/{sub}",
                        raw_value=float(score),
                        normalized_score=max(-1.0, min(1.0, norm_score)),
                        content=f"[r/{sub}] {title[:300]} (score: {score}, comments: {num_comments})",
                        confidence=min(0.65, relevance * 0.7),
                        alert_flag=alert,
                        alert_severity="WARNING" if alert else None,
                        raw_payload={
                            "subreddit": sub,
                            "title": title,
                            "score": score,
                            "num_comments": num_comments,
                            "upvote_ratio": upvote_ratio,
                            "relevance": relevance,
                            "url": d.get("url", ""),
                        },
                    ))

            except Exception as inner_e:
                logger.warning("Reddit failed for r/%s: %s", sub, inner_e)
                continue

        cb_reddit.record_success()
    except Exception as e:
        cb_reddit.record_failure()
        logger.error("L2 Reddit error: %s", e)

    return signals


@celery_app.task(name="app.workers.l2_social.ingest")
def ingest():
    """L2 ingestion entrypoint."""
    all_signals = _ingest_reddit()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L2 Social: ingested %d signals", count)
    return len(all_signals)
