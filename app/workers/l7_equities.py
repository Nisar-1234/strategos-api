"""
L7 — Equities & Bonds Signal Layer

Sources:
  - Alpha Vantage: Individual stock quotes for defense sector + VIX

Ingestion schedule: every 60 seconds
Weight: 0.9 (partially manipulable)

Key signals:
  - Defense stocks (RTX, LMT, NOC, GD, BAESY) rising = conflict expectations
  - VIX rising = market fear / uncertainty
  - Sector divergence from S&P 500 = anomalous military spending expectations
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l7")
settings = get_settings()

cb_av = CircuitBreaker("L7-AlphaVantage")

TRACKED_SYMBOLS = {
    "RTX": {"name": "RTX Corp (Raytheon)", "sector": "defense"},
    "LMT": {"name": "Lockheed Martin", "sector": "defense"},
    "NOC": {"name": "Northrop Grumman", "sector": "defense"},
    "GD": {"name": "General Dynamics", "sector": "defense"},
    "BAESY": {"name": "BAE Systems ADR", "sector": "defense"},
    "VIX": {"name": "CBOE Volatility Index", "sector": "fear"},
    "SPY": {"name": "S&P 500 ETF", "sector": "benchmark"},
}


@celery_app.task(name="app.workers.l7_equities.ingest")
def ingest():
    """L7 ingestion entrypoint — called by Celery beat every 60s."""
    key = settings.ALPHA_VANTAGE_KEY
    if not key:
        logger.warning("ALPHA_VANTAGE_KEY not set, skipping L7")
        return 0

    if cb_av.is_open:
        logger.warning("Circuit breaker open for Alpha Vantage L7, skipping")
        return 0

    signals = []
    try:
        for symbol, meta in TRACKED_SYMBOLS.items():
            try:
                data = fetch_json_sync(
                    "https://www.alphavantage.co/query",
                    params={
                        "function": "GLOBAL_QUOTE",
                        "symbol": symbol,
                        "apikey": key,
                    },
                )

                quote = data.get("Global Quote", {})
                price = float(quote.get("05. price", 0))
                prev_close = float(quote.get("08. previous close", 0))
                change_pct = float(quote.get("10. change percent", "0").replace("%", ""))

                if price == 0:
                    continue

                source_name = f"AV/{symbol}"
                baseline = get_latest_value("L7", source_name) or prev_close or price
                alert, severity = SignalNormalizer.detect_alert(price, baseline, threshold_pct=3.0)
                score = SignalNormalizer.pct_change_score(price, baseline, cap=15.0)

                signals.append(SignalNormalizer.normalize(
                    layer="L7",
                    source_name=source_name,
                    raw_value=price,
                    normalized_score=score,
                    content=f"{meta['name']} ({symbol}): ${price:.2f} ({change_pct:+.1f}%) [{meta['sector']}]",
                    confidence=0.88,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "symbol": symbol,
                        "price": price,
                        "prev_close": prev_close,
                        "change_pct": change_pct,
                        "sector": meta["sector"],
                    },
                ))

            except Exception as inner_e:
                logger.warning("L7 failed for %s: %s", symbol, inner_e)
                continue

        cb_av.record_success()
        if signals:
            count = store_signals(signals)
            logger.info("L7 Equities: ingested %d signals", count)

    except Exception as e:
        cb_av.record_failure()
        logger.error("L7 Alpha Vantage error: %s", e)

    return len(signals)
