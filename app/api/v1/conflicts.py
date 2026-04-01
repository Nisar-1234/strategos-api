from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID
from sqlalchemy import text
from app.core.database import get_db

router = APIRouter()


class ConflictResponse(BaseModel):
    id: UUID
    name: str
    region: str
    status: str
    description: str | None
    created_at: datetime


@router.get("/conflicts", response_model=list[ConflictResponse])
async def list_conflicts(
    status: str | None = Query(None, description="Filter: active, resolved, monitoring"),
    region: str | None = Query(None),
):
    """List all monitored conflicts."""
    async for db in get_db():
        query = "SELECT id, name, region, status, description, created_at FROM conflicts"
        conditions = []
        params: dict = {}

        if status:
            conditions.append("status = :status")
            params["status"] = status
        if region:
            conditions.append("region = :region")
            params["region"] = region

        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY created_at DESC"

        result = await db.execute(text(query), params)
        rows = result.fetchall()
        return [
            ConflictResponse(
                id=r.id, name=r.name, region=r.region,
                status=r.status, description=r.description,
                created_at=r.created_at,
            )
            for r in rows
        ]
    return []


@router.get("/conflicts/{conflict_id}", response_model=ConflictResponse)
async def get_conflict(conflict_id: UUID):
    """Get conflict details."""
    async for db in get_db():
        result = await db.execute(
            text("SELECT id, name, region, status, description, created_at FROM conflicts WHERE id = :id"),
            {"id": str(conflict_id)},
        )
        row = result.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Conflict not found")
        return ConflictResponse(
            id=row.id, name=row.name, region=row.region,
            status=row.status, description=row.description,
            created_at=row.created_at,
        )
    raise HTTPException(status_code=500, detail="Database unavailable")


@router.get("/conflicts/{conflict_id}/convergence")
async def get_convergence_history(conflict_id: UUID, days: int = Query(30, le=90)):
    """Get convergence score history for a conflict."""
    async for db in get_db():
        result = await db.execute(
            text("""
                SELECT timestamp, score, layer_contributions
                FROM convergence_scores
                WHERE conflict_id = :cid
                  AND timestamp >= NOW() - INTERVAL '1 day' * :days
                ORDER BY timestamp ASC
            """),
            {"cid": str(conflict_id), "days": days},
        )
        rows = result.fetchall()
        return {
            "conflict_id": str(conflict_id),
            "scores": [
                {
                    "timestamp": r.timestamp.isoformat(),
                    "score": r.score,
                    "layer_contributions": r.layer_contributions,
                }
                for r in rows
            ],
        }
    return {"conflict_id": str(conflict_id), "scores": []}
