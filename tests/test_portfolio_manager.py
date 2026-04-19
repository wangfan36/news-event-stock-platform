from iching_alpha.portfolio_manager import build_portfolio_plan


def test_portfolio_plan_builds_target_positions_and_alerts() -> None:
    recommendations = [
        {
            "symbol": "300308",
            "name": "中际旭创",
            "action": "买入",
            "final_score": 91,
            "confidence": 0.78,
            "ai_beneficiary_rank": 1,
            "ai_beneficiary_level": "直接受益",
            "confidence_gate": {"high_confidence_eligible": True},
            "company_profile": {"industry_name": "AI 光模块与交换链"},
            "related_industries": ["AI 光模块与交换链"],
        },
        {
            "symbol": "300502",
            "name": "新易盛",
            "action": "买入",
            "final_score": 86,
            "confidence": 0.69,
            "ai_beneficiary_rank": 2,
            "ai_beneficiary_level": "直接受益",
            "confidence_gate": {"high_confidence_eligible": True},
            "company_profile": {"industry_name": "AI 光模块与交换链"},
            "related_industries": ["AI 光模块与交换链"],
        },
        {
            "symbol": "600026",
            "name": "中远海能",
            "action": "观察",
            "final_score": 72,
            "confidence": 0.58,
            "ai_beneficiary_rank": None,
            "ai_beneficiary_level": "",
            "confidence_gate": {"high_confidence_eligible": False},
            "company_profile": {"industry_name": "油运与能源航运"},
            "related_industries": ["油运与能源航运"],
        },
    ]
    watchlist = [
        {"symbol": "300308", "name": "中际旭创", "position_pct": 8.0, "industry_name": "AI 光模块与交换链"},
        {"symbol": "300502", "name": "新易盛", "position_pct": 4.0, "industry_name": "AI 光模块与交换链"},
    ]
    plan = build_portfolio_plan(
        recommendations=recommendations,
        watchlist=watchlist,
        risk_thresholds={
            "single_name_limit_pct": 12,
            "sector_limit_pct": 12,
        },
    )

    assert plan["target_positions"]
    assert plan["target_positions"][0]["symbol"] == "300308"
    assert plan["target_positions"][0]["suggested_position_pct"] <= 12
    assert plan["theme_exposure"]
    assert plan["portfolio_replay"]["summary"]
    assert plan["risk_budget"]["summary"]
    assert plan["risk_budget"]["drivers"]
    assert plan["risk_budget"]["regime_reason"]
    assert "pre_constraint_target_gross_pct" in plan["risk_budget"]
    assert plan["applied_constraints"]
    assert any(item["constraint_type"] == "sector_cap" for item in plan["applied_constraints"])
