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
    deviation_pct: float | None = None
    confidence: float
    source_name: str
    content: str | None
    latitude: float | None = None
    longitude: float | None = None


class LayerStatus(BaseModel):
    layer: str
    status: str          # ACTIVE | DEGRADED | OFFLINE
    last_signal_at: datetime | None
    signal_count_24h: int


@router.get("/signals", response_model=list[SignalResponse])
async def list_signals(
    layer: str | None = Query(None, description="Filter by layer (L1-L10)"),
    conflict_id: str | None = Query(None),
    alert_only: bool = Query(False, description="Show only ALERT/WATCH signals"),
    limit: int = Query(50, le=200),
):
    """List signals with optional filters."""
    async for db in get_db():
        conditions = []
        params: dict = {}

        if layer:
            conditions.append("layer = :layer")
            params["layer"] = layer
        if conflict_id:
            conditions.append("conflict_id = :conflict_id")
            params["conflict_id"] = conflict_id
        if alert_only:
            conditions.append("alert_severity IN ('ALERT', 'WATCH')")

        where = (" WHERE " + " AND ".join(conditions)) if conditions else ""
        params["limit"] = limit

        result = await db.execute(
            text(f"""
                SELECT id, layer, conflict_id, timestamp, normalized_score,
                       alert_flag, alert_severity, deviation_pct, confidence,
                       source_name, content, latitude, longitude
                FROM signals{where}
                ORDER BY timestamp DESC LIMIT :limit
            """),
            params,
        )
        rows = result.fetchall()
        return [
            SignalResponse(
                id=r.id, layer=r.layer, conflict_id=r.conflict_id,
                timestamp=r.timestamp, normalized_score=r.normalized_score,
                alert_flag=r.alert_flag, alert_severity=r.alert_severity,
                deviation_pct=r.deviation_pct, confidence=r.confidence,
                source_name=r.source_name, content=r.content,
                latitude=r.latitude, longitude=r.longitude,
            )
            for r in rows
        ]
    return []


@router.get("/signals/feed")
async def signal_feed(limit: int = Query(20, le=100)):
    """Real-time signal feed for dashboard."""
    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT id, layer, source_name, content, timestamp,
                       alert_flag, alert_severity, deviation_pct, confidence
                FROM signals
                ORDER BY timestamp DESC LIMIT :limit
            """),
            {"limit": limit},
        )
        rows = result.fetchall()
        return [
            {
                "id": str(r.id),
                "layer": r.layer,
                "source_name": r.source_name,
                "content": r.content,
                "timestamp": r.timestamp.isoformat(),
                "alert_flag": r.alert_flag,
                "alert_severity": r.alert_severity,
                "deviation_pct": r.deviation_pct,
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


@router.get("/signals/layer-status", response_model=list[LayerStatus])
async def layer_status():
    """
    Per-layer ingestion health: status, last signal time, 24h count.
    ACTIVE = signal in last 15 min (or 30 min for slow layers like L8/L9)
    DEGRADED = signal in last 2 hours
    OFFLINE = no signal in 2 hours
    """
    slow_layers = {"L8", "L9", "L3", "L4"}
    active_threshold = {
        "default": 15 * 60,
        "slow": 30 * 60,
    }

    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT layer,
                       MAX(timestamp)  AS last_signal_at,
                       COUNT(*)        AS signal_count_24h
                FROM signals
                WHERE timestamp >= NOW() - INTERVAL '24 hours'
                GROUP BY layer
            """),
        )
        rows = result.fetchall()

        from datetime import timezone
        now = datetime.now(timezone.utc)
        by_layer: dict[str, dict] = {}
        for r in rows:
            age_s = (now - r.last_signal_at.replace(tzinfo=timezone.utc)).total_seconds()
            threshold = active_threshold["slow"] if r.layer in slow_layers else active_threshold["default"]
            if age_s <= threshold:
                status = "ACTIVE"
            elif age_s <= 7200:
                status = "DEGRADED"
            else:
                status = "OFFLINE"
            by_layer[r.layer] = {
                "layer": r.layer,
                "status": status,
                "last_signal_at": r.last_signal_at,
                "signal_count_24h": r.signal_count_24h,
            }

        all_layers = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"]
        statuses = []
        for layer in all_layers:
            if layer in by_layer:
                statuses.append(LayerStatus(**by_layer[layer]))
            else:
                statuses.append(LayerStatus(
                    layer=layer, status="OFFLINE",
                    last_signal_at=None, signal_count_24h=0,
                ))
        return statuses
    return []


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
        query += " GROUP BY bucket_time, layer ORDER BY bucket_time ASC"

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
