"""Live RSS news source integration."""

from __future__ import annotations

import html
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

RSS_SOURCES: tuple[dict[str, str], ...] = (
    {
        "source_id": "gn_world",
        "label": "Google News World",
        "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-US&gl=US&ceid=US:en",
        "region": "全球",
        "market_scope": "全球",
        "source_kind": "国际媒体",
        "credibility_score": "74",
    },
    {
        "source_id": "gn_business",
        "label": "Google News Business",
        "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=en-US&gl=US&ceid=US:en",
        "region": "全球",
        "market_scope": "全球",
        "source_kind": "财经媒体",
        "credibility_score": "74",
    },
    {
        "source_id": "gn_a_share",
        "label": "Google News A股",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("A股 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股",
        "source_kind": "市场媒体",
        "credibility_score": "70",
        "default_tags": "A股",
    },
    {
        "source_id": "gn_h_share",
        "label": "Google News 港股",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("港股 when:1d")
        + "&hl=zh-CN&gl=HK&ceid=HK:zh-Hant",
        "region": "国内",
        "market_scope": "港股",
        "source_kind": "市场媒体",
        "credibility_score": "70",
        "default_tags": "港股",
    },
    {
        "source_id": "gn_policy",
        "label": "Google News 产业政策",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("工信部 OR 发改委 OR 国家能源局 OR 产业政策 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股+港股",
        "source_kind": "政策监控",
        "credibility_score": "78",
        "default_tags": "政策,产业政策",
    },
    {
        "source_id": "gn_earnings",
        "label": "Google News 财报与业绩预告",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("业绩预告 OR 财报 OR 快报 OR 一季报 OR 年报 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股+港股",
        "source_kind": "财报监控",
        "credibility_score": "76",
        "default_tags": "财报,业绩",
    },
    {
        "source_id": "gn_announcement",
        "label": "Google News 公告与披露",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("公告 OR 披露 OR 交易所 OR 巨潮资讯 OR HKEX when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股+港股",
        "source_kind": "公告监控",
        "credibility_score": "77",
        "default_tags": "公告,披露",
    },
    {
        "source_id": "gn_tender",
        "label": "Google News 招标与中标",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("招标 OR 中标 OR 开标 OR 扩产 OR 订单 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股",
        "source_kind": "招投标监控",
        "credibility_score": "75",
        "default_tags": "订单,招标",
    },
    {
        "source_id": "gn_ai_optics",
        "label": "Google News AI算力与光模块",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("AI算力 OR 光模块 OR 800G OR 1.6T OR 数据中心 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "全球",
        "market_scope": "A股+港股",
        "source_kind": "主题监控",
        "credibility_score": "73",
        "default_tags": "AI算力,光模块",
    },
    {
        "source_id": "gn_semi_equipment",
        "label": "Google News 半导体设备",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("半导体设备 OR 晶圆厂 OR 刻蚀 OR 薄膜 OR 清洗 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股+港股",
        "source_kind": "主题监控",
        "credibility_score": "73",
        "default_tags": "半导体设备,国产替代",
    },
    {
        "source_id": "gn_storage",
        "label": "Google News 储能与电网",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("储能 OR 电网 OR 并网 OR 电池 OR PCS when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股",
        "source_kind": "主题监控",
        "credibility_score": "73",
        "default_tags": "储能,电网",
    },
    {
        "source_id": "gn_shipping",
        "label": "Google News 航运与油运",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("航运 OR 油运 OR 运价 OR BDTI OR BCTI when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "全球",
        "market_scope": "A股+港股",
        "source_kind": "行业数据监控",
        "credibility_score": "74",
        "default_tags": "航运,油运",
    },
    {
        "source_id": "gn_budget",
        "label": "Google News 财政与专项债",
        "url": "https://news.google.com/rss/search?q="
        + urllib.parse.quote("专项债 OR 财政 OR 预算 OR 基建 when:1d")
        + "&hl=zh-CN&gl=CN&ceid=CN:zh-Hans",
        "region": "国内",
        "market_scope": "A股",
        "source_kind": "宏观监控",
        "credibility_score": "75",
        "default_tags": "预算,财政",
    },
)


def fetch_live_raw_news_feed(
    timeout: float = 5.0,
    limit_per_source: int = 8,
    sources: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for source in sources or list(RSS_SOURCES):
        try:
            items.extend(fetch_rss_source(source, timeout=timeout, limit=limit_per_source))
        except Exception:
            continue
    return items


def fetch_rss_source(source: dict[str, str], timeout: float = 5.0, limit: int = 8) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        source["url"],
        headers={"User-Agent": "Mozilla/5.0 (Codex News Fetcher)"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        xml_bytes = response.read()

    root = ET.fromstring(xml_bytes)
    items: list[dict[str, Any]] = []
    entries = [node for node in root.iter() if _local_name(node.tag) in {"item", "entry"}]
    for raw_item in entries[:limit]:
        title = _child_text(raw_item, "title")
        description = _clean_description(
            _child_text(raw_item, "description")
            or _child_text(raw_item, "summary")
            or _child_text(raw_item, "content")
        )
        source_url = _entry_link(raw_item)
        published_at = _parse_publication_date(
            _child_text(raw_item, "pubDate")
            or _child_text(raw_item, "published")
            or _child_text(raw_item, "updated")
            or _child_text(raw_item, "date")
        )
        if not title:
            continue
        items.append(
            {
                "source_id": f"{source['source_id']}::{_slugify(source_url or title)}",
                "headline": title,
                "summary": description or title,
                "source_url": source_url,
                "source_name": source["label"],
                "source_kind": source.get("source_kind", "RSS"),
                "region": source["region"],
                "market_scope": source["market_scope"],
                "credibility_score": int(source.get("credibility_score", "72") or 72),
                "published_at": published_at,
                "published_offset_hours": 6 if not published_at else 0,
                "tags": _merge_source_tags(_infer_tags(title, description), source.get("default_tags", "")),
            }
        )
    return items


def _local_name(tag: str) -> str:
    return tag.rsplit("}", maxsplit=1)[-1]


def _child_text(node: ET.Element, tag: str) -> str:
    for child in node:
        if _local_name(child.tag) == tag:
            return "".join(child.itertext()).strip()
    return ""


def _entry_link(node: ET.Element) -> str:
    for child in node:
        if _local_name(child.tag) != "link":
            continue
        href = str(child.attrib.get("href", "") or "").strip()
        if href:
            return href
        if child.text:
            return child.text.strip()
    return ""


def _parse_publication_date(value: str) -> str:
    candidate = str(value or "").strip()
    if not candidate:
        return ""
    try:
        parsed = parsedate_to_datetime(candidate)
    except (TypeError, ValueError, OverflowError):
        try:
            parsed = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat(timespec="minutes")


def _clean_description(raw: str) -> str:
    text = html.unescape(raw)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _slugify(value: str) -> str:
    lowered = re.sub(r"\s+", "-", value.lower()).strip("-")
    lowered = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", lowered)
    return lowered[:48] or "item"


def _infer_tags(title: str, description: str) -> list[str]:
    text = f"{title} {description}".lower()
    mapping = {
        "AI算力": ("ai", "cloud", "data center", "gpu", "光模块"),
        "资本开支": ("capex", "budget", "spending"),
        "半导体设备": ("semiconductor", "chip", "wafer", "设备", "晶圆"),
        "国产替代": ("domestic", "国产", "替代"),
        "储能": ("storage", "battery", "储能", "电池"),
        "航运": ("shipping", "oil tanker", "航运", "运价"),
        "预算": ("budget", "债", "财政"),
        "政策": ("policy", "regulation", "政策"),
    }
    tags = [tag for tag, keywords in mapping.items() if any(keyword in text for keyword in keywords)]
    return tags or ["综合"]


def parse_custom_rss_sources(raw_text: str) -> list[dict[str, str]]:
    sources: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    for index, line in enumerate(raw_text.splitlines(), start=1):
        value = line.strip()
        if not value or value.startswith("#"):
            continue
        parts = [part.strip() for part in value.split("|")]
        url = parts[0]
        parsed_url = urllib.parse.urlparse(url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc or url in seen_urls:
            continue
        seen_urls.add(url)
        label = parts[1] if len(parts) >= 2 and parts[1] else f"Custom RSS {index}"
        region = parts[2] if len(parts) >= 3 and parts[2] else "自定义"
        market_scope = parts[3] if len(parts) >= 4 and parts[3] else "自定义"
        source_kind = parts[4] if len(parts) >= 5 and parts[4] else "自定义RSS"
        sources.append(
            {
                "source_id": f"custom_{index}",
                "label": label,
                "url": url,
                "region": region,
                "market_scope": market_scope,
                "source_kind": source_kind,
            }
        )
        if len(sources) >= 50:
            break
    return sources


def _merge_source_tags(inferred_tags: list[str], raw_default_tags: str) -> list[str]:
    tags = list(inferred_tags)
    for tag in [part.strip() for part in str(raw_default_tags or "").split(",") if part.strip()]:
        if tag not in tags:
            tags.append(tag)
    return tags or ["综合"]
