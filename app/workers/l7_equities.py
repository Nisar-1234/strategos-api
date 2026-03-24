"""
L7 — Equities & Bonds Signal Layer

Sources:
  - Polygon.io (Massive): Defense stocks, VIX proxy, S&P 500 benchmark
  - Fallback: Alpha Vantage if Polygon fails

Ingestion schedule: every 60 seconds
Weight: 0.9 (partially manipulable)

Key signals:
  - Defense stocks (RTX, LMT, NOC, GD, BAESY) rising = conflict expectations
  - VIX proxy (VIXY) rising = market fear / uncertainty
  - Sector divergence from S&P 500 = anomalous military spending expectations
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l7")
settings = get_settings()

cb_polygon = CircuitBreaker("L7-Polygon")
cb_av = CircuitBreaker("L7-AlphaVantage")

TRACKED_SYMBOLS = {
    "RTX": {"name": "RTX Corp (Raytheon)", "sector": "defense"},
    "LMT": {"name": "Lockheed Martin", "sector": "defense"},
    "NOC": {"name": "Northrop Grumman", "sector": "defense"},
    "GD": {"name": "General Dynamics", "sector": "defense"},
    "BAESY": {"name": "BAE Systems ADR", "sector": "defense"},
    "VIXY": {"name": "ProShares VIX Short-Term", "sector": "fear"},
    "SPY": {"name": "S&P 500 ETF", "sector": "benchmark"},
}


def _ingest_polygon_equities() -> list[dict]:
    """Fetch defense stocks and benchmark from Polygon.io."""
    signals = []
    key = settings.POLYGON_API_KEY
    if not key:
        logger.warning("POLYGON_API_KEY not set, skipping L7 Polygon")
        return signals

    if cb_polygon.is_open:
        logger.warning("Circuit breaker open for Polygon L7, skipping")
        return signals

    try:
        for symbol, meta in TRACKED_SYMBOLS.items():
            try:
                data = fetch_json_sync(
                    f"https://api.polygon.io/v2/aggs/ticker/{symbol}/prev",
                    params={"adjusted": "true", "apiKey": key},
                )

                results = data.get("results", [])
                if not results:
                    continue

                bar = results[0]
                close_price = float(bar.get("c", 0))
                open_price = float(bar.get("o", 0))
                high = float(bar.get("h", 0))
                low = float(bar.get("l", 0))
                volume = int(bar.get("v", 0))

                if close_price == 0:
                    continue

                source_name = f"Polygon/{symbol}"
                baseline = get_latest_value("L7", source_name) or open_price or close_price
                alert, severity = SignalNormalizer.detect_alert(
                    close_price, baseline, threshold_pct=3.0
                )
                score = SignalNormalizer.pct_change_score(close_price, baseline, cap=15.0)
                change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0

                signals.append(SignalNormalizer.normalize(
                    layer="L7",
                    source_name=source_name,
                    raw_value=close_price,
                    normalized_score=score,
                    content=f"{meta['name']} ({symbol}): ${close_price:.2f} ({change_pct:+.1f}%) [{meta['sector']}]",
                    confidence=0.88,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "symbol": symbol,
                        "open": open_price,
                        "high": high,
                        "low": low,
                        "close": close_price,
                        "volume": volume,
                        "sector": meta["sector"],
                        "source": "polygon.io",
                    },
                ))

            except Exception as inner_e:
                logger.warning("Polygon L7 failed for %s: %s", symbol, inner_e)
                continue

        cb_polygon.record_success()
    except Exception as e:
        cb_polygon.record_failure()
        logger.error("L7 Polygon error: %s", e)

    return signals


def _ingest_alpha_vantage_fallback() -> list[dict]:
    """Fallback: fetch equities from Alpha Vantage when Polygon circuit is open."""
    signals = []
    key = settings.ALPHA_VANTAGE_KEY
    if not key or not cb_polygon.is_open:
        return signals

    if cb_av.is_open:
        return signals

    try:
        for symbol, meta in TRACKED_SYMBOLS.items():
            try:
                data = fetch_json_sync(
                    "https://www.alphavantage.co/query",
                    params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key},
                )
                quote = data.get("Global Quote", {})
                price = float(quote.get("05. price", 0))
                if price == 0:
                    continue

                source_name = f"AV-fallback/{symbol}"
                baseline = get_latest_value("L7", source_name) or price
                alert, severity = SignalNormalizer.detect_alert(price, baseline, threshold_pct=3.0)
                score = SignalNormalizer.pct_change_score(price, baseline, cap=15.0)

                signals.append(SignalNormalizer.normalize(
                    layer="L7",
                    source_name=source_name,
                    raw_value=price,
                    normalized_score=score,
                    content=f"[Fallback] {meta['name']} ({symbol}): ${price:.2f} [{meta['sector']}]",
                    confidence=0.75,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={"symbol": symbol, "sector": meta["sector"], "source": "alphavantage-fallback"},
                ))
            except Exception:
                continue

        cb_av.record_success()
    except Exception as e:
        cb_av.record_failure()
        logger.error("L7 Alpha Vantage fallback error: %s", e)

    return signals


@celery_app.task(name="app.workers.l7_equities.ingest")
def ingest():
    """L7 ingestion entrypoint — called by Celery beat every 60s."""
    all_signals = _ingest_polygon_equities() + _ingest_alpha_vantage_fallback()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L7 Equities: ingested %d signals", count)
    return len(all_signals)
