"""
L10 — Connectivity Signal Layer

Sources:
  - Cloudflare Radar: Internet traffic anomalies by country
  - IODA (Internet Outage Detection & Analysis): BGP route withdrawals

Ingestion schedule: every 120 seconds (2 minutes)
Weight: 1.2 (ground truth — network measurements can't be faked)

Key signals:
  - Internet traffic drops in conflict zones = active operations
  - BGP withdrawals = infrastructure targeting or government shutdowns
  - Traffic anomalies preceding media reports = early warning
"""

import logging
from datetime import datetime, timezone, timedelta
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals
from app.core.config import get_settings

logger = logging.getLogger("strategos.l10")
settings = get_settings()

cb_cloudflare = CircuitBreaker("L10-CloudflareRadar")
cb_ioda = CircuitBreaker("L10-IODA")

MONITORED_COUNTRIES = {
    "PS": {"name": "Palestine", "conflict": "Gaza Conflict"},
    "IL": {"name": "Israel", "conflict": "Gaza Conflict"},
    "UA": {"name": "Ukraine", "conflict": "Ukraine Conflict"},
    "RU": {"name": "Russia", "conflict": "Ukraine Conflict"},
    "SD": {"name": "Sudan", "conflict": "Sudan Civil War"},
    "TW": {"name": "Taiwan", "conflict": "Taiwan Strait"},
    "CN": {"name": "China", "conflict": "Taiwan Strait"},
    "IR": {"name": "Iran", "conflict": "Iran Nuclear"},
    "SY": {"name": "Syria", "conflict": "Syria Instability"},
    "MM": {"name": "Myanmar", "conflict": "Myanmar Civil War"},
    "YE": {"name": "Yemen", "conflict": "Yemen/Houthi"},
}


def _ingest_cloudflare_radar() -> list[dict]:
    """Fetch internet traffic anomalies from Cloudflare Radar API."""
    signals = []
    if cb_cloudflare.is_open:
        logger.warning("Circuit breaker open for Cloudflare Radar, skipping")
        return signals

    try:
        for code, meta in MONITORED_COUNTRIES.items():
            try:
                data = fetch_json_sync(
                    f"https://api.cloudflare.com/client/v4/radar/http/summary/http_protocol",
                    params={"location": code, "dateRange": "1d"},
                    headers={"Authorization": f"Bearer {settings.MAPBOX_TOKEN}"},
                )

                summary = data.get("result", {}).get("summary_0", {})
                http2_pct = float(summary.get("HTTP/2", 0))
                http3_pct = float(summary.get("HTTP/3", 0))
                total_pct = http2_pct + http3_pct

                if total_pct < 10:
                    score = -0.8
                    alert = True
                    severity = "CRITICAL"
                    content = f"{meta['name']} ({code}): Internet traffic severely disrupted. H2+H3={total_pct:.0f}%"
                elif total_pct < 30:
                    score = -0.4
                    alert = True
                    severity = "WARNING"
                    content = f"{meta['name']} ({code}): Degraded connectivity. H2+H3={total_pct:.0f}%"
                else:
                    score = 0.0
                    alert = False
                    severity = None
                    content = f"{meta['name']} ({code}): Normal connectivity. H2+H3={total_pct:.0f}%"

                signals.append(SignalNormalizer.normalize(
                    layer="L10",
                    source_name=f"CloudflareRadar/{code}",
                    raw_value=total_pct,
                    normalized_score=score,
                    content=content,
                    confidence=0.92,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "country_code": code,
                        "country_name": meta["name"],
                        "conflict": meta["conflict"],
                        "http2_pct": http2_pct,
                        "http3_pct": http3_pct,
                    },
                ))
            except Exception as inner_e:
                logger.warning("Cloudflare Radar failed for %s: %s", code, inner_e)
                continue

        cb_cloudflare.record_success()
    except Exception as e:
        cb_cloudflare.record_failure()
        logger.error("L10 Cloudflare Radar error: %s", e)

    return signals


def _ingest_ioda() -> list[dict]:
    """Fetch BGP/active probing outage signals from IODA."""
    signals = []
    if cb_ioda.is_open:
        logger.warning("Circuit breaker open for IODA, skipping")
        return signals

    try:
        now = datetime.now(timezone.utc)
        start = (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        end = now.strftime("%Y-%m-%dT%H:%M")

        for code, meta in MONITORED_COUNTRIES.items():
            try:
                data = fetch_json_sync(
                    f"https://api.ioda.inetintel.cc.gatech.edu/v2/signals/raw/country/{code}",
                    params={"from": start, "until": end},
                )

                entries = data.get("data", [])
                if not entries:
                    continue

                for entry in entries[-5:]:
                    source_type = entry.get("datasource", "bgp")
                    value = float(entry.get("value", 100))

                    if value < 30:
                        score = -0.9
                        alert = True
                        severity = "CRITICAL"
                    elif value < 60:
                        score = -0.5
                        alert = True
                        severity = "WARNING"
                    else:
                        score = 0.0
                        alert = False
                        severity = None

                    signals.append(SignalNormalizer.normalize(
                        layer="L10",
                        source_name=f"IODA/{code}/{source_type}",
                        raw_value=value,
                        normalized_score=score,
                        content=f"IODA {source_type.upper()} for {meta['name']}: {value:.0f}% of baseline",
                        confidence=0.90,
                        alert_flag=alert,
                        alert_severity=severity,
                        raw_payload={
                            "country_code": code,
                            "datasource": source_type,
                            "value": value,
                            "conflict": meta["conflict"],
                        },
                    ))
            except Exception as inner_e:
                logger.warning("IODA failed for %s: %s", code, inner_e)
                continue

        cb_ioda.record_success()
    except Exception as e:
        cb_ioda.record_failure()
        logger.error("L10 IODA error: %s", e)

    return signals


@celery_app.task(name="app.workers.l10_connectivity.ingest")
def ingest():
    """L10 ingestion entrypoint — called by Celery beat every 2min."""
    all_signals = _ingest_cloudflare_radar() + _ingest_ioda()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L10 Connectivity: ingested %d signals", count)
    return len(all_signals)
