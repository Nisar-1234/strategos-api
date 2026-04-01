"""
L2 — Social Media Signal Layer

Primary (BRD): Telegram channel monitoring via Telethon — critical for conflict zones.
Supplementary: Reddit public JSON (no auth), optional future PRAW/X.

Ingestion schedule: every 300 seconds (5 minutes)
Weight: 0.6 (high noise — requires bot/spam filtering)
"""

import asyncio
import logging

from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals
from app.core.config import get_settings

logger = logging.getLogger("strategos.l2")
settings = get_settings()

cb_reddit = CircuitBreaker("L2-Reddit")
cb_telegram = CircuitBreaker("L2-Telegram")

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
    words = set(title.lower().split())
    hits = len(words & CONFLICT_KEYWORDS)
    return min(1.0, hits / 3.0)


def _ingest_reddit() -> list[dict]:
    """Supplementary: hot posts from geopolitics subreddits via public JSON API."""
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
                            "role": "supplementary",
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


async def _ingest_telegram_async() -> list[dict]:
    """Primary L2: recent messages from configured Telegram channels."""
    from telethon import TelegramClient
    from telethon.sessions import StringSession

    signals: list[dict] = []
    api_id = (settings.TELEGRAM_API_ID or "").strip()
    api_hash = (settings.TELEGRAM_API_HASH or "").strip()
    session_str = (settings.TELEGRAM_SESSION_STRING or "").strip()
    raw_channels = (settings.TELEGRAM_CHANNELS or "").strip()

    if not api_id or not api_hash:
        logger.info("L2 Telegram skipped: set TELEGRAM_API_ID and TELEGRAM_API_HASH")
        return signals
    if not session_str:
        logger.info(
            "L2 Telegram skipped: set TELEGRAM_SESSION_STRING "
            "(run: python scripts/telegram_session_setup.py)"
        )
        return signals

    channels = [c.strip() for c in raw_channels.split(",") if c.strip()]
    if not channels:
        logger.info("L2 Telegram skipped: set TELEGRAM_CHANNELS (comma-separated @channels or IDs)")
        return signals

    client = TelegramClient(
        StringSession(session_str),
        int(api_id),
        api_hash,
    )
    await client.connect()
    if not await client.is_user_authorized():
        logger.error("L2 Telegram: session not authorized — regenerate TELEGRAM_SESSION_STRING")
        await client.disconnect()
        return signals

    try:
        for ch in channels:
            try:
                async for msg in client.iter_messages(ch, limit=12):
                    text = (msg.message or "").strip()
                    if not text:
                        continue
                    relevance = _estimate_relevance(text)
                    if relevance < 0.25:
                        continue
                    views = getattr(msg, "views", None) or 0
                    engagement = min(1.0, (float(views) / 50000.0) + 0.2) if views else 0.35
                    norm_score = (relevance * 0.55 + engagement * 0.45) - 0.45
                    alert = relevance > 0.55 and engagement > 0.5
                    peer = getattr(msg, "chat", None)
                    label = getattr(peer, "username", None) or ch
                    signals.append(SignalNormalizer.normalize(
                        layer="L2",
                        source_name=f"Telegram/{label}",
                        raw_value=float(views or msg.id),
                        normalized_score=max(-1.0, min(1.0, norm_score)),
                        content=f"[TG @{label}] {text[:400]}",
                        confidence=min(0.72, 0.45 + relevance * 0.35),
                        alert_flag=alert,
                        alert_severity="WARNING" if alert else None,
                        raw_payload={
                            "channel": ch,
                            "message_id": msg.id,
                            "views": views,
                            "relevance": relevance,
                            "role": "primary",
                        },
                    ))
            except Exception as inner_e:
                logger.warning("Telegram channel %s: %s", ch, inner_e)
                continue
    finally:
        await client.disconnect()

    return signals


def _ingest_telegram() -> list[dict]:
    if cb_telegram.is_open:
        logger.warning("Circuit breaker open for Telegram, skipping")
        return []
    try:
        out = asyncio.run(_ingest_telegram_async())
        cb_telegram.record_success()
        return out
    except Exception as e:
        cb_telegram.record_failure()
        logger.error("L2 Telegram error: %s", e)
        return []


@celery_app.task(name="app.workers.l2_social.ingest")
def ingest():
    """L2 ingestion: Telegram first (primary), then Reddit (supplementary)."""
    all_signals = _ingest_telegram() + _ingest_reddit()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L2 Social: ingested %d signals", count)
    return len(all_signals)
