"""SQLite persistence for research workspace snapshots."""

from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Any


def artifacts_root(repo_root: Path) -> Path:
    root = repo_root / "artifacts"
    root.mkdir(parents=True, exist_ok=True)
    return root


def default_db_path(repo_root: Path) -> Path:
    db_dir = artifacts_root(repo_root) / "db"
    db_dir.mkdir(parents=True, exist_ok=True)
    return db_dir / "news_stock.db"


def initialize_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS workspace_runs (
                run_id TEXT PRIMARY KEY,
                generated_at TEXT NOT NULL,
                payload_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS news_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                news_id TEXT NOT NULL,
                cluster_id TEXT NOT NULL,
                headline TEXT NOT NULL,
                published_at TEXT NOT NULL,
                credibility_score INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(run_id, news_id)
            );

            CREATE TABLE IF NOT EXISTS event_cases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                event_id TEXT NOT NULL,
                title TEXT NOT NULL,
                direction TEXT NOT NULL,
                heat_score INTEGER NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(run_id, event_id)
            );

            CREATE TABLE IF NOT EXISTS stock_recommendations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                action TEXT NOT NULL,
                score INTEGER NOT NULL,
                confidence REAL NOT NULL,
                payload_json TEXT NOT NULL,
                UNIQUE(run_id, symbol)
            );

            CREATE TABLE IF NOT EXISTS app_settings (
                key TEXT PRIMARY KEY,
                value_json TEXT NOT NULL
            );
            """
        )


def persist_workspace(workspace: dict[str, Any], db_path: Path) -> str:
    initialize_database(db_path)
    run_id = str(uuid.uuid4())
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO workspace_runs (run_id, generated_at, payload_json) VALUES (?, ?, ?)",
            (run_id, workspace["generated_at"], json.dumps(workspace, ensure_ascii=False)),
        )
        for item in workspace.get("news_stream", {}).get("daily", []):
            connection.execute(
                """
                INSERT OR REPLACE INTO news_items
                (run_id, news_id, cluster_id, headline, published_at, credibility_score, payload_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item["news_id"],
                    item["cluster_id"],
                    item["headline"],
                    item["published_at"],
                    item["credibility_score"],
                    json.dumps(item, ensure_ascii=False),
                ),
            )
        for item in workspace.get("hotspot_events", []):
            connection.execute(
                """
                INSERT OR REPLACE INTO event_cases
                (run_id, event_id, title, direction, heat_score, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item["event_id"],
                    item["title"],
                    item["direction"],
                    item["heat_score"],
                    json.dumps(item, ensure_ascii=False),
                ),
            )
        for item in workspace.get("recommendation_views", []):
            connection.execute(
                """
                INSERT OR REPLACE INTO stock_recommendations
                (run_id, symbol, action, score, confidence, payload_json)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    item["symbol"],
                    item["action"],
                    item["score"],
                    item["confidence"],
                    json.dumps(item, ensure_ascii=False),
                ),
            )
    return run_id


def list_workspace_runs(db_path: Path, limit: int = 20) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT run_id, generated_at, payload_json FROM workspace_runs ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    result = []
    for run_id, generated_at, payload_json in rows:
        payload = json.loads(payload_json)
        top_recommendations = payload.get("recommendation_views", []) if isinstance(payload, dict) else []
        hotspot_events = payload.get("hotspot_events", []) if isinstance(payload, dict) else []
        top_recommendation = top_recommendations[0] if isinstance(top_recommendations, list) and top_recommendations else {}
        top_event = hotspot_events[0] if isinstance(hotspot_events, list) and hotspot_events else {}
        result.append(
            {
                "run_id": run_id,
                "generated_at": generated_at,
                "top_event": top_event.get("title"),
                "top_event_master_id": top_event.get("event_master_id") or top_event.get("event_id"),
                "top_recommendation": top_recommendation.get("name"),
                "top_recommendation_action": top_recommendation.get("action"),
                "top_recommendation_score": top_recommendation.get("final_score", top_recommendation.get("score")),
            }
        )
    return result


