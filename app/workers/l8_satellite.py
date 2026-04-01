"""
L8 — Satellite / Remote Sensing Signal Layer

Replaces NASA EONET (natural-events catalog — not conflict-zone EO per BRD) with:

  - NASA FIRMS: VIIRS/MODIS thermal anomalies (active fire / thermal hotspots) — free MAP_KEY
  - NASA CMR: VIIRS VNP46A2 daily nighttime lights product coverage (gap-filled NTL) — free, no key

Radiance time-series and change detection from VNP46A2 HDF lives in Phase 2 enrichment (LAADS);
here we ingest metadata-level signals suitable for Celery without heavy GIS pipelines.

Ingestion schedule: every 600 seconds (10 minutes)
Weight: 1.2 (ground truth — orbital observations)
"""

import logging
from datetime import datetime, timedelta, timezone

import httpx

from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_text_sync, DEFAULT_HEADERS
from app.workers.store import store_signals
from app.core.config import get_settings

logger = logging.getLogger("strategos.l8")
settings = get_settings()

cb_firms = CircuitBreaker("L8-FIRMS")
cb_viirs_nl = CircuitBreaker("L8-VIIRS-NTL")

# west,south,east,north for NASA FIRMS Area API and CMR bounding_box
CONFLICT_REGIONS = {
    "ukraine": {"bbox": "22,44,40,53", "conflict": "Russia-Ukraine War"},
    "gaza": {"bbox": "33.5,30.5,35.5,32.5", "conflict": "Gaza Conflict"},
    "sudan": {"bbox": "21.8,3.5,38.6,22", "conflict": "Sudan Civil War"},
    "myanmar": {"bbox": "92.2,9.8,101.2,28.5", "conflict": "Myanmar Civil War"},
    "sahel": {"bbox": "-10,10,15,25", "conflict": "Sahel Instability"},
    "yemen": {"bbox": "42,12,54,19", "conflict": "Yemen/Houthi Conflict"},
}


def _firms_csv_url(map_key: str, source: str, bbox: str, day_range: int = 3) -> str:
    return (
        f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{map_key}/{source}/{bbox}/{day_range}"
    )


def _count_firms_csv_rows(csv_text: str) -> int:
    lines = [ln.strip() for ln in csv_text.strip().splitlines() if ln.strip()]
    if not lines:
        return 0
    # Header usually contains latitude or confidence
    start = 1 if "latitude" in lines[0].lower() or "lat" in lines[0].lower() else 0
    return max(0, len(lines) - start)


def _ingest_firms_thermal() -> list[dict]:
    """NASA FIRMS area CSV — thermal fire / hotspot detections (VIIRS SNPP NRT)."""
    signals: list[dict] = []
    map_key = (settings.NASA_FIRMS_MAP_KEY or "").strip()
    if not map_key:
        logger.info(
            "L8 FIRMS skipped: set NASA_FIRMS_MAP_KEY (free: "
            "https://firms.modaps.eosdis.nasa.gov/api/map_key/)"
        )
        return signals

    if cb_firms.is_open:
        logger.warning("Circuit breaker open for FIRMS, skipping")
        return signals

    source = "VIIRS_SNPP_NRT"
    try:
        for region_key, meta in CONFLICT_REGIONS.items():
            try:
                url = _firms_csv_url(map_key, source, meta["bbox"], day_range=3)
                text = fetch_text_sync(url, timeout=25.0)
                n = _count_firms_csv_rows(text)
                if n > 25:
                    score = -0.65
                    alert = True
                    severity = "WARNING"
                elif n > 8:
                    score = -0.35
                    alert = True
                    severity = "WARNING"
                elif n > 0:
                    score = -0.15
                    alert = False
                    severity = None
                else:
                    score = 0.05
                    alert = False
                    severity = None

                signals.append(SignalNormalizer.normalize(
                    layer="L8",
                    source_name=f"NASA-FIRMS/{source}/{region_key}",
                    raw_value=float(n),
                    normalized_score=score,
                    content=(
                        f"NASA FIRMS ({source}): {n} thermal detection(s) in {meta['conflict']} "
                        f"bbox ({region_key}) — last 3 days"
                    ),
                    confidence=0.88,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "region": region_key,
                        "conflict": meta["conflict"],
                        "bbox": meta["bbox"],
                        "detection_count": n,
                        "source": "nasa-firms",
                        "product": "thermal_anomaly",
                    },
                ))
            except Exception as inner_e:
                logger.warning("FIRMS failed for %s: %s", region_key, inner_e)
                continue

        cb_firms.record_success()
    except Exception as e:
        cb_firms.record_failure()
        logger.error("L8 FIRMS error: %s", e)

    return signals


