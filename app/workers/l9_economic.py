"""
L9 — Economic Indicators Signal Layer

Sources:
  - FRED (Federal Reserve Economic Data): Free, key optional
  - World Bank Open Data: Free, no key required
  - UN COMTRADE preview API: Global trade flows (not maritime AIS — lives here by BRD)

Ingestion schedule: every 3600 seconds (1 hour) — macro data moves slowly
Weight: 0.9 (government reporting bias possible)

Key signals:
  - Global PMI direction (manufacturing contraction = stress)
  - CPI/inflation trends in conflict-adjacent economies
  - Unemployment spikes in sanction-hit countries
  - Trade balance shifts indicating embargo effects
  - Commodity trade value shifts (COMTRADE — economic, not L3 shipping)
"""

import logging
from app.workers.celery_app import celery_app
from app.workers.base import CircuitBreaker, SignalNormalizer, fetch_json_sync
from app.workers.store import store_signals, get_latest_value
from app.core.config import get_settings

logger = logging.getLogger("strategos.l9")
settings = get_settings()

cb_fred = CircuitBreaker("L9-FRED")
cb_worldbank = CircuitBreaker("L9-WorldBank")
cb_comtrade = CircuitBreaker("L9-COMTRADE")

FRED_SERIES = {
    "T10Y2Y": {
        "name": "Treasury 10Y-2Y Spread",
        "description": "Yield curve inversion = recession signal",
        "alert_threshold": 0.0,
        "invert": True,
    },
    "VIXCLS": {
        "name": "VIX Fear Index",
        "description": "Market volatility / fear gauge",
        "alert_threshold": 30.0,
        "invert": False,
    },
    "DCOILWTICO": {
        "name": "WTI Crude Oil",
        "description": "Oil price — geopolitical risk proxy",
        "alert_threshold": 90.0,
        "invert": False,
    },
    "GOLDAMGBD228NLBM": {
        "name": "Gold London Fix",
        "description": "Gold price — safe haven demand",
        "alert_threshold": 2200.0,
        "invert": False,
    },
    "UNRATE": {
        "name": "US Unemployment Rate",
        "description": "Labor market stress indicator",
        "alert_threshold": 5.0,
        "invert": False,
    },
    "GFDEBTN": {
        "name": "Federal Debt Total",
        "description": "Fiscal stress / war funding capacity",
        "alert_threshold": None,
        "invert": False,
    },
}

COMMODITY_CODES = {
    "2709": "Crude Oil",
    "2711": "LNG",
    "1001": "Wheat",
    "7108": "Gold",
}


def _ingest_comtrade() -> list[dict]:
    """
    UN COMTRADE preview — trade / economic flows (BRD: belongs in L9, not L3 maritime).
    Free preview endpoint; no API key required.
    """
    signals = []
    if cb_comtrade.is_open:
        logger.warning("Circuit breaker open for COMTRADE, skipping")
        return signals

    try:
        data = fetch_json_sync(
            "https://comtradeapi.un.org/public/v1/preview/C/A/HS",
            params={
                "cmdCode": "2709,2711,1001,7108",
                "flowCode": "M",
                "partnerCode": "0",
                "period": "2023",
                "maxRecords": "50",
            },
            timeout=15.0,
        )

        records = data.get("data", [])
        for rec in records[:30]:
            commodity_code = str(rec.get("cmdCode", ""))
            commodity_name = COMMODITY_CODES.get(commodity_code, f"HS-{commodity_code}")
            reporter = rec.get("reporterDesc", "Unknown")
            trade_value = float(rec.get("primaryValue", 0))

            if trade_value == 0:
                continue

            source_name = f"COMTRADE/{commodity_name}"
            baseline = get_latest_value("L9", source_name) or trade_value
            pct_change = ((trade_value - baseline) / abs(baseline) * 100) if baseline else 0

            alert = abs(pct_change) > 15
            severity = "CRITICAL" if abs(pct_change) > 30 else ("WARNING" if alert else None)
            score = SignalNormalizer.pct_change_score(trade_value, baseline, cap=40.0)

            signals.append(SignalNormalizer.normalize(
                layer="L9",
                source_name=source_name,
                raw_value=trade_value,
                normalized_score=score,
                content=f"{commodity_name} imports by {reporter}: ${trade_value:,.0f} ({pct_change:+.1f}%)",
                confidence=0.85,
                alert_flag=alert,
                alert_severity=severity,
                raw_payload={
                    "commodity_code": commodity_code,
                    "commodity_name": commodity_name,
                    "reporter": reporter,
                    "trade_value": trade_value,
                    "flow": "import",
                    "source": "comtrade",
                },
            ))

        cb_comtrade.record_success()
    except Exception as e:
        cb_comtrade.record_failure()
        logger.error("L9 COMTRADE error: %s", e)

    return signals


WORLDBANK_INDICATORS = {
    "FP.CPI.TOTL.ZG": {
        "name": "CPI Inflation (annual %)",
        "countries": ["RUS", "UKR", "IRN", "TUR", "EGY", "SDN"],
        "alert_threshold": 15.0,
    },
    "NY.GDP.MKTP.KD.ZG": {
        "name": "GDP Growth (annual %)",
        "countries": ["RUS", "UKR", "IRN", "CHN", "TWN"],
        "alert_threshold": -2.0,
    },
    "BN.CAB.XOKA.GD.ZS": {
        "name": "Current Account Balance (% GDP)",
        "countries": ["RUS", "IRN", "SAU", "CHN"],
        "alert_threshold": -5.0,
    },
}