def list_workspace_runs_grouped(
    db_path: Path,
    *,
    mode: str = "run",
    limit: int = 50,
) -> list[dict[str, Any]]:
    runs = list_workspace_runs(db_path, limit=200)
    if mode == "run":
        return runs[:limit]

    grouped: dict[str, dict[str, Any]] = {}
    for item in runs:
        if mode == "event":
            key = str(item.get("top_event_master_id") or item.get("top_event") or "未命名事件")
            label = str(item.get("top_event") or "未命名事件")
            sublabel = str(item.get("top_recommendation") or "无建议")
        elif mode == "company":
            key = str(item.get("top_recommendation") or "无建议")
            label = key
            sublabel = str(item.get("top_event") or "未命名事件")
        elif mode == "date":
            key = str(item.get("generated_at", ""))[:10]
            label = key or "未知日期"
            sublabel = str(item.get("top_event") or "未命名事件")
        else:
            key = item["run_id"]
            label = str(item.get("top_event") or "未命名事件")
            sublabel = str(item.get("top_recommendation") or "无建议")

        bucket = grouped.setdefault(
            key,
            {
                "group_key": key,
                "group_label": label,
                "group_mode": mode,
                "latest_generated_at": item.get("generated_at", ""),
                "count": 0,
                "sample_run_id": item["run_id"],
                "sample_top_event": item.get("top_event"),
                "sample_top_event_master_id": item.get("top_event_master_id"),
                "sample_top_recommendation": item.get("top_recommendation"),
                "sample_top_recommendation_action": item.get("top_recommendation_action"),
                "sample_top_recommendation_score": item.get("top_recommendation_score"),
                "sublabels": [],
            },
        )
        bucket["count"] += 1
        if sublabel and sublabel not in bucket["sublabels"]:
            bucket["sublabels"].append(sublabel)
        if item.get("generated_at", "") > bucket["latest_generated_at"]:
            bucket["latest_generated_at"] = item.get("generated_at", "")
            bucket["sample_run_id"] = item["run_id"]
            bucket["sample_top_event"] = item.get("top_event")
            bucket["sample_top_event_master_id"] = item.get("top_event_master_id")
            bucket["sample_top_recommendation"] = item.get("top_recommendation")
            bucket["sample_top_recommendation_action"] = item.get("top_recommendation_action")
            bucket["sample_top_recommendation_score"] = item.get("top_recommendation_score")

    result = sorted(grouped.values(), key=lambda item: item["latest_generated_at"], reverse=True)
    return result[:limit]


def get_workspace_run(db_path: Path, run_id: str) -> dict[str, Any] | None:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT payload_json FROM workspace_runs WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    if not row:
        return None
    return json.loads(row[0])


def get_run_comparison(db_path: Path, run_id: str) -> dict[str, Any]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT run_id, generated_at, payload_json FROM workspace_runs ORDER BY generated_at DESC"
        ).fetchall()

    indexed: list[dict[str, Any]] = []
    for item_run_id, generated_at, payload_json in rows:
        payload = json.loads(payload_json)
        top_events = payload.get("hotspot_events", []) if isinstance(payload, dict) else []
        top_recommendations = payload.get("recommendation_views", []) if isinstance(payload, dict) else []
        top_event = top_events[0] if isinstance(top_events, list) and top_events else {}
        top_rec = top_recommendations[0] if isinstance(top_recommendations, list) and top_recommendations else {}
        indexed.append(
            {
                "run_id": item_run_id,
                "generated_at": generated_at,
                "payload": payload,
                "top_event_title": top_event.get("title"),
                "top_event_master_id": top_event.get("event_master_id") or top_event.get("event_id"),
                "top_symbol": top_rec.get("symbol"),
                "top_name": top_rec.get("name"),
                "top_action": top_rec.get("action"),
            }
        )

    for index, item in enumerate(indexed):
        if item["run_id"] != run_id:
            continue
        previous = indexed[index + 1] if index + 1 < len(indexed) else None
        if previous is None:
            return {
                "has_previous": False,
                "summary": "当前没有上一版可供比较。",
            }
        same_event = item.get("top_event_master_id") == previous.get("top_event_master_id")
        same_symbol = item.get("top_symbol") == previous.get("top_symbol")
        if same_event and same_symbol and item.get("top_action") == previous.get("top_action"):
            summary = "和上一版相比，核心事件、首条标的与动作均未发生明显变化。"
        elif same_event and not same_symbol:
            summary = "核心事件延续，但首条标的已经发生切换。"
        elif not same_event and same_symbol:
            summary = "首条标的延续，但驱动它的核心事件已经变化。"
        else:
            summary = "和上一版相比，核心事件与首条标的都发生了变化。"
        return {
            "has_previous": True,
            "summary": summary,
            "current_run_id": item["run_id"],
            "previous_run_id": previous["run_id"],
            "previous_generated_at": previous["generated_at"],
            "same_top_event": same_event,
            "same_top_symbol": same_symbol,
            "current_top_event": item.get("top_event_title"),
            "previous_top_event": previous.get("top_event_title"),
            "current_top_event_master_id": item.get("top_event_master_id"),
            "previous_top_event_master_id": previous.get("top_event_master_id"),
            "current_top_symbol": item.get("top_symbol"),
            "previous_top_symbol": previous.get("top_symbol"),
            "current_top_name": item.get("top_name"),
            "previous_top_name": previous.get("top_name"),
            "current_top_action": item.get("top_action"),
            "previous_top_action": previous.get("top_action"),
        }
    return {
        "has_previous": False,
        "summary": "未找到当前版本对应的历史记录。",
    }


