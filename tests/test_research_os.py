from datetime import date

import news_alpha.ai_research_pipeline as ai_pipeline_module
import news_alpha.research_os as research_os_module
from news_alpha.research_os import (
    ResearchRequest,
    _apply_confidence_gate_to_action,
    _build_ai_participation_status,
    _build_high_confidence_gate,
    audit_copy_payload,
    build_product_overview,
    build_research_workspace,
    default_demo_request,
)


def test_research_workspace_contains_required_product_outputs() -> None:
    payload = default_demo_request()
    payload["use_live_news"] = False
    request = ResearchRequest.from_dict(payload)

    workspace = build_research_workspace(request, as_of=date(2026, 4, 9))

    assert set(workspace).issuperset(
        {
            "news_stream",
            "hotspot_events",
            "industry_views",
            "candidate_stocks",
            "recommendation_views",
            "recommendation_history",
            "portfolio_plan",
            "daily_digest",
            "ai_research_pipeline",
            "source_diagnostics",
            "ai_participation_status",
            "agent_trace",
        }
    )
    assert len(workspace["agent_trace"]) == 6
    assert workspace["compliance"]["is_compliant"] is True

    event = workspace["hotspot_events"][0]
    for field in (
        "title",
        "event_summary",
        "industry_impacts",
        "heat_score",
        "supporting_news",
        "invalidation_conditions",
        "event_master_id",
        "event_instance_id",
        "event_signature",
        "profit_propagation",
        "source_diversity_score",
        "source_diversity_label",
        "source_diversity_detail",
        "coverage_gap_warning",
    ):
        assert field in event
    assert 0 <= event["heat_score"] <= 100
    assert event["event_master_id"].startswith("evt_")
    assert event["event_instance_id"].startswith(event["event_master_id"])
    assert event["profit_propagation"]["primary_profit_centers"]
    assert "segments" in event["profit_propagation"]
    assert event["event_master_id"] in event["event_instance_id"]

    industry_view = workspace["industry_views"][0]
    assert "profit_propagation" in industry_view
    assert "primary_profit_centers" in industry_view["profit_propagation"]

    recommendation = workspace["recommendation_views"][0]
    for field in (
        "action",
        "core_logic",
        "catalysts",
        "risks",
        "target_return_pct",
        "confidence",
        "profit_focus_summary",
        "profit_focus_nodes",
        "invalidation_conditions",
        "evidence_chain",
        "technical_overlay",
        "execution_plan",
        "price_snapshot",
        "valuation_snapshot",
        "fundamental_snapshot",
        "market_score",
        "fundamental_score",
        "risk_score",
        "confidence_gate",
        "company_profile",
        "final_score",
        "analyst_signals",
        "manager_summary",
        "manager_rationale",
        "base_action",
        "source_diversity_score",
        "source_diversity_label",
        "source_diversity_detail",
        "coverage_gap_warning",
        "crowding_penalty",
    ):
        assert field in recommendation
    assert "technical_score" in recommendation["technical_overlay"]
    assert recommendation["technical_overlay"]["provider"] == "mock"
    assert recommendation["price_snapshot"]["status"] in {"ok", "missing"}
    assert recommendation["valuation_snapshot"]["status"] in {"ok", "missing"}
    assert recommendation["fundamental_snapshot"]["status"] in {"ok", "missing"}
    assert recommendation["execution_plan"]["status"] in {"ok", "missing"}
    assert "event_analyst" in recommendation["analyst_signals"]
    assert "beneficiary_analyst" in recommendation["analyst_signals"]
    assert "risk_analyst" in recommendation["analyst_signals"]
    assert isinstance(recommendation["manager_rationale"], list)
    assert "penalty" in recommendation["crowding_penalty"]
    assert "profile_completeness" in recommendation["company_profile"]
    assert "high_confidence_eligible" in recommendation["confidence_gate"]
    assert "event_master_ids" in recommendation["evidence_chain"]
    assert isinstance(recommendation["profit_focus_nodes"], list)
    assert "source_diversity_score" in workspace["news_stream"]
    assert "coverage_gap_warning" in workspace["news_stream"]
    assert "source_diversity_score" in workspace["daily_digest"]
    assert "coverage_gaps" in workspace["daily_digest"]
    assert "layer_counts" in workspace["source_diagnostics"]
    assert "stages" in workspace["ai_participation_status"]
    assert workspace["portfolio_plan"]["target_positions"]
    assert workspace["ai_research_pipeline"]["status"] in {"disabled", "missing_credentials", "ok", "partial", "error"}
    assert "news_localization" in workspace["ai_research_pipeline"]
    assert "goal" in workspace["ai_research_pipeline"]["event_understanding"]
    assert "constraints" in workspace["ai_research_pipeline"]["event_understanding"]
    assert "next_stage_goal" in workspace["ai_research_pipeline"]["event_understanding"]
    assert "company_beneficiary_ranking" in workspace["ai_research_pipeline"]


