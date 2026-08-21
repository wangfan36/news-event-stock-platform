"""Helpers for generating optional Hong Kong price overrides."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib.request import Request, urlopen

from .catalogs import COMPANY_CATALOG
from .config import get_app_config

PRICE_OVERRIDE_PATH = get_app_config().price_override_path


def build_hk_price_overrides() -> dict[str, object]:
    PRICE_OVERRIDE_PATH.parent.mkdir(parents=True, exist_ok=True)
    overrides: dict[str, dict[str, object]] = {}
    misses: list[str] = []
    for symbol in COMPANY_CATALOG:
        if not str(symbol).endswith(".HK"):
            continue
        payload = fetch_yahoo_chart_price(symbol)
        if payload:
            overrides[symbol] = payload
        else:
            misses.append(symbol)

    document = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "yahoo-public-chart",
        "items": overrides,
    }
    PRICE_OVERRIDE_PATH.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
    latest_as_of = max((item.get("as_of", "") for item in overrides.values()), default="")
    return {
        "path": str(PRICE_OVERRIDE_PATH),
        "count": len(overrides),
        "misses": misses,
        "latest_as_of": latest_as_of,
    }


def fetch_yahoo_chart_price(symbol: str) -> dict[str, object] | None:
    ticker = _to_yahoo_hk_symbol(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}?range=3mo&interval=1d"
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        payload = json.loads(urlopen(req, timeout=20).read().decode("utf-8"))
    except Exception:
        return None

    results = payload.get("chart", {}).get("result", [])
    if not results:
        return None
    result = results[0]
    timestamps = result.get("timestamp") or []
    quote = result.get("indicators", {}).get("quote", [{}])[0]
    closes = quote.get("close") or []
    highs = quote.get("high") or []
    lows = quote.get("low") or []
    volumes = quote.get("volume") or []
    valid = [
        (ts, close, high, low, volume)
        for ts, close, high, low, volume in zip(timestamps, closes, highs, lows, volumes)
        if close is not None
    ]
    if len(valid) < 2:
        return None

    latest_ts, latest_close, latest_high, latest_low, latest_volume = valid[-1]
    prev_close = valid[-2][1]
    last_20 = [row[1] for row in valid[-20:]]
    last_60 = [row[1] for row in valid[-60:]]

    return {
        "status": "ok",
        "symbol": symbol,
        "yahoo_symbol": ticker,
        "as_of": datetime.utcfromtimestamp(latest_ts).strftime("%Y-%m-%d"),
        "latest_price": round(float(latest_close), 3),
        "prev_close": round(float(prev_close), 3),
        "previous_close": round(float(prev_close), 3),
        "day_change_pct": round((float(latest_close) / float(prev_close) - 1) * 100, 2),
        "position_20d_pct": _window_position(last_20),
        "position_60d_pct": _window_position(last_60),
        "sma20": round(sum(last_20) / len(last_20), 3),
        "sma60": round(sum(last_60) / len(last_60), 3),
        "high": round(float(latest_high), 3) if latest_high is not None else None,
        "low": round(float(latest_low), 3) if latest_low is not None else None,
        "volume": float(latest_volume) if latest_volume is not None else None,
        "provider": "yahoo-public-chart",
    }


def _to_yahoo_hk_symbol(symbol: str) -> str:
    code = str(symbol).upper().replace(".HK", "")
    try:
        return str(int(code)) + ".HK"
    except ValueError:
        return code + ".HK"


def _window_position(values: list[float]) -> float | None:
    if not values:
        return None
    highest = max(values)
    lowest = min(values)
    latest = values[-1]
    if highest == lowest:
        return 50.0
    return round((latest - lowest) / (highest - lowest) * 100, 1)