def _ingest_fred() -> list[dict]:
    """
    Fetch latest values from FRED for macro indicators.
    Free key: register at https://fred.stlouisfed.org/docs/api/api_key.html
    """
    signals = []
    fred_key = settings.FRED_API_KEY
    if not fred_key:
        logger.warning("FRED_API_KEY not set — get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        return signals

    if cb_fred.is_open:
        logger.warning("Circuit breaker open for FRED, skipping")
        return signals

    try:
        for series_id, meta in FRED_SERIES.items():
            try:
                data = fetch_json_sync(
                    "https://api.stlouisfed.org/fred/series/observations",
                    params={
                        "series_id": series_id,
                        "api_key": fred_key,
                        "file_type": "json",
                        "sort_order": "desc",
                        "limit": "5",
                    },
                    timeout=10.0,
                )

                observations = data.get("observations", [])
                if not observations:
                    continue

                latest = None
                for obs in observations:
                    val = obs.get("value", ".")
                    if val != ".":
                        latest = obs
                        break

                if not latest:
                    continue

                value = float(latest["value"])
                date = latest.get("date", "")

                source_name = f"FRED/{series_id}"
                baseline = get_latest_value("L9", source_name) or value
                score = SignalNormalizer.pct_change_score(value, baseline, cap=30.0)

                if meta["invert"]:
                    score = -score

                alert = False
                severity = None
                threshold = meta["alert_threshold"]
                if threshold is not None:
                    if meta["invert"]:
                        alert = value < threshold
                    else:
                        alert = value > threshold
                    severity = "WARNING" if alert else None

                signals.append(SignalNormalizer.normalize(
                    layer="L9",
                    source_name=source_name,
                    raw_value=value,
                    normalized_score=score,
                    content=f"{meta['name']}: {value:.2f} ({date}) — {meta['description']}",
                    confidence=0.85,
                    alert_flag=alert,
                    alert_severity=severity,
                    raw_payload={
                        "series_id": series_id,
                        "value": value,
                        "date": date,
                        "description": meta["description"],
                        "source": "fred.stlouisfed.org",
                    },
                ))
            except Exception as inner_e:
                logger.warning("FRED failed for %s: %s", series_id, inner_e)
                continue

        cb_fred.record_success()
    except Exception as e:
        cb_fred.record_failure()
        logger.error("L9 FRED error: %s", e)

    return signals


def _ingest_worldbank() -> list[dict]:
    """
    Fetch macro indicators for conflict-relevant countries from World Bank.
    Free, no key required. Returns annual data (lagged).
    """
    signals = []
    if cb_worldbank.is_open:
        logger.warning("Circuit breaker open for World Bank, skipping")
        return signals

    try:
        for indicator_id, meta in WORLDBANK_INDICATORS.items():
            for country in meta["countries"]:
                try:
                    data = fetch_json_sync(
                        f"https://api.worldbank.org/v2/country/{country}/indicator/{indicator_id}",
                        params={
                            "format": "json",
                            "per_page": "3",
                            "date": "2020:2024",
                            "MRV": "1",
                        },
                        timeout=20.0,
                    )

                    if not isinstance(data, list) or len(data) < 2:
                        continue

                    records = data[1]
                    if not records:
                        continue

                    latest = None
                    for rec in records:
                        if rec.get("value") is not None:
                            latest = rec
                            break

                    if not latest:
                        continue

                    value = float(latest["value"])
                    year = latest.get("date", "")
                    country_name = latest.get("country", {}).get("value", country)

                    source_name = f"WorldBank/{country}/{indicator_id}"
                    score = 0.0
                    threshold = meta["alert_threshold"]

                    if threshold is not None:
                        if threshold < 0:
                            alert = value < threshold
                            score = max(-1.0, value / 10.0)
                        else:
                            alert = value > threshold
                            score = min(1.0, -value / (threshold * 2))
                    else:
                        alert = False

                    severity = "WARNING" if alert else None

                    signals.append(SignalNormalizer.normalize(
                        layer="L9",
                        source_name=source_name,
                        raw_value=value,
                        normalized_score=score,
                        content=f"{meta['name']} — {country_name}: {value:.1f}% ({year})",
                        confidence=0.78,
                        alert_flag=alert,
                        alert_severity=severity,
                        raw_payload={
                            "indicator": indicator_id,
                            "indicator_name": meta["name"],
                            "country_code": country,
                            "country_name": country_name,
                            "value": value,
                            "year": year,
                            "source": "worldbank.org",
                        },
                    ))
                except Exception as inner_e:
                    logger.warning("World Bank failed for %s/%s: %s", country, indicator_id, inner_e)
                    continue

        cb_worldbank.record_success()
    except Exception as e:
        cb_worldbank.record_failure()
        logger.error("L9 World Bank error: %s", e)

    return signals


@celery_app.task(name="app.workers.l9_economic.ingest")
def ingest():
    """L9 ingestion entrypoint — called by Celery beat every 1hr."""
    all_signals = _ingest_fred() + _ingest_worldbank() + _ingest_comtrade()
    if all_signals:
        count = store_signals(all_signals)
        logger.info("L9 Economic: ingested %d signals", count)
    return len(all_signals)
