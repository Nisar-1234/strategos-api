"""
Prediction Worker

Generates probabilistic predictions for each conflict based on:
- Latest convergence score
- Signal layer analysis
- Historical trend

Produces escalation/negotiation/stalemate/resolution probabilities.
Runs every 10 minutes via Celery Beat.
"""

import logging
from datetime import datetime, timezone
from uuid import uuid4

import numpy as np
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger("strategos.prediction")
settings = get_settings()

_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=3, max_overflow=1)


def _compute_prediction(session: Session, conflict_id: str) -> dict | None:
    """
    Generate prediction for one conflict.
    
    Uses signal statistics + convergence score to derive outcome probabilities.
    """
    conv_row = session.execute(
        text("""
            SELECT score, layer_contributions
            FROM convergence_scores
            WHERE conflict_id = :cid
            ORDER BY timestamp DESC
            LIMIT 1
        """),
        {"cid": conflict_id},
    ).fetchone()

    convergence = conv_row.score if conv_row else 5.0

    sig_result = session.execute(
        text("""
            SELECT AVG(normalized_score) AS avg_score,
                   STDDEV(normalized_score) AS std_score,
                   AVG(confidence) AS avg_conf,
                   COUNT(*) AS total,
                   SUM(CASE WHEN alert_flag THEN 1 ELSE 0 END) AS alerts,
                   COUNT(DISTINCT layer) AS n_layers
            FROM signals
            WHERE timestamp >= NOW() - INTERVAL '24 hours'
        """),
    ).fetchone()

    if not sig_result or sig_result.total == 0:
        return None

    avg_score = float(sig_result.avg_score or 0)
    std_score = float(sig_result.std_score or 0.5)
    avg_conf = float(sig_result.avg_conf or 0.5)
    alert_ratio = sig_result.alerts / max(sig_result.total, 1)
    n_layers = sig_result.n_layers

    escalation_raw = (0.5 - avg_score * 0.3) + alert_ratio * 0.3 + (convergence / 10) * 0.2
    negotiation_raw = (0.3 + avg_score * 0.25) * (1 - alert_ratio * 0.5)
    stalemate_raw = 0.15 + std_score * 0.2
    resolution_raw = max(0.05, 0.1 + avg_score * 0.15 - alert_ratio * 0.1)

    total = escalation_raw + negotiation_raw + stalemate_raw + resolution_raw
    escalation = round(escalation_raw / total, 3)
    negotiation = round(negotiation_raw / total, 3)
    stalemate = round(stalemate_raw / total, 3)
    resolution = round(1.0 - escalation - negotiation - stalemate, 3)

    if n_layers >= 6 and sig_result.total > 50:
        confidence = "HIGH"
    elif n_layers >= 3 and sig_result.total > 15:
        confidence = "MED"
    else:
        confidence = "LOW"

    return {
        "conflict_id": conflict_id,
        "escalation_prob": max(0, escalation),
        "negotiation_prob": max(0, negotiation),
        "stalemate_prob": max(0, stalemate),
        "resolution_prob": max(0, resolution),
        "confidence": confidence,
        "convergence_score": convergence,
    }


@celery_app.task(name="app.workers.prediction_worker.compute_all")
def compute_all():
    """Generate predictions for all active conflicts."""
    now = datetime.now(timezone.utc)

    with Session(_engine) as session:
        conflicts = session.execute(
            text("SELECT id FROM conflicts WHERE status IN ('active', 'monitoring')")
        ).fetchall()

        count = 0
        for conflict in conflicts:
            result = _compute_prediction(session, str(conflict.id))
            if result is None:
                continue

            session.execute(
                text("""
                    INSERT INTO predictions
                        (id, conflict_id, escalation_prob, negotiation_prob,
                         stalemate_prob, resolution_prob, confidence,
                         convergence_score, created_at)
                    VALUES (:id, :cid, :esc, :neg, :stale, :res, :conf, :conv, :now)
                """),
                {
                    "id": str(uuid4()),
                    "cid": result["conflict_id"],
                    "esc": result["escalation_prob"],
                    "neg": result["negotiation_prob"],
                    "stale": result["stalemate_prob"],
                    "res": result["resolution_prob"],
                    "conf": result["confidence"],
                    "conv": result["convergence_score"],
                    "now": now,
                },
            )
            count += 1

        session.commit()

    logger.info("Generated predictions for %d conflicts", count)
    return {"predicted": count}
