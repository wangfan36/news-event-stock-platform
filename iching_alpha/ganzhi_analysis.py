"""Explore stock and industry return patterns against Ganzhi calendar features."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .calendar_features import build_calendar_features
from .config import AppConfig
from .data import load_market_bundle

CALENDAR_FEATURES = ["day_stem", "day_branch", "day_ganzhi", "month_ganzhi", "solar_term"]
TARGET_COLUMNS = {
    "same_day_ret_1d": "ret_1d",
    "fwd_ret_1d": "fwd_ret_1d",
    "fwd_ret_5d": "fwd_open_return",
}


def prepare_stock_frame(config: AppConfig) -> pd.DataFrame:
    bundle = load_market_bundle(config)
    calendar = build_calendar_features(bundle.backtest_dates)
    market = bundle.market.merge(calendar, on="datetime", how="left")
    market = market[
        (market["datetime"] >= pd.Timestamp(config.start_date))
        & (market["datetime"] <= pd.Timestamp(config.end_date))
        & market["industry"].notna()
        & market["symbol"].isin(bundle.universe_symbols)
    ].copy()
    market["fwd_ret_1d"] = market.groupby("symbol", observed=True)["ret_1d"].shift(-1)
    return market


def prepare_industry_frame(stock_frame: pd.DataFrame) -> pd.DataFrame:
    group_cols = ["datetime", "industry", *CALENDAR_FEATURES]
    agg = (
        stock_frame.groupby(group_cols, observed=True)[list(TARGET_COLUMNS.values())]
        .mean()
        .reset_index()
    )
    return agg


def _split_label(date: pd.Timestamp) -> str:
    return "train" if date <= pd.Timestamp("2022-12-31") else "test"


def _calc_t_stat(values: pd.Series) -> float | None:
    clean = values.dropna()
    if len(clean) < 2:
        return None
    std = clean.std(ddof=1)
    if pd.isna(std) or std == 0:
        return None
    return float(clean.mean() / (std / np.sqrt(len(clean))))


def compute_group_stats(frame: pd.DataFrame, level: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    working = frame.copy()
    working["split"] = working["datetime"].map(_split_label)

    for feature in CALENDAR_FEATURES:
        for target_name, column in TARGET_COLUMNS.items():
            for split, split_frame in working.groupby("split", observed=True):
                grouped = split_frame.groupby(feature, observed=True)[column]
                for bucket, values in grouped:
                    clean = values.dropna()
                    if clean.empty:
                        continue
                    rows.append(
                        {
                            "level": level,
                            "feature": feature,
                            "target": target_name,
                            "split": split,
                            "bucket": bucket,
                            "count": int(clean.shape[0]),
                            "mean_return": float(clean.mean()),
                            "median_return": float(clean.median()),
                            "std_return": float(clean.std(ddof=0)),
                            "up_rate": float((clean > 0).mean()),
                            "t_stat": _calc_t_stat(clean),
                        }
                    )
    return pd.DataFrame(rows)


def summarize_feature_edges(group_stats: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    keys = ["level", "feature", "target"]
    for (level, feature, target), feature_frame in group_stats.groupby(keys, observed=True):
        train = feature_frame[feature_frame["split"] == "train"].copy()
        test = feature_frame[feature_frame["split"] == "test"].copy()
        if train.empty or test.empty:
            continue

        best_train = train.sort_values("mean_return", ascending=False).iloc[0]
        worst_train = train.sort_values("mean_return", ascending=True).iloc[0]
        test_map = test.set_index("bucket")
        best_bucket = best_train["bucket"]
        worst_bucket = worst_train["bucket"]

        if best_bucket not in test_map.index or worst_bucket not in test_map.index:
            continue

        best_test = test_map.loc[best_bucket]
        worst_test = test_map.loc[worst_bucket]
        rows.append(
            {
                "level": level,
                "feature": feature,
                "target": target,
                "train_best_bucket": best_bucket,
                "train_best_mean": float(best_train["mean_return"]),
                "test_best_mean": float(best_test["mean_return"]),
                "train_worst_bucket": worst_bucket,
                "train_worst_mean": float(worst_train["mean_return"]),
                "test_worst_mean": float(worst_test["mean_return"]),
                "test_spread": float(best_test["mean_return"] - worst_test["mean_return"]),
                "test_best_up_rate": float(best_test["up_rate"]),
                "test_worst_up_rate": float(worst_test["up_rate"]),
            }
        )
    return pd.DataFrame(rows).sort_values("test_spread", ascending=False).reset_index(drop=True)


def run_analysis(config: AppConfig) -> Path:
    stock_frame = prepare_stock_frame(config)
    industry_frame = prepare_industry_frame(stock_frame)

    stock_stats = compute_group_stats(stock_frame, level="stock")
    industry_stats = compute_group_stats(industry_frame, level="industry")
    group_stats = pd.concat([stock_stats, industry_stats], ignore_index=True)
    summary = summarize_feature_edges(group_stats)

    run_id = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    output_dir = config.artifacts_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    stock_stats.to_csv(output_dir / "ganzhi_stock_group_stats.csv", index=False)
    industry_stats.to_csv(output_dir / "ganzhi_industry_group_stats.csv", index=False)
    summary.to_csv(output_dir / "ganzhi_feature_summary.csv", index=False)

    top_summary = summary.head(20).to_dict(orient="records")
    (output_dir / "ganzhi_summary_top20.json").write_text(
        json.dumps(top_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze stock and industry returns by Ganzhi calendar features.")
    parser.add_argument("--config", required=True, help="Path to the YAML config file.")
    args = parser.parse_args()

    output_dir = run_analysis(AppConfig.from_file(args.config))
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
