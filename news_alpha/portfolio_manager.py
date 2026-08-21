"""Portfolio manager and position sizing engine for the research workspace."""

from __future__ import annotations

from collections import defaultdict
from typing import Any


def build_portfolio_plan(
    *,
    recommendations: list[dict[str, Any]],
    watchlist: list[dict[str, Any]],
    risk_thresholds: dict[str, Any],
) -> dict[str, Any]:
    watch_map = {str(item.get("symbol", "")).strip(): item for item in watchlist if str(item.get("symbol", "")).strip()}
    single_limit = float(risk_thresholds.get("single_name_limit_pct", 15) or 15)
    sector_limit = float(risk_thresholds.get("sector_limit_pct", 22) or 22)

    ranked = sorted(
        recommendations,
        key=lambda item: (
            int(item.get("final_score", item.get("score", 0)) or 0),
            float(item.get("confidence", 0) or 0),
        ),
        reverse=True,
    )

    target_positions: list[dict[str, Any]] = []
    for index, item in enumerate(ranked[:8], start=1):
        symbol = str(item.get("symbol", "")).strip()
        current_position = float((watch_map.get(symbol) or {}).get("position_pct", 0) or 0)
        industry_name = str(
            (item.get("company_profile") or {}).get("industry_name")
            or (item.get("related_industries") or [None])[0]
            or "未知行业"
        )
        suggested_position = _suggested_position_pct(
            recommendation=item,
            current_position=current_position,
            single_limit=single_limit,
        )
        target_positions.append(
            {
                "priority_rank": index,
                "symbol": symbol,
                "name": item.get("name"),
                "action": item.get("action"),
                "final_score": item.get("final_score", item.get("score")),
                "confidence": item.get("confidence"),
                "industry_name": industry_name,
                "current_position_pct": round(current_position, 1),
                "base_suggested_position_pct": suggested_position,
                "suggested_position_pct": suggested_position,
                "position_delta_pct": 0.0,
                "sizing_bucket": "",
                "sizing_reason": "",
                "applied_constraints": [],
            }
        )

    constraint_actions: list[dict[str, Any]] = []
    _apply_sector_caps(target_positions, sector_limit, constraint_actions)
    risk_budget = _build_risk_budget(target_positions, ranked, sector_limit)
    _apply_total_risk_budget(target_positions, risk_budget["target_gross_exposure_pct"], constraint_actions)
    _finalize_target_positions(target_positions)

    current_industry_exposure: dict[str, float] = defaultdict(float)
    for item in watchlist:
        industry_name = str(item.get("industry_name") or "未知行业")
        current_industry_exposure[industry_name] += float(item.get("position_pct", 0) or 0)

    target_industry_exposure = _build_target_industry_exposure(target_positions)
    concentration_alerts = [
        {
            "industry_name": industry,
            "target_exposure_pct": round(weight, 1),
            "threshold_pct": sector_limit,
            "reason": f"{industry} 目标权重 {weight:.1f}% 高于行业阈值 {sector_limit:.1f}%。",
        }
        for industry, weight in sorted(target_industry_exposure.items(), key=lambda kv: kv[1], reverse=True)
        if weight > sector_limit
    ]

    suggested_invested = round(sum(item["suggested_position_pct"] for item in target_positions), 1)
    cash_buffer = max(0.0, round(100.0 - suggested_invested, 1))
    theme_exposure = _build_theme_exposure(current_industry_exposure, target_industry_exposure, sector_limit)

    add_order = [
        {
            "symbol": item["symbol"],
            "name": item["name"],
            "delta_pct": item["position_delta_pct"],
            "reason": item["sizing_reason"],
        }
        for item in target_positions
        if item["position_delta_pct"] > 0
    ]
    trim_order = [
        {
            "symbol": item["symbol"],
            "name": item["name"],
            "delta_pct": item["position_delta_pct"],
            "reason": item["sizing_reason"],
        }
        for item in target_positions
        if item["position_delta_pct"] < 0
    ]

    target_by_symbol = {item["symbol"]: item for item in target_positions}
    replay_new = [item for item in target_positions if item["current_position_pct"] <= 0 and item["suggested_position_pct"] > 0]
    replay_increase = [item for item in target_positions if item["current_position_pct"] > 0 and item["position_delta_pct"] > 0]
    replay_trim = [item for item in target_positions if item["current_position_pct"] > 0 and item["position_delta_pct"] < 0]
    replay_hold = [item for item in target_positions if item["current_position_pct"] > 0 and abs(item["position_delta_pct"]) < 0.1]
    replay_remove = []
    for item in watchlist:
        symbol = str(item.get("symbol", "")).strip()
        current_pct = float(item.get("position_pct", 0) or 0)
        if not symbol or current_pct <= 0:
            continue
        target = target_by_symbol.get(symbol)
        if target and target["suggested_position_pct"] > 0:
            continue
        replay_remove.append(
            {
                "symbol": symbol,
                "name": item.get("name") or symbol,
                "current_position_pct": round(current_pct, 1),
                "reason": "当前组合建议不再保留该仓位。",
            }
        )

    portfolio_replay = {
        "summary": (
            f"新增 {len(replay_new)} 只，增加 {len(replay_increase)} 只，"
            f"维持 {len(replay_hold)} 只，降低 {len(replay_trim)} 只，移除 {len(replay_remove)} 只。"
        ),
        "new_positions": _replay_items(replay_new),
        "increase_positions": _replay_items(replay_increase),
        "hold_positions": _replay_items(replay_hold),
        "trim_positions": _replay_items(replay_trim),
        "remove_positions": replay_remove[:5],
    }

    return {
        "summary": (
            f"建议组合总投入约 {suggested_invested:.1f}% ，保留现金缓冲 {cash_buffer:.1f}% 。"
            f" 当前优先加仓 {len(add_order)} 只，需降低暴露 {len(trim_order)} 只。"
        ),
        "single_name_limit_pct": single_limit,
        "sector_limit_pct": sector_limit,
        "cash_buffer_pct": cash_buffer,
        "suggested_invested_pct": suggested_invested,
        "target_positions": target_positions,
        "add_order": add_order[:5],
        "trim_order": trim_order[:5],
        "current_industry_exposure": [
            {"industry_name": industry, "current_position_pct": round(weight, 1)}
            for industry, weight in sorted(current_industry_exposure.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "target_industry_exposure": [
            {"industry_name": industry, "target_position_pct": round(weight, 1)}
            for industry, weight in sorted(target_industry_exposure.items(), key=lambda kv: kv[1], reverse=True)
        ],
        "theme_exposure": theme_exposure,
        "concentration_alerts": concentration_alerts,
        "portfolio_replay": portfolio_replay,
        "risk_budget": risk_budget,
        "applied_constraints": constraint_actions,
    }


def _suggested_position_pct(
    *,
    recommendation: dict[str, Any],
    current_position: float,
    single_limit: float,
) -> float:
    action = str(recommendation.get("action") or "")
    final_score = float(recommendation.get("final_score", recommendation.get("score", 0)) or 0)
    confidence = float(recommendation.get("confidence", 0) or 0)
    gate = recommendation.get("confidence_gate", {}) or {}
    beneficiary_rank = recommendation.get("ai_beneficiary_rank")
    beneficiary_level = str(recommendation.get("ai_beneficiary_level") or "")

    if action == "卖出":
        return 0.0
    if action == "观察" and current_position <= 0:
        return 0.0

    target = 0.0
    if action == "买入":
        if final_score >= 90 and confidence >= 0.72 and gate.get("high_confidence_eligible"):
            target = min(single_limit, 10.0)
        elif final_score >= 84 and confidence >= 0.65:
            target = min(single_limit, 8.0)
        elif final_score >= 76:
            target = min(single_limit, 6.0)
        else:
            target = min(single_limit, 4.0)
    elif action == "持有":
        target = max(current_position, min(single_limit, 5.0 if final_score >= 80 else 3.0))
    else:
        target = current_position if current_position > 0 else 0.0

    if beneficiary_rank and int(beneficiary_rank) <= 3 and beneficiary_level in {"直接受益", "核心受益", "高优先级"}:
        target = min(single_limit, target + 2.0)
    elif beneficiary_level in {"主题映射", "间接受益"}:
        target = max(0.0, target - 1.0)
    elif beneficiary_level in {"弱相关", "低优先级"}:
        target = max(0.0, target - 2.0)

    if not gate.get("high_confidence_eligible", True):
        target = min(target, 5.0 if current_position > 0 else 3.0)

    return round(max(0.0, min(single_limit, target)), 1)


def _build_risk_budget(
    target_positions: list[dict[str, Any]],
    ranked_recommendations: list[dict[str, Any]],
    sector_limit: float,
) -> dict[str, Any]:
    top = ranked_recommendations[:5]
    high_conviction = [
        item
        for item in top
        if str(item.get("action") or "") == "买入"
        and float(item.get("confidence", 0) or 0) >= 0.65
        and (item.get("confidence_gate", {}) or {}).get("high_confidence_eligible", True)
    ]
    avg_confidence = round(
        sum(float(item.get("confidence", 0) or 0) for item in top) / len(top),
        2,
    ) if top else 0.0
    strict_block_count = sum(
        1
        for item in top
        if (item.get("confidence_gate", {}) or {}).get("strict_block")
    )
    if len(high_conviction) >= 3 and avg_confidence >= 0.68:
        regime = "进攻"
        target_gross = 55.0
        regime_reason = "高确信买入数量充足且平均置信度较高，可适度提高总暴露。"
    elif len(high_conviction) >= 2 and avg_confidence >= 0.6:
        regime = "平衡"
        target_gross = 42.0
        regime_reason = "高确信标的不少，但证据强度还不足以切到进攻配置。"
    else:
        regime = "谨慎"
        target_gross = 30.0
        regime_reason = "高确信标的不足或证据强度偏弱，应优先保留现金缓冲。"
    if strict_block_count >= 2:
        target_gross = max(22.0, target_gross - 8.0)
    sector_over_limit = any(
        sum(item["suggested_position_pct"] for item in target_positions if item["industry_name"] == industry) > sector_limit
        for industry in {item["industry_name"] for item in target_positions}
    )
    if sector_over_limit:
        target_gross = max(22.0, target_gross - 4.0)
    current_target = round(sum(item["suggested_position_pct"] for item in target_positions), 1)
    drivers = [
        f"高确信买入 {len(high_conviction)} 只",
        f"平均置信度 {avg_confidence}",
    ]
    if strict_block_count:
        drivers.append(f"严格门槛拦截 {strict_block_count} 只")
    if sector_over_limit:
        drivers.append("存在主题/行业超限，需要额外压仓")
    if current_target > target_gross:
        drivers.append(f"原始目标总暴露 {current_target:.1f}% 高于风险预算 {target_gross:.1f}%")
    return {
        "regime": regime,
        "regime_reason": regime_reason,
        "target_gross_exposure_pct": round(target_gross, 1),
        "avg_confidence": avg_confidence,
        "high_conviction_count": len(high_conviction),
        "strict_block_count": strict_block_count,
        "sector_over_limit": sector_over_limit,
        "pre_constraint_target_gross_pct": current_target,
        "target_cash_buffer_pct": round(max(0.0, 100.0 - target_gross), 1),
        "requires_scaling": current_target > target_gross,
        "drivers": drivers,
        "summary": f"{regime} 风格下建议风险预算 {target_gross:.1f}% ，现金缓冲 {max(0.0, 100.0 - target_gross):.1f}%。",
    }


def _apply_sector_caps(
    target_positions: list[dict[str, Any]],
    sector_limit: float,
    actions: list[dict[str, Any]],
) -> None:
    by_industry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in target_positions:
        by_industry[item["industry_name"]].append(item)

    for industry, items in by_industry.items():
        total = sum(item["suggested_position_pct"] for item in items)
        if total <= sector_limit or total <= 0:
            continue
        scale = sector_limit / total
        for item in items:
            original = item["suggested_position_pct"]
            item["suggested_position_pct"] = round(original * scale, 1)
            item["applied_constraints"].append(f"行业上限压缩至 {sector_limit:.1f}%")
        actions.append(
            {
                "constraint_type": "sector_cap",
                "industry_name": industry,
                "before_pct": round(total, 1),
                "after_pct": round(sum(item["suggested_position_pct"] for item in items), 1),
                "reason": f"{industry} 原始目标暴露 {total:.1f}% ，按行业上限压缩到 {sector_limit:.1f}%。",
            }
        )


def _apply_total_risk_budget(
    target_positions: list[dict[str, Any]],
    target_gross_exposure_pct: float,
    actions: list[dict[str, Any]],
) -> None:
    total = sum(item["suggested_position_pct"] for item in target_positions)
    if total <= target_gross_exposure_pct or total <= 0:
        return
    scale = target_gross_exposure_pct / total
    for item in target_positions:
        original = item["suggested_position_pct"]
        item["suggested_position_pct"] = round(original * scale, 1)
        item["applied_constraints"].append(f"总风险预算压缩至 {target_gross_exposure_pct:.1f}%")
    actions.append(
        {
            "constraint_type": "risk_budget",
            "before_pct": round(total, 1),
            "after_pct": round(sum(item["suggested_position_pct"] for item in target_positions), 1),
            "reason": f"原始目标总暴露 {total:.1f}% ，按风险预算压缩到 {target_gross_exposure_pct:.1f}%。",
        }
    )


def _finalize_target_positions(target_positions: list[dict[str, Any]]) -> None:
    for item in target_positions:
        suggested = round(float(item.get("suggested_position_pct", 0) or 0), 1)
        current = round(float(item.get("current_position_pct", 0) or 0), 1)
        item["suggested_position_pct"] = suggested
        item["position_delta_pct"] = round(suggested - current, 1)
        item["sizing_bucket"] = _sizing_bucket(suggested)
        item["sizing_reason"] = _sizing_reason(item, suggested, current)


def _build_target_industry_exposure(target_positions: list[dict[str, Any]]) -> dict[str, float]:
    totals: dict[str, float] = defaultdict(float)
    for item in target_positions:
        totals[item["industry_name"]] += float(item["suggested_position_pct"] or 0)
    return totals


def _build_theme_exposure(
    current_industry_exposure: dict[str, float],
    target_industry_exposure: dict[str, float],
    sector_limit: float,
) -> list[dict[str, Any]]:
    theme_exposure: list[dict[str, Any]] = []
    for industry in sorted(set(current_industry_exposure) | set(target_industry_exposure)):
        current_pct = round(float(current_industry_exposure.get(industry, 0.0)), 1)
        target_pct = round(float(target_industry_exposure.get(industry, 0.0)), 1)
        theme_exposure.append(
            {
                "industry_name": industry,
                "current_position_pct": current_pct,
                "target_position_pct": target_pct,
                "delta_pct": round(target_pct - current_pct, 1),
                "limit_utilization_pct": round(min(100.0, (target_pct / sector_limit) * 100), 1) if sector_limit else 0.0,
                "over_limit": target_pct > sector_limit,
            }
        )
    return sorted(theme_exposure, key=lambda item: item["target_position_pct"], reverse=True)


def _sizing_bucket(suggested_position: float) -> str:
    if suggested_position >= 9:
        return "核心仓位"
    if suggested_position >= 6:
        return "标准仓位"
    if suggested_position >= 3:
        return "试探仓位"
    if suggested_position > 0:
        return "观察跟踪"
    return "不配置"


def _sizing_reason(recommendation: dict[str, Any], suggested_position: float, current_position: float) -> str:
    action = str(recommendation.get("action") or "")
    final_score = recommendation.get("final_score", recommendation.get("score", 0))
    beneficiary_rank = recommendation.get("ai_beneficiary_rank")
    gate = recommendation.get("confidence_gate", {}) or {}
    constraints = recommendation.get("applied_constraints", []) or []
    constraint_text = f"（{constraints[-1]}）" if constraints else ""
    if suggested_position <= 0:
        return "当前建议不支持配置仓位。"
    if action == "买入" and gate.get("high_confidence_eligible", True):
        if beneficiary_rank:
            return f"综合分 {final_score}，AI 排名第 {beneficiary_rank} 位，适合按 {suggested_position:.1f}% 建立仓位。{constraint_text}"
        return f"综合分 {final_score}，建议按 {suggested_position:.1f}% 建立仓位。{constraint_text}"
    if action == "持有":
        return f"当前更适合持有跟踪，建议仓位维持在 {suggested_position:.1f}% 附近。{constraint_text}"
    if not gate.get("high_confidence_eligible", True):
        return f"高置信度门槛未过，先把仓位压到 {suggested_position:.1f}% 以内。{constraint_text}"
    if current_position > suggested_position:
        return f"当前仓位高于建议，宜降至 {suggested_position:.1f}% 附近。{constraint_text}"
    return f"建议作为试探/观察仓位控制在 {suggested_position:.1f}% 左右。{constraint_text}"


def _replay_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "symbol": item["symbol"],
            "name": item["name"],
            "current_position_pct": item["current_position_pct"],
            "suggested_position_pct": item["suggested_position_pct"],
            "position_delta_pct": item["position_delta_pct"],
            "sizing_reason": item["sizing_reason"],
        }
        for item in items[:5]
    ]
