"""Compare pure-Qimen usage patterns on a saved artifact set."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from .backtest import run_backtest
from .config import AppConfig
from .qimen_filter import build_market_regime, run_market_filter_strategy
from .qimen_variants import build_qimen_selector


def _load_artifact_scores(artifact_dir: Path, config: AppConfig) -> tuple[pd.DataFrame, list[pd.Timestamp]]:
    scores = pd.read_parquet(artifact_dir / "daily_scores.parquet")
    scores["datetime"] = pd.to_datetime(scores["datetime"])
    scores = scores[
        (scores["datetime"] >= pd.Timestamp(config.start_date))
        & (scores["datetime"] <= pd.Timestamp(config.end_date))
        & scores["industry"].notna()
    ].copy()
    backtest_dates = sorted(scores["datetime"].drop_duplicates().tolist())
    return scores, backtest_dates


def _build_filtered_equal_returns(scores: pd.DataFrame, backtest_dates: list[pd.Timestamp]) -> pd.DataFrame:
    frame = scores.sort_values(["symbol", "datetime"]).copy()
    prev_close = frame.groupby("symbol", observed=True)["close"].shift(1)
    valid = frame["close"].gt(0) & prev_close.gt(0)
    frame["filtered_equal_ret"] = np.where(valid, frame["close"] / prev_close - 1, np.nan)
    bench = (
        frame.groupby("datetime", observed=True)["filtered_equal_ret"]
        .mean()
        .reindex(backtest_dates)
        .fillna(0.0)
        .reset_index()
    )
    return bench


def scan_usage_modes(artifact_dir: Path, config: AppConfig) -> pd.DataFrame:
    scores, backtest_dates = _load_artifact_scores(artifact_dir, config)
    rebalance_dates = set(backtest_dates[:: config.rebalance_every])
    signal_frame = scores[
        scores["datetime"].isin(rebalance_dates)
    ][["datetime", "symbol", "industry", "qimen_palace", "qimen_score", "fwd_open_return"]].dropna(subset=["qimen_score"])
    benchmark_returns = _build_filtered_equal_returns(scores, backtest_dates)

    rows: list[dict[str, object]] = []

    for direction in ["top", "bottom"]:
        for top_palaces in [1, 2, 3]:
            result = run_backtest(
                name=f"selector_{direction}_{top_palaces}",
                market=scores,
                signal_frame=signal_frame,
                score_col="qimen_score",
                backtest_dates=backtest_dates,
                select_targets=build_qimen_selector(top_palaces=top_palaces, weighting="industry", direction=direction),
                initial_capital=config.initial_capital,
                cost_bps=config.cost_bps,
            )
            rows.append(
                {
                    "usage_type": "selector",
                    "variant": result.name,
                    "total_return": result.metrics["total_return"],
                    "annualized_return": result.metrics["annualized_return"],
                    "max_drawdown": result.metrics["max_drawdown"],
                    "final_equity": result.metrics["final_equity"],
                }
            )

    filter_specs = [
        ("spread", (0, 1)),
        ("spread", (0,)),
        ("top1", (3, 4)),
        ("top1", (4,)),
    ]
    for metric, allowed_bins in filter_specs:
        regime = build_market_regime(
            palace_scores=scores[["datetime", "qimen_palace", "qimen_score"]].dropna().drop_duplicates(),
            metric=metric,
            train_end=config.qimen_filter_train_end,
            bin_count=config.qimen_filter_bin_count,
        )
        result = run_market_filter_strategy(
            benchmark_returns=benchmark_returns,
            regime_frame=regime,
            allowed_bins=allowed_bins,
            initial_capital=config.initial_capital,
            strategy_name=f"filter_{metric}_{'-'.join(map(str, allowed_bins))}",
        )
        rows.append(
            {
                "usage_type": "filter",
                "variant": result.metrics["strategy"],
                "total_return": result.metrics["total_return"],
                "annualized_return": result.metrics["annualized_return"],
                "max_drawdown": result.metrics["max_drawdown"],
                "final_equity": result.metrics["final_equity"],
                "invested_ratio": result.metrics["invested_ratio"],
            }
        )

    report = pd.DataFrame(rows).sort_values("total_return", ascending=False).reset_index(drop=True)
    report.to_csv(artifact_dir / "qimen_usage_scan.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan pure-Qimen usage modes over saved artifacts.")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory containing daily_scores.parquet.")
    parser.add_argument("--config", required=True, help="Path to the YAML config file.")
    args = parser.parse_args()

    report = scan_usage_modes(Path(args.artifact_dir).resolve(), AppConfig.from_file(args.config))
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
