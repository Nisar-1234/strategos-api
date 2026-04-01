"""
Convergence Score Worker

Computes a composite convergence score (0-10) for each conflict
by aggregating signals from all available layers.

The convergence score represents how many independent signal layers
are pointing in the same direction (convergent = high score).

Runs every 5 minutes via Celery Beat.
"""

import logging
import json
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.workers.celery_app import celery_app

logger = logging.getLogger("strategos.convergence")
settings = get_settings()

_engine = create_engine(settings.DATABASE_URL_SYNC, pool_size=3, max_overflow=1)


def _compute_for_conflict(session: Session, conflict_id: str) -> dict | None:
    """
    Compute convergence score for one conflict.
    
    Algorithm:
    1. Pull latest signals per layer (last 6 hours)
    2. For each layer, compute average normalized_score
    3. Weight by LAYER_WEIGHTS
    4. Measure directional alignment across layers
    5. Scale to 0-10
    """
    result = session.execute(
        text("""
            SELECT layer, 
                   AVG(normalized_score) AS avg_score,
                   AVG(confidence) AS avg_confidence,
                   COUNT(*) AS signal_count,
                   SUM(CASE WHEN alert_flag THEN 1 ELSE 0 END) AS alert_count
            FROM signals
            WHERE timestamp >= NOW() - INTERVAL '6 hours'
            GROUP BY layer
        """),
    )
    rows = result.fetchall()

    if not rows:
        return None

    layer_data = {}
    weighted_scores = []
    total_weight = 0.0

    for r in rows:
        weight = settings.LAYER_WEIGHTS.get(r.layer, 0.8)
        layer_data[r.layer] = {
            "avg_score": round(r.avg_score, 4),
            "confidence": round(r.avg_confidence, 4),
            "signal_count": r.signal_count,
            "alert_count": r.alert_count,
            "weight": weight,
        }
        weighted_scores.append(r.avg_score * weight * r.avg_confidence)
        total_weight += weight

    if total_weight == 0:
        return None

    weighted_avg = sum(weighted_scores) / total_weight

    scores = [d["avg_score"] for d in layer_data.values()]
    n_negative = sum(1 for s in scores if s < -0.1)
    n_positive = sum(1 for s in scores if s > 0.1)
    n_neutral = len(scores) - n_negative - n_positive

    dominant = max(n_negative, n_positive, n_neutral)
    alignment = dominant / max(len(scores), 1)

    alert_boost = min(2.0, sum(d["alert_count"] for d in layer_data.values()) * 0.2)
    raw_score = abs(weighted_avg) * 5 + alignment * 3 + alert_boost

    convergence = round(max(0.0, min(10.0, raw_score)), 1)

    return {
        "conflict_id": conflict_id,
        "score": convergence,
        "layer_contributions": layer_data,
    }


@celery_app.task(name="app.workers.convergence_worker.compute_all")
def compute_all():
    """Compute convergence scores for all active conflicts."""
    now = datetime.now(timezone.utc)

    with Session(_engine) as session:
        conflicts = session.execute(
            text("SELECT id, name FROM conflicts WHERE status IN ('active', 'monitoring')")
        ).fetchall()

        count = 0
        for conflict in conflicts:
            result = _compute_for_conflict(session, str(conflict.id))
            if result is None:
                continue

            session.execute(
                text("""
                    INSERT INTO convergence_scores (id, conflict_id, timestamp, score, layer_contributions)
                    VALUES (:id, :cid, :ts, :score, CAST(:layers AS jsonb))
                """),
                {
                    "id": str(uuid4()),
                    "cid": result["conflict_id"],
                    "ts": now,
                    "score": result["score"],
                    "layers": json.dumps(result["layer_contributions"]),
                },
            )
            count += 1

        session.commit()

    logger.info("Computed convergence scores for %d conflicts", count)
    return {"computed": count}
