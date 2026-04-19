"""Run qimen portfolio-construction sweeps over saved artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .backtest import run_backtest
from .config import AppConfig
from .qimen_variants import build_qimen_selector


def scan_variants(artifact_dir: Path, config: AppConfig, top_values: list[int], weightings: list[str]) -> pd.DataFrame:
    scores = pd.read_parquet(artifact_dir / "daily_scores.parquet")
    scores["datetime"] = pd.to_datetime(scores["datetime"])
    backtest_market = scores[
        (scores["datetime"] >= pd.Timestamp(config.start_date))
        & (scores["datetime"] <= pd.Timestamp(config.end_date))
        & scores["industry"].notna()
    ].copy()
    backtest_dates = sorted(backtest_market["datetime"].drop_duplicates().tolist())
    rebalance_dates = set(backtest_dates[:: config.rebalance_every])
    signal_frame = backtest_market[
        backtest_market["datetime"].isin(rebalance_dates)
    ][["datetime", "symbol", "industry", "qimen_palace", "qimen_score", "fwd_open_return"]].dropna(subset=["qimen_score"])

    rows: list[dict[str, object]] = []
    for top_palaces in top_values:
        for weighting in weightings:
            result = run_backtest(
                name=f"qimen_top{top_palaces}_{weighting}",
                market=backtest_market,
                signal_frame=signal_frame,
                score_col="qimen_score",
                backtest_dates=backtest_dates,
                select_targets=build_qimen_selector(top_palaces, weighting),
                initial_capital=config.initial_capital,
                cost_bps=config.cost_bps,
            )
            rows.append(
                {
                    "variant": result.name,
                    "top_palaces": top_palaces,
                    "weighting": weighting,
                    "total_return": result.metrics["total_return"],
                    "annualized_return": result.metrics["annualized_return"],
                    "max_drawdown": result.metrics["max_drawdown"],
                    "turnover_ratio": result.metrics["turnover_ratio"],
                    "buy_failure_ratio": result.metrics["buy_failure_ratio"],
                    "sell_failure_ratio": result.metrics["sell_failure_ratio"],
                    "final_equity": result.metrics["final_equity"],
                }
            )
    report = pd.DataFrame(rows).sort_values("total_return", ascending=False).reset_index(drop=True)
    report.to_csv(artifact_dir / "qimen_variant_scan.csv", index=False)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Scan qimen portfolio-construction variants using saved artifacts.")
    parser.add_argument("--artifact-dir", required=True, help="Artifact directory containing daily_scores.parquet.")
    parser.add_argument("--config", required=True, help="Path to the YAML config file.")
    parser.add_argument("--top-palaces", nargs="+", type=int, default=[1, 2, 3], help="Top palace counts to test.")
    parser.add_argument(
        "--weightings",
        nargs="+",
        default=["stock", "industry", "palace"],
        choices=["stock", "industry", "palace"],
        help="Weighting modes to test.",
    )
    args = parser.parse_args()

    report = scan_variants(
        artifact_dir=Path(args.artifact_dir).resolve(),
        config=AppConfig.from_file(args.config),
        top_values=args.top_palaces,
        weightings=args.weightings,
    )
    print(report.to_string(index=False))


if __name__ == "__main__":
    main()
