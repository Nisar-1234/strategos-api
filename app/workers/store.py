"""
Signal storage — writes normalized signals to PostgreSQL.

Used by all ingestion workers to persist data after normalization.
Synchronous because Celery workers run in a sync context.
"""

import logging
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.config import get_settings

logger = logging.getLogger("strategos.store")
settings = get_settings()

_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=5, max_overflow=2)


def store_signals(signals: list[dict]) -> int:
    """
    Batch-insert normalized signals into the signals table.
    Returns count of inserted rows.
    """
    if not signals:
        return 0

    with Session(_engine) as session:
        for sig in signals:
            session.execute(
                text("""
                    INSERT INTO signals (id, layer, conflict_id, timestamp, raw_value,
                        normalized_score, alert_flag, alert_severity, confidence,
                        source_name, content, raw_payload)
                    VALUES (:id, :layer, :conflict_id, :timestamp, :raw_value,
                        :normalized_score, :alert_flag, :alert_severity, :confidence,
                        :source_name, :content, :raw_payload::jsonb)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": sig["id"],
                    "layer": sig["layer"],
                    "conflict_id": sig.get("conflict_id"),
                    "timestamp": sig["timestamp"],
                    "raw_value": sig.get("raw_value"),
                    "normalized_score": sig["normalized_score"],
                    "alert_flag": sig.get("alert_flag", False),
                    "alert_severity": sig.get("alert_severity"),
                    "confidence": sig.get("confidence", 0.5),
                    "source_name": sig["source_name"],
                    "content": sig.get("content"),
                    "raw_payload": str(sig.get("raw_payload")) if sig.get("raw_payload") else None,
                },
            )
        session.commit()

    count = len(signals)
    logger.info("Stored %d signals", count)
    return count


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