def test_event_identity_and_profit_propagation_are_stable_for_same_snapshot() -> None:
    payload = default_demo_request()
    payload["use_live_news"] = False
    request = ResearchRequest.from_dict(payload)

    first = build_research_workspace(request, as_of=date(2026, 4, 9))
    second = build_research_workspace(request, as_of=date(2026, 4, 9))

    first_event = first["hotspot_events"][0]
    second_event = second["hotspot_events"][0]

    assert first_event["event_master_id"] == second_event["event_master_id"]
    assert first_event["event_instance_id"] == second_event["event_instance_id"]
    assert first_event["event_signature"] == second_event["event_signature"]
    assert first_event["profit_propagation"]["transmission_summary"]


def test_high_confidence_gate_blocks_buy_without_required_evidence() -> None:
    gate = _build_high_confidence_gate(
        source_coverage={"score": 42, "warning": "证据覆盖存在缺口"},
        price_snapshot={"status": "missing"},
        fundamental_snapshot={"status": "missing"},
        ai_research_pipeline={"enabled": True, "status": "error"},
        candidate={"selection_mode": "topic_scan"},
        related_events=[],
    )

    assert gate["high_confidence_eligible"] is False
    assert gate["strict_block"] is True
    assert _apply_confidence_gate_to_action(
        action="买入",
        confidence_gate=gate,
        is_watchlist=False,
    ) == "观察"


def test_negative_event_can_trigger_risk_card() -> None:
    payload = {
        "watchlist": [
            {
                "symbol": "002371",
                "name": "北方华创",
                "position_pct": 18,
                "thesis": "等待设备订单确认，但如果预算和资本开支放慢要快速下调预期。",
            }
        ],
        "focus_topics": ["国产替代", "预算"],
        "risk_thresholds": {
            "single_name_limit_pct": 15,
            "sector_limit_pct": 20,
            "negative_event_score_threshold": 60,
        },
        "personal_notes": "如果预算释放继续偏慢，需要马上提示我重做短期预期。",
    }

    payload["use_live_news"] = False
    workspace = build_research_workspace(ResearchRequest.from_dict(payload), as_of=date(2026, 4, 9))

    assert any(card["risk_type"] == "单名仓位超阈值" for card in workspace["risk_cards"])
    assert any(event["direction"] == "negative" for event in workspace["hotspot_events"])


def test_copy_audit_blocks_promissory_language() -> None:
    audit = audit_copy_payload("这是一个稳赚的自动荐股 AI顾问。")

    assert audit["is_compliant"] is False
    assert set(audit["blocked_terms"]) >= {"稳赚", "自动荐股", "AI顾问"}


def test_product_overview_is_safe_and_fixed() -> None:
    overview = build_product_overview()

    assert overview["pricing"]["monthly_rmb"] == 699
    assert overview["pricing"]["trial_days"] == 7
    assert overview["compliance"]["is_compliant"] is True
    assert overview["positioning"] == "事件驱动投研与建议平台"


def test_live_news_flag_uses_live_feed_when_available(monkeypatch) -> None:
    monkeypatch.setattr(
        research_os_module,
        "fetch_live_raw_news_feed",
        lambda **kwargs: [
            {
                "source_id": "live-1",
                "headline": "海外云厂商继续上调 AI capex",
                "summary": "用于验证 live 分支。",
                "source_name": "mock-live",
                "source_kind": "RSS",
                "region": "全球",
                "market_scope": "A股+港股",
                "credibility_score": 80,
                "published_offset_hours": 1,
                "tags": ["AI算力", "资本开支"],
            }
        ],
    )
    payload = default_demo_request()
    payload["use_live_news"] = True

    workspace = build_research_workspace(ResearchRequest.from_dict(payload), as_of=date(2026, 4, 9))

    assert any(item["source_name"] == "mock-live" for item in workspace["news_stream"]["daily"])


def test_ai_pipeline_can_expand_candidates_beyond_manual_company_catalog(monkeypatch) -> None:
    monkeypatch.setattr(
        research_os_module,
        "build_ai_research_pipeline",
        lambda **kwargs: {
            "enabled": True,
            "status": "ok",
            "provider": "mock",
            "model_name": "mock-model",
            "note": "mock",
            "event_understanding": {
                "stage": "event_understanding",
                "status": "ok",
                "message": "ok",
                "data": {"events": [{"event_name": "商业航天推进", "affected_sectors": ["国防军工"]}]},
            },
            "scenario_analysis": {
                "stage": "scenario_analysis",
                "status": "ok",
                "message": "ok",
                "data": {"scenarios": [{"base_case": "商业航天需求释放"}]},
            },
            "supply_chain_expansion": {
                "stage": "supply_chain_expansion",
                "status": "ok",
                "message": "ok",
                "data": {"industries": [{"industry_name": "国防军工"}]},
            },
        },
    )

    payload = default_demo_request()
    payload["use_live_news"] = False
    workspace = build_research_workspace(ResearchRequest.from_dict(payload), as_of=date(2026, 4, 9))

    assert any(item["symbol"] == "000519" for item in workspace["candidate_stocks"])


