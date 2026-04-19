"""Flask app for the A-share research OS MVP."""

from __future__ import annotations

from datetime import date
import subprocess
from typing import Any

from flask import Flask, jsonify, render_template, request

from .data_refresh import get_news_data_status, get_stock_data_status, refresh_all_data
from .research_os import (
    REPO_ROOT,
    ResearchRequest,
    audit_copy_payload,
    build_product_overview,
    build_research_workspace,
    default_demo_request,
    load_internal_lab_snapshot,
)
from .storage import (
    clear_workspace_runs,
    delete_workspace_run,
    default_db_path,
    get_event_history_detail,
    get_event_histories,
    get_portfolio_comparison,
    get_portfolio_detail,
    get_portfolio_timeline,
    get_run_comparison,
    get_user_settings,
    get_symbol_history,
    get_workspace_run,
    list_workspace_runs,
    list_workspace_runs_grouped,
    merge_user_settings,
    persist_workspace,
    prepare_settings_for_storage,
    sanitize_settings_for_output,
    save_user_settings,
)


def _attach_event_histories(workspace: dict[str, Any], db_path) -> dict[str, Any]:
    events = workspace.get("hotspot_events", [])
    event_master_ids = [str(item.get("event_master_id") or "").strip() for item in events if str(item.get("event_master_id") or "").strip()]
    history_map = get_event_histories(db_path, event_master_ids)
    for item in events:
        event_master_id = str(item.get("event_master_id") or "").strip()
        item["event_history"] = history_map.get(event_master_id, [])
    return workspace


def _demo_workspace(use_live_news: bool = False) -> dict[str, Any]:
    payload = default_demo_request()
    saved_settings = get_user_settings(default_db_path(REPO_ROOT))
    payload["rss_sources_text"] = saved_settings.get("rss_sources_text", "")
    payload["technical_settings"] = {
        "provider": "mock",
        "endpoint": "",
        "timeout_seconds": 2,
        "fallback_to_mock": True,
    }
    payload["model_settings"] = saved_settings.get("model_settings", {})
    payload["use_live_news"] = use_live_news
    payload["recommendation_limit"] = 3
    return build_research_workspace(ResearchRequest.from_dict(payload))


def _form_defaults() -> dict[str, Any]:
    saved = get_user_settings(default_db_path(REPO_ROOT))
    return merge_user_settings(default_demo_request(), {
        "watchlist": saved.get("watchlist", []),
        "focus_topics": saved.get("focus_topics", []),
        "risk_thresholds": saved.get("risk_thresholds", {}),
        "personal_notes": saved.get("personal_notes", ""),
        "use_live_news": saved.get("use_live_news", default_demo_request().get("use_live_news", False)),
    })


