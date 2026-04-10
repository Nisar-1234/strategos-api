"""
Badge Engine — deviation-based alert classification.

For each incoming signal, computes how far the current value deviates
from the 30-day rolling baseline for that layer + conflict combination.
Returns a (deviation_pct, alert_severity) tuple used by store.py before write.

Thresholds (absolute % deviation from mean):
  |dev| > 20%  →  ALERT
  |dev| > 10%  →  WATCH
  else          →  NORMAL

Requires at least MIN_BASELINE_ROWS data points in the window; returns
NORMAL with 0.0 deviation when insufficient history exists.
"""

import logging
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("strategos.badge")

MIN_BASELINE_ROWS = 5
ALERT_THRESHOLD = 20.0
WATCH_THRESHOLD = 10.0


def compute_badge(
    layer: str,
    conflict_id: str | None,
    raw_value: float | None,
    session: Session,
) -> tuple[float, str]:
    """
    Return (deviation_pct, alert_severity) for a new signal value.
    deviation_pct is signed: positive = above baseline, negative = below.
    alert_severity is one of ALERT / WATCH / NORMAL.
    """
    if raw_value is None:
        return 0.0, "NORMAL"

    try:
        params: dict = {"layer": layer}
        where = "layer = :layer AND timestamp > NOW() - INTERVAL '30 days'"
        if conflict_id:
            where += " AND conflict_id = :cid"
            params["cid"] = conflict_id

        row = session.execute(
            text(f"""
                SELECT AVG(raw_value) AS mean,
                       STDDEV(raw_value) AS stddev,
                       COUNT(*) AS n
                FROM signals
                WHERE {where} AND raw_value IS NOT NULL
            """),
            params,
        ).fetchone()

        if not row or row.n < MIN_BASELINE_ROWS or row.mean is None or row.mean == 0:
            return 0.0, "NORMAL"

        deviation_pct = (raw_value - row.mean) / abs(row.mean) * 100.0
        abs_dev = abs(deviation_pct)

        if abs_dev >= ALERT_THRESHOLD:
            severity = "ALERT"
        elif abs_dev >= WATCH_THRESHOLD:
            severity = "WATCH"
        else:
            severity = "NORMAL"

        return round(deviation_pct, 2), severity

    except Exception as exc:
        logger.debug("Badge compute failed for %s: %s", layer, exc)
        return 0.0, "NORMAL"