def get_portfolio_comparison(db_path: Path, run_id: str) -> dict[str, Any]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT run_id, generated_at, payload_json FROM workspace_runs ORDER BY generated_at DESC"
        ).fetchall()

    indexed: list[dict[str, Any]] = []
    for item_run_id, generated_at, payload_json in rows:
        payload = json.loads(payload_json)
        indexed.append(
            {
                "run_id": item_run_id,
                "generated_at": generated_at,
                "portfolio_plan": payload.get("portfolio_plan", {}),
            }
        )

    for index, item in enumerate(indexed):
        if item["run_id"] != run_id:
            continue
        previous = indexed[index + 1] if index + 1 < len(indexed) else None
        current_plan = item.get("portfolio_plan", {}) or {}
        if previous is None:
            return {
                "has_previous": False,
                "summary": "当前没有上一版组合可供比较。",
            }
        previous_plan = previous.get("portfolio_plan", {}) or {}
        current_exposure = float(current_plan.get("suggested_invested_pct", 0) or 0)
        previous_exposure = float(previous_plan.get("suggested_invested_pct", 0) or 0)
        delta_exposure = round(current_exposure - previous_exposure, 1)
        current_cash = float(current_plan.get("cash_buffer_pct", 0) or 0)
        previous_cash = float(previous_plan.get("cash_buffer_pct", 0) or 0)
        current_budget = current_plan.get("risk_budget", {}) or {}
        previous_budget = previous_plan.get("risk_budget", {}) or {}
        current_regime = str(current_budget.get("regime") or "未生成")
        previous_regime = str(previous_budget.get("regime") or "未生成")
        if delta_exposure > 0:
            summary = f"相对上一版，组合更激进，总暴露提升 {delta_exposure:.1f}% 。"
        elif delta_exposure < 0:
            summary = f"相对上一版，组合更保守，总暴露下降 {abs(delta_exposure):.1f}% 。"
        else:
            summary = "相对上一版，总暴露基本持平。"
        return {
            "has_previous": True,
            "summary": summary,
            "current_run_id": item["run_id"],
            "previous_run_id": previous["run_id"],
            "previous_generated_at": previous["generated_at"],
            "current_suggested_invested_pct": round(current_exposure, 1),
            "previous_suggested_invested_pct": round(previous_exposure, 1),
            "exposure_delta_pct": delta_exposure,
            "current_cash_buffer_pct": round(current_cash, 1),
            "previous_cash_buffer_pct": round(previous_cash, 1),
            "current_regime": current_regime,
            "previous_regime": previous_regime,
            "current_constraints": current_plan.get("applied_constraints", []),
            "previous_constraints": previous_plan.get("applied_constraints", []),
            "current_theme_exposure": current_plan.get("theme_exposure", []),
            "previous_theme_exposure": previous_plan.get("theme_exposure", []),
            "current_replay_summary": (current_plan.get("portfolio_replay", {}) or {}).get("summary"),
            "previous_replay_summary": (previous_plan.get("portfolio_replay", {}) or {}).get("summary"),
        }
    return {
        "has_previous": False,
        "summary": "未找到当前版本对应的组合记录。",
    }


