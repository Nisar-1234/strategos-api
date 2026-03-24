from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.api.v1 import health, signals, predictions, conflicts, game_theory, chat

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Multi-Source Ground Truth Intelligence Platform API",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix=settings.API_V1_PREFIX, tags=["Health"])
app.include_router(signals.router, prefix=settings.API_V1_PREFIX, tags=["Signals"])
app.include_router(predictions.router, prefix=settings.API_V1_PREFIX, tags=["Predictions"])
app.include_router(conflicts.router, prefix=settings.API_V1_PREFIX, tags=["Conflicts"])
app.include_router(game_theory.router, prefix=settings.API_V1_PREFIX, tags=["Game Theory"])
app.include_router(chat.router, prefix=settings.API_V1_PREFIX, tags=["AI Chat"])
