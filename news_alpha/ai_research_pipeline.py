"""AI-assisted multi-stage research pipeline."""

from __future__ import annotations

import json
from typing import Any

from .model_client import _chat_completion, _extract_json

STAGE_CONTRACTS: dict[str, dict[str, Any]] = {
    "news_localization": {
        "title": "AI 新闻中文化",
        "goal": "把英文或非中文新闻翻译/转写成适合中文投研使用的标题与摘要，同时保留原意和关键实体。",
        "constraints": [
            "只能基于输入新闻文本做翻译和中文化解释，不得凭空补充事实。",
            "公司名、机构名、产品名、政策名尽量保留原始专有名词并给出自然中文表达。",
            "若原文已经是中文，可直接复用并说明无需翻译。",
            "输出必须是结构化 JSON，并逐条对应 news_id。",
        ],
        "output_contract": {
            "items": [
                "news_id",
                "translated_headline",
                "translated_summary",
                "language",
                "translation_note",
            ]
        },
        "next_stage_goal": "基于中文化后的新闻样本，识别真正的事件对象。",
    },
    "event_understanding": {
        "title": "AI 新闻理解",
        "goal": "把新闻簇抽象成真正值得研究的事件对象，而不是停留在媒体表述和公司名层面。",
        "constraints": [
            "只允许基于输入新闻样本做事件归并，不得凭空发明新新闻。",
            "必须先回答“发生了什么变化”，不能直接输出买卖建议。",
            "必须区分真实事件、噪声新闻和重复报道。",
            "输出必须是结构化 JSON。",
        ],
        "output_contract": {
            "events": [
                "event_name",
                "event_type",
                "stage",
                "event_interpretation",
                "affected_sectors",
                "key_variables",
                "confidence",
                "noise_flag",
            ]
        },
        "next_stage_goal": "基于已识别事件，推演 base / bull / bear 三种情形和失效条件。",
    },
    "scenario_analysis": {
        "title": "AI 事态推演",
        "goal": "根据上一阶段识别出的事件，做可审计的事态推演，而不是直接给股票结论。",
        "constraints": [
            "只能基于上一步的事件对象继续推演，不能回头重新解读新闻。",
            "每个事件必须给出 base_case、bull_case、bear_case。",
            "必须给出 key_observables 和 invalidation_conditions。",
            "禁止直接输出公司推荐或股价判断。",
        ],
        "output_contract": {
            "scenarios": [
                "event_name",
                "base_case",
                "bull_case",
                "bear_case",
                "key_observables",
                "invalidation_conditions",
                "timing_window",
            ]
        },
        "next_stage_goal": "基于事件和情景，展开产业链、利润重心、集中度和受益方向。",
    },
    "supply_chain_expansion": {
        "title": "AI 产业链展开",
        "goal": "把事件推演扩展成产业链分析，识别所有可能受影响的环节，而不是套用固定链条模板。",
        "constraints": [
            "只能基于上一步情景推演继续分析，不能脱离事件单独讲行业。",
            "必须区分直接受益、间接受益、主题映射、潜在受损。",
            "必须给出利润重心、价值池和集中度判断。",
            "允许展开到新闻未直接提及、但逻辑上会受影响的环节。",
        ],
        "output_contract": {
            "industries": [
                "industry_name",
                "summary",
                "current_state",
                "chain_nodes[name, stage, relation_type, value_pool, profit_pool_weight, concentration_view, beneficiary_type, note]",
            ]
        },
        "next_stage_goal": "把产业链环节映射到公司，并判断哪些公司受益最多、为什么受益最多。",
    },
    "company_beneficiary_ranking": {
        "title": "AI 公司受益排序",
        "goal": "基于上一步产业链环节、利润重心和集中度判断，对候选公司做受益排序，识别谁最受益、为什么最受益。",
        "constraints": [
            "只能基于上一步的产业链环节和给定公司池继续排序，不能发明公司。",
            "必须输出 symbol 和 company_name，禁止只写模糊公司类型。",
            "必须区分龙头受益、弹性受益、主题映射和弱相关。",
            "必须给出 beneficiary_rank、ranking_rationale、key_profit_link 和 caution。",
        ],
        "output_contract": {
            "companies": [
                "symbol",
                "company_name",
                "beneficiary_rank",
                "beneficiary_level",
                "ranking_rationale",
                "key_profit_link",
                "caution",
            ]
        },
        "next_stage_goal": "将公司受益排序结果接入最终投资建议与仓位判断。",
    },
}

TERMINAL_PROVIDER_STATUSES = {
    "quota_exceeded",
    "auth_error",
    "rate_limited",
    "provider_unavailable",
    "provider_timeout",
}


