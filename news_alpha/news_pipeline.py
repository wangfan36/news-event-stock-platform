"""Raw news ingestion, normalization, deduplication, and clustering."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

DEMO_RAW_NEWS_FEED: tuple[dict[str, Any], ...] = (
    {"source_id": "g1", "headline": "海外云厂商上修训练集群预算，800G 链路需求继续抬升", "summary": "全球算力热点延续，资本开支并未中断。", "source_name": "全球科技资本开支监测", "source_kind": "产业链监测", "region": "全球", "market_scope": "A/H 映射", "credibility_score": 91, "published_offset_hours": 2, "tags": ["AI算力", "光模块", "海外需求"], "cluster_hint": "cluster_ai_capex"},
    {"source_id": "g2", "headline": "北美云厂商维持 2026 年数据中心 capex 指引", "summary": "景气从单点客户扩散到更多云厂商。", "source_name": "海外业绩会纪要流", "source_kind": "公司动态", "region": "全球", "market_scope": "A股+港股", "credibility_score": 88, "published_offset_hours": 4, "tags": ["AI算力", "资本开支", "云厂商"], "cluster_hint": "cluster_ai_capex"},
    {"source_id": "g2-dup", "headline": "北美云厂商维持2026年数据中心capex指引", "summary": "同一条新闻的轻微标题变体，用于测试去重。", "source_name": "海外业绩会纪要流", "source_kind": "公司动态", "region": "全球", "market_scope": "A股+港股", "credibility_score": 87, "published_offset_hours": 4, "tags": ["AI算力", "资本开支"], "cluster_hint": "cluster_ai_capex"},
    {"source_id": "s1", "headline": "设备更新贴息范围扩围，半导体设备国产化订单预期回暖", "summary": "国内政策继续支持设备替代。", "source_name": "国内政策观察", "source_kind": "政策", "region": "国内", "market_scope": "A股+港股", "credibility_score": 86, "published_offset_hours": 5, "tags": ["国产替代", "半导体设备", "设备更新"], "cluster_hint": "cluster_semi_policy"},
    {"source_id": "s2", "headline": "多家晶圆厂披露扩产节奏恢复，设备招标窗口边际改善", "summary": "从政策到订单的传导开始有验证。", "source_name": "晶圆厂招标跟踪", "source_kind": "招投标", "region": "国内", "market_scope": "A股+港股", "credibility_score": 82, "published_offset_hours": 9, "tags": ["晶圆厂", "扩产", "设备"], "cluster_hint": "cluster_semi_policy"},
    {"source_id": "e1", "headline": "多地新型储能示范项目集中开标，并网节奏明显提速", "summary": "储能链关注点从政策刺激转到项目落地。", "source_name": "国内储能项目库", "source_kind": "项目", "region": "国内", "market_scope": "A股", "credibility_score": 84, "published_offset_hours": 6, "tags": ["储能", "电池", "并网"], "cluster_hint": "cluster_storage"},
    {"source_id": "e2", "headline": "欧洲工商业储能报价趋稳，头部厂商订单可见度延长", "summary": "海外储能需求仍在，价格战阶段性缓解。", "source_name": "欧洲储能渠道跟踪", "source_kind": "渠道", "region": "全球", "market_scope": "A股", "credibility_score": 79, "published_offset_hours": 12, "tags": ["储能", "出海", "价格"], "cluster_hint": "cluster_storage"},
    {"source_id": "o1", "headline": "中东航线扰动延续，油运绕航推动运价中枢再抬升", "summary": "航运链条进入典型事件驱动窗口。", "source_name": "全球航运雷达", "source_kind": "航运数据", "region": "全球", "market_scope": "A股+港股", "credibility_score": 87, "published_offset_hours": 3, "tags": ["航运", "油运", "地缘"], "cluster_hint": "cluster_shipping"},
    {"source_id": "o2", "headline": "原油贸易流继续重构，亚洲进口航次拉长", "summary": "运输距离增加，运力供需改善超预期。", "source_name": "能源航运链路", "source_kind": "产业链监测", "region": "全球", "market_scope": "A股+港股", "credibility_score": 81, "published_offset_hours": 10, "tags": ["航运", "原油", "贸易流"], "cluster_hint": "cluster_shipping"},
    {"source_id": "r1", "headline": "部分地方专项债投放慢于预期，政企项目预算释放偏滞后", "summary": "预算节奏滞后会压制部分项目确认。", "source_name": "地方财政与招标跟踪", "source_kind": "宏观", "region": "国内", "market_scope": "A股", "credibility_score": 76, "published_offset_hours": 8, "tags": ["预算", "风险", "项目"], "cluster_hint": "cluster_budget_risk"},
)


def load_demo_raw_news_feed() -> list[dict[str, Any]]:
    return [dict(item) for item in DEMO_RAW_NEWS_FEED]


def normalize_news_item(raw_item: dict[str, Any], run_clock: datetime) -> dict[str, Any]:
    headline = str(raw_item.get("headline", "")).strip()
    summary = str(raw_item.get("summary", "")).strip()
    tags = [str(tag).strip() for tag in raw_item.get("tags", []) if str(tag).strip()]
    normalized_headline = _headline_fingerprint(headline)
    published_at, published_offset_hours = _resolve_publication_time(raw_item, run_clock)
    cluster_id = str(raw_item.get("cluster_hint") or _cluster_from_content(headline, summary, tags))
    news_id = str(raw_item.get("source_id") or hashlib.sha1(f"{cluster_id}:{headline}".encode("utf-8")).hexdigest()[:12])
    source_kind = str(raw_item.get("source_kind", "其他"))
    return {
        "news_id": news_id,
        "cluster_id": cluster_id,
        "headline": headline,
        "summary": summary,
        "source_url": str(raw_item.get("source_url", "")).strip(),
        "source_name": str(raw_item.get("source_name", "未知来源")),
        "source_kind": source_kind,
        "source_layer": _source_layer(source_kind),
        "region": str(raw_item.get("region", "未知")),
        "market_scope": str(raw_item.get("market_scope", "A股+港股")),
        "credibility_score": int(raw_item.get("credibility_score", 60) or 60),
        "published_offset_hours": published_offset_hours,
        "published_at": published_at,
        "tags": tags,
        "normalized_headline": normalized_headline,
    }


def deduplicate_and_cluster_news(raw_items: list[dict[str, Any]], run_clock: datetime) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_item in raw_items:
        item = normalize_news_item(raw_item, run_clock)
        dedup_key = (item["cluster_id"], item["normalized_headline"])
        previous = deduped.get(dedup_key)
        if previous is None or item["credibility_score"] > previous["credibility_score"]:
            deduped[dedup_key] = item

    clusters: dict[str, list[dict[str, Any]]] = {}
    for item in deduped.values():
        clusters.setdefault(item["cluster_id"], []).append(item)

    results: list[dict[str, Any]] = []
    for cluster_id, items in clusters.items():
        ordered = sorted(items, key=lambda item: (item["credibility_score"], item["published_at"]), reverse=True)
        representative = ordered[0]
        merged_tags = sorted({tag for item in ordered for tag in item["tags"]})
        results.extend(
            {
                **item,
                "cluster_size": len(ordered),
                "cluster_tags": merged_tags,
                "cluster_headline": representative["headline"],
            }
            for item in ordered
        )
    return sorted(results, key=lambda item: (item["credibility_score"], item["published_at"]), reverse=True)


def _source_layer(source_kind: str) -> str:
    kind = str(source_kind or "").strip().lower()
    if any(token in kind for token in ("政策", "监管", "央行", "证监", "工信", "商务", "统计")):
        return "policy"
    if any(token in kind for token in ("公告", "披露", "财报", "业绩")):
        return "filing"
    if any(token in kind for token in ("招投标", "项目", "行业数据", "产业链", "渠道", "航运数据")):
        return "industry_data"
    if any(token in kind for token in ("媒体", "rss", "快讯", "国际媒体", "财经媒体", "市场媒体")):
        return "media"
    return "media"


def _resolve_publication_time(raw_item: dict[str, Any], run_clock: datetime) -> tuple[str, int]:
    raw_published_at = str(raw_item.get("published_at", "") or "").strip()
    if raw_published_at:
        try:
            published = datetime.fromisoformat(raw_published_at.replace("Z", "+00:00"))
            local_zone = ZoneInfo("Asia/Shanghai")
            run_local = run_clock.replace(tzinfo=local_zone) if run_clock.tzinfo is None else run_clock.astimezone(local_zone)
            published_local = published.replace(tzinfo=local_zone) if published.tzinfo is None else published.astimezone(local_zone)
            offset = max(0, round((run_local - published_local).total_seconds() / 3600))
            return published_local.isoformat(timespec="minutes"), offset
        except ValueError:
            pass
    offset = max(0, int(raw_item.get("published_offset_hours", 0) or 0))
    return (run_clock - timedelta(hours=offset)).isoformat(timespec="minutes"), offset


def summarize_clusters(clustered_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: dict[str, list[dict[str, Any]]] = {}
    for item in clustered_items:
        clusters.setdefault(item["cluster_id"], []).append(item)
    summary = []
    for cluster_id, items in clusters.items():
        ordered = sorted(items, key=lambda item: (item["credibility_score"], item["published_at"]), reverse=True)
        summary.append(
            {
                "cluster_id": cluster_id,
                "headline": ordered[0]["headline"],
                "news_count": len(ordered),
                "regions": sorted({item["region"] for item in ordered}),
                "market_scopes": sorted({item["market_scope"] for item in ordered}),
                "tags": sorted({tag for item in ordered for tag in item["tags"]}),
                "avg_credibility_score": round(sum(item["credibility_score"] for item in ordered) / len(ordered)),
                "news_ids": [item["news_id"] for item in ordered],
            }
        )
    return sorted(summary, key=lambda item: item["avg_credibility_score"], reverse=True)


def _headline_fingerprint(headline: str) -> str:
    normalized = re.sub(r"\s+", "", headline.lower())
    normalized = re.sub(r"[，。、“”‘’！!？?（）()\-—_:/：]", "", normalized)
    return normalized


def _cluster_from_headline(headline: str) -> str:
    digest = hashlib.sha1(_headline_fingerprint(headline).encode("utf-8")).hexdigest()[:10]
    return f"cluster_{digest}"


def _cluster_from_content(headline: str, summary: str, tags: list[str]) -> str:
    text = f"{headline} {summary} {' '.join(tags)}".lower()
    if any(keyword in text for keyword in ("ai", "capex", "cloud", "光模块", "数据中心", "云厂商")):
        return "cluster_ai_capex"
    if any(keyword in text for keyword in ("semiconductor", "chip", "晶圆", "设备", "国产替代", "wafer")):
        return "cluster_semi_policy"
    if any(keyword in text for keyword in ("storage", "battery", "储能", "并网", "电池")):
        return "cluster_storage"
    if any(keyword in text for keyword in ("shipping", "oil tanker", "航运", "运价", "原油")):
        return "cluster_shipping"
    if any(keyword in text for keyword in ("budget", "财政", "专项债", "预算")):
        return "cluster_budget_risk"
    return _cluster_from_headline(headline)
