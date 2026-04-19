"""Walk-forward validation for Ganzhi calendar buckets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from .config import AppConfig
from .ganzhi_analysis import TARGET_COLUMNS, prepare_industry_frame, prepare_stock_frame

WALKFORWARD_FEATURES = ["month_ganzhi", "solar_term"]


def build_walkforward_yearly(
    frame: pd.DataFrame,
    level: str,
    min_train_years: int = 3,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    working = frame.copy()
    working["year"] = pd.to_datetime(working["datetime"]).dt.year
    years = sorted(int(year) for year in working["year"].dropna().unique())

    for feature in WALKFORWARD_FEATURES:
        for target_name, column in TARGET_COLUMNS.items():
            feature_frame = working.dropna(subset=[feature, column]).copy()
            if feature_frame.empty:
                continue

            for test_year in years:
                train_years = [year for year in years if year < test_year]
                if len(train_years) < min_train_years:
                    continue

                train = feature_frame[feature_frame["year"].isin(train_years)]
                test = feature_frame[feature_frame["year"] == test_year]
                if train.empty or test.empty:
                    continue

                train_means = train.groupby(feature, observed=True)[column].mean().sort_values()
                if train_means.empty:
                    continue

                train_worst_bucket = str(train_means.index[0])
                train_best_bucket = str(train_means.index[-1])

                test_grouped = test.groupby(feature, observed=True)[column]
                test_means = test_grouped.mean()
                if train_best_bucket not in test_means.index or train_worst_bucket not in test_means.index:
                    continue

                benchmark_mean = float(test[column].mean())
                best_test_series = test.loc[test[feature] == train_best_bucket, column]
                worst_test_series = test.loc[test[feature] == train_worst_bucket, column]

                rows.append(
                    {
                        "level": level,
                        "feature": feature,
                        "target": target_name,
                        "test_year": test_year,
                        "train_year_start": min(train_years),
                        "train_year_end": max(train_years),
                        "train_best_bucket": train_best_bucket,
                        "train_worst_bucket": train_worst_bucket,
                        "train_best_mean": float(train_means.loc[train_best_bucket]),
                        "train_worst_mean": float(train_means.loc[train_worst_bucket]),
                        "train_spread": float(train_means.loc[train_best_bucket] - train_means.loc[train_worst_bucket]),
                        "test_best_mean": float(test_means.loc[train_best_bucket]),
                        "test_worst_mean": float(test_means.loc[train_worst_bucket]),
                        "test_spread": float(test_means.loc[train_best_bucket] - test_means.loc[train_worst_bucket]),
                        "test_best_count": int(best_test_series.shape[0]),
                        "test_worst_count": int(worst_test_series.shape[0]),
                        "test_best_up_rate": float((best_test_series > 0).mean()),
                        "test_worst_up_rate": float((worst_test_series > 0).mean()),
                        "benchmark_mean": benchmark_mean,
                        "test_best_excess": float(test_means.loc[train_best_bucket] - benchmark_mean),
                        "test_worst_excess": float(test_means.loc[train_worst_bucket] - benchmark_mean),
                    }
                )

    return pd.DataFrame(rows).sort_values(["level", "feature", "target", "test_year"]).reset_index(drop=True)


def summarize_walkforward_results(yearly: pd.DataFrame) -> pd.DataFrame:
    if yearly.empty:
        return pd.DataFrame(
            columns=[
                "level",
                "feature",
                "target",
                "n_years",
                "expected_test_years",
                "coverage_ratio",
                "year_range",
                "avg_test_spread",
                "median_test_spread",
                "positive_spread_ratio",
                "avg_test_best_excess",
                "avg_test_worst_excess",
                "avg_test_best_up_rate",
                "avg_test_worst_up_rate",
                "most_common_best_bucket",
                "most_common_worst_bucket",
            ]
        )

    rows: list[dict[str, object]] = []
    keys = ["level", "feature", "target"]
    expected_years = int(yearly["test_year"].nunique())
    for (level, feature, target), group in yearly.groupby(keys, observed=True):
        ordered = group.sort_values("test_year")
        best_mode = ordered["train_best_bucket"].mode()
        worst_mode = ordered["train_worst_bucket"].mode()
        rows.append(
            {
                "level": level,
                "feature": feature,
                "target": target,
                "n_years": int(len(ordered)),
                "expected_test_years": expected_years,
                "coverage_ratio": float(len(ordered) / expected_years),
                "year_range": f"{int(ordered['test_year'].min())}-{int(ordered['test_year'].max())}",
                "avg_test_spread": float(ordered["test_spread"].mean()),
                "median_test_spread": float(ordered["test_spread"].median()),
                "positive_spread_ratio": float((ordered["test_spread"] > 0).mean()),
                "avg_test_best_excess": float(ordered["test_best_excess"].mean()),
                "avg_test_worst_excess": float(ordered["test_worst_excess"].mean()),
                "avg_test_best_up_rate": float(ordered["test_best_up_rate"].mean()),
                "avg_test_worst_up_rate": float(ordered["test_worst_up_rate"].mean()),
                "most_common_best_bucket": None if best_mode.empty else str(best_mode.iloc[0]),
                "most_common_worst_bucket": None if worst_mode.empty else str(worst_mode.iloc[0]),
            }
        )

    return pd.DataFrame(rows).sort_values(
        ["coverage_ratio", "positive_spread_ratio", "avg_test_spread"],
        ascending=[False, False, False],
    ).reset_index(drop=True)


def run_walkforward_validation(config: AppConfig, min_train_years: int = 3) -> Path:
    stock_frame = prepare_stock_frame(config)
    industry_frame = prepare_industry_frame(stock_frame)

    stock_yearly = build_walkforward_yearly(stock_frame, level="stock", min_train_years=min_train_years)
    industry_yearly = build_walkforward_yearly(industry_frame, level="industry", min_train_years=min_train_years)
    yearly = pd.concat([stock_yearly, industry_yearly], ignore_index=True)
    summary = summarize_walkforward_results(yearly)

    run_id = pd.Timestamp.utcnow().strftime("%Y%m%d_%H%M%S")
    output_dir = config.artifacts_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    yearly.to_csv(output_dir / "ganzhi_walkforward_yearly.csv", index=False)
    summary.to_csv(output_dir / "ganzhi_walkforward_summary.csv", index=False)
    (output_dir / "ganzhi_walkforward_top10.json").write_text(
        json.dumps(summary.head(10).to_dict(orient="records"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def main() -> None:
    parser = argparse.ArgumentParser(description="Run walk-forward validation for Ganzhi calendar buckets.")
    parser.add_argument("--config", required=True, help="Path to the YAML config file.")
    parser.add_argument("--min-train-years", type=int, default=3, help="Minimum number of full prior years required.")
    args = parser.parse_args()

    output_dir = run_walkforward_validation(
        AppConfig.from_file(args.config),
        min_train_years=args.min_train_years,
    )
    print(f"Artifacts written to: {output_dir}")


if __name__ == "__main__":
    main()