def build_ai_research_pipeline(
    *,
    news_items: list[dict[str, Any]],
    watchlist: tuple[Any, ...],
    focus_topics: tuple[str, ...],
    personal_notes: str,
    company_pool: list[dict[str, Any]],
    model_settings: dict[str, Any],
) -> dict[str, Any]:
    if not model_settings.get("enabled"):
        return _disabled_pipeline("disabled", "未启用模型增强，AI 研究链未执行。")

    provider = str(model_settings.get("provider", "openai-compatible") or "openai-compatible").strip()
    api_key = str(model_settings.get("api_key", "")).strip()
    base_url = str(model_settings.get("base_url", "")).strip()
    model_name = str(model_settings.get("model_name", "")).strip()
    if provider == "codex-cli":
        if not model_name:
            model_name = "gpt-5.4"
            model_settings = {**model_settings, "model_name": model_name}
        news_limit = 2
        company_pool_limit = 24
    elif not api_key or not base_url or not model_name:
        return _disabled_pipeline("missing_credentials", "模型配置不完整，AI 研究链未执行。")
    else:
        news_limit = 4
        company_pool_limit = len(company_pool)

    news_context = [
        {
            "news_id": item.get("news_id"),
            "headline": item.get("headline"),
            "summary": item.get("summary"),
            "source_name": item.get("source_name"),
            "source_kind": item.get("source_kind"),
            "region": item.get("region"),
            "market_scope": item.get("market_scope"),
            "tags": item.get("tags", []),
            "published_at": item.get("published_at"),
            "hot_score": item.get("hot_score"),
        }
        for item in news_items[:news_limit]
    ]
    watchlist_context = [
        {
            "symbol": getattr(item, "symbol", ""),
            "name": getattr(item, "name", ""),
            "position_pct": getattr(item, "position_pct", 0),
            "thesis": getattr(item, "thesis", ""),
        }
        for item in watchlist
    ]

    localization_input = {
        "news_items": news_context,
        "focus_topics": list(focus_topics),
        "watchlist": watchlist_context,
        "personal_notes": personal_notes,
    }
    localization_stage = _run_stage(
        stage_name="news_localization",
        input_payload=localization_input,
        model_settings=model_settings,
    )
    if localization_stage.get("status") != "ok":
        return _pipeline_from_stages(
            status=localization_stage["status"] if _is_terminal_stage_failure(localization_stage) else "error",
            note=localization_stage["message"],
            model_settings=model_settings,
            stages=[
                localization_stage,
                _blocked_stage("event_understanding", localization_stage["message"]),
                _blocked_stage("scenario_analysis", localization_stage["message"]),
                _blocked_stage("supply_chain_expansion", localization_stage["message"]),
                _blocked_stage("company_beneficiary_ranking", localization_stage["message"]),
            ],
        )
    localized_news_context = _apply_localization_to_news_context(news_context, localization_stage)

    event_input = {
        "news_items": localized_news_context,
        "focus_topics": list(focus_topics),
        "watchlist": watchlist_context,
        "personal_notes": personal_notes,
    }
    event_stage = _run_stage(
        stage_name="event_understanding",
        input_payload=event_input,
        model_settings=model_settings,
    )
    if event_stage.get("status") != "ok":
        return _pipeline_from_stages(
            status=event_stage["status"] if _is_terminal_stage_failure(event_stage) else "error",
            note=event_stage["message"],
            model_settings=model_settings,
            stages=[
                localization_stage,
                event_stage,
                _blocked_stage("scenario_analysis", event_stage["message"]),
                _blocked_stage("supply_chain_expansion", event_stage["message"]),
                _blocked_stage("company_beneficiary_ranking", event_stage["message"]),
            ],
        )

    scenario_input = {
        "events": event_stage.get("data", {}).get("events", []),
        "focus_topics": list(focus_topics),
        "watchlist": watchlist_context,
        "personal_notes": personal_notes,
    }
    scenario_stage = _run_stage(
        stage_name="scenario_analysis",
        input_payload=scenario_input,
        model_settings=model_settings,
    )
    if scenario_stage.get("status") != "ok":
        return _pipeline_from_stages(
            status=scenario_stage["status"] if _is_terminal_stage_failure(scenario_stage) else "error",
            note=scenario_stage["message"],
            model_settings=model_settings,
            stages=[
                localization_stage,
                event_stage,
                scenario_stage,
                _blocked_stage("supply_chain_expansion", scenario_stage["message"]),
                _blocked_stage("company_beneficiary_ranking", scenario_stage["message"]),
            ],
        )

    supply_chain_input = {
        "events": event_stage.get("data", {}).get("events", []),
        "scenarios": scenario_stage.get("data", {}).get("scenarios", []),
        "focus_topics": list(focus_topics),
        "watchlist": watchlist_context,
        "personal_notes": personal_notes,
    }
    supply_chain_stage = _run_stage(
        stage_name="supply_chain_expansion",
        input_payload=supply_chain_input,
        model_settings=model_settings,
    )
    if supply_chain_stage.get("status") != "ok":
        return _pipeline_from_stages(
            status=supply_chain_stage["status"] if _is_terminal_stage_failure(supply_chain_stage) else "error",
            note=supply_chain_stage["message"],
            model_settings=model_settings,
            stages=[
                localization_stage,
                event_stage,
                scenario_stage,
                supply_chain_stage,
                _blocked_stage("company_beneficiary_ranking", supply_chain_stage["message"]),
            ],
        )

    company_ranking_input = {
        "events": event_stage.get("data", {}).get("events", []),
        "scenarios": scenario_stage.get("data", {}).get("scenarios", []),
        "industries": supply_chain_stage.get("data", {}).get("industries", []),
        "company_pool": company_pool[:company_pool_limit],
        "watchlist": watchlist_context,
        "focus_topics": list(focus_topics),
        "personal_notes": personal_notes,
    }
    company_ranking_stage = _run_stage(
        stage_name="company_beneficiary_ranking",
        input_payload=company_ranking_input,
        model_settings=model_settings,
    )
    return _pipeline_from_stages(
        status=company_ranking_stage["status"] if company_ranking_stage.get("status") != "ok" and _is_terminal_stage_failure(company_ranking_stage) else None,
        note=company_ranking_stage.get("message", "") if company_ranking_stage.get("status") != "ok" and _is_terminal_stage_failure(company_ranking_stage) else None,
        model_settings=model_settings,
        stages=[localization_stage, event_stage, scenario_stage, supply_chain_stage, company_ranking_stage],
    )


