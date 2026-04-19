import pandas as pd

from iching_alpha.qimen_filter import build_market_regime, run_market_filter_strategy


def test_market_filter_regime_and_strategy() -> None:
    palace_scores = pd.DataFrame(
        [
            {"datetime": pd.Timestamp("2020-01-01"), "qimen_palace": "乾", "qimen_score": 1.0},
            {"datetime": pd.Timestamp("2020-01-01"), "qimen_palace": "坤", "qimen_score": 3.0},
            {"datetime": pd.Timestamp("2020-01-02"), "qimen_palace": "乾", "qimen_score": 5.0},
            {"datetime": pd.Timestamp("2020-01-02"), "qimen_palace": "坤", "qimen_score": 6.0},
        ]
    )
    regime = build_market_regime(palace_scores, metric="spread", train_end="2020-01-02", bin_count=2)
    benchmark_returns = pd.DataFrame(
        {
            "datetime": [pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-02")],
            "filtered_equal_ret": [0.1, -0.05],
        }
    )
    result = run_market_filter_strategy(
        benchmark_returns=benchmark_returns,
        regime_frame=regime,
        allowed_bins=(0,),
        initial_capital=100.0,
    )
    assert "invested_ratio" in result.metrics
    assert len(result.equity_curve) == 2

