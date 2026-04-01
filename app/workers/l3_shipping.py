"""
L3 — Shipping & Maritime Signal Layer (Phase 2)

BRD: MarineTraffic AIS, chokepoint traffic, shipping-lane anomalies (commercial API / cost).

This layer is NOT implemented in Phase 1. Do not substitute UN Comtrade or Wikipedia —
Comtrade belongs under economic/trade indicators (L9); Wikipedia is not a maritime signal.

When Phase 2 ships: integrate MarineTraffic (or equivalent AIS) with real vessel/AIS data.
"""

import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger("strategos.l3")


@celery_app.task(name="app.workers.l3_shipping.ingest")
def ingest():
    """
    Phase 2 placeholder — no synthetic shipping signals.

    UN Comtrade ingestion lives under L9 (economic / trade flows).
    """
    logger.debug(
        "L3 Shipping: not implemented — Phase 2 (MarineTraffic AIS / chokepoint AIS). "
        "No signals emitted."
    )
    return 0