def _run_stage(
    *,
    stage_name: str,
    input_payload: dict[str, Any],
    model_settings: dict[str, Any],
) -> dict[str, Any]:
    contract = STAGE_CONTRACTS[stage_name]
    system_prompt = _compose_system_prompt(stage_name, contract)
    user_prompt = _compose_user_prompt(stage_name, contract, input_payload)
    try:
        response_text = _chat_completion(
            str(model_settings.get("base_url", "")).strip(),
            str(model_settings.get("api_key", "")).strip(),
            str(model_settings.get("model_name", "")).strip(),
            system_prompt,
            user_prompt,
            model_settings,
        )
        parsed = _extract_json(response_text)
        if not isinstance(parsed, dict):
            return _stage_result(stage_name, "invalid_response", "模型未返回 JSON 对象。", {}, contract)
        if _contains_corrupted_text(parsed):
            return _stage_result(stage_name, "invalid_response", "模型返回疑似编码乱码，已拒绝写入研究链。", {}, contract)
        return _stage_result(stage_name, "ok", "ok", parsed, contract)
    except Exception as exc:
        status, message = _classify_stage_error(exc)
        return _stage_result(stage_name, status, message, {}, contract)


def _disabled_pipeline(status: str, note: str) -> dict[str, Any]:
    localization_contract = STAGE_CONTRACTS["news_localization"]
    event_contract = STAGE_CONTRACTS["event_understanding"]
    scenario_contract = STAGE_CONTRACTS["scenario_analysis"]
    chain_contract = STAGE_CONTRACTS["supply_chain_expansion"]
    ranking_contract = STAGE_CONTRACTS["company_beneficiary_ranking"]
    return {
        "enabled": False,
        "status": status,
        "provider": "",
        "model_name": "",
        "note": note,
        "news_localization": _stage_result("news_localization", status, note, {}, localization_contract),
        "event_understanding": _stage_result("event_understanding", status, note, {}, event_contract),
        "scenario_analysis": _stage_result("scenario_analysis", status, note, {}, scenario_contract),
        "supply_chain_expansion": _stage_result("supply_chain_expansion", status, note, {}, chain_contract),
        "company_beneficiary_ranking": _stage_result("company_beneficiary_ranking", status, note, {}, ranking_contract),
    }


def _blocked_stage(stage_name: str, upstream_message: str) -> dict[str, Any]:
    contract = STAGE_CONTRACTS[stage_name]
    return _stage_result(
        stage_name,
        "blocked",
        f"因上游 AI 阶段失败而未执行。{upstream_message}",
        {},
        contract,
    )


def _pipeline_from_stages(
    *,
    status: str | None,
    note: str | None,
    model_settings: dict[str, Any],
    stages: list[dict[str, Any]],
) -> dict[str, Any]:
    final_status = status
    final_note = note
    if not final_status:
        if all(stage["status"] == "ok" for stage in stages):
            final_status = "ok"
            final_note = "AI 研究链已完成新闻中文化、新闻理解、事态推演、产业链展开和公司受益排序。"
        elif any(stage["status"] == "ok" for stage in stages):
            final_status = "partial"
            final_note = "AI 研究链部分完成，至少一个阶段返回成功。"
        else:
            final_status = "error"
            final_note = "AI 研究链执行失败。"
    return {
        "enabled": True,
        "status": final_status,
        "provider": str(model_settings.get("provider", "openai-compatible")),
        "model_name": str(model_settings.get("model_name", "")),
        "note": final_note or "",
        "news_localization": stages[0],
        "event_understanding": stages[1],
        "scenario_analysis": stages[2],
        "supply_chain_expansion": stages[3],
        "company_beneficiary_ranking": stages[4],
    }


