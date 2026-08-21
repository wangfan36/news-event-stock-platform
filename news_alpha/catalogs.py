"""Catalog loaders for industry, company, and event mappings."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

CATALOG_DIR = Path(__file__).resolve().parent / "catalogs"


def _load_json(filename: str) -> dict[str, Any]:
    path = CATALOG_DIR / filename
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def load_industry_catalog() -> dict[str, dict[str, Any]]:
    return _load_json("industry_catalog.json")


@lru_cache(maxsize=1)
def load_company_catalog() -> dict[str, dict[str, Any]]:
    return _load_json("company_catalog.json")


@lru_cache(maxsize=1)
def load_event_blueprints() -> dict[str, dict[str, Any]]:
    return _load_json("event_blueprints.json")


@lru_cache(maxsize=1)
def load_high_quality_development_universe() -> dict[str, Any]:
    return _load_json("high_quality_development_universe.json")


@lru_cache(maxsize=1)
def load_a_share_name_map() -> dict[str, str]:
    return _load_json("a_share_name_map.json")


INDUSTRY_CATALOG = load_industry_catalog()
COMPANY_CATALOG = load_company_catalog()
EVENT_BLUEPRINTS = load_event_blueprints()
HIGH_QUALITY_DEVELOPMENT_UNIVERSE = load_high_quality_development_universe()
A_SHARE_NAME_MAP = load_a_share_name_map()
