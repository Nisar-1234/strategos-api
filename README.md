# STRATEGOS API

Multi-Source Ground Truth Intelligence Platform — Backend

## Quick Start

### Prerequisites
- Python 3.12+
- Docker & Docker Compose (for PostgreSQL + Redis)

### Setup

```bash
# 1. Clone and enter
git clone https://github.com/Nisar-1234/strategos-api.git
cd strategos-api

# 2. Create virtual environment
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/Mac

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy environment config
cp .env.example .env
# Edit .env with your API keys

# 5. Start infrastructure
docker compose up -d db redis

# 6. Run migrations
alembic upgrade head

# 7. Seed initial data
python scripts/seed_data.py

# 8. Start the API server
uvicorn app.main:app --reload --port 8000

# 9. Start Celery worker (separate terminal)
celery -A app.workers.celery_app worker --loglevel=info

# 10. Start Celery beat scheduler (separate terminal)
celery -A app.workers.celery_app beat --loglevel=info
```

### API Docs
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/api/v1/health

## Architecture

```
app/
├── api/v1/          # FastAPI route handlers
│   ├── health.py    # GET /api/v1/health
│   ├── signals.py   # Signal CRUD + feed
│   ├── predictions.py
│   ├── conflicts.py
│   ├── game_theory.py
│   └── chat.py      # AI analysis endpoint
├── core/
│   ├── config.py    # Pydantic settings (env vars)
│   └── database.py  # Async SQLAlchemy engine
├── models/
│   └── signal.py    # All SQLAlchemy ORM models
├── services/
│   ├── convergence.py    # Convergence Score engine
│   ├── llm_gateway.py    # LLM abstraction (Claude + GPT-4o)
│   └── bias_registry.py  # Source bias seed data
├── workers/
│   ├── celery_app.py     # Celery config + beat schedule
│   ├── base.py           # CircuitBreaker + SignalNormalizer
│   ├── store.py          # Signal persistence layer
│   ├── l1_editorial.py   # GDELT + NewsAPI
│   ├── l2_social.py      # Reddit
│   ├── l5_commodities.py # Gold, Oil, Silver, Platinum
│   ├── l6_currency.py    # FX rates (11 currencies)
│   ├── l7_equities.py    # Defense stocks + VIX
│   └── l10_connectivity.py # Cloudflare Radar + IODA
└── websocket/

migrations/          # Alembic database migrations
scripts/
└── seed_data.py     # Seed conflicts + signal sources
```

## Signal Layers (Phase 1)

| Layer | Name | Source | Schedule |
|-------|------|--------|----------|
| L1 | Editorial Media | GDELT, NewsAPI | 5 min |
| L2 | Social Media | Reddit | 5 min |
| L5 | Commodities | Alpha Vantage, Metals-API | 1 min |
| L6 | Currency/FX | Open Exchange Rates | 5 min |
| L7 | Equities | Alpha Vantage | 1 min |
| L10 | Connectivity | Cloudflare Radar, IODA | 2 min |
