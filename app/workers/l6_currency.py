"""
L6 — Currency & FX Signal Layer

Sources:
  - Open Exchange Rates: Major currency pairs vs USD

Ingestion schedule: every 300 seconds (5 minutes)
Weight: 0.9 (partially manipulable)

Key geopolitical signals:
  - ILS weakening = Israel risk perception
  - RUB weakening = Russia sanctions pressure
  - CNY moves = China trade/Taiwan risk
  - TRY weakening = Turkey/regional instability
  - EUR/GBP moves = European geopolitical risk
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l6")
settings = get_settings()

cb_oxr = CircuitBreaker("L6-OpenExchangeRates")

TRACKED_CURRENCIES = {
    "ILS": {"name": "Israeli Shekel", "conflict_signal": "Israel risk"},
    "RUB": {"name": "Russian Ruble", "conflict_signal": "Russia sanctions"},
    "UAH": {"name": "Ukrainian Hryvnia", "conflict_signal": "Ukraine instability"},
    "CNY": {"name": "Chinese Yuan", "conflict_signal": "China/Taiwan risk"},
    "TRY": {"name": "Turkish Lira", "conflict_signal": "Turkey/regional risk"},
    "IRR": {"name": "Iranian Rial", "conflict_signal": "Iran sanctions"},
    "EUR": {"name": "Euro", "conflict_signal": "EU stability"},
    "GBP": {"name": "British Pound", "conflict_signal": "UK policy shift"},
    "JPY": {"name": "Japanese Yen", "conflict_signal": "Pacific risk (safe haven)"},
    "CHF": {"name": "Swiss Franc", "conflict_signal": "Global risk (safe haven)"},
    "SAR": {"name": "Saudi Riyal", "conflict_signal": "Gulf stability"},
}


@celery_app.task(name="app.workers.l6_currency.ingest")
def ingest():
    """L6 ingestion entrypoint — called by Celery beat every 5min."""
    key = settings.OPEN_EXCHANGE_RATES_KEY
    if not key:
        logger.warning("OPEN_EXCHANGE_RATES_KEY not set, skipping L6")
        return 0

    if cb_oxr.is_open:
        logger.warning("Circuit breaker open for OXR, skipping L6")
        return 0

    signals = []
    try:
        data = fetch_json_sync(
            "https://openexchangerates.org/api/latest.json",
            params={
                "app_id": key,
                "symbols": ",".join(TRACKED_CURRENCIES.keys()),
            },
        )

        rates = data.get("rates", {})
        for currency, meta in TRACKED_CURRENCIES.items():
            rate = rates.get(currency)
            if rate is None:
                continue

            source_name = f"OXR/USD-{currency}"
            baseline = get_latest_value("L6", source_name) or rate
            alert, severity = SignalNormalizer.detect_alert(rate, baseline, threshold_pct=2.0)
            score = SignalNormalizer.pct_change_score(rate, baseline, cap=10.0)
            change_pct = ((rate - baseline) / baseline * 100) if baseline else 0

            signals.append(SignalNormalizer.normalize(
                layer="L6",
                source_name=source_name,
                raw_value=rate,
                normalized_score=score,
                content=f"USD/{currency} ({meta['name']}): {rate:.4f} ({change_pct:+.2f}%) -- {meta['conflict_signal']}",
                confidence=0.82,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={
                    "currency": currency,
                    "rate": rate,
                    "base": "USD",
                    "conflict_signal": meta["conflict_signal"],
                },
            ))

        cb_oxr.record_success()
        if signals:
            count = store_signals(signals)
            logger.info("L6 Currency: ingested %d signals", count)

    except Exception as e:
        cb_oxr.record_failure()
        logger.error("L6 OXR error: %s", e)

    return len(signals)
