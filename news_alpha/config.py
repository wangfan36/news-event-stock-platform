"""Portable application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "default.yaml"


@dataclass(frozen=True)
class AppConfig:
    """Runtime paths. Market data is optional so a fresh clone can run immediately."""

    repo_root: Path
    artifacts_dir: Path
    parquet_path: Path | None
    universe_path: Path | None
    price_override_path: Path

    @classmethod
    def from_file(cls, path: str | Path = DEFAULT_CONFIG_PATH) -> "AppConfig":
        config_path = Path(path).resolve()
        repo_root = config_path.parent.parent
        raw: dict[str, Any] = {}
        if config_path.exists():
            raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}

        market = raw.get("market_data", {}) or {}

        def resolve_optional(value: Any) -> Path | None:
            text = str(value or "").strip()
            if not text:
                return None
            candidate = Path(text).expanduser()
            return candidate if candidate.is_absolute() else (repo_root / candidate).resolve()

        artifacts_dir = resolve_optional(raw.get("artifacts_dir", "artifacts")) or (repo_root / "artifacts")
        override_path = resolve_optional(market.get("price_override_path", "artifacts/data/price_overrides.json"))
        return cls(
            repo_root=repo_root,
            artifacts_dir=artifacts_dir,
            parquet_path=resolve_optional(market.get("parquet_path")),
            universe_path=resolve_optional(market.get("universe_path")),
            price_override_path=override_path or (artifacts_dir / "data" / "price_overrides.json"),
        )


@lru_cache(maxsize=1)
def get_app_config() -> AppConfig:
    configured = os.getenv("NEWS_ALPHA_CONFIG", "").strip()
    if configured:
        return AppConfig.from_file(configured)
    local_path = REPO_ROOT / "config" / "local.yaml"
    return AppConfig.from_file(local_path if local_path.exists() else DEFAULT_CONFIG_PATH)
