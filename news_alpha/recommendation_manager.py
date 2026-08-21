"""Final recommendation synthesis over registered analysis modules."""

from __future__ import annotations

from typing import Any

from .analysis_registry import build_analyst_signals, weighted_final_score


def synthesize_recommendation(
    *,
    candidate: dict[str, Any],
    base_action: str,
    base_score: int,
    related_events: list[dict[str, Any]],
    technical_overlay: dict[str, Any],
    market_score: dict[str, Any],
    fundamental_score: dict[str, Any],
    beneficiary_score: dict[str, Any],
    risk_score: dict[str, Any],
    execution_plan: dict[str, Any],
) -> dict[str, Any]:
    analyst_signals = build_analyst_signals(
        base_event_score=base_score,
        technical_overlay=technical_overlay,
        market_score=market_score,
        fundamental_score=fundamental_score,
        beneficiary_score=beneficiary_score,
        risk_score=risk_score,
        execution_plan=execution_plan,
        related_events=related_events,
        candidate=candidate,
    )
    final_score = weighted_final_score(analyst_signals)
    manager_action = _manager_action(
        base_action,
        final_score,
        candidate.get("is_watchlist", False),
        analyst_signals.get("beneficiary_analyst", {}),
    )
    return {
        "analyst_signals": analyst_signals,
        "manager_action": manager_action,
        "manager_summary": _manager_summary(manager_action, final_score, candidate, analyst_signals),
        "manager_rationale": _manager_rationale(analyst_signals),
        "final_score": final_score,
    }


def _manager_action(
    base_action: str,
    final_score: int,
    is_watchlist: bool,
    beneficiary_signal: dict[str, Any] | None = None,
) -> str:
    beneficiary_signal = beneficiary_signal or {}
    beneficiary_score = int(beneficiary_signal.get("score", 50) or 50)
    metrics = beneficiary_signal.get("metrics", {}) or {}
    beneficiary_level = str(metrics.get("level", "") or "")
    if base_action == "卖出":
        if beneficiary_score >= 80:
            return "观察"
        return "卖出" if final_score <= 55 else "观察"
    if beneficiary_level in {"弱相关", "低优先级"}:
        if is_watchlist and final_score >= 90:
            return "持有"
        return "观察"
    if beneficiary_level in {"主题映射", "间接受益"}:
        if final_score >= 88:
            return "买入"
        if final_score >= 70:
            return "持有" if is_watchlist else "观察"
        return "观察"
    if beneficiary_score >= 80:
        if final_score >= 70:
            return "买入"
        if final_score >= 62:
            return "持有" if is_watchlist else "观察"
    if final_score >= 82:
        return "买入"
    if final_score >= 68:
        return "持有" if is_watchlist else "观察"
    return "观察"


def _manager_summary(
    manager_action: str,
    final_score: int,
    candidate: dict[str, Any],
    analyst_signals: dict[str, dict[str, Any]],
) -> str:
    top_signal = max(analyst_signals.values(), key=lambda item: item["score"])
    beneficiary = analyst_signals.get("beneficiary_analyst", {})
    beneficiary_reason = beneficiary.get("reasoning", "")
    beneficiary_level = str((beneficiary.get("metrics", {}) or {}).get("level", "") or "")
    if beneficiary_reason and beneficiary.get("score", 0) >= 70:
        return (
            f"{candidate['name']} 当前收口动作为 {manager_action}，综合分 {final_score}。"
            f"AI 受益排序认为它处于{beneficiary_level or '高优先级'}受益位置；最强支撑来自 {top_signal['display_name']}。"
        )
    return (
        f"{candidate['name']} 当前收口动作为 {manager_action}，综合分 {final_score}。"
        f"最强支撑来自 {top_signal['display_name']}。"
    )


def _manager_rationale(analyst_signals: dict[str, dict[str, Any]]) -> list[str]:
    ordered = sorted(analyst_signals.values(), key=lambda item: item["weight"], reverse=True)
    return [
        f"{item['display_name']}: {item['score']} / {item['reasoning']}"
        for item in ordered
    ]
