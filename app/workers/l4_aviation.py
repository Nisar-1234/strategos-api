"""
L4 — Aviation Signal Layer

Sources:
  - OpenSky Network: Free ADS-B flight data (no key for public endpoints)
  - Live flight tracking for military-significant airspace

Ingestion schedule: every 300 seconds (5 minutes)
Weight: 1.2 (ground truth — aircraft transponder data)

Key signals:
  - NOTAM zones (no-fly indicators near conflict areas)
  - Military aircraft activity in sensitive regions
  - Commercial flight diversions around conflict zones
  - Flight volume drops over conflict areas = active hostilities
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l4")
settings = get_settings()

cb_opensky = CircuitBreaker("L4-OpenSky")

MONITORED_AIRSPACES = {
    "ukraine": {
        "name": "Ukraine Airspace",
        "conflict": "Russia-Ukraine War",
        "bbox": {"lamin": 44.0, "lomin": 22.0, "lamax": 52.5, "lomax": 40.0},
        "baseline_flights": 200,
    },
    "gaza": {
        "name": "Gaza / Southern Israel",
        "conflict": "Gaza Conflict",
        "bbox": {"lamin": 30.5, "lomin": 33.5, "lamax": 32.5, "lomax": 35.5},
        "baseline_flights": 50,
    },
    "taiwan_strait": {
        "name": "Taiwan Strait",
        "conflict": "Taiwan Strait Tensions",
        "bbox": {"lamin": 22.0, "lomin": 117.0, "lamax": 26.0, "lomax": 121.0},
        "baseline_flights": 150,
    },
    "red_sea": {
        "name": "Red Sea / Yemen",
        "conflict": "Yemen/Houthi Conflict",
        "bbox": {"lamin": 12.0, "lomin": 42.0, "lamax": 20.0, "lomax": 46.0},
        "baseline_flights": 30,
    },
    "iran": {
        "name": "Iranian Airspace",
        "conflict": "Iran Nuclear Program",
        "bbox": {"lamin": 25.0, "lomin": 44.0, "lamax": 40.0, "lomax": 63.5},
        "baseline_flights": 120,
    },
    "sudan": {
        "name": "Sudan Airspace",
        "conflict": "Sudan Civil War",
        "bbox": {"lamin": 3.5, "lomin": 21.8, "lamax": 22.0, "lomax": 38.6},
        "baseline_flights": 40,
    },
    "myanmar": {
        "name": "Myanmar Airspace",
        "conflict": "Myanmar Civil War",
        "bbox": {"lamin": 9.8, "lomin": 92.2, "lamax": 28.5, "lomax": 101.2},
        "baseline_flights": 60,
    },
    "south_china_sea": {
        "name": "South China Sea",
        "conflict": "South China Sea Dispute",
        "bbox": {"lamin": 5.0, "lomin": 105.0, "lamax": 22.0, "lomax": 120.0},
        "baseline_flights": 300,
    },
}


def _ingest_opensky() -> list[dict]:
    """
    Fetch live aircraft counts over monitored conflict zones from OpenSky Network.
    Free public API: max 10 requests/10 seconds, no key required.
    """
    signals = []
    if cb_opensky.is_open:
        logger.warning("Circuit breaker open for OpenSky, skipping")
        return signals

    try:
        for region_key, meta in MONITORED_AIRSPACES.items():
            try:
                bb = meta["bbox"]
                data = fetch_json_sync(
                    "https://opensky-network.org/api/states/all",
                    params={
                        "lamin": str(bb["lamin"]),
                        "lomin": str(bb["lomin"]),
                        "lamax": str(bb["lamax"]),
                        "lomax": str(bb["lomax"]),
                    },
                    timeout=15.0,
                )

                states = data.get("states", []) or []
                flight_count = len(states)
                baseline = meta["baseline_flights"]

                source_name = f"OpenSky/{region_key}"
                prev = get_latest_value("L4", source_name)
                if prev is not None:
                    baseline = prev

                pct_change = ((flight_count - baseline) / max(baseline, 1)) * 100
                score = SignalNormalizer.pct_change_score(flight_count, baseline, cap=80.0)
                score = -score

                if pct_change < -50:
                    alert = True
                    severity = "CRITICAL"
                    content = (
                        f"{meta['name']}: {flight_count} aircraft detected — "
                        f"{pct_change:.0f}% below baseline. Possible airspace closure."
                    )
                elif pct_change < -25:
                    alert = True
                    severity = "WARNING"
                    content = (
                        f"{meta['name']}: {flight_count} aircraft — "
                        f"{pct_change:.0f}% below normal. Flight diversions likely."
                    )
                elif pct_change > 50:
                    alert = True
                    severity = "WARNING"
                    content = (
                        f"{meta['name']}: {flight_count} aircraft — "
                        f"{pct_change:+.0f}% above baseline. Possible military surge."
                    )
                else:
                    alert = False
                    severity = None
                    content = (
                        f"{meta['name']}: {flight_count} aircraft tracked. "
                        f"Normal range ({pct_change:+.0f}% vs baseline)."
                    )

                on_ground = sum(1 for s in states if s[8] is True) if states else 0

                signals.append(SignalNormalizer.normalize(
                    layer="L4",
                    source_name=source_name,
                    raw_value=float(flight_count),
                    normalized_score=score,
                    content=content,
                    confidence=0.90,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "region": region_key,
                        "region_name": meta["name"],
                        "conflict": meta["conflict"],
                        "flight_count": flight_count,
                        "on_ground": on_ground,
                        "baseline": meta["baseline_flights"],
                        "pct_change": round(pct_change, 1),
                        "bbox": meta["bbox"],
                        "source": "opensky-network.org",
                    },
                ))

            except Exception as inner_e:
                logger.warning("OpenSky failed for %s: %s", region_key, inner_e)
                continue

        cb_opensky.record_success()
    except Exception as e:
        cb_opensky.record_failure()
        logger.error("L4 OpenSky error: %s", e)

    return signals


@celery_app.task(name="app.workers.l4_aviation.ingest")
def ingest():
    """L4 ingestion entrypoint — called by Celery beat every 5min."""
    all_signals = _ingest_opensky()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L4 Aviation: ingested %d signals", count)
    return len(all_signals)