def get_portfolio_timeline(
    db_path: Path,
    *,
    limit: int = 8,
) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT run_id, generated_at, payload_json FROM workspace_runs ORDER BY generated_at DESC LIMIT ?",
            (limit,),
        ).fetchall()

    items: list[dict[str, Any]] = []
    previous_exposure: float | None = None
    for run_id, generated_at, payload_json in rows:
        payload = json.loads(payload_json)
        portfolio_plan = payload.get("portfolio_plan", {}) or {}
        risk_budget = portfolio_plan.get("risk_budget", {}) or {}
        top_targets = [
            {
                "symbol": item.get("symbol"),
                "name": item.get("name"),
                "suggested_position_pct": item.get("suggested_position_pct"),
            }
            for item in (portfolio_plan.get("target_positions", []) or [])[:3]
        ]
        current_exposure = float(portfolio_plan.get("suggested_invested_pct", 0) or 0)
        delta = None if previous_exposure is None else round(current_exposure - previous_exposure, 1)
        items.append(
            {
                "run_id": run_id,
                "generated_at": generated_at,
                "suggested_invested_pct": round(current_exposure, 1),
                "cash_buffer_pct": round(float(portfolio_plan.get("cash_buffer_pct", 0) or 0), 1),
                "regime": risk_budget.get("regime"),
                "top_targets": top_targets,
                "delta_vs_newer_pct": delta,
                "replay_summary": (portfolio_plan.get("portfolio_replay", {}) or {}).get("summary"),
            }
        )
        previous_exposure = current_exposure
    return items


def get_portfolio_detail(db_path: Path, run_id: str) -> dict[str, Any] | None:
    workspace = get_workspace_run(db_path, run_id)
    if workspace is None:
        return None
    return {
        "run_id": run_id,
        "generated_at": workspace.get("generated_at"),
        "portfolio_plan": workspace.get("portfolio_plan", {}),
        "portfolio_comparison": get_portfolio_comparison(db_path, run_id),
    }


