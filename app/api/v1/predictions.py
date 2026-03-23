from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

router = APIRouter()


class PredictionResponse(BaseModel):
    id: UUID
    conflict_id: UUID
    conflict_name: str
    escalation_prob: float
    negotiation_prob: float
    stalemate_prob: float
    resolution_prob: float
    confidence: str
    convergence_score: float
    created_at: datetime


@router.get("/predictions", response_model=list[PredictionResponse])
async def list_predictions(
    confidence: str | None = Query(None, description="Filter: HIGH, MED, LOW"),
    limit: int = Query(50, le=200),
):
    """List all active predictions ranked by convergence score."""
    # TODO: Wire to database
    return []


@router.get("/predictions/{prediction_id}", response_model=PredictionResponse | None)
async def get_prediction(prediction_id: UUID):
    """Get detailed prediction for a specific conflict."""
    # TODO: Wire to database
    return None
