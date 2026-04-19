import pandas as pd

from iching_alpha.backtest import run_backtest


def test_strategy_backtests_are_isolated() -> None:
    dates = list(pd.date_range("2024-01-01", periods=8, freq="B"))
    market = pd.DataFrame(
        [
            {
                "datetime": date,
                "symbol": symbol,
                "open": 10 + i + j,
                "close": 10.5 + i + j,
                "high": 11 + i + j,
                "low": 9.5 + i + j,
                "volume": 1000,
                "can_buy": True,
                "can_sell": True,
                "industry": "电子",
            }
            for i, date in enumerate(dates)
            for j, symbol in enumerate(["000001", "000002"])
        ]
    )
    signal_frame = pd.DataFrame(
        [
            {"datetime": dates[0], "symbol": "000001", "score": 2.0, "fwd_open_return": 0.05},
            {"datetime": dates[0], "symbol": "000002", "score": 1.0, "fwd_open_return": 0.01},
            {"datetime": dates[5], "symbol": "000001", "score": 1.0, "fwd_open_return": 0.02},
            {"datetime": dates[5], "symbol": "000002", "score": 2.0, "fwd_open_return": 0.03},
        ]
    )

    strategy_a = run_backtest(
        name="a",
        market=market,
        signal_frame=signal_frame,
        score_col="score",
        backtest_dates=dates,
        select_targets=lambda date, frame: ["000001"],
        initial_capital=1000,
        cost_bps=30,
    )
    strategy_b = run_backtest(
        name="b",
        market=market,
        signal_frame=signal_frame,
        score_col="score",
        backtest_dates=dates,
        select_targets=lambda date, frame: ["000002"],
        initial_capital=1000,
        cost_bps=30,
    )

    assert strategy_a.name != strategy_b.name
    assert not strategy_a.equity_curve.equals(strategy_b.equity_curve)


def test_backtest_respects_weighted_targets() -> None:
    dates = list(pd.date_range("2024-01-01", periods=4, freq="B"))
    market = pd.DataFrame(
        [
            {
                "datetime": date,
                "symbol": symbol,
                "open": 10.0 if symbol == "000001" else 20.0,
                "close": 10.0 if symbol == "000001" else 20.0,
                "high": 10.0 if symbol == "000001" else 20.0,
                "low": 10.0 if symbol == "000001" else 20.0,
                "volume": 1000,
                "can_buy": True,
                "can_sell": True,
                "industry": "电子",
            }
            for date in dates
            for symbol in ["000001", "000002"]
        ]
    )
    signal_frame = pd.DataFrame(
        [
            {"datetime": dates[0], "symbol": "000001", "score": 2.0, "fwd_open_return": 0.0},
            {"datetime": dates[0], "symbol": "000002", "score": 1.0, "fwd_open_return": 0.0},
        ]
    )
    result = run_backtest(
        name="weighted",
        market=market,
        signal_frame=signal_frame,
        score_col="score",
        backtest_dates=dates,
        select_targets=lambda date, frame: {"000001": 0.75, "000002": 0.25},
        initial_capital=1000,
        cost_bps=0,
    )

    first_trade_equity = result.equity_curve.loc[result.equity_curve["datetime"] == dates[1], "equity"].iloc[0]
    assert first_trade_equity == 1000
