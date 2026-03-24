"""
L5 — Commodities & Metals Signal Layer

Sources:
  - Alpha Vantage: Gold (XAU/USD), Oil (WTI Crude) intraday quotes
  - Metals-API: Silver, Platinum, Palladium spot prices

Ingestion schedule: every 60 seconds
Weight: 0.9 (partially manipulable)

Gold and oil are top geopolitical fear signals.
Rapid spikes in gold + oil + silver = high-confidence escalation signal.
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l5")
settings = get_settings()

cb_alpha_vantage = CircuitBreaker("L5-AlphaVantage")
cb_metals_api = CircuitBreaker("L5-MetalsAPI")


def _ingest_gold_oil() -> list[dict]:
    """Fetch gold and oil prices from Alpha Vantage."""
    signals = []
    key = settings.ALPHA_VANTAGE_KEY
    if not key:
        logger.warning("ALPHA_VANTAGE_KEY not set, skipping gold/oil")
        return signals

    if cb_alpha_vantage.is_open:
        logger.warning("Circuit breaker open for Alpha Vantage, skipping")
        return signals

    try:
        for symbol, name, asset in [
            ("XAUUSD", "Gold XAU/USD", "gold"),
            ("WTI", "Oil WTI Crude", "oil"),
        ]:
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

            if price == 0:
                continue

            baseline = get_latest_value("L5", name) or prev_close or price
            alert, severity = SignalNormalizer.detect_alert(price, baseline)
            score = SignalNormalizer.pct_change_score(price, baseline)
            change_pct = ((price - prev_close) / prev_close * 100) if prev_close else 0

            signals.append(SignalNormalizer.normalize(
                layer="L5",
                source_name=name,
                raw_value=price,
                normalized_score=score,
                content=f"{name} at ${price:,.2f} ({change_pct:+.1f}% vs prev close)",
                confidence=0.85,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={"quote": quote, "asset": asset},
            ))

        cb_alpha_vantage.record_success()
    except Exception as e:
        cb_alpha_vantage.record_failure()
        logger.error("L5 Alpha Vantage error: %s", e)

    return signals


def _ingest_metals() -> list[dict]:
    """Fetch silver, platinum, palladium from Metals-API."""
    signals = []
    key = settings.METALS_API_KEY
    if not key:
        logger.warning("METALS_API_KEY not set, skipping metals")
        return signals

    if cb_metals_api.is_open:
        logger.warning("Circuit breaker open for Metals-API, skipping")
        return signals

    try:
        data = fetch_json_sync(
            "https://metals-api.com/api/latest",
            params={
                "access_key": key,
                "base": "USD",
                "symbols": "XAG,XPT,XPD",
            },
        )

        rates = data.get("rates", {})
        for symbol, name in [("XAG", "Silver XAG"), ("XPT", "Platinum XPT"), ("XPD", "Palladium XPD")]:
            rate = rates.get(symbol, 0)
            if rate == 0:
                continue
            price = 1.0 / rate

            baseline = get_latest_value("L5", name) or price
            alert, severity = SignalNormalizer.detect_alert(price, baseline)
            score = SignalNormalizer.pct_change_score(price, baseline)

            signals.append(SignalNormalizer.normalize(
                layer="L5",
                source_name=name,
                raw_value=price,
                normalized_score=score,
                content=f"{name} at ${price:,.2f}",
                confidence=0.80,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={"symbol": symbol, "rate": rate},
            ))

        cb_metals_api.record_success()
    except Exception as e:
        cb_metals_api.record_failure()
        logger.error("L5 Metals-API error: %s", e)

    return signals


@celery_app.task(name="app.workers.l5_commodities.ingest")
def ingest():
    """L5 ingestion entrypoint — called by Celery beat every 60s."""
    all_signals = _ingest_gold_oil() + _ingest_metals()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L5 Commodities: ingested %d signals", count)
    return len(all_signals)
