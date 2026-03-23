from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

router = APIRouter()


class SignalResponse(BaseModel):
    id: UUID
    layer: str
    conflict_id: UUID
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
    conflict_id: UUID | None = Query(None, description="Filter by conflict"),
    alert_only: bool = Query(False, description="Show only alert signals"),
    limit: int = Query(50, le=200),
):
    """List signals across all layers with optional filters."""
    # TODO: Wire to database
    return []


@router.get("/signals/feed")
async def signal_feed(
    conflict_id: UUID | None = None,
    limit: int = Query(20, le=100),
):
    """Real-time signal feed for dashboard. Returns most recent signals across all layers."""
    # TODO: Wire to database with WebSocket upgrade
    return []
