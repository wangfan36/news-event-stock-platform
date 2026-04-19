"""CLI entrypoint for the prototype."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from .backtest import compute_benchmarks, compute_signal_diagnostics, run_backtest
from .calendar_features import build_calendar_features
from .config import AppConfig
from .data import load_market_bundle
from .iching import build_iching_scores
from .qimen_filter import build_market_regime, run_market_filter_strategy
from .qimen import build_qimen_scores, load_industry_palace_map
from .qimen_variants import build_qimen_selector


def _select_iching_targets(signal_date: pd.Timestamp, signal_rows: pd.DataFrame, top_pct: float) -> list[str]:
    frame = signal_rows.dropna(subset=["iching_score"]).sort_values("iching_score", ascending=False)
    if frame.empty:
        return []
    top_n = max(1, int(len(frame) * top_pct))
    return frame.head(top_n)["symbol"].tolist()

def _attach_benchmark_metrics(metrics: dict[str, object], strategy_curve: pd.DataFrame, benchmarks: pd.DataFrame) -> None:
    merged = strategy_curve.merge(benchmarks, on="datetime", how="left")
    if merged.empty:
        return
    metrics["benchmark_filtered_equal_total_return"] = float(merged["filtered_equal_equity"].iloc[-1] - 1)
    metrics["benchmark_csi300_total_return"] = float(merged["csi300_equity"].iloc[-1] - 1)
    metrics["excess_vs_filtered_equal"] = float(metrics["total_return"] - metrics["benchmark_filtered_equal_total_return"])
    metrics["excess_vs_csi300"] = float(metrics["total_return"] - metrics["benchmark_csi300_total_return"])

    sample = merged[merged["datetime"] >= pd.Timestamp("2023-01-01")]
    if not sample.empty:
        strategy_base = sample["equity"].iloc[0]
        benchmark_base = sample["filtered_equal_equity"].iloc[0]
        strategy_oos = sample["equity"].iloc[-1] / strategy_base - 1 if strategy_base else float("nan")
        benchmark_oos = sample["filtered_equal_equity"].iloc[-1] / benchmark_base - 1 if benchmark_base else float("nan")
        metrics["validation_conclusion"] = (
            "当前规则映射未被验证"
            if pd.notna(strategy_oos) and pd.notna(benchmark_oos) and strategy_oos < benchmark_oos
            else "样本外相对基准未失效"
        )


def _rebalance_dates(backtest_dates: list[pd.Timestamp], step: int) -> set[pd.Timestamp]:
    return set(backtest_dates[::step])


def _write_outputs(
    output_dir: Path,
    all_scores: pd.DataFrame,
    portfolio_curves: list[pd.DataFrame],
    yearly_frames: list[pd.DataFrame],
    metrics_by_name: dict[str, dict[str, object]],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    all_scores.to_parquet(output_dir / "daily_scores.parquet", index=False)
    pd.concat(portfolio_curves, ignore_index=True).to_csv(output_dir / "portfolio_returns.csv", index=False)
    pd.concat(yearly_frames, ignore_index=True).to_csv(output_dir / "yearly_report.csv", index=False)
    for name, metrics in metrics_by_name.items():
        (output_dir / f"{name}_metrics.json").write_text(
            json.dumps(metrics, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )


def run_pipeline(config: AppConfig, signal_mode: str) -> Path:
    bundle = load_market_bundle(config)
    calendar_features = build_calendar_features(bundle.backtest_dates)
    market = bundle.market.merge(calendar_features, on="datetime", how="left")

    all_scores = market.copy()
    palace_scores = pd.DataFrame()

    if signal_mode in {"iching", "both"}:
        iching_scores = build_iching_scores(market, calendar_features)
        all_scores = all_scores.merge(
            iching_scores[
                [
                    "datetime",
                    "symbol",
                    "hexagram_id",
                    "changed_hexagram_id",
                    "moving_line_count",
                    "iching_score",
                ]
            ],
            on=["datetime", "symbol"],
            how="left",
        )
    else:
        all_scores["hexagram_id"] = pd.NA
        all_scores["changed_hexagram_id"] = pd.NA
        all_scores["moving_line_count"] = pd.NA
        all_scores["iching_score"] = pd.NA

    if signal_mode in {"qimen", "both", "qimen-filter"}:
        industry_palace_map = load_industry_palace_map(config.industry_palace_map_path)
        palace_scores, qimen_scores = build_qimen_scores(
            bundle.backtest_dates,
            market[market["industry"].notna()][["symbol", "industry"]].drop_duplicates(),
            industry_palace_map,
            config.qimen_time,
        )
        all_scores = all_scores.merge(
            qimen_scores[
                [
                    "datetime",
                    "symbol",
                    "qimen_palace",
                    "qimen_gate",
                    "qimen_star",
                    "qimen_god",
                    "qimen_sky_stem",
                    "qimen_earth_stem",
                    "qimen_changsheng",
                    "qimen_zhifu_palace",
                    "qimen_zhishi_palace",
                    "qimen_score",
                ]
            ],
            on=["datetime", "symbol"],
            how="left",
        )
    else:
        for column in [
            "qimen_palace",
            "qimen_gate",
            "qimen_star",
            "qimen_god",
            "qimen_sky_stem",
            "qimen_earth_stem",
            "qimen_changsheng",
            "qimen_zhifu_palace",
            "qimen_zhishi_palace",
            "qimen_score",
        ]:
            all_scores[column] = pd.NA

    backtest_market = all_scores[
        (all_scores["datetime"] >= pd.Timestamp(config.start_date))
        & (all_scores["datetime"] <= pd.Timestamp(config.end_date))
        & all_scores["symbol"].isin(bundle.universe_symbols)
    ].copy()
    backtest_dates = [date for date in bundle.backtest_dates if pd.Timestamp(config.start_date) <= date <= pd.Timestamp(config.end_date)]
    rebalance_dates = _rebalance_dates(backtest_dates, config.rebalance_every)
    benchmarks = compute_benchmarks(
        market[
            (market["datetime"] >= pd.Timestamp(config.start_date))
            & (market["datetime"] <= pd.Timestamp(config.end_date))
        ].copy(),
        backtest_dates,
    )

    results = []
    metrics_by_name: dict[str, dict[str, object]] = {}
    if signal_mode in {"iching", "both"}:
        iching_signal_frame = backtest_market[
            backtest_market["datetime"].isin(rebalance_dates)
        ][["datetime", "symbol", "iching_score", "fwd_open_return"]].dropna(subset=["iching_score"])
        iching_result = run_backtest(
            name="iching",
            market=backtest_market,
            signal_frame=iching_signal_frame,
            score_col="iching_score",
            backtest_dates=backtest_dates,
            select_targets=lambda date, frame: _select_iching_targets(date, frame, config.top_pct),
            initial_capital=config.initial_capital,
            cost_bps=config.cost_bps,
        )
        diagnostics = compute_signal_diagnostics(iching_signal_frame, "iching_score")
        iching_result.metrics.update(diagnostics)
        _attach_benchmark_metrics(iching_result.metrics, iching_result.equity_curve, benchmarks)
        results.append(iching_result)
        metrics_by_name["iching"] = iching_result.metrics

    if signal_mode in {"qimen", "both"}:
        qimen_signal_frame = backtest_market[
            backtest_market["datetime"].isin(rebalance_dates)
        ][["datetime", "symbol", "industry", "qimen_palace", "qimen_score", "fwd_open_return"]].dropna(subset=["qimen_score"])
        qimen_result = run_backtest(
            name="qimen",
            market=backtest_market,
            signal_frame=qimen_signal_frame,
            score_col="qimen_score",
            backtest_dates=backtest_dates,
            select_targets=build_qimen_selector(
                top_palaces=config.qimen_top_palaces,
                weighting=config.qimen_weighting,
            ),
            initial_capital=config.initial_capital,
            cost_bps=config.cost_bps,
        )
        diagnostics = compute_signal_diagnostics(qimen_signal_frame, "qimen_score")
        qimen_result.metrics.update(diagnostics)
        _attach_benchmark_metrics(qimen_result.metrics, qimen_result.equity_curve, benchmarks)
        results.append(qimen_result)
        metrics_by_name["qimen"] = qimen_result.metrics

    if signal_mode == "qimen-filter":
        regime_frame = build_market_regime(
            palace_scores=palace_scores,
            metric=config.qimen_filter_metric,
            train_end=config.qimen_filter_train_end,
            bin_count=config.qimen_filter_bin_count,
        )
        qimen_filter_result = run_market_filter_strategy(
            benchmark_returns=benchmarks[["datetime", "filtered_equal_ret"]].copy(),
            regime_frame=regime_frame,
            allowed_bins=config.qimen_filter_allowed_bins,
            initial_capital=config.initial_capital,
            strategy_name="qimen_filter",
        )
        qimen_filter_result.metrics["benchmark_filtered_equal_total_return"] = float(benchmarks["filtered_equal_equity"].iloc[-1] - 1)
        qimen_filter_result.metrics["benchmark_csi300_total_return"] = float(benchmarks["csi300_equity"].iloc[-1] - 1)
        qimen_filter_result.metrics["excess_vs_filtered_equal"] = float(
            qimen_filter_result.metrics["total_return"] - qimen_filter_result.metrics["benchmark_filtered_equal_total_return"]
        )
        qimen_filter_result.metrics["excess_vs_csi300"] = float(
            qimen_filter_result.metrics["total_return"] - qimen_filter_result.metrics["benchmark_csi300_total_return"]
        )
        sample = qimen_filter_result.equity_curve[qimen_filter_result.equity_curve["datetime"] >= pd.Timestamp("2023-01-01")]
        if not sample.empty:
            strategy_oos = sample["equity"].iloc[-1] / sample["equity"].iloc[0] - 1 if sample["equity"].iloc[0] else float("nan")
            benchmark_oos = (
                benchmarks.loc[benchmarks["datetime"] >= pd.Timestamp("2023-01-01"), "filtered_equal_equity"].iloc[-1]
                / benchmarks.loc[benchmarks["datetime"] >= pd.Timestamp("2023-01-01"), "filtered_equal_equity"].iloc[0]
                - 1
            )
            qimen_filter_result.metrics["validation_conclusion"] = (
                "样本外相对基准未失效" if strategy_oos > benchmark_oos else "当前规则映射未被验证"
            )
        results.append(
            SimpleNamespace(
                name="qimen_filter",
                equity_curve=qimen_filter_result.equity_curve,
                metrics=qimen_filter_result.metrics,
                yearly=qimen_filter_result.yearly,
            )
        )
        metrics_by_name["qimen_filter"] = qimen_filter_result.metrics

    run_id = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    output_dir = config.artifacts_dir / run_id
    yearly_frames = [result.yearly for result in results]

    benchmark_years = []
    for strategy_col, strategy_name in [("filtered_equal_equity", "filtered_equal"), ("csi300_equity", "csi300")]:
        for year, group in benchmarks.groupby(benchmarks["datetime"].dt.year, observed=True):
            benchmark_years.append(
                {
                    "strategy": strategy_name,
                    "year": int(year),
                    "return": float(group[strategy_col].iloc[-1] / group[strategy_col].iloc[0] - 1)
                    if group[strategy_col].iloc[0]
                    else None,
                }
            )
    yearly_frames.append(pd.DataFrame(benchmark_years))

    portfolio_frames = [result.equity_curve for result in results]
    portfolio_frames.append(
        benchmarks[
            [
                "datetime",
                "filtered_equal_equity",
                "csi300_equity",
            ]
        ]
        .rename(
            columns={
                "filtered_equal_equity": "filtered_equal",
                "csi300_equity": "csi300",
            }
        )
        .melt(id_vars="datetime", var_name="strategy", value_name="equity")
        .assign(
            daily_return=lambda df: df.groupby("strategy", observed=True)["equity"].pct_change().fillna(0.0),
            turnover=0.0,
        )
    )
    _write_outputs(output_dir, all_scores, portfolio_frames, yearly_frames, metrics_by_name)
    if not palace_scores.empty:
        palace_scores.to_csv(output_dir / "qimen_palace_scores.csv", index=False)
    if signal_mode == "qimen-filter":
        regime_frame.to_csv(output_dir / "qimen_filter_regime.csv", index=False)
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the I Ching and Qimen stock-selection prototype.")
    parser.add_argument("--config", required=True, help="Path to the YAML config file.")
    parser.add_argument(
        "--signal-mode",
        required=True,
        choices=["iching", "qimen", "both", "qimen-filter"],
        help="Which signal head to run.",
    )
    args = parser.parse_args()

    config = AppConfig.from_file(args.config)
    output_dir = run_pipeline(config, args.signal_mode)
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
