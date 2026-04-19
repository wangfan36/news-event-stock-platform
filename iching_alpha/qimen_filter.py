"""Qimen market-filter strategy."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class MarketFilterResult:
    equity_curve: pd.DataFrame
    metrics: dict[str, object]
    yearly: pd.DataFrame
    regime_frame: pd.DataFrame


def build_market_regime(
    palace_scores: pd.DataFrame,
    metric: str,
    train_end: str,
    bin_count: int,
) -> pd.DataFrame:
    if metric not in {"top1", "spread"}:
        raise ValueError("metric must be one of: top1, spread")

    pivot = palace_scores.pivot(index="datetime", columns="qimen_palace", values="qimen_score").sort_index()
    regime = pd.DataFrame(index=pivot.index)
    regime["top1"] = pivot.max(axis=1)
    regime["spread"] = pivot.max(axis=1) - pivot.min(axis=1)

    train = regime[regime.index <= pd.Timestamp(train_end)][metric].dropna()
    quantiles = [i / bin_count for i in range(1, bin_count)]
    thresholds = sorted(set(train.quantile(quantiles).tolist()))
    bins = [-float("inf"), *thresholds, float("inf")]
    regime["metric"] = regime[metric]
    regime["bin"] = pd.cut(regime["metric"], bins=bins, labels=False, include_lowest=True)
    regime = regime.reset_index()
    regime["metric_name"] = metric
    return regime


def run_market_filter_strategy(
    benchmark_returns: pd.DataFrame,
    regime_frame: pd.DataFrame,
    allowed_bins: tuple[int, ...],
    initial_capital: float,
    strategy_name: str = "qimen_filter",
) -> MarketFilterResult:
    merged = benchmark_returns.merge(regime_frame[["datetime", "bin", "metric", "metric_name"]], on="datetime", how="left")
    merged = merged.sort_values("datetime").copy()
    merged["invested"] = merged["bin"].isin(allowed_bins)

    equity = initial_capital
    rows: list[dict[str, object]] = []
    for _, row in merged.iterrows():
        if bool(row["invested"]):
            equity *= 1 + float(row["filtered_equal_ret"])
        rows.append(
            {
                "datetime": row["datetime"],
                "strategy": strategy_name,
                "equity": equity,
                "daily_return": (float(row["filtered_equal_ret"]) if bool(row["invested"]) else 0.0),
                "turnover": 0.0,
                "invested": bool(row["invested"]),
                "qimen_filter_bin": row["bin"],
                "qimen_filter_metric": row["metric"],
            }
        )

    equity_curve = pd.DataFrame(rows)
    equity_curve["year"] = pd.to_datetime(equity_curve["datetime"]).dt.year
    yearly = (
        equity_curve.groupby("year", observed=True)["equity"]
        .agg(["first", "last"])
        .reset_index()
        .assign(strategy=strategy_name, return_=lambda df: df["last"] / df["first"] - 1)
        .rename(columns={"return_": "return"})
        [["strategy", "year", "return"]]
    )

    metrics = {
        "strategy": strategy_name,
        "initial_capital": initial_capital,
        "final_equity": float(equity_curve["equity"].iloc[-1]),
        "total_return": float(equity_curve["equity"].iloc[-1] / initial_capital - 1),
        "annualized_return": float((equity_curve["equity"].iloc[-1] / initial_capital) ** (252 / len(equity_curve)) - 1),
        "max_drawdown": float((equity_curve["equity"] / equity_curve["equity"].cummax() - 1).min()),
        "win_rate": float((equity_curve["daily_return"] > 0).mean()),
        "invested_ratio": float(equity_curve["invested"].mean()),
        "allowed_bins": list(allowed_bins),
        "metric_name": regime_frame["metric_name"].iloc[0] if not regime_frame.empty else None,
    }
    return MarketFilterResult(equity_curve=equity_curve, metrics=metrics, yearly=yearly, regime_frame=regime_frame)