def create_app() -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    @app.get("/")
    def index() -> str:
        return render_template(
            "index.html",
            overview=build_product_overview(),
            demo_request=default_demo_request(),
            form_defaults=_form_defaults(),
            demo_workspace=None,
            user_settings=sanitize_settings_for_output(get_user_settings(default_db_path(REPO_ROOT))),
            lab_snapshot=load_internal_lab_snapshot(),
            page_mode="workspace",
        )

    @app.get("/portfolio")
    def portfolio_terminal() -> str:
        return render_template(
            "index.html",
            overview=build_product_overview(),
            demo_request=default_demo_request(),
            form_defaults=_form_defaults(),
            demo_workspace=None,
            user_settings=sanitize_settings_for_output(get_user_settings(default_db_path(REPO_ROOT))),
            lab_snapshot=load_internal_lab_snapshot(),
            page_mode="portfolio",
        )

    @app.get("/api/health")
    def health() -> Any:
        return jsonify({"status": "ok"})

    @app.get("/api/model/codex-status")
    def codex_status() -> Any:
        try:
            result = subprocess.run(
                ["codex", "login", "status"],
                capture_output=True,
                text=True,
                timeout=20,
                cwd=str(REPO_ROOT),
            )
            output = (result.stdout or "").strip() or (result.stderr or "").strip()
            logged_in = "Logged in using ChatGPT" in output
            return jsonify(
                {
                    "available": True,
                    "logged_in": logged_in,
                    "message": "已使用 ChatGPT 登录 Codex CLI。" if logged_in else (output or "未检测到 ChatGPT 登录态。"),
                }
            )
        except Exception as exc:
            return jsonify(
                {
                    "available": False,
                    "logged_in": False,
                    "message": str(exc),
                }
            )

    @app.get("/api/runtime/status")
    def runtime_status() -> Any:
        db_path = default_db_path(REPO_ROOT)
        runs = list_workspace_runs(db_path, limit=1)
        latest = runs[0] if runs else {}
        stock_status = get_stock_data_status()
        news_status = get_news_data_status()
        return jsonify(
            {
                "status": "ok",
                "database_path": str(db_path),
                "history_count": len(list_workspace_runs(db_path, limit=200)),
                "latest_generated_at": latest.get("generated_at", ""),
                "latest_top_event": latest.get("top_event", ""),
                "latest_top_recommendation": latest.get("top_recommendation", ""),
                **stock_status,
                **news_status,
            }
        )

    @app.post("/api/data/refresh")
    def refresh_data() -> Any:
        payload = request.get_json(silent=True) or {}
        rss_sources_text = str(payload.get("rss_sources_text", "") or "")
        return jsonify(refresh_all_data(rss_sources_text))

    @app.get("/api/product/overview")
    def product_overview() -> Any:
        return jsonify(build_product_overview())

    @app.get("/api/demo-profile")
    def demo_profile() -> Any:
        return jsonify(default_demo_request())

    @app.get("/api/settings")
    def settings() -> Any:
        return jsonify(sanitize_settings_for_output(get_user_settings(default_db_path(REPO_ROOT))))

    @app.post("/api/settings")
    def save_settings() -> Any:
        payload = request.get_json(silent=True) or {}
        db_path = default_db_path(REPO_ROOT)
        existing = get_user_settings(db_path)
        prepared = prepare_settings_for_storage(payload, existing)
        save_user_settings(db_path, prepared)
        return jsonify(sanitize_settings_for_output(prepared))

    @app.get("/api/news/stream")
    def news_stream() -> Any:
        return jsonify(_demo_workspace(use_live_news=request.args.get("live") == "1")["news_stream"])

    @app.get("/api/events")
    def events() -> Any:
        return jsonify(_demo_workspace(use_live_news=request.args.get("live") == "1")["hotspot_events"])

    @app.get("/api/events/<event_id>")
    def event_detail(event_id: str) -> Any:
        for event in _demo_workspace(use_live_news=request.args.get("live") == "1")["hotspot_events"]:
            if event["event_id"] == event_id:
                return jsonify(event)
        return jsonify({"error": "event not found"}), 404

    @app.get("/api/history/events/<event_master_id>")
    def history_event_detail(event_master_id: str) -> Any:
        detail = get_event_history_detail(default_db_path(REPO_ROOT), event_master_id)
        if not detail["history"]:
            return jsonify({"error": "event not found"}), 404
        return jsonify(detail)

    @app.get("/api/industries/<industry_id>")
    def industry_detail(industry_id: str) -> Any:
        for industry in _demo_workspace(use_live_news=request.args.get("live") == "1")["industry_views"]:
            if industry["industry_id"] == industry_id:
                return jsonify(industry)
        return jsonify({"error": "industry not found"}), 404

    @app.get("/api/recommendations")
    def recommendations() -> Any:
        return jsonify(_demo_workspace(use_live_news=request.args.get("live") == "1")["recommendation_views"])

    @app.get("/api/history/runs")
    def history_runs() -> Any:
        mode = str(request.args.get("mode", "run") or "run").strip()
        query = str(request.args.get("q", "") or "").strip()
        date_from = str(request.args.get("date_from", "") or "").strip()
        date_to = str(request.args.get("date_to", "") or "").strip()
        runs = list_workspace_runs_grouped(default_db_path(REPO_ROOT), mode=mode)
        if query:
            query_lower = query.lower()
            runs = [
                item
                for item in runs
                if query_lower in str(item.get("top_event", item.get("sample_top_event", ""))).lower()
                or query_lower in str(item.get("top_recommendation", item.get("sample_top_recommendation", ""))).lower()
                or query_lower in str(item.get("run_id", item.get("sample_run_id", ""))).lower()
                or query_lower in str(item.get("group_label", "")).lower()
            ]
        if date_from:
            runs = [item for item in runs if str(item.get("generated_at", item.get("latest_generated_at", "")))[:10] >= date_from]
        if date_to:
            runs = [item for item in runs if str(item.get("generated_at", item.get("latest_generated_at", "")))[:10] <= date_to]
        return jsonify(runs)

    @app.get("/api/history/runs/<run_id>")
    def history_run_detail(run_id: str) -> Any:
        run = get_workspace_run(default_db_path(REPO_ROOT), run_id)
        if run is None:
            return jsonify({"error": "run not found"}), 404
        run = _attach_event_histories(run, default_db_path(REPO_ROOT))
        run["run_comparison"] = get_run_comparison(default_db_path(REPO_ROOT), run_id)
        run["portfolio_comparison"] = get_portfolio_comparison(default_db_path(REPO_ROOT), run_id)
        run["portfolio_timeline"] = get_portfolio_timeline(default_db_path(REPO_ROOT))
        return jsonify(run)

    @app.delete("/api/history/runs/<run_id>")
    def history_run_delete(run_id: str) -> Any:
        deleted = delete_workspace_run(default_db_path(REPO_ROOT), run_id)
        if not deleted:
            return jsonify({"error": "run not found"}), 404
        return jsonify({"deleted": True, "run_id": run_id})

    @app.delete("/api/history/runs")
    def history_runs_clear() -> Any:
        deleted_count = clear_workspace_runs(default_db_path(REPO_ROOT))
        return jsonify({"deleted": True, "deleted_count": deleted_count})

    @app.get("/api/history/recommendations/<symbol>")
    def recommendation_history(symbol: str) -> Any:
        return jsonify(get_symbol_history(default_db_path(REPO_ROOT), symbol))

    @app.get("/api/history/portfolio/<run_id>")
    def portfolio_history_detail(run_id: str) -> Any:
        detail = get_portfolio_detail(default_db_path(REPO_ROOT), run_id)
        if detail is None:
            return jsonify({"error": "run not found"}), 404
        return jsonify(detail)

    @app.post("/api/compliance/audit")
    def compliance_audit() -> Any:
        payload = request.get_json(silent=True) or {}
        audit = audit_copy_payload(str(payload.get("copy_text", "")))
        return jsonify(audit)

    @app.post("/api/research/generate")
    def generate_research_workspace() -> Any:
        payload = request.get_json(silent=True) or {}
        db_path = default_db_path(REPO_ROOT)
        saved_settings = get_user_settings(db_path)
        if "use_live_news" in payload:
            payload["use_live_news"] = bool(payload.get("use_live_news", False))
        else:
            payload["use_live_news"] = bool(saved_settings.get("use_live_news", default_demo_request().get("use_live_news", False)))
        payload["rss_sources_text"] = str(payload.get("rss_sources_text") or saved_settings.get("rss_sources_text", ""))
        payload["technical_settings"] = payload.get("technical_settings", {}) or saved_settings.get("technical_settings", {})
        payload["model_settings"] = prepare_settings_for_storage(
            payload.get("model_settings", {}),
            saved_settings,
        ).get("model_settings", {})
        try:
            research_request = ResearchRequest.from_dict(payload)
        except (TypeError, ValueError) as exc:
            return jsonify({"error": str(exc)}), 400

        as_of = None
        if payload.get("as_of"):
            try:
                as_of = date.fromisoformat(str(payload["as_of"]))
            except ValueError:
                return jsonify({"error": "as_of must use YYYY-MM-DD."}), 400

        workspace = build_research_workspace(research_request, as_of=as_of)
        run_id = persist_workspace(workspace, db_path)
        workspace["storage"] = {"run_id": run_id}
        workspace = _attach_event_histories(workspace, db_path)
        workspace["run_comparison"] = get_run_comparison(db_path, run_id)
        workspace["portfolio_comparison"] = get_portfolio_comparison(db_path, run_id)
        workspace["portfolio_timeline"] = get_portfolio_timeline(db_path)
        return jsonify(workspace)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False, use_reloader=False)
