"""Configuration loading."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path

import yaml


@dataclass(frozen=True)
class AppConfig:
    qlib_provider_uri: Path
    parquet_path: Path
    industry_mapping_path: Path
    industry_palace_map_path: Path
    artifacts_dir: Path
    universe: str
    start_date: str
    end_date: str
    rebalance_every: int
    hold_days: int
    cost_bps: float
    top_pct: float
    qimen_time: str
    qimen_pan_method: str
    qimen_top_palaces: int
    qimen_weighting: str
    qimen_filter_metric: str
    qimen_filter_allowed_bins: tuple[int, ...]
    qimen_filter_train_end: str
    qimen_filter_bin_count: int
    csi300_symbol: str
    initial_capital: float
    limit_move_threshold: float
    lookback_days: int
    repo_root: Path

    @classmethod
    def from_file(cls, path: str | Path) -> "AppConfig":
        config_path = Path(path).resolve()
        repo_root = config_path.parent.parent
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        def resolve(value: str) -> Path:
            candidate = Path(value)
            if candidate.is_absolute():
                return candidate
            return (repo_root / candidate).resolve()

        return cls(
            qlib_provider_uri=resolve(raw["qlib_provider_uri"]),
            parquet_path=resolve(raw["parquet_path"]),
            industry_mapping_path=resolve(raw["industry_mapping_path"]),
            industry_palace_map_path=resolve(raw["industry_palace_map_path"]),
            artifacts_dir=resolve(raw["artifacts_dir"]),
            universe=str(raw["universe"]),
            start_date=str(raw["start_date"]),
            end_date=str(raw["end_date"]),
            rebalance_every=int(raw["rebalance_every"]),
            hold_days=int(raw["hold_days"]),
            cost_bps=float(raw["cost_bps"]),
            top_pct=float(raw["top_pct"]),
            qimen_time=str(raw["qimen_time"]),
            qimen_pan_method=str(raw["qimen_pan_method"]),
            qimen_top_palaces=int(raw["qimen_top_palaces"]),
            qimen_weighting=str(raw["qimen_weighting"]),
            qimen_filter_metric=str(raw["qimen_filter_metric"]),
            qimen_filter_allowed_bins=tuple(int(v) for v in raw["qimen_filter_allowed_bins"]),
            qimen_filter_train_end=str(raw["qimen_filter_train_end"]),
            qimen_filter_bin_count=int(raw["qimen_filter_bin_count"]),
            csi300_symbol=str(raw["csi300_symbol"]).zfill(6),
            initial_capital=float(raw["initial_capital"]),
            limit_move_threshold=float(raw["limit_move_threshold"]),
            lookback_days=int(raw["lookback_days"]),
            repo_root=repo_root,
        )

    def with_overrides(self, **kwargs: object) -> "AppConfig":
        return replace(self, **kwargs)
