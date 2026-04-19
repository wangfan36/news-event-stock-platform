from iching_alpha.recommendation_manager import synthesize_recommendation


def _minimal_payload(level: str, score: int) -> dict:
    return synthesize_recommendation(
        candidate={"name": "测试公司", "industry_name": "测试行业", "is_watchlist": False},
        base_action="观察",
        base_score=72,
        related_events=[{"title": "测试事件"}],
        technical_overlay={"technical_score": 70, "trend_alignment": "顺势确认", "provider": "mock", "provider_status": "ok", "setup_quality": "优秀"},
        market_score={"score": 72, "label": "较强", "reason": "市场尚可"},
        fundamental_score={"score": 68, "label": "较强", "reason": "基本面尚可"},
        beneficiary_score={"score": score, "rank": 1 if score >= 80 else 8, "level": level, "boost": 0, "reason": "AI 排名结果"},
        risk_score={"score": 60, "label": "中性赔率", "reason": "风险中性"},
        execution_plan={"status": "ok", "pricing_note": "测试"},
    )


def test_beneficiary_signal_can_upgrade_action() -> None:
    decision = _minimal_payload("直接受益", 88)
    assert decision["manager_action"] == "买入"


def test_weak_beneficiary_signal_can_hold_back_action() -> None:
    decision = _minimal_payload("弱相关", 35)
    assert decision["manager_action"] == "观察"


def test_indirect_beneficiary_signal_keeps_action_conservative() -> None:
    decision = _minimal_payload("主题映射", 72)
    assert decision["manager_action"] in {"观察", "持有"}