def get_event_histories(
    db_path: Path,
    event_master_ids: list[str],
    *,
    limit_per_event: int = 6,
) -> dict[str, list[dict[str, Any]]]:
    initialize_database(db_path)
    normalized_ids = [str(item).strip() for item in event_master_ids if str(item).strip()]
    if not normalized_ids:
        return {}
    targets = set(normalized_ids)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT e.run_id, w.generated_at, e.payload_json
            FROM event_cases e
            JOIN workspace_runs w ON e.run_id = w.run_id
            ORDER BY w.generated_at DESC
            """
        ).fetchall()

    grouped: dict[str, list[dict[str, Any]]] = {event_master_id: [] for event_master_id in normalized_ids}
    for run_id, generated_at, payload_json in rows:
        payload = json.loads(payload_json)
        event_master_id = str(payload.get("event_master_id") or payload.get("event_id") or "").strip()
        if event_master_id not in targets:
            continue
        bucket = grouped.setdefault(event_master_id, [])
        if len(bucket) >= limit_per_event:
            continue
        previous = bucket[-1] if bucket else None
        profit_focus = (
            payload.get("profit_propagation", {}).get("profit_focus", [])
            if isinstance(payload.get("profit_propagation"), dict)
            else []
        )
        item = {
            "run_id": run_id,
            "generated_at": generated_at,
            "event_instance_id": payload.get("event_instance_id"),
            "event_signature": payload.get("event_signature"),
            "title": payload.get("title"),
            "stage": payload.get("stage"),
            "heat_score": payload.get("heat_score"),
            "summary": payload.get("event_summary"),
            "profit_focus": profit_focus,
            "change_summary": _event_change_summary(payload, previous),
        }
        bucket.append(item)
    return grouped


def get_event_history_detail(
    db_path: Path,
    event_master_id: str,
    *,
    limit: int = 10,
) -> dict[str, Any]:
    history_map = get_event_histories(db_path, [event_master_id], limit_per_event=limit)
    items = history_map.get(event_master_id, [])
    latest = items[0] if items else {}
    current_event = None
    related_recommendations: list[dict[str, Any]] = []
    related_candidates: list[dict[str, Any]] = []
    related_industries: list[dict[str, Any]] = []
    latest_run_id = latest.get("run_id")
    if latest_run_id:
        with sqlite3.connect(db_path) as connection:
            row = connection.execute(
                "SELECT payload_json FROM workspace_runs WHERE run_id = ?",
                (latest_run_id,),
            ).fetchone()
        if row:
            payload = json.loads(row[0])
            hotspot_events = payload.get("hotspot_events", [])
            current_event = next(
                (
                    event
                    for event in hotspot_events
                    if str(event.get("event_master_id") or event.get("event_id") or "").strip() == event_master_id
                ),
                None,
            )
            if current_event:
                event_id = str(current_event.get("event_id") or "").strip()
                industry_ids = {
                    str(item.get("industry_id") or "").strip()
                    for item in current_event.get("industry_impacts", [])
                    if str(item.get("industry_id") or "").strip()
                }
                related_recommendations = [
                    {
                        "symbol": item.get("symbol"),
                        "name": item.get("name"),
                        "action": item.get("action"),
                        "final_score": item.get("final_score", item.get("score")),
                        "manager_summary": item.get("manager_summary"),
                        "profit_focus_summary": item.get("profit_focus_summary"),
                    }
                    for item in payload.get("recommendation_views", [])
                    if event_master_id in set(item.get("evidence_chain", {}).get("event_master_ids", []))
                    or event_id in set(item.get("evidence_chain", {}).get("event_ids", []))
                ][:6]
                related_candidates = [
                    {
                        "symbol": item.get("symbol"),
                        "name": item.get("name"),
                        "match_score": item.get("match_score"),
                        "linkage_type": item.get("linkage_type"),
                        "rationale": item.get("rationale"),
                    }
                    for item in payload.get("candidate_stocks", [])
                    if any(
                        str(raw.get("event_master_id") or "").strip() == event_master_id
                        or str(raw.get("event_id") or "").strip() == event_id
                        for raw in item.get("events", [])
                    )
                ][:10]
                related_industries = [
                    {
                        "industry_id": item.get("industry_id"),
                        "industry_name": item.get("industry_name"),
                        "current_state": item.get("current_state"),
                        "profit_focus": item.get("profit_propagation", {}).get("profit_focus", []),
                    }
                    for item in payload.get("industry_views", [])
                    if str(item.get("industry_id") or "").strip() in industry_ids
                ][:6]
    return {
        "event_master_id": event_master_id,
        "count": len(items),
        "latest_title": latest.get("title"),
        "latest_stage": latest.get("stage"),
        "latest_run_id": latest_run_id,
        "current_event": current_event,
        "related_recommendations": related_recommendations,
        "related_candidates": related_candidates,
        "related_industries": related_industries,
        "history": items,
    }


def _event_change_summary(current_payload: dict[str, Any], previous_item: dict[str, Any] | None) -> str:
    if previous_item is None:
        return "这是当前事件在本地历史中的最新起点。"
    current_stage = str(current_payload.get("stage") or "")
    previous_stage = str(previous_item.get("stage") or "")
    current_heat = int(current_payload.get("heat_score") or 0)
    previous_heat = int(previous_item.get("heat_score") or 0)
    current_profit = current_payload.get("profit_propagation", {}).get("profit_focus", []) if isinstance(current_payload.get("profit_propagation"), dict) else []
    previous_profit = previous_item.get("profit_focus") or []
    if current_stage != previous_stage:
        return f"阶段从 {previous_stage or '未标注'} 变化为 {current_stage or '未标注'}。"
    if current_heat != previous_heat:
        direction = "上升" if current_heat > previous_heat else "下降"
        return f"热度较上一版{direction} {abs(current_heat - previous_heat)} 分。"
    if list(current_profit) != list(previous_profit):
        return "利润重心较上一版发生变化。"
    return "与上一版相比，事件判断基本保持一致。"


def get_symbol_history(db_path: Path, symbol: str, limit: int = 20) -> list[dict[str, Any]]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            """
            SELECT run_id, payload_json
            FROM stock_recommendations
            WHERE symbol = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (symbol, limit),
        ).fetchall()
    result = []
    for run_id, payload_json in rows:
        payload = json.loads(payload_json)
        result.append(
            {
                "run_id": run_id,
                "symbol": payload["symbol"],
                "name": payload["name"],
                "action": payload["action"],
                "score": payload["score"],
                "confidence": payload["confidence"],
                "effective_window": payload["effective_window"],
                "generated_logic": payload["core_logic"],
            }
        )
    return result


def load_recent_crowding_context(
    db_path: Path,
    *,
    lookback_runs: int = 6,
    top_recommendations: int = 3,
    top_events: int = 2,
) -> dict[str, Any]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute(
            "SELECT payload_json FROM workspace_runs ORDER BY generated_at DESC LIMIT ?",
            (lookback_runs,),
        ).fetchall()

    symbol_counts: dict[str, int] = {}
    event_counts: dict[str, int] = {}
    for (payload_json,) in rows:
        payload = json.loads(payload_json)
        for item in payload.get("recommendation_views", [])[:top_recommendations]:
            symbol = str(item.get("symbol", "")).strip()
            if symbol:
                symbol_counts[symbol] = symbol_counts.get(symbol, 0) + 1
        for item in payload.get("hotspot_events", [])[:top_events]:
            event_id = str(item.get("event_master_id") or item.get("event_id") or "").strip()
            if event_id:
                event_counts[event_id] = event_counts.get(event_id, 0) + 1

    return {
        "lookback_runs": len(rows),
        "symbol_counts": symbol_counts,
        "event_counts": event_counts,
    }


