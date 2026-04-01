from fastapi import APIRouter
from datetime import datetime, timezone
from sqlalchemy import text

from app.core.database import get_db
from app.core.config import get_settings

router = APIRouter()
settings = get_settings()


@router.get("/health")
async def health_check():
    db_ok = False
    signal_count = 0
    redis_ok = False

    try:
        async for db in get_db():
            result = await db.execute(text("SELECT COUNT(*) FROM signals"))
            signal_count = result.scalar() or 0
            db_ok = True
    except Exception:
        pass

    try:
        import redis
        r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
        r.ping()
        redis_ok = True
    except Exception:
        pass

    layer_query = {}
    if db_ok:
        try:
            async for db in get_db():
                result = await db.execute(
                    text("""
                        SELECT layer, COUNT(*) as cnt,
                               MAX(timestamp) as last_seen
                        FROM signals
                        GROUP BY layer
                    """)
                )
                for r in result.fetchall():
                    age_seconds = (datetime.now(timezone.utc) - r.last_seen.replace(tzinfo=timezone.utc)).total_seconds() if r.last_seen else 99999
                    status = "active" if age_seconds < 600 else "stale" if age_seconds < 3600 else "inactive"
                    layer_query[f"{r.layer}"] = status
        except Exception:
            pass

    all_layers = ["L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8", "L9", "L10"]
    layers = {}
    for layer in all_layers:
        if layer in layer_query:
            layers[layer] = layer_query[layer]
        else:
            layers[layer] = "no_data"

    status = "healthy" if db_ok and redis_ok else "degraded" if db_ok or redis_ok else "unhealthy"

    return {
        "status": status,
        "service": "strategos-api",
        "version": "0.3.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": "connected" if db_ok else "disconnected",
        "redis": "connected" if redis_ok else "disconnected",
        "total_signals": signal_count,
        "layers": layers,
    }
