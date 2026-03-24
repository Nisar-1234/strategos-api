import os
from celery import Celery

REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

broker_url = REDIS_URL
backend_url = REDIS_URL.rstrip("/").rsplit("/", 1)[0] + "/1" if "/" in REDIS_URL else REDIS_URL

celery_app = Celery(
    "strategos",
    broker=broker_url,
    backend=backend_url,
    include=[
        "app.workers.l1_editorial",
        "app.workers.l2_social",
        "app.workers.l5_commodities",
        "app.workers.l6_currency",
        "app.workers.l7_equities",
        "app.workers.l10_connectivity",
    ],
)

celery_app.conf.update(
    broker_connection_retry_on_startup=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_routes={
        "app.workers.l1_editorial.*": {"queue": "l1_editorial"},
        "app.workers.l2_social.*": {"queue": "l2_social"},
        "app.workers.l5_commodities.*": {"queue": "l5_commodities"},
        "app.workers.l6_currency.*": {"queue": "l6_currency"},
        "app.workers.l7_equities.*": {"queue": "l7_equities"},
        "app.workers.l10_connectivity.*": {"queue": "l10_connectivity"},
    },
    beat_schedule={
        "ingest-l1-editorial": {
            "task": "app.workers.l1_editorial.ingest",
            "schedule": 300.0,  # 5 minutes
        },
        "ingest-l2-social": {
            "task": "app.workers.l2_social.ingest",
            "schedule": 300.0,  # 5 minutes
        },
        "ingest-l5-commodities": {
            "task": "app.workers.l5_commodities.ingest",
            "schedule": 60.0,  # 1 minute
        },
        "ingest-l6-currency": {
            "task": "app.workers.l6_currency.ingest",
            "schedule": 300.0,  # 5 minutes
        },
        "ingest-l7-equities": {
            "task": "app.workers.l7_equities.ingest",
            "schedule": 60.0,  # 1 minute
        },
        "ingest-l10-connectivity": {
            "task": "app.workers.l10_connectivity.ingest",
            "schedule": 120.0,  # 2 minutes
        },
    },
)
