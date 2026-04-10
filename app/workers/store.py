"""
Signal storage — writes normalized signals to PostgreSQL + publishes to Redis.

Used by all ingestion workers. Synchronous because Celery runs in a sync context.
After each batch write, publishes per-conflict and global alert channels so the
WebSocket layer can push updates to connected dashboard clients.
"""

import json
import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.workers.badge_engine import compute_badge

logger = logging.getLogger("strategos.store")
settings = get_settings()

_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5, max_overflow=2)


def _get_redis():
    """Lazy Redis client — only imported when first needed."""
    import redis as _redis
    return _redis.from_url(settings.REDIS_URL, socket_timeout=2, decode_responses=True)


def store_signals(signals: list[dict]) -> int:
    """
    Batch-insert normalized signals, compute badge scores, and publish
    to Redis pub/sub channels for WebSocket delivery.
    Returns count of inserted rows.
    """
    if not signals:
        return 0

    with Session(_engine) as session:
        published: list[dict] = []

        for sig in signals:
            # Compute deviation badge before insert so it lands in DB
            deviation_pct, alert_severity = compute_badge(
                layer=sig["layer"],
                conflict_id=sig.get("conflict_id"),
                raw_value=sig.get("raw_value"),
                session=session,
            )
            sig["deviation_pct"] = deviation_pct
            sig["alert_severity"] = alert_severity
            sig["alert_flag"] = alert_severity in ("ALERT", "WATCH")

            raw = sig.get("raw_payload")
            payload_str = json.dumps(raw) if raw else None

            session.execute(
                text("""
                    INSERT INTO signals (
                        id, layer, conflict_id, timestamp, raw_value,
                        normalized_score, alert_flag, alert_severity, confidence,
                        source_name, content, raw_payload, deviation_pct,
                        latitude, longitude
                    )
                    VALUES (
                        :id, :layer, :conflict_id, :timestamp, :raw_value,
                        :normalized_score, :alert_flag, :alert_severity, :confidence,
                        :source_name, :content, CAST(:raw_payload AS jsonb), :deviation_pct,
                        :latitude, :longitude
                    )
                    ON CONFLICT (id, timestamp) DO NOTHING
                """),
                {
                    "id": sig["id"],
                    "layer": sig["layer"],
                    "conflict_id": sig.get("conflict_id"),
                    "timestamp": sig["timestamp"],
                    "raw_value": sig.get("raw_value"),
                    "normalized_score": sig["normalized_score"],
                    "alert_flag": sig.get("alert_flag", False),
                    "alert_severity": sig.get("alert_severity", "NORMAL"),
                    "confidence": sig.get("confidence", 0.5),
                    "source_name": sig["source_name"],
                    "content": sig.get("content"),
                    "raw_payload": payload_str,
                    "deviation_pct": sig.get("deviation_pct"),
                    "latitude": sig.get("latitude"),
                    "longitude": sig.get("longitude"),
                },
            )
            published.append(sig)

        session.commit()

    _publish_to_redis(published)
    logger.info("Stored %d signals", len(signals))
    return len(signals)


def _publish_to_redis(signals: list[dict]) -> None:
    """Publish new signals to Redis pub/sub so WebSocket clients get live updates."""
    if not signals:
        return
    try:
        r = _get_redis()
        pipe = r.pipeline(transaction=False)
        for sig in signals:
            payload = json.dumps({
                "id": sig["id"],
                "layer": sig["layer"],
                "source_name": sig["source_name"],
                "content": sig.get("content"),
                "timestamp": sig["timestamp"],
                "alert_flag": sig.get("alert_flag", False),
                "alert_severity": sig.get("alert_severity", "NORMAL"),
                "deviation_pct": sig.get("deviation_pct", 0.0),
                "normalized_score": sig["normalized_score"],
                "conflict_id": sig.get("conflict_id"),
            })
            conflict_id = sig.get("conflict_id")
            if conflict_id:
                pipe.publish(f"ws:signal:{conflict_id}", payload)
            if sig.get("alert_flag"):
                pipe.publish("ws:alert", payload)
        pipe.execute()
    except Exception as exc:
        logger.debug("Redis publish skipped: %s", exc)


def get_latest_value(layer: str, source_name: str) -> float | None:
    """Fetch the most recent raw_value for a source. Used as baseline for alert detection."""
    with Session(_engine) as session:
        result = session.execute(
            text("""
                SELECT raw_value FROM signals
                WHERE layer = :layer AND source_name = :source_name
                ORDER BY timestamp DESC LIMIT 1
            """),
            {"layer": layer, "source_name": source_name},
        )
        row = result.fetchone()
        return row[0] if row else None