def test_ai_pipeline_can_augment_industry_views(monkeypatch) -> None:
    monkeypatch.setattr(
        research_os_module,
        "build_ai_research_pipeline",
        lambda **kwargs: {
            "enabled": True,
            "status": "ok",
            "provider": "mock",
            "model_name": "mock-model",
            "note": "mock",
            "event_understanding": {
                "stage": "event_understanding",
                "status": "ok",
                "message": "ok",
                "data": {"events": [{"event_name": "商业航天推进", "affected_sectors": ["国防军工"]}]},
            },
            "scenario_analysis": {
                "stage": "scenario_analysis",
                "status": "ok",
                "message": "ok",
                "data": {"scenarios": [{"base_case": "商业航天需求释放"}]},
            },
            "supply_chain_expansion": {
                "stage": "supply_chain_expansion",
                "status": "ok",
                "message": "ok",
                "data": {
                    "industries": [
                        {
                            "industry_name": "油运",
                            "summary": "AI 识别到油运链条存在新增的高弹性环节。",
                            "current_state": "催化强化",
                            "chain_nodes": [
                                {
                                    "name": "卫星导航与船队数字化",
                                    "stage": "AI 推演环节",
                                    "concentration_view": "集中度中等",
                                    "profit_pool_weight": "中",
                                    "beneficiary_type": "间接受益",
                                    "note": "通过船队数字化和调度优化受益。",
                                }
                            ],
                        }
                    ]
                },
            },
        },
    )

    payload = default_demo_request()
    payload["use_live_news"] = False
    workspace = build_research_workspace(ResearchRequest.from_dict(payload), as_of=date(2026, 4, 9))

    shipping = next(item for item in workspace["industry_views"] if item["industry_id"] == "shipping_energy")
    assert shipping["ai_generated"] is True
    assert "卫星导航与船队数字化" in shipping["ai_chain_expansion"]
    assert any(
        item["node_name"] == "卫星导航与船队数字化"
        for item in shipping["profit_propagation"]["segments"]
    )


def test_ai_company_ranking_can_promote_ranked_symbols(monkeypatch) -> None:
    monkeypatch.setattr(
        research_os_module,
        "build_ai_research_pipeline",
        lambda **kwargs: {
            "enabled": True,
            "status": "ok",
            "provider": "mock",
            "model_name": "mock-model",
            "note": "mock",
            "event_understanding": {"stage": "event_understanding", "status": "ok", "message": "ok", "data": {}},
            "scenario_analysis": {"stage": "scenario_analysis", "status": "ok", "message": "ok", "data": {}},
            "supply_chain_expansion": {"stage": "supply_chain_expansion", "status": "ok", "message": "ok", "data": {}},
            "company_beneficiary_ranking": {
                "stage": "company_beneficiary_ranking",
                "status": "ok",
                "message": "ok",
                "data": {
                    "companies": [
                        {
                            "symbol": "000519",
                            "company_name": "中兵红箭",
                            "beneficiary_rank": 1,
                            "beneficiary_level": "直接受益",
                            "ranking_rationale": "在商业航天和军工链条中具备高弹性。",
                            "key_profit_link": "订单弹性",
                            "caution": "仍需新增订单验证",
                        }
                    ]
                },
            },
        },
    )

    workspace = build_research_workspace(ResearchRequest.from_dict(default_demo_request()), as_of=date(2026, 4, 9))

    ranked = next(item for item in workspace["candidate_stocks"] if item["symbol"] == "000519")
    assert "ai_ranking" in ranked["selection_mode"]
    assert ranked["match_score"] >= 90