def delete_workspace_run(db_path: Path, run_id: str) -> bool:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        deleted = connection.execute(
            "DELETE FROM workspace_runs WHERE run_id = ?",
            (run_id,),
        ).rowcount
        connection.execute("DELETE FROM news_items WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM event_cases WHERE run_id = ?", (run_id,))
        connection.execute("DELETE FROM stock_recommendations WHERE run_id = ?", (run_id,))
    return bool(deleted)


def clear_workspace_runs(db_path: Path) -> int:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        count_row = connection.execute("SELECT COUNT(*) FROM workspace_runs").fetchone()
        total = int(count_row[0]) if count_row else 0
        connection.execute("DELETE FROM workspace_runs")
        connection.execute("DELETE FROM news_items")
        connection.execute("DELETE FROM event_cases")
        connection.execute("DELETE FROM stock_recommendations")
    return total


def save_user_settings(db_path: Path, settings: dict[str, Any]) -> None:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO app_settings (key, value_json) VALUES (?, ?)",
            ("user_settings", json.dumps(settings, ensure_ascii=False)),
        )


def get_user_settings(db_path: Path) -> dict[str, Any]:
    initialize_database(db_path)
    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            "SELECT value_json FROM app_settings WHERE key = ?",
            ("user_settings",),
        ).fetchone()
    if not row:
        return default_user_settings()
    payload = json.loads(row[0])
    return merge_user_settings(default_user_settings(), payload)


def default_user_settings() -> dict[str, Any]:
    return {
        "watchlist": [],
        "focus_topics": [],
        "risk_thresholds": {
            "single_name_limit_pct": 15,
            "sector_limit_pct": 22,
            "negative_event_score_threshold": 70,
        },
        "personal_notes": "",
        "use_live_news": True,
        "rss_sources_text": "",
        "technical_settings": {
            "provider": "mock",
            "endpoint": "",
            "timeout_seconds": 8,
            "fallback_to_mock": True,
        },
        "model_settings": {
            "enabled": False,
            "provider": "openai-compatible",
            "base_url": "",
            "model_name": "",
            "system_prompt": "",
            "temperature": 0.2,
            "timeout_seconds": 20,
            "has_api_key": False,
            "api_key_masked": "",
        },
    }


def merge_user_settings(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = json.loads(json.dumps(base, ensure_ascii=False))
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key].update(value)
        else:
            merged[key] = value
    return merged


def sanitize_settings_for_output(settings: dict[str, Any]) -> dict[str, Any]:
    payload = json.loads(json.dumps(settings, ensure_ascii=False))
    model_settings = payload.setdefault("model_settings", {})
    api_key = str(model_settings.pop("api_key", "") or "")
    if api_key:
        model_settings["has_api_key"] = True
        model_settings["api_key_masked"] = _mask_secret(api_key)
    else:
        model_settings["has_api_key"] = bool(model_settings.get("has_api_key"))
        model_settings["api_key_masked"] = str(model_settings.get("api_key_masked", ""))
    return payload


def prepare_settings_for_storage(payload: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    current = merge_user_settings(default_user_settings(), existing or {})
    merged = merge_user_settings(current, payload)
    technical_settings = merged.setdefault("technical_settings", {})
    provider = str(technical_settings.get("provider", "mock") or "mock")
    if provider == "yahoo":
        provider = "akshare"
    technical_settings["provider"] = provider
    model_settings = merged.setdefault("model_settings", {})
    api_key = str(model_settings.get("api_key", "") or "").strip()
    if not api_key and existing:
        existing_key = str(existing.get("model_settings", {}).get("api_key", "") or "").strip()
        if existing_key:
            model_settings["api_key"] = existing_key
    if model_settings.get("api_key"):
        model_settings["has_api_key"] = True
        model_settings["api_key_masked"] = _mask_secret(str(model_settings["api_key"]))
    else:
        model_settings["has_api_key"] = False
        model_settings["api_key_masked"] = ""
    return merged


def _mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "*" * len(value)
    return value[:4] + "*" * max(4, len(value) - 8) + value[-4:]
