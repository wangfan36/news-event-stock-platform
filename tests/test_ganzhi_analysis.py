import pandas as pd

from iching_alpha.ganzhi_analysis import summarize_feature_edges


def test_summarize_feature_edges_uses_train_rank_and_test_spread() -> None:
    stats = pd.DataFrame(
        [
            {"level": "stock", "feature": "day_stem", "target": "fwd_ret_1d", "split": "train", "bucket": "甲", "count": 10, "mean_return": 0.03, "median_return": 0.02, "std_return": 0.1, "up_rate": 0.6, "t_stat": 1.0},
            {"level": "stock", "feature": "day_stem", "target": "fwd_ret_1d", "split": "train", "bucket": "乙", "count": 10, "mean_return": -0.01, "median_return": -0.01, "std_return": 0.1, "up_rate": 0.4, "t_stat": -0.3},
            {"level": "stock", "feature": "day_stem", "target": "fwd_ret_1d", "split": "test", "bucket": "甲", "count": 10, "mean_return": 0.02, "median_return": 0.01, "std_return": 0.1, "up_rate": 0.55, "t_stat": 0.7},
            {"level": "stock", "feature": "day_stem", "target": "fwd_ret_1d", "split": "test", "bucket": "乙", "count": 10, "mean_return": -0.03, "median_return": -0.02, "std_return": 0.1, "up_rate": 0.35, "t_stat": -1.1},
        ]
    )
    summary = summarize_feature_edges(stats)
    row = summary.iloc[0]
    assert row["train_best_bucket"] == "甲"
    assert row["train_worst_bucket"] == "乙"
    assert row["test_spread"] == 0.05