def _is_terminal_stage_failure(stage: dict[str, Any]) -> bool:
    return str(stage.get("status", "") or "") in TERMINAL_PROVIDER_STATUSES


def _classify_stage_error(exc: Exception) -> tuple[str, str]:
    raw = str(exc)
    message = raw.lower()
    if "http 401" in message or "incorrect api key" in message or "invalid api key" in message or "unauthorized" in message:
        return "auth_error", "模型鉴权失败，请检查 API Key、Base URL 和模型名。"
    if "http 400" in message and "invalid temperature" in message:
        return "error", "模型参数不兼容：Kimi/Moonshot 模型要求 temperature=1，系统已自动适配，请重新生成。"
    if "http 429" in message and (
        "quota" in message
        or "billing" in message
        or "insufficient_quota" in message
        or "exceeded your current quota" in message
    ):
        return "quota_exceeded", "模型配额不足或计费未开通，请检查 API 平台余额与账单设置。"
    if "http 429" in message or "rate limit" in message or "rate_limited" in message:
        return "rate_limited", "模型请求过于频繁，已触发速率限制，请稍后重试。"
    if "timed out" in message or "timeout" in message:
        return "provider_timeout", "模型请求超时，请稍后重试或调高超时设置。"
    if "http 5" in message or "service unavailable" in message or "bad gateway" in message:
        return "provider_unavailable", "模型服务当前不可用，请稍后重试。"
    return "error", raw[:200]


def _compose_system_prompt(stage_name: str, contract: dict[str, Any]) -> str:
    return (
        "你是专业基金公司的投研人员，正在执行一条分阶段的研究链。\n"
        f"当前阶段：{contract['title']}。\n"
        f"当前阶段目标：{contract['goal']}\n"
        "你必须严格遵守以下约束：\n- "
        + "\n- ".join(contract["constraints"])
        + "\n输出必须是 JSON，不要输出 Markdown，不要输出解释性前言。"
    )


def _compose_user_prompt(stage_name: str, contract: dict[str, Any], input_payload: dict[str, Any]) -> str:
    return (
        f"当前阶段：{contract['title']}\n"
        f"阶段目标：{contract['goal']}\n"
        "本阶段输入只允许使用下面 JSON，不允许自行补充外部事实。\n"
        f"本阶段必须产出这些字段：{json.dumps(contract['output_contract'], ensure_ascii=False)}\n"
        f"下一阶段目标：{contract['next_stage_goal']}\n\n"
        "输入 JSON："
        + json.dumps(input_payload, ensure_ascii=False)
    )


def _stage_result(
    stage_name: str,
    status: str,
    message: str,
    data: dict[str, Any],
    contract: dict[str, Any],
) -> dict[str, Any]:
    return {
        "stage": stage_name,
        "status": status,
        "message": message,
        "goal": contract["goal"],
        "constraints": list(contract["constraints"]),
        "output_contract": contract["output_contract"],
        "next_stage_goal": contract["next_stage_goal"],
        "data": data,
    }


def _apply_localization_to_news_context(news_context: list[dict[str, Any]], localization_stage: dict[str, Any]) -> list[dict[str, Any]]:
    if localization_stage.get("status") != "ok":
        return news_context
    items = localization_stage.get("data", {}).get("items", [])
    if not isinstance(items, list):
        return news_context
    localized_map = {str(item.get("news_id", "")): item for item in items if isinstance(item, dict)}
    result: list[dict[str, Any]] = []
    for item in news_context:
        localized = localized_map.get(str(item.get("news_id", "")), {})
        result.append(
            {
                **item,
                "translated_headline": str(localized.get("translated_headline", "") or "").strip(),
                "translated_summary": str(localized.get("translated_summary", "") or "").strip(),
                "translation_note": str(localized.get("translation_note", "") or "").strip(),
                "language": str(localized.get("language", "") or "").strip(),
            }
        )
    return result


def _contains_corrupted_text(payload: Any) -> bool:
    if isinstance(payload, dict):
        return any(_contains_corrupted_text(value) for value in payload.values())
    if isinstance(payload, list):
        return any(_contains_corrupted_text(value) for value in payload)
    if isinstance(payload, str):
        stripped = payload.strip()
        if not stripped:
            return False
        question_count = stripped.count("?")
        return "????" in stripped or (question_count >= 8 and question_count / max(1, len(stripped)) > 0.25)
    return False