def _cmr_vnp46a2_hits(bbox: str, days: int = 7) -> int:
    """Granule count for VNP46A2 (VIIRS daily nighttime lights) from CMR (metadata only)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    temporal = f"{start.strftime('%Y-%m-%dT%H:%M:%SZ')},{end.strftime('%Y-%m-%dT%H:%M:%SZ')}"
    merged = {**DEFAULT_HEADERS}
    merged["Accept"] = "application/json"
    with httpx.Client(timeout=35.0) as client:
        resp = client.get(
            "https://cmr.earthdata.nasa.gov/search/granules.json",
            params={
                "short_name": "VNP46A2",
                "bounding_box": bbox,
                "temporal": temporal,
                "page_size": 1,
            },
            headers=merged,
        )
        resp.raise_for_status()
        hits_raw = resp.headers.get("cmr-hits") or resp.headers.get("CMR-Hits") or "0"
        return int(hits_raw)


def _ingest_viirs_nightlights() -> list[dict]:
    """
    VIIRS VNP46A2 — daily gap-filled lunar BRDF-adjusted nighttime lights (LAADS).
    Uses CMR granule hit counts over region/time (radiance requires HDF — Phase 2).
    """
    signals: list[dict] = []
    if cb_viirs_nl.is_open:
        logger.warning("Circuit breaker open for VIIRS NTL, skipping")
        return signals

    try:
        for region_key, meta in CONFLICT_REGIONS.items():
            try:
                hits = _cmr_vnp46a2_hits(meta["bbox"], days=7)
                # More overlapping granules ≈ better tile coverage for NTL product in bbox
                if hits > 40:
                    score = -0.25
                    alert = True
                    severity = "WARNING"
                elif hits > 15:
                    score = -0.1
                    alert = False
                    severity = None
                else:
                    score = 0.05
                    alert = False
                    severity = None

                signals.append(SignalNormalizer.normalize(
                    layer="L8",
                    source_name=f"VIIRS-VNP46A2-NTL/{region_key}",
                    raw_value=float(hits),
                    normalized_score=score,
                    content=(
                        f"VIIRS VNP46A2 (nighttime lights product): {hits} CMR granule(s) "
                        f"intersecting {meta['conflict']} region (7d) — metadata proxy; "
                        f"power-loss monitoring uses radiance deltas (Phase 2 LAADS/HDF)"
                    ),
                    confidence=0.52,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "region": region_key,
                        "conflict": meta["conflict"],
                        "bbox": meta["bbox"],
                        "cmr_granule_hits": hits,
                        "source": "nasa-cmr-vnp46a2",
                        "product": "nighttime_lights_metadata",
                    },
                ))
            except Exception as inner_e:
                logger.warning("VIIRS NTL CMR failed for %s: %s", region_key, inner_e)
                continue

        cb_viirs_nl.record_success()
    except Exception as e:
        cb_viirs_nl.record_failure()
        logger.error("L8 VIIRS NTL error: %s", e)

    return signals


@celery_app.task(name="app.workers.l8_satellite.ingest")
def ingest():
    """L8: NASA FIRMS thermal + VIIRS VNP46A2 nighttime-lights (CMR metadata)."""
    all_signals = _ingest_firms_thermal() + _ingest_viirs_nightlights()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L8 Satellite: ingested %d signals", count)
    return len(all_signals)