def test_ai_company_ranking_writes_into_core_logic(monkeypatch) -> None:
    monkeypatch.setattr(
        research_os_module,
        "build_ai_research_pipeline",
        lambda **kwargs: {
            "enabled": True,
            "status": "ok",
            "provider": "mock",
            "model_name": "mock-model",
            "note": "mock",
            "event_understanding": {"stage": "event_understanding", "status": "ok", "message": "ok", "data": {}},
            "scenario_analysis": {"stage": "scenario_analysis", "status": "ok", "message": "ok", "data": {}},
            "supply_chain_expansion": {"stage": "supply_chain_expansion", "status": "ok", "message": "ok", "data": {}},
            "company_beneficiary_ranking": {
                "stage": "company_beneficiary_ranking",
                "status": "ok",
                "message": "ok",
                "goal": "",
                "constraints": [],
                "output_contract": {},
                "next_stage_goal": "",
                "data": {
                    "companies": [
                        {
                            "symbol": "300308",
                            "company_name": "中际旭创",
                            "beneficiary_rank": 1,
                            "beneficiary_level": "直接受益",
                            "ranking_rationale": "直接承接利润弹性。",
                            "key_profit_link": "利润承接",
                            "caution": "",
                        }
                    ]
                },
            },
        },
    )

    workspace = build_research_workspace(ResearchRequest.from_dict(default_demo_request()), as_of=date(2026, 4, 9))
    rec = next(item for item in workspace["recommendation_views"] if item["symbol"] == "300308")

    assert "第 1 受益标的" in rec["core_logic"] or "第 1 位受益标的" in rec["core_logic"]


def test_ai_pipeline_short_circuits_on_quota_error(monkeypatch) -> None:
    def _raise_quota(*args, **kwargs):
        raise RuntimeError('HTTP 429: {"error":{"message":"You exceeded your current quota, please check your plan and billing details."}}')

    monkeypatch.setattr(ai_pipeline_module, "_chat_completion", _raise_quota)

    pipeline = ai_pipeline_module.build_ai_research_pipeline(
        news_items=[
            {
                "news_id": "n1",
                "headline": "headline",
                "summary": "summary",
                "source_name": "source",
                "source_kind": "RSS",
                "region": "全球",
                "market_scope": "A股+港股",
                "tags": ["AI算力"],
                "published_at": "2026-04-17T08:00",
                "hot_score": 80,
            }
        ],
        watchlist=tuple(),
        focus_topics=("AI算力",),
        personal_notes="",
        company_pool=[],
        model_settings={
            "enabled": True,
            "provider": "openai-compatible",
            "base_url": "https://api.openai.com/v1",
            "model_name": "gpt-5.4",
            "api_key": "sk-test",
            "timeout_seconds": 10,
        },
    )

    assert pipeline["status"] == "quota_exceeded"
    assert pipeline["news_localization"]["status"] == "quota_exceeded"
    assert pipeline["event_understanding"]["status"] == "blocked"
    assert pipeline["scenario_analysis"]["status"] == "blocked"
    status = _build_ai_participation_status(pipeline)
    assert status["failed_count"] == 1
    assert status["disabled_count"] == 4


def test_ai_pipeline_uses_environment_api_key(monkeypatch) -> None:
    received: dict[str, str] = {}

    def _capture_key(base_url, api_key, *args, **kwargs):
        received["api_key"] = api_key
        return "{}"

    monkeypatch.setenv("NEWS_ALPHA_API_KEY", "environment-key-for-test")
    monkeypatch.setattr(ai_pipeline_module, "_chat_completion", _capture_key)

    pipeline = ai_pipeline_module.build_ai_research_pipeline(
        news_items=[{"news_id": "n1", "headline": "headline", "summary": "summary"}],
        watchlist=tuple(),
        focus_topics=tuple(),
        personal_notes="",
        company_pool=[],
        model_settings={
            "enabled": True,
            "provider": "openai-compatible",
            "base_url": "https://example.com/v1",
            "model_name": "example-model",
            "api_key": "",
        },
    )

    assert received["api_key"] == "environment-key-for-test"
    assert pipeline["status"] == "partial"


def test_ai_pipeline_rejects_corrupted_question_mark_text(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_pipeline_module,
        "_chat_completion",
        lambda *args, **kwargs: '{"items":[{"news_id":"n1","translated_headline":"????????????","translated_summary":"????????????","language":"zh","translation_note":"bad"}]}',
    )

    pipeline = ai_pipeline_module.build_ai_research_pipeline(
        news_items=[
            {
                "news_id": "n1",
                "headline": "headline",
                "summary": "summary",
                "source_name": "source",
                "source_kind": "RSS",
                "region": "全球",
                "market_scope": "A股+港股",
                "tags": ["AI算力"],
                "published_at": "2026-04-17T08:00",
                "hot_score": 80,
            }
        ],
        watchlist=tuple(),
        focus_topics=("AI算力",),
        personal_notes="",
        company_pool=[],
        model_settings={
            "enabled": True,
            "provider": "codex-cli",
            "base_url": "",
            "model_name": "gpt-5.4",
            "api_key": "",
            "timeout_seconds": 90,
        },
    )

    assert pipeline["news_localization"]["status"] == "invalid_response"
    assert "编码乱码" in pipeline["news_localization"]["message"]
    assert pipeline["event_understanding"]["status"] == "blocked"
