from fastapi import APIRouter
from datetime import datetime, timezone

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "service": "strategos-api",
        "version": "0.1.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "layers": {
            "L1_editorial": "ready",
            "L2_social": "ready",
            "L5_commodities": "ready",
            "L6_currency": "ready",
            "L7_equities": "ready",
            "L10_connectivity": "ready",
        },
    }
