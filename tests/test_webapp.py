from news_alpha.research_os import default_demo_request
from news_alpha.webapp import create_app


def test_homepage_renders_core_positioning() -> None:
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        response = client.get("/")
        portfolio_response = client.get("/portfolio")
        script_response = client.get("/static/app.js")

    assert response.status_code == 200
    assert portfolio_response.status_code == 200
    assert script_response.status_code == 200
    page = response.get_data(as_text=True)
    portfolio_page = portfolio_response.get_data(as_text=True)
    script = script_response.get_data(as_text=True)
    assert "新闻驱动选股系统" in page
    assert "组合终端" in portfolio_page
    assert "formDefaults" in page
    assert "盘中 + 日度双节奏" in page
    assert "自动荐股" not in page
    assert "查看原文" in script


def test_generate_endpoint_returns_workspace() -> None:
    app = create_app()
    app.testing = True
    payload = default_demo_request()
    payload["use_live_news"] = False

    with app.test_client() as client:
        response = client.post("/api/research/generate", json=payload)

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["compliance"]["is_compliant"] is True
    assert len(payload["hotspot_events"]) >= 1
    assert len(payload["recommendation_views"]) >= 1
    assert payload["daily_digest"]["headline"]
    assert payload["storage"]["run_id"]
    assert "run_comparison" in payload
    assert "portfolio_comparison" in payload
    assert "portfolio_timeline" in payload
    assert "event_history" in payload["hotspot_events"][0]


def test_compliance_audit_endpoint_flags_banned_terms() -> None:
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        response = client.post("/api/compliance/audit", json={"copy_text": "这是稳赚的AI顾问"})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["is_compliant"] is False


def test_public_api_endpoints_return_new_views() -> None:
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        news_response = client.get("/api/news/stream")
        events_response = client.get("/api/events")
        recommendations_response = client.get("/api/recommendations")
        codex_status_response = client.get("/api/model/codex-status")

    assert news_response.status_code == 200
    assert events_response.status_code == 200
    assert recommendations_response.status_code == 200
    assert codex_status_response.status_code == 200
    assert len(news_response.get_json()["intraday"]) >= 1
    assert len(events_response.get_json()) >= 1
    assert len(recommendations_response.get_json()) >= 1


def test_history_endpoints_return_persisted_runs() -> None:
    app = create_app()
    app.testing = True
    payload = default_demo_request()
    payload["use_live_news"] = False

    with app.test_client() as client:
        generate_response = client.post("/api/research/generate", json=payload)
        generated_payload = generate_response.get_json()
        run_id = generated_payload["storage"]["run_id"]
        runs_response = client.get("/api/history/runs")
        detail_response = client.get(f"/api/history/runs/{run_id}")
        portfolio_detail_response = client.get(f"/api/history/portfolio/{run_id}")
        symbol = generate_response.get_json()["recommendation_views"][0]["symbol"]
        symbol_history_response = client.get(f"/api/history/recommendations/{symbol}")
        event_master_id = generated_payload["hotspot_events"][0]["event_master_id"]
        event_history_response = client.get(f"/api/history/events/{event_master_id}")

    assert runs_response.status_code == 200
    assert detail_response.status_code == 200
    assert portfolio_detail_response.status_code == 200
    assert symbol_history_response.status_code == 200
    assert event_history_response.status_code == 200
    assert any(item["run_id"] == run_id for item in runs_response.get_json())
    assert detail_response.get_json()["generated_at"]
    assert "run_comparison" in detail_response.get_json()
    assert "portfolio_comparison" in detail_response.get_json()
    assert "portfolio_timeline" in detail_response.get_json()
    assert "portfolio_plan" in portfolio_detail_response.get_json()
    assert event_history_response.get_json()["history"]
    assert "related_recommendations" in event_history_response.get_json()
    assert "related_industries" in event_history_response.get_json()
    assert len(symbol_history_response.get_json()) >= 1


def test_history_delete_and_clear_endpoints_work() -> None:
    app = create_app()
    app.testing = True
    payload = default_demo_request()
    payload["use_live_news"] = False

    with app.test_client() as client:
        first = client.post("/api/research/generate", json=payload).get_json()["storage"]["run_id"]
        second = client.post("/api/research/generate", json=payload).get_json()["storage"]["run_id"]
        delete_response = client.delete(f"/api/history/runs/{first}")
        runs_after_delete = client.get("/api/history/runs").get_json()
        clear_response = client.delete("/api/history/runs")
        runs_after_clear = client.get("/api/history/runs").get_json()

    assert delete_response.status_code == 200
    assert all(item["run_id"] != first for item in runs_after_delete)
    assert any(item["run_id"] == second for item in runs_after_delete)
    assert clear_response.status_code == 200
    assert runs_after_clear == []


def test_settings_endpoints_save_and_return_masked_configuration() -> None:
    app = create_app()
    app.testing = True

    with app.test_client() as client:
        save_response = client.post(
            "/api/settings",
            json={
                "focus_topics": ["新一代信息技术", "集成电路"],
                "personal_notes": "测试研究笔记",
                "use_live_news": True,
                "risk_thresholds": {
                    "single_name_limit_pct": 18,
                    "sector_limit_pct": 25,
                    "negative_event_score_threshold": 66,
                },
                "rss_sources_text": "https://example.com/rss | 我的源 | 全球 | A股+港股",
                "technical_settings": {
                    "provider": "akshare",
                    "endpoint": "",
                },
                "model_settings": {
                    "enabled": True,
                    "provider": "openai-compatible",
                    "base_url": "https://api.example.com/v1",
                    "model_name": "demo-model",
                    "api_key": "secret-key-123456",
                },
            },
        )
        get_response = client.get("/api/settings")

    assert save_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.get_json()
    assert payload["rss_sources_text"].startswith("https://example.com/rss")
    assert payload["focus_topics"] == ["新一代信息技术", "集成电路"]
    assert payload["personal_notes"] == "测试研究笔记"
    assert payload["risk_thresholds"]["single_name_limit_pct"] == 18
    assert payload["technical_settings"]["provider"] == "akshare"
    assert payload["model_settings"]["has_api_key"] is True
    assert "api_key" not in payload["model_settings"]
