"""Technical confirmation provider abstraction layer."""

from __future__ import annotations

import statistics
from typing import Any


def build_market_snapshot(symbols: list[str], technical_settings: dict[str, Any] | None = None) -> dict[str, Any]:
    settings = normalize_technical_settings(technical_settings)
    provider = settings["provider"]
    if provider == "akshare":
        return _build_market_snapshot_akshare(symbols, settings)
    if provider == "tradingview-mcp":
        return _build_market_snapshot_tradingview(symbols, settings)
    return _build_market_snapshot_mock(symbols, settings)


def get_symbol_technical_overlay(
    symbol: str,
    action: str,
    score: int,
    technical_settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = normalize_technical_settings(technical_settings)
    provider = settings["provider"]
    if provider == "akshare":
        return _get_symbol_overlay_akshare(symbol, action, score, settings)
    if provider == "tradingview-mcp":
        return _get_symbol_overlay_tradingview(symbol, action, score, settings)
    return _get_symbol_overlay_mock(symbol, action, score, settings)


def normalize_technical_settings(settings: dict[str, Any] | None) -> dict[str, Any]:
    defaults = {
        "provider": "mock",
        "base_url": "",
        "endpoint": "",
        "timeout_seconds": 8,
        "fallback_to_mock": True,
    }
    payload = dict(defaults)
    payload.update(dict(settings or {}))
    provider = str(payload.get("provider", "mock") or "mock")
    if provider == "yahoo":
        provider = "akshare"
    payload["provider"] = provider
    payload["base_url"] = str(payload.get("base_url", "") or "")
    payload["endpoint"] = str(payload.get("endpoint", "") or "")
    payload["timeout_seconds"] = int(payload.get("timeout_seconds", 8) or 8)
    payload["fallback_to_mock"] = bool(payload.get("fallback_to_mock", True))
    return payload


def _build_market_snapshot_mock(symbols: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    del symbols
    return {
        "risk_regime": "中性偏进攻",
        "index_bias": "成长风格占优",
        "volatility_state": "波动可控",
        "breadth_note": "热点集中于科技制造与事件驱动链条。",
        "provider": settings["provider"],
        "provider_status": "ok",
    }


def _get_symbol_overlay_mock(symbol: str, action: str, score: int, settings: dict[str, Any]) -> dict[str, Any]:
    base = _seed_from_symbol(symbol)
    technical_score = max(35, min(95, score - 8 + base["score_shift"]))
    return {
        "technical_score": technical_score,
        "trend_alignment": _trend_alignment(action, technical_score),
        "setup_quality": _setup_quality(technical_score),
        "entry_window": base["entry_window"],
        "risk_level": base["risk_level"],
        "stop_reference": base["stop_reference"],
        "confirmation_signals": base["confirmation_signals"],
        "warning_signals": base["warning_signals"],
        "provider": settings["provider"],
        "provider_status": "ok",
    }


def _build_market_snapshot_akshare(symbols: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    symbol_list = list(symbols)
    try:
        index_data = _fetch_akshare_index_snapshot()
        changes = [item["change_pct"] for item in index_data if isinstance(item.get("change_pct"), (int, float))]
        avg_change = statistics.mean(changes) if changes else 0.0
        risk_regime = "中性偏进攻" if avg_change >= 0.3 else "中性偏防守" if avg_change <= -0.3 else "中性震荡"
        return {
            "risk_regime": risk_regime,
            "index_bias": _index_bias_from_snapshot(index_data),
            "volatility_state": "偏强" if avg_change > 0.8 else "温和" if avg_change > -0.5 else "偏弱",
            "breadth_note": " / ".join(f"{item['name']} {item['change_pct']:.2f}%" for item in index_data[:3]),
            "provider": settings["provider"],
            "provider_status": "ok",
        }
    except Exception as exc:
        if settings["fallback_to_mock"]:
            payload = _build_market_snapshot_mock(symbol_list, {"provider": "mock"})
            payload["provider"] = settings["provider"]
            payload["provider_status"] = f"fallback:{type(exc).__name__}"
            return payload
        return {
            "risk_regime": "未生成",
            "index_bias": "未生成",
            "volatility_state": "未生成",
            "breadth_note": str(exc),
            "provider": settings["provider"],
            "provider_status": "error",
        }


def _get_symbol_overlay_akshare(symbol: str, action: str, score: int, settings: dict[str, Any]) -> dict[str, Any]:
    try:
        history = _fetch_akshare_price_history(symbol)
        closes = [value for value in history if isinstance(value, (int, float))]
        if len(closes) < 25:
            raise RuntimeError("Not enough AKShare history.")
        last_price = closes[-1]
        sma5 = statistics.mean(closes[-5:])
        sma20 = statistics.mean(closes[-20:])
        relative = ((last_price / sma20) - 1) * 100 if sma20 else 0.0
        technical_score = max(35, min(95, round(score * 0.45 + (55 if last_price >= sma20 else 40) + min(15, relative))))
        overlay = {
            "technical_score": technical_score,
            "trend_alignment": "顺势确认" if sma5 >= sma20 else "等待均线修复",
            "setup_quality": _setup_quality(technical_score),
            "entry_window": "等待回踩 5 日均线后确认" if last_price >= sma20 else "先观察均线修复再介入",
            "risk_level": "中" if abs(relative) < 8 else "中高",
            "stop_reference": "20 日均线",
            "confirmation_signals": [
                f"现价 {last_price:.2f}",
                f"5 日均线 {sma5:.2f} / 20 日均线 {sma20:.2f}",
            ],
            "warning_signals": [
                "跌破 20 日均线",
                "成交放大但收盘站不回均线",
            ],
            "provider": settings["provider"],
            "provider_status": "ok",
        }
        if action == "卖出" and technical_score > 60:
            overlay["trend_alignment"] = "技术尚未完全转弱"
        return overlay
    except Exception as exc:
        if settings["fallback_to_mock"]:
            payload = _get_symbol_overlay_mock(symbol, action, score, {"provider": "mock"})
            payload["provider"] = settings["provider"]
            payload["provider_status"] = f"fallback:{type(exc).__name__}"
            return payload
        return {
            "technical_score": 50,
            "trend_alignment": "未生成",
            "setup_quality": "未生成",
            "entry_window": "未生成",
            "risk_level": "未生成",
            "stop_reference": "未生成",
            "confirmation_signals": [],
            "warning_signals": [str(exc)],
            "provider": settings["provider"],
            "provider_status": "error",
        }


def _build_market_snapshot_tradingview(symbols: list[str], settings: dict[str, Any]) -> dict[str, Any]:
    symbol_list = list(symbols)
    if not settings.get("endpoint"):
        return {
            "risk_regime": "未接入",
            "index_bias": "未接入",
            "volatility_state": "未接入",
            "breadth_note": "tradingview-mcp 需要单独桥接服务或适配器 endpoint。",
            "provider": settings["provider"],
            "provider_status": "bridge_not_configured",
        }
    if settings["fallback_to_mock"]:
        payload = _build_market_snapshot_mock(symbol_list, {"provider": "mock"})
        payload["provider"] = settings["provider"]
        payload["provider_status"] = "bridge_pending"
        return payload
    return {
        "risk_regime": "未生成",
        "index_bias": "未生成",
        "volatility_state": "未生成",
        "breadth_note": "endpoint 已配置，但本地适配器尚未实现。",
        "provider": settings["provider"],
        "provider_status": "not_implemented",
    }


def _get_symbol_overlay_tradingview(symbol: str, action: str, score: int, settings: dict[str, Any]) -> dict[str, Any]:
    del symbol
    if not settings.get("endpoint"):
        payload = _get_symbol_overlay_mock("bridge", action, score, {"provider": "mock"})
        payload["provider"] = settings["provider"]
        payload["provider_status"] = "bridge_not_configured"
        payload["warning_signals"] = ["tradingview-mcp endpoint 未配置"]
        return payload
    payload = _get_symbol_overlay_mock("bridge", action, score, {"provider": "mock"})
    payload["provider"] = settings["provider"]
    payload["provider_status"] = "bridge_pending"
    payload["warning_signals"] = ["endpoint 已配置，但本地 tradingview-mcp bridge 尚未实现"]
    return payload


def _fetch_akshare_index_snapshot() -> list[dict[str, Any]]:
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise RuntimeError("akshare is not installed.") from exc

    index_df = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
    if index_df.empty:
        raise RuntimeError("AKShare index snapshot is empty.")
    desired = {
        "000001": "上证指数",
        "399001": "深证成指",
        "000300": "沪深300",
    }
    result: list[dict[str, Any]] = []
    for code, name in desired.items():
        row = index_df[index_df["代码"].astype(str) == code]
        if row.empty:
            continue
        first = row.iloc[0]
        result.append(
            {
                "symbol": code,
                "name": name,
                "change_pct": float(first["涨跌幅"]),
            }
        )
    if not result:
        raise RuntimeError("AKShare did not return target indices.")
    return result


def _fetch_akshare_price_history(symbol: str) -> list[float]:
    try:
        import akshare as ak
    except ModuleNotFoundError as exc:
        raise RuntimeError("akshare is not installed.") from exc

    normalized = str(symbol).strip().upper()
    if normalized.endswith(".HK"):
        hk_symbol = normalized.replace(".HK", "")
        df = ak.stock_hk_hist(
            symbol=hk_symbol,
            period="daily",
            start_date="20240101",
            end_date="22220101",
            adjust="qfq",
        )
    else:
        cn_symbol = normalized[-6:] if len(normalized) >= 6 else normalized
        df = ak.stock_zh_a_hist(
            symbol=cn_symbol,
            period="daily",
            start_date="20240101",
            end_date="22220101",
            adjust="qfq",
        )
    if df.empty:
        raise RuntimeError(f"AKShare history is empty for {symbol}")
    closes = df["收盘"].tolist() if "收盘" in df.columns else []
    return [float(value) for value in closes if isinstance(value, (int, float))]


def _index_bias_from_snapshot(index_data: list[dict[str, Any]]) -> str:
    mapping = {item["name"]: item["change_pct"] for item in index_data}
    hs300 = mapping.get("沪深300", 0.0)
    sz = mapping.get("深证成指", 0.0)
    sh = mapping.get("上证指数", 0.0)
    if sz >= sh and sz >= hs300:
        return "成长偏强"
    if hs300 >= sz and hs300 >= sh:
        return "核心资产偏强"
    return "权重指数主导"


def _seed_from_symbol(symbol: str) -> dict[str, Any]:
    checksum = sum(ord(char) for char in symbol)
    return {
        "score_shift": checksum % 9 - 4,
        "entry_window": ["等待回踩 5 日线", "突破后首个缩量回踩", "盘中放量确认后分批介入"][checksum % 3],
        "risk_level": ["低", "中", "中高"][checksum % 3],
        "stop_reference": ["前低", "10 日均线", "事件失效日内低点"][checksum % 3],
        "confirmation_signals": [
            ["量能放大", "日线站上短中期均线"],
            ["多周期共振", "回踩不破关键均线"],
            ["相对强度持续领先", "成交额放大"],
        ][checksum % 3],
        "warning_signals": [
            ["放量冲高回落", "跌破前低"],
            ["量价背离", "热点切换过快"],
            ["高位横盘放量滞涨", "板块龙头转弱"],
        ][checksum % 3],
    }


def _trend_alignment(action: str, technical_score: int) -> str:
    if action == "买入":
        return "顺势确认" if technical_score >= 70 else "逻辑强于技术"
    if action == "卖出":
        return "技术转弱" if technical_score <= 45 else "逻辑先行减分"
    if action == "持有":
        return "趋势尚可"
    return "等待确认"


def _setup_quality(technical_score: int) -> str:
    if technical_score >= 82:
        return "优秀"
    if technical_score >= 68:
        return "良好"
    if technical_score >= 55:
        return "一般"
    return "偏弱"
