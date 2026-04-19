import pandas as pd

from iching_alpha.ganzhi_walkforward import build_walkforward_yearly, summarize_walkforward_results


def test_build_walkforward_yearly_uses_only_prior_years() -> None:
    frame = pd.DataFrame(
        [
            {"datetime": "2016-01-05", "month_ganzhi": "甲子", "solar_term": "立春", "ret_1d": 0.01, "fwd_ret_1d": 0.01, "fwd_open_return": 0.02},
            {"datetime": "2016-02-05", "month_ganzhi": "乙丑", "solar_term": "雨水", "ret_1d": -0.01, "fwd_ret_1d": -0.01, "fwd_open_return": -0.02},
            {"datetime": "2017-01-05", "month_ganzhi": "甲子", "solar_term": "立春", "ret_1d": 0.02, "fwd_ret_1d": 0.02, "fwd_open_return": 0.03},
            {"datetime": "2017-02-05", "month_ganzhi": "乙丑", "solar_term": "雨水", "ret_1d": -0.02, "fwd_ret_1d": -0.02, "fwd_open_return": -0.01},
            {"datetime": "2018-01-05", "month_ganzhi": "甲子", "solar_term": "立春", "ret_1d": 0.03, "fwd_ret_1d": 0.01, "fwd_open_return": 0.01},
            {"datetime": "2018-02-05", "month_ganzhi": "乙丑", "solar_term": "雨水", "ret_1d": -0.01, "fwd_ret_1d": -0.01, "fwd_open_return": -0.03},
        ]
    )
    frame["datetime"] = pd.to_datetime(frame["datetime"])

    yearly = build_walkforward_yearly(frame, level="stock", min_train_years=1)
    target_rows = yearly[(yearly["feature"] == "month_ganzhi") & (yearly["target"] == "fwd_ret_5d")]
    assert target_rows["test_year"].tolist() == [2017, 2018]
    assert target_rows["train_best_bucket"].tolist() == ["甲子", "甲子"]
    assert target_rows["train_worst_bucket"].tolist() == ["乙丑", "乙丑"]
    assert target_rows["test_spread"].tolist() == [0.04, 0.04]


def test_summarize_walkforward_results_reports_positive_ratio() -> None:
    yearly = pd.DataFrame(
        [
            {"level": "stock", "feature": "month_ganzhi", "target": "fwd_ret_5d", "test_year": 2017, "train_best_bucket": "甲子", "train_worst_bucket": "乙丑", "test_spread": 0.04, "test_best_excess": 0.02, "test_worst_excess": -0.02, "test_best_up_rate": 0.6, "test_worst_up_rate": 0.4},
            {"level": "stock", "feature": "month_ganzhi", "target": "fwd_ret_5d", "test_year": 2018, "train_best_bucket": "甲子", "train_worst_bucket": "乙丑", "test_spread": -0.01, "test_best_excess": 0.01, "test_worst_excess": 0.02, "test_best_up_rate": 0.55, "test_worst_up_rate": 0.45},
        ]
    )

    summary = summarize_walkforward_results(yearly)
    row = summary.iloc[0]
    assert row["n_years"] == 2
    assert row["expected_test_years"] == 2
    assert row["coverage_ratio"] == 1.0
    assert row["positive_spread_ratio"] == 0.5
    assert row["avg_test_spread"] == 0.015
    assert row["most_common_best_bucket"] == "甲子"
