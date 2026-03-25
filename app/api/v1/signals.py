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
