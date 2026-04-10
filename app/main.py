from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1 import health, signals, predictions, conflicts, game_theory, chat
from app.api.v1 import settings as settings_router
from app.api.v1 import ws as ws_router

app_settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.core.database import engine, Base
    from app.models.signal import Signal, Conflict, Prediction, ConvergenceScore  # noqa: F401
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title=app_settings.PROJECT_NAME,
    description="Multi-Source Ground Truth Intelligence Platform API",
    version="0.4.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=app_settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=app_settings.API_V1_PREFIX, tags=["Health"])
app.include_router(signals.router, prefix=app_settings.API_V1_PREFIX, tags=["Signals"])
app.include_router(predictions.router, prefix=app_settings.API_V1_PREFIX, tags=["Predictions"])
app.include_router(conflicts.router, prefix=app_settings.API_V1_PREFIX, tags=["Conflicts"])
app.include_router(game_theory.router, prefix=app_settings.API_V1_PREFIX, tags=["Game Theory"])
app.include_router(chat.router, prefix=app_settings.API_V1_PREFIX, tags=["AI Chat"])
app.include_router(settings_router.router, prefix=app_settings.API_V1_PREFIX, tags=["Settings"])
app.include_router(ws_router.router, prefix=app_settings.API_V1_PREFIX, tags=["WebSocket"])
