"""
L5 — Commodities & Metals Signal Layer

Sources:
  - Polygon.io (Massive): Gold (XAU/USD), Silver (XAG/USD), Platinum, Oil (via USO ETF)
  - Fallback: Alpha Vantage if Polygon fails

Ingestion schedule: every 60 seconds
Weight: 0.9 (partially manipulable)

Gold and oil are top geopolitical fear signals.
Rapid spikes in gold + oil + silver = high-confidence escalation signal.
"""

import logging
import time
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l5")
settings = get_settings()

cb_polygon = CircuitBreaker("L5-Polygon")
cb_alpha_vantage = CircuitBreaker("L5-AlphaVantage")

FOREX_TICKERS = {
    "C:XAUUSD": {"name": "Gold XAU/USD", "asset": "gold", "alert_pct": 2.0},
    "C:XAGUSD": {"name": "Silver XAG/USD", "asset": "silver", "alert_pct": 3.0},
    "C:XPTUSD": {"name": "Platinum XPT/USD", "asset": "platinum", "alert_pct": 3.0},
    "C:XPDUSD": {"name": "Palladium XPD/USD", "asset": "palladium", "alert_pct": 3.0},
}

STOCK_TICKERS = {
    "USO": {"name": "Oil WTI (USO ETF)", "asset": "oil", "alert_pct": 3.0},
    "UNG": {"name": "Natural Gas (UNG ETF)", "asset": "nat_gas", "alert_pct": 4.0},
    "WEAT": {"name": "Wheat (WEAT ETF)", "asset": "wheat", "alert_pct": 3.0},
}


def _fetch_polygon_prev(ticker: str) -> dict | None:
    """Fetch previous-day OHLCV bar from Polygon.io."""
    key = settings.POLYGON_API_KEY
    if not key:
        return None
    try:
        data = fetch_json_sync(
            f"https://api.polygon.io/v2/aggs/ticker/{ticker}/prev",
            params={"adjusted": "true", "apiKey": key},
        )
        results = data.get("results", [])
        return results[0] if results else None
    except Exception as e:
        logger.warning("Polygon prev-day fetch failed for %s: %s", ticker, e)
        return None


def _ingest_polygon_commodities() -> list[dict]:
    """Fetch commodity prices from Polygon.io (forex metals + commodity ETFs)."""
    signals = []
    key = settings.POLYGON_API_KEY
    if not key:
        logger.warning("POLYGON_API_KEY not set, skipping Polygon commodities")
        return signals

    if cb_polygon.is_open:
        logger.warning("Circuit breaker open for Polygon L5, skipping")
        return signals

    try:
        all_tickers = {**FOREX_TICKERS, **STOCK_TICKERS}
        for i, (ticker, meta) in enumerate(all_tickers.items()):
            if i > 0:
                time.sleep(13)
            bar = _fetch_polygon_prev(ticker)
            if not bar:
                continue

            close_price = float(bar.get("c", 0))
            open_price = float(bar.get("o", 0))
            high = float(bar.get("h", 0))
            low = float(bar.get("l", 0))
            volume = int(bar.get("v", 0))

            if close_price == 0:
                continue

            source_name = f"Polygon/{meta['asset']}"
            baseline = get_latest_value("L5", source_name) or open_price or close_price
            alert, severity = SignalNormalizer.detect_alert(
                close_price, baseline, threshold_pct=meta["alert_pct"]
            )
            score = SignalNormalizer.pct_change_score(close_price, baseline)
            change_pct = ((close_price - open_price) / open_price * 100) if open_price else 0

            signals.append(SignalNormalizer.normalize(
                layer="L5",
                source_name=source_name,
                raw_value=close_price,
                normalized_score=score,
                content=f"{meta['name']} at ${close_price:,.2f} ({change_pct:+.1f}% session)",
                confidence=0.88,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={
                    "ticker": ticker,
                    "asset": meta["asset"],
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                    "volume": volume,
                    "source": "polygon.io",
                },
            ))

        cb_polygon.record_success()
    except Exception as e:
        cb_polygon.record_failure()
        logger.error("L5 Polygon error: %s", e)

    return signals


def _ingest_alpha_vantage_fallback() -> list[dict]:
    """Fallback: fetch gold/oil from Alpha Vantage if Polygon fails."""
    signals = []
    key = settings.ALPHA_VANTAGE_KEY
    if not key or not cb_polygon.is_open:
        return signals

    if cb_alpha_vantage.is_open:
        return signals

    try:
        for symbol, name in [("XAUUSD", "Gold XAU/USD"), ("WTI", "Oil WTI Crude")]:
            data = fetch_json_sync(
                "https://www.alphavantage.co/query",
                params={"function": "GLOBAL_QUOTE", "symbol": symbol, "apikey": key},
            )
            quote = data.get("Global Quote", {})
            price = float(quote.get("05. price", 0))
            if price == 0:
                continue

            source_name = f"AV-fallback/{name}"
            baseline = get_latest_value("L5", source_name) or price
            alert, severity = SignalNormalizer.detect_alert(price, baseline)
            score = SignalNormalizer.pct_change_score(price, baseline)

            signals.append(SignalNormalizer.normalize(
                layer="L5",
                source_name=source_name,
                raw_value=price,
                normalized_score=score,
                content=f"[Fallback] {name} at ${price:,.2f}",
                confidence=0.75,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={"quote": quote, "source": "alphavantage-fallback"},
            ))

        cb_alpha_vantage.record_success()
    except Exception as e:
        cb_alpha_vantage.record_failure()
        logger.error("L5 Alpha Vantage fallback error: %s", e)

    return signals


@celery_app.task(name="app.workers.l5_commodities.ingest")
def ingest():
    """L5 ingestion entrypoint — called by Celery beat every 60s."""
    all_signals = _ingest_polygon_commodities() + _ingest_alpha_vantage_fallback()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L5 Commodities: ingested %d signals", count)
    return len(all_signals)
