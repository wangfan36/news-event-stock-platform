"""Registered analysis modules for recommendation synthesis."""

from __future__ import annotations

from typing import Any

ANALYSIS_REGISTRY: dict[str, dict[str, Any]] = {
    "event_analyst": {
        "display_name": "事件分析器",
        "description": "根据事件强度、证据链和产业链映射判断事件驱动质量。",
        "weight": 0.40,
    },
    "technical_analyst": {
        "display_name": "技术确认器",
        "description": "根据趋势、均线、信号确认和风险提示给出执行层判断。",
        "weight": 0.20,
    },
    "market_analyst": {
        "display_name": "价格位置分析器",
        "description": "根据价格位置、涨跌幅、均线与换手率评估市场层条件。",
        "weight": 0.20,
    },
    "fundamental_analyst": {
        "display_name": "基本面分析器",
        "description": "根据盈利质量、ROE、负债率和估值快照评估基本面层质量。",
        "weight": 0.15,
    },
    "beneficiary_analyst": {
        "display_name": "AI 受益排序分析器",
        "description": "根据 AI 公司受益排序判断公司在产业链中的获益强度和优先级。",
        "weight": 0.15,
    },
    "risk_analyst": {
        "display_name": "风险分析器",
        "description": "根据仓位集中、缺失数据、技术回退和价格波动情况评估风险。",
        "weight": 0.10,
    },
    "execution_analyst": {
        "display_name": "执行价位分析器",
        "description": "根据买入价、卖出价、止损和当前价位判断可执行性。",
        "weight": 0.05,
    },
}


def build_analyst_signals(
    *,
    base_event_score: int,
    technical_overlay: dict[str, Any],
    market_score: dict[str, Any],
    fundamental_score: dict[str, Any],
    beneficiary_score: dict[str, Any],
    risk_score: dict[str, Any],
    execution_plan: dict[str, Any],
    related_events: list[dict[str, Any]],
    candidate: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    event_title = related_events[0]["title"] if related_events else "无主事件"
    event_score = _bounded_score(base_event_score)
    technical_score = _bounded_score(technical_overlay.get("technical_score", 50))
    market_value = _bounded_score(market_score.get("score", 50))
    fundamental_value = _bounded_score(fundamental_score.get("score", 50))
    execution_value = 70 if execution_plan.get("status") == "ok" else 35

    payload = {
        "event_analyst": _make_signal(
            "event_analyst",
            event_score,
            f"核心事件为“{event_title}”，当前映射到 {candidate['industry_name']}。",
            {
                "watchlist_overlap": candidate.get("is_watchlist", False),
                "industry_name": candidate["industry_name"],
            },
        ),
        "technical_analyst": _make_signal(
            "technical_analyst",
            technical_score,
            technical_overlay.get("trend_alignment", "技术状态未生成"),
            {
                "provider": technical_overlay.get("provider"),
                "provider_status": technical_overlay.get("provider_status"),
                "setup_quality": technical_overlay.get("setup_quality"),
            },
        ),
        "market_analyst": _make_signal(
            "market_analyst",
            market_value,
            market_score.get("reason", "市场位置未生成"),
            {"label": market_score.get("label")},
        ),
        "fundamental_analyst": _make_signal(
            "fundamental_analyst",
            fundamental_value,
            fundamental_score.get("reason", "基本面未生成"),
            {"label": fundamental_score.get("label")},
        ),
        "beneficiary_analyst": _make_signal(
            "beneficiary_analyst",
            _bounded_score(beneficiary_score.get("score", 50)),
            beneficiary_score.get("reason", "AI 公司受益排序未生成"),
            {
                "rank": beneficiary_score.get("rank"),
                "level": beneficiary_score.get("level"),
            },
        ),
        "risk_analyst": _make_signal(
            "risk_analyst",
            _bounded_score(risk_score.get("score", 50)),
            risk_score.get("reason", "风险未生成"),
            {"label": risk_score.get("label")},
        ),
        "execution_analyst": _make_signal(
            "execution_analyst",
            execution_value,
            execution_plan.get("pricing_note", execution_plan.get("reason", "执行价位未生成")),
            {
                "suggested_buy_price": execution_plan.get("suggested_buy_price"),
                "suggested_sell_price": execution_plan.get("suggested_sell_price"),
            },
        ),
    }
    return payload


def weighted_final_score(analyst_signals: dict[str, dict[str, Any]]) -> int:
    numerator = 0.0
    denominator = 0.0
    for key, signal in analyst_signals.items():
        config = ANALYSIS_REGISTRY.get(key)
        if not config:
            continue
        weight = float(config["weight"])
        numerator += float(signal["score"]) * weight
        denominator += weight
    if denominator <= 0:
        return 50
    return _bounded_score(round(numerator / denominator))


def _make_signal(key: str, score: int, reasoning: str, metrics: dict[str, Any]) -> dict[str, Any]:
    config = ANALYSIS_REGISTRY[key]
    return {
        "display_name": config["display_name"],
        "score": score,
        "signal": _signal_from_score(score),
        "confidence": score,
        "reasoning": reasoning,
        "weight": config["weight"],
        "metrics": metrics,
    }


def _signal_from_score(score: int) -> str:
    if score >= 70:
        return "bullish"
    if score <= 40:
        return "bearish"
    return "neutral"


def _bounded_score(value: Any) -> int:
    try:
        score = int(round(float(value)))
    except (TypeError, ValueError):
        score = 50
    return max(0, min(100, score))
