"""Runtime refresh helpers for stock/news data status and updates."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from .config import AppConfig
from .news_pipeline import deduplicate_and_cluster_news
from .news_sources import fetch_live_raw_news_feed, parse_custom_rss_sources
from .overrides import PRICE_OVERRIDE_PATH, build_hk_price_overrides
from .storage import artifacts_root


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
ARTIFACTS_DIR = artifacts_root(Path(__file__).resolve().parent.parent)
NEWS_CACHE_PATH = ARTIFACTS_DIR / "cache" / "news_refresh_cache.json"
MARKET_TZ = ZoneInfo("Asia/Shanghai")


def load_config() -> AppConfig:
    return AppConfig.from_file(CONFIG_PATH)


def refresh_all_data(rss_sources_text: str = "") -> dict[str, Any]:
    stock = refresh_stock_data()
    news = refresh_news_data(rss_sources_text)
    return {"stock": stock, "news": news}


def refresh_stock_data() -> dict[str, Any]:
    result = build_hk_price_overrides()
    status = get_stock_data_status()
    status.update({"refresh_count": result["count"], "refresh_misses": result["misses"]})
    return status


def refresh_news_data(rss_sources_text: str = "") -> dict[str, Any]:
    custom_sources = parse_custom_rss_sources(rss_sources_text)
    raw_items = fetch_live_raw_news_feed(sources=custom_sources or None)
    now = datetime.now(timezone.utc)
    clustered = deduplicate_and_cluster_news(raw_items, now)
    latest_published = max((item.get("published_at", "") for item in clustered), default="")
    preview_items = [
        {
            "news_id": str(item.get("news_id", "") or ""),
            "headline": str(item.get("translated_headline") or item.get("headline") or "").strip(),
            "source_name": str(item.get("source_name", "") or "").strip(),
            "source_url": str(item.get("source_url", "") or "").strip(),
            "published_at": str(item.get("published_at", "") or "").strip(),
            "source_layer": str(item.get("source_layer", "") or "").strip(),
        }
        for item in clustered[:8]
    ]
    NEWS_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    NEWS_CACHE_PATH.write_text(
        json.dumps(
            {
                "refreshed_at": now.isoformat(),
                "latest_published_at": latest_published,
                "items_count": len(clustered),
                "preview_items": preview_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return get_news_data_status()


def get_stock_data_status() -> dict[str, Any]:
    config = load_config()
    price_df = pd.read_parquet(config.parquet_path, columns=["datetime"])
    price_df["datetime"] = pd.to_datetime(price_df["datetime"])
    primary_as_of = price_df["datetime"].max().strftime("%Y-%m-%d")
    override_as_of = ""
    override_count = 0
    if PRICE_OVERRIDE_PATH.exists():
        payload = json.loads(PRICE_OVERRIDE_PATH.read_text(encoding="utf-8"))
        items = payload.get("items", {})
        override_count = len(items)
        override_as_of = max((item.get("as_of", "") for item in items.values()), default="")
    display_as_of = override_as_of or primary_as_of
    note = f"A股主数据 {primary_as_of}"
    if override_as_of:
        note += f" / 港股覆盖 {override_as_of}"
    return {
        "stock_data_as_of": display_as_of,
        "stock_data_note": note,
        "stock_primary_as_of": primary_as_of,
        "stock_override_as_of": override_as_of,
        "stock_override_count": override_count,
    }


def get_news_data_status() -> dict[str, Any]:
    if not NEWS_CACHE_PATH.exists():
        return {
            "news_data_as_of": "",
            "news_data_note": "尚未刷新真实新闻源",
            "news_items_count": 0,
            "news_preview_items": [],
        }
    payload = json.loads(NEWS_CACHE_PATH.read_text(encoding="utf-8"))
    latest_published_at = str(payload.get("latest_published_at", ""))
    refreshed_at = str(payload.get("refreshed_at", ""))
    return {
        "news_data_as_of": _format_market_date(latest_published_at),
        "news_data_note": (
            f"最近刷新 {_format_market_timestamp(refreshed_at)} / "
            f"最新新闻时间 {_format_market_timestamp(latest_published_at)} / "
            f"{payload.get('items_count', 0)} 条新闻"
        ),
        "news_items_count": int(payload.get("items_count", 0)),
        "news_preview_items": list(payload.get("preview_items", [])),
    }


def _format_market_date(value: str) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return str(value)[:10]
    return dt.astimezone(MARKET_TZ).strftime("%Y-%m-%d")


def _format_market_timestamp(value: str) -> str:
    dt = _parse_datetime(value)
    if dt is None:
        return str(value)[:19]
    return dt.astimezone(MARKET_TZ).strftime("%Y-%m-%d %H:%M")


def _parse_datetime(value: str) -> datetime | None:
    if not value:
        return None
    candidate = str(value).strip()
    if not candidate:
        return None
    try:
        dt = datetime.fromisoformat(candidate.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
