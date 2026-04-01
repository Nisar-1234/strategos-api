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
        "app.workers.l3_shipping",
        "app.workers.l4_aviation",
        "app.workers.l5_commodities",
        "app.workers.l6_currency",
        "app.workers.l7_equities",
        "app.workers.l8_satellite",
        "app.workers.l9_economic",
        "app.workers.l10_connectivity",
        "app.workers.convergence_worker",
        "app.workers.prediction_worker",
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
        "app.workers.l3_shipping.*": {"queue": "l3_shipping"},
        "app.workers.l4_aviation.*": {"queue": "l4_aviation"},
        "app.workers.l5_commodities.*": {"queue": "l5_commodities"},
        "app.workers.l6_currency.*": {"queue": "l6_currency"},
        "app.workers.l7_equities.*": {"queue": "l7_equities"},
        "app.workers.l8_satellite.*": {"queue": "l8_satellite"},
        "app.workers.l9_economic.*": {"queue": "l9_economic"},
        "app.workers.l10_connectivity.*": {"queue": "l10_connectivity"},
        "app.workers.convergence_worker.*": {"queue": "compute"},
        "app.workers.prediction_worker.*": {"queue": "compute"},
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
        "ingest-l3-shipping": {
            "task": "app.workers.l3_shipping.ingest",
            "schedule": 300.0,  # 5 minutes
        },
        "ingest-l4-aviation": {
            "task": "app.workers.l4_aviation.ingest",
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
        "ingest-l8-satellite": {
            "task": "app.workers.l8_satellite.ingest",
            "schedule": 600.0,  # 10 minutes
        },
        "ingest-l9-economic": {
            "task": "app.workers.l9_economic.ingest",
            "schedule": 3600.0,  # 1 hour
        },
        "ingest-l10-connectivity": {
            "task": "app.workers.l10_connectivity.ingest",
            "schedule": 120.0,  # 2 minutes
        },
        "compute-convergence-scores": {
            "task": "app.workers.convergence_worker.compute_all",
            "schedule": 300.0,  # 5 minutes
        },
        "compute-predictions": {
            "task": "app.workers.prediction_worker.compute_all",
            "schedule": 600.0,  # 10 minutes
        },
    },
)
