from fastapi import APIRouter, Query
from pydantic import BaseModel
from datetime import datetime
from uuid import UUID

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
    # TODO: Wire to database
    return []


@router.get("/conflicts/{conflict_id}", response_model=ConflictResponse | None)
async def get_conflict(conflict_id: UUID):
    """Get conflict details."""
    # TODO: Wire to database
    return None


@router.get("/conflicts/{conflict_id}/convergence")
async def get_convergence_history(conflict_id: UUID, days: int = Query(30, le=90)):
    """Get convergence score history for a conflict."""
    # TODO: Wire to database
    return {"conflict_id": conflict_id, "scores": []}
