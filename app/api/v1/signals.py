from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter()


class SignalResponse(BaseModel):
    id: UUID
    layer: str
    conflict_id: UUID | None = None
    timestamp: datetime
    normalized_score: float
    alert_flag: bool
    alert_severity: str | None
    confidence: float
    source_name: str
    content: str | None


@router.get("/signals", response_model=list[SignalResponse])
async def list_signals(
    layer: str | None = Query(None, description="Filter by layer (L1-L10)"),
    alert_only: bool = Query(False, description="Show only alert signals"),
    limit: int = Query(50, le=200),
):
    """List signals across all layers with optional filters."""
    async for db in get_db():
        query = "SELECT id, layer, conflict_id, timestamp, normalized_score, alert_flag, alert_severity, confidence, source_name, content FROM signals"
        conditions = []
        params: dict = {}

        if layer:
            conditions.append("layer = :layer")
            params["layer"] = layer
        if alert_only:
            conditions.append("alert_flag = true")

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp DESC LIMIT :limit"
        params["limit"] = limit

        result = await db.execute(text(query), params)
        rows = result.fetchall()
        return [
            SignalResponse(
                id=r.id, layer=r.layer, conflict_id=r.conflict_id,
                timestamp=r.timestamp, normalized_score=r.normalized_score,
                alert_flag=r.alert_flag, alert_severity=r.alert_severity,
                confidence=r.confidence, source_name=r.source_name,
                content=r.content,
            )
            for r in rows
        ]
    return []


@router.get("/signals/feed")
async def signal_feed(limit: int = Query(20, le=100)):
    """Real-time signal feed for dashboard."""
    async for db in get_db():
        result = await db.execute(
            text("SELECT id, layer, source_name, content, timestamp, alert_flag, alert_severity, confidence FROM signals ORDER BY timestamp DESC LIMIT :limit"),
            {"limit": limit},
        )
        rows = result.fetchall()
        return [
            {
                "id": str(r.id), "layer": r.layer, "source_name": r.source_name,
                "content": r.content, "timestamp": r.timestamp.isoformat(),
                "alert_flag": r.alert_flag, "alert_severity": r.alert_severity,
                "confidence": r.confidence,
            }
            for r in rows
        ]
    return []


@router.get("/signals/count")
async def signal_count():
    """Quick count of signals per layer."""
    async for db in get_db():
        result = await db.execute(text("SELECT layer, count(*) as cnt FROM signals GROUP BY layer ORDER BY layer"))
        rows = result.fetchall()
        return {r.layer: r.cnt for r in rows}
    return {}


@router.get("/signals/timeseries")
async def signal_timeseries(
    layer: str | None = Query(None, description="Filter by layer"),
    days: int = Query(30, le=90),
    bucket: str = Query("1d", description="Time bucket: 1h, 6h, 1d"),
):
    """Aggregated signal timeseries for trend analysis."""
    interval_map = {"1h": "1 hour", "6h": "6 hours", "1d": "1 day"}
    interval = interval_map.get(bucket, "1 day")

    async for db in get_db():
        query = f"""
            SELECT
                date_trunc('hour', timestamp) +
                    (EXTRACT(EPOCH FROM date_trunc('hour', timestamp))::int %
                     EXTRACT(EPOCH FROM INTERVAL '{interval}')::int) * INTERVAL '1 second' AS bucket_time,
                COALESCE(layer, 'ALL') AS layer,
                COUNT(*) AS signal_count,
                AVG(normalized_score) AS avg_score,
                AVG(confidence) AS avg_confidence,
                SUM(CASE WHEN alert_flag THEN 1 ELSE 0 END) AS alert_count
            FROM signals
            WHERE timestamp >= NOW() - INTERVAL '1 day' * :days
        """
        params: dict = {"days": days}
        if layer:
            query += " AND layer = :layer"
            params["layer"] = layer
        query += f"""
            GROUP BY bucket_time, layer
            ORDER BY bucket_time ASC
        """

        result = await db.execute(text(query), params)
        rows = result.fetchall()
        return [
            {
                "timestamp": r.bucket_time.isoformat() if r.bucket_time else None,
                "layer": r.layer,
                "signal_count": r.signal_count,
                "avg_score": round(r.avg_score, 4) if r.avg_score else 0,
                "avg_confidence": round(r.avg_confidence, 4) if r.avg_confidence else 0,
                "alert_count": r.alert_count,
            }
            for r in rows
        ]
    return []
