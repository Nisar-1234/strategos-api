from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from sqlalchemy import text
from app.core.database import get_db

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
    async for db in get_db():
        query = """
            SELECT p.id, p.conflict_id, c.name AS conflict_name,
                   p.escalation_prob, p.negotiation_prob, p.stalemate_prob,
                   p.resolution_prob, p.confidence, p.convergence_score, p.created_at
            FROM predictions p
            JOIN conflicts c ON c.id = p.conflict_id
        """
        conditions = []
        params: dict = {"limit": limit}

        if confidence:
            conditions.append("p.confidence = :confidence")
            params["confidence"] = confidence

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY p.convergence_score DESC, p.created_at DESC LIMIT :limit"

        result = await db.execute(text(query), params)
        rows = result.fetchall()
        return [
            PredictionResponse(
                id=r.id, conflict_id=r.conflict_id, conflict_name=r.conflict_name,
                escalation_prob=r.escalation_prob, negotiation_prob=r.negotiation_prob,
                stalemate_prob=r.stalemate_prob, resolution_prob=r.resolution_prob,
                confidence=r.confidence, convergence_score=r.convergence_score,
                created_at=r.created_at,
            )
            for r in rows
        ]
    return []


@router.get("/predictions/{prediction_id}", response_model=PredictionResponse)
async def get_prediction(prediction_id: UUID):
    """Get detailed prediction for a specific conflict."""
    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT p.id, p.conflict_id, c.name AS conflict_name,
                       p.escalation_prob, p.negotiation_prob, p.stalemate_prob,
                       p.resolution_prob, p.confidence, p.convergence_score, p.created_at
                FROM predictions p
                JOIN conflicts c ON c.id = p.conflict_id
                WHERE p.id = :pid
            """),
            {"pid": str(prediction_id)},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Prediction not found")
        return PredictionResponse(
            id=row.id, conflict_id=row.conflict_id, conflict_name=row.conflict_name,
            escalation_prob=row.escalation_prob, negotiation_prob=row.negotiation_prob,
            stalemate_prob=row.stalemate_prob, resolution_prob=row.resolution_prob,
            confidence=row.confidence, convergence_score=row.convergence_score,
            created_at=row.created_at,
        )
    raise HTTPException(status_code=500, detail="Database unavailable")
