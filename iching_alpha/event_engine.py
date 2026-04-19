"""Event identity and profit propagation helpers."""

from __future__ import annotations

import hashlib
import re
from typing import Any


def build_event_identity(
    *,
    event_type: str,
    cluster_id: str,
    title: str,
    stage: str,
    supporting_news: list[dict[str, Any]],
) -> dict[str, str]:
    master_seed = "||".join(
        [
            str(event_type or "").strip().lower(),
            str(cluster_id or "").strip().lower(),
            str(title or "").strip().lower(),
        ]
    )
    master_hash = _short_hash(master_seed, 12)
    event_master_id = f"evt_{master_hash}"

    latest_source_date = max(
        (
            str(item.get("published_at", "") or "")[:10]
            for item in supporting_news
            if str(item.get("published_at", "") or "").strip()
        ),
        default="undated",
    )
    top_news_ids = sorted(
        str(item.get("news_id", "") or "").strip()
        for item in supporting_news[:5]
        if str(item.get("news_id", "") or "").strip()
    )
    instance_seed = "||".join(
        [
            event_master_id,
            str(stage or "").strip().lower(),
            latest_source_date,
            *top_news_ids,
        ]
    )
    event_signature = _short_hash(instance_seed, 16)
    compact_date = latest_source_date.replace("-", "")
    event_instance_id = f"{event_master_id}_{compact_date}_{event_signature[:8]}"
    return {
        "event_master_id": event_master_id,
        "event_instance_id": event_instance_id,
        "event_signature": event_signature,
        "latest_source_date": latest_source_date,
    }


def build_event_profit_propagation(
    *,
    event_master_id: str,
    event_instance_id: str,
    event_title: str,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = [_enrich_segment(item) for item in segments]
    enriched = [item for item in enriched if item]
    enriched.sort(key=lambda item: item["propagation_score"], reverse=True)
    for index, item in enumerate(enriched, start=1):
        item["propagation_rank"] = index

    direct = [item for item in enriched if item["beneficiary_type"] == "直接受益"]
    indirect = [item for item in enriched if item["beneficiary_type"] == "间接受益"]
    weak = [item for item in enriched if item["beneficiary_type"] in {"主题映射", "弱相关"}]
    primary = enriched[:3]
    return {
        "event_master_id": event_master_id,
        "event_instance_id": event_instance_id,
        "profit_focus": [item["node_name"] for item in primary],
        "primary_profit_centers": _slim_segments(primary),
        "direct_beneficiaries": _slim_segments(direct[:4]),
        "indirect_beneficiaries": _slim_segments(indirect[:4]),
        "weak_links": _slim_segments(weak[:4]),
        "concentration_summary": _summarize_concentration(primary),
        "transmission_summary": _summarize_transmission(event_title, primary, direct, indirect, weak),
        "segments": enriched,
    }


def build_industry_profit_map(
    *,
    industry_id: str,
    industry_name: str,
    segments: list[dict[str, Any]],
) -> dict[str, Any]:
    enriched = [_enrich_segment(item) for item in segments]
    enriched = [item for item in enriched if item]
    enriched.sort(key=lambda item: item["propagation_score"], reverse=True)
    for index, item in enumerate(enriched, start=1):
        item["propagation_rank"] = index

    primary = enriched[:3]
    direct = [item for item in enriched if item["beneficiary_type"] == "直接受益"]
    indirect = [item for item in enriched if item["beneficiary_type"] == "间接受益"]
    weak = [item for item in enriched if item["beneficiary_type"] in {"主题映射", "弱相关"}]
    return {
        "industry_id": industry_id,
        "industry_name": industry_name,
        "profit_focus": [item["node_name"] for item in primary],
        "primary_profit_centers": _slim_segments(primary),
        "direct_beneficiaries": _slim_segments(direct[:5]),
        "indirect_beneficiaries": _slim_segments(indirect[:5]),
        "weak_links": _slim_segments(weak[:5]),
        "concentration_summary": _summarize_concentration(primary),
        "segments": enriched,
    }


def _enrich_segment(item: dict[str, Any]) -> dict[str, Any]:
    node_name = str(item.get("node_name") or item.get("name") or "").strip()
    if not node_name:
        return {}
    raw_relation_type = str(item.get("relation_type") or item.get("beneficiary_type") or "").strip()
    relation_type = _normalize_beneficiary_type(raw_relation_type)
    impact_strength = int(item.get("impact_strength", 0) or 0)
    profit_pool_text = str(item.get("profit_pool_weight") or item.get("value_contribution") or "").strip()
    value_pool = str(item.get("value_pool") or item.get("profit_level") or "").strip()
    concentration_text = str(item.get("concentration") or "").strip()
    profit_pool_weight_numeric = _estimate_profit_weight(profit_pool_text, value_pool)
    concentration_score = _estimate_concentration_score(concentration_text)
    role_multiplier = {
        "直接受益": 1.0,
        "间接受益": 0.72,
        "主题映射": 0.46,
        "弱相关": 0.26,
    }.get(relation_type, 0.5)
    propagation_score = round(
        max(
            0,
            min(
                100,
                impact_strength * role_multiplier * 0.68
                + profit_pool_weight_numeric * 0.22
                + concentration_score * 0.10,
            ),
        )
    )
    return {
        "industry_id": str(item.get("industry_id", "") or "").strip(),
        "industry_name": str(item.get("industry_name", "") or "").strip(),
        "node_id": str(item.get("node_id", "") or "").strip(),
        "node_name": node_name,
        "stage": str(item.get("stage", "") or "").strip(),
        "beneficiary_type": relation_type,
        "impact_direction": str(item.get("direction", "positive") or "positive").strip(),
        "impact_strength": impact_strength,
        "profit_pool_weight": profit_pool_text,
        "profit_pool_weight_numeric": profit_pool_weight_numeric,
        "value_pool": value_pool,
        "concentration": concentration_text,
        "concentration_score": concentration_score,
        "profit_role": _derive_profit_role(
            beneficiary_type=relation_type,
            profit_pool_weight_numeric=profit_pool_weight_numeric,
            value_pool=value_pool,
        ),
        "propagation_score": propagation_score,
        "representative_companies": list(item.get("representative_companies", []) or []),
        "rationale": str(item.get("rationale", "") or item.get("note", "") or "").strip(),
    }


def _normalize_beneficiary_type(raw_value: str) -> str:
    value = str(raw_value or "").strip()
    if value in {"直接受益", "核心受益", "高优先级"}:
        return "直接受益"
    if value in {"间接受益", "次级受益"}:
        return "间接受益"
    if value in {"主题映射", "待验证"}:
        return "主题映射"
    if value in {"弱相关", "低优先级"}:
        return "弱相关"
    return value or "主题映射"


def _estimate_profit_weight(text: str, value_pool: str) -> int:
    matches = [int(item) for item in re.findall(r"(\d{1,3})\s*%", text)]
    if matches:
        return round(sum(matches) / len(matches))
    combined = f"{text} {value_pool}".strip()
    if any(token in combined for token in ("最大", "最强", "利润中心", "弹性极高")):
        return 82
    if any(token in combined for token in ("较高", "高", "弹性强", "核心")):
        return 68
    if any(token in combined for token in ("中等", "稳定", "中游")):
        return 48
    if any(token in combined for token in ("较低", "低", "防御", "不是利润中心")):
        return 28
    return 40


def _estimate_concentration_score(text: str) -> int:
    value = str(text or "").strip()
    if any(token in value for token in ("高度集中", "龙头集中", "集中度高", "头部集中")):
        return 84
    if any(token in value for token in ("集中", "中等", "寡头")):
        return 62
    if any(token in value for token in ("分散", "玩家较多")):
        return 36
    return 50


def _derive_profit_role(
    *,
    beneficiary_type: str,
    profit_pool_weight_numeric: int,
    value_pool: str,
) -> str:
    if beneficiary_type == "直接受益" and profit_pool_weight_numeric >= 55:
        return "利润中心"
    if beneficiary_type == "直接受益":
        return "收入承接"
    if beneficiary_type == "间接受益":
        return "链条传导"
    if beneficiary_type == "弱相关":
        return "弱相关映射"
    if "利润" in value_pool and "高" in value_pool:
        return "利润中心"
    return "主题映射"


def _summarize_concentration(primary_segments: list[dict[str, Any]]) -> str:
    if not primary_segments:
        return "暂无利润传导集中度结论。"
    high = [item for item in primary_segments if item["concentration_score"] >= 75]
    if high:
        names = "、".join(item["node_name"] for item in high[:2])
        return f"利润更集中在 {names} 等头部环节，龙头集中度较高。"
    names = "、".join(item["node_name"] for item in primary_segments[:2])
    return f"利润主要落在 {names}，但环节集中度仍需继续验证。"


def _summarize_transmission(
    event_title: str,
    primary_segments: list[dict[str, Any]],
    direct: list[dict[str, Any]],
    indirect: list[dict[str, Any]],
    weak: list[dict[str, Any]],
) -> str:
    if not primary_segments:
        return f"{event_title} 尚未形成稳定的利润传导路径。"
    direct_names = "、".join(item["node_name"] for item in direct[:2]) or "暂无"
    indirect_names = "、".join(item["node_name"] for item in indirect[:2]) or "暂无"
    weak_names = "、".join(item["node_name"] for item in weak[:2]) or "暂无"
    return (
        f"{event_title} 的利润传导先落到 {direct_names}，"
        f"再扩散到 {indirect_names}；{weak_names} 更偏主题映射或弱相关。"
    )


def _slim_segments(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "industry_id": item["industry_id"],
            "industry_name": item["industry_name"],
            "node_id": item["node_id"],
            "node_name": item["node_name"],
            "beneficiary_type": item["beneficiary_type"],
            "profit_role": item["profit_role"],
            "propagation_score": item["propagation_score"],
            "profit_pool_weight": item["profit_pool_weight"],
            "concentration": item["concentration"],
        }
        for item in items
    ]


def _short_hash(seed: str, width: int) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:width]
