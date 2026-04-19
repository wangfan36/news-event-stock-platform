"""Signal diagnostics and portfolio simulation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd


@dataclass
class StrategyResult:
    name: str
    equity_curve: pd.DataFrame
    metrics: dict[str, object]
    yearly: pd.DataFrame


def select_signal_dates(
    available_dates: list[pd.Timestamp],
    scored_dates: pd.Series,
    step: int,
) -> list[pd.Timestamp]:
    scored_set = set(pd.to_datetime(scored_dates.unique()))
    signal_dates = [date for date in available_dates if date in scored_set]
    return signal_dates[::step]


def compute_signal_diagnostics(signal_frame: pd.DataFrame, score_col: str) -> dict[str, object]:
    rows: list[dict[str, object]] = []
    for date, group in signal_frame.groupby("datetime", observed=True):
        group = group.dropna(subset=[score_col, "fwd_open_return"])
        if len(group) < 10:
            continue
        ic = group[score_col].rank().corr(group["fwd_open_return"].rank(), method="pearson")
        bins = min(5, group[score_col].nunique())
        quantile_returns: dict[str, float] = {}
        if bins >= 2:
            bucketed = group.assign(
                quantile=pd.qcut(group[score_col], q=bins, labels=False, duplicates="drop")
            )
            quantile_returns = {
                f"q{int(quantile) + 1}": float(values["fwd_open_return"].mean())
                for quantile, values in bucketed.groupby("quantile", observed=True)
            }
        rows.append(
            {
                "datetime": date,
                "rank_ic": float(ic) if pd.notna(ic) else np.nan,
                "quantile_returns": quantile_returns,
            }
        )

    if not rows:
        return {
            "rank_ic_mean": None,
            "rank_ic_std": None,
            "icir": None,
            "quantile_returns": {},
        }

    diag_df = pd.DataFrame(rows)
    rank_ic = diag_df["rank_ic"].dropna()
    quantile_summary: dict[str, list[float]] = {}
    for record in diag_df["quantile_returns"]:
        for quantile, value in record.items():
            quantile_summary.setdefault(quantile, []).append(value)

    return {
        "rank_ic_mean": float(rank_ic.mean()) if not rank_ic.empty else None,
        "rank_ic_std": float(rank_ic.std(ddof=0)) if not rank_ic.empty else None,
        "icir": float(rank_ic.mean() / rank_ic.std(ddof=0)) if len(rank_ic) > 1 and rank_ic.std(ddof=0) else None,
        "quantile_returns": {
            quantile: float(np.mean(values))
            for quantile, values in sorted(quantile_summary.items())
        },
    }


def annualized_return(equity: pd.Series) -> float | None:
    if len(equity) < 2 or equity.iloc[0] <= 0:
        return None
    total_return = equity.iloc[-1] / equity.iloc[0] - 1
    years = len(equity) / 252.0
    if years <= 0:
        return None
    return float((1 + total_return) ** (1 / years) - 1)


def max_drawdown(equity: pd.Series) -> float | None:
    if equity.empty:
        return None
    running_max = equity.cummax()
    drawdown = equity / running_max - 1
    return float(drawdown.min())


def compute_yearly_returns(equity_curve: pd.DataFrame, strategy_name: str) -> pd.DataFrame:
    df = equity_curve.copy()
    df["year"] = pd.to_datetime(df["datetime"]).dt.year
    rows: list[dict[str, object]] = []
    for year, group in df.groupby("year", observed=True):
        start_equity = group["equity"].iloc[0]
        end_equity = group["equity"].iloc[-1]
        rows.append(
            {
                "strategy": strategy_name,
                "year": int(year),
                "return": float(end_equity / start_equity - 1) if start_equity else None,
            }
        )
    return pd.DataFrame(rows)


def compute_benchmarks(market: pd.DataFrame, backtest_dates: list[pd.Timestamp]) -> pd.DataFrame:
    date_frame = pd.DataFrame({"datetime": backtest_dates})
    stock_rows = market[market["industry"].notna()].copy()
    stock_rows = stock_rows.sort_values(["symbol", "datetime"])
    prev_close = stock_rows.groupby("symbol", observed=True)["close"].shift(1)
    valid_ret = stock_rows["close"].gt(0) & prev_close.gt(0)
    stock_rows["daily_ret"] = np.where(valid_ret, stock_rows["close"] / prev_close - 1, np.nan)
    equal_weight = (
        stock_rows.groupby("datetime", observed=True)["daily_ret"].mean().rename("filtered_equal_ret").reset_index()
    )

    index_rows = market[market["symbol"] == "000300"].copy()
    index_rows = index_rows.sort_values("datetime")
    prev_index_close = index_rows["close"].shift(1)
    valid_index = index_rows["close"].gt(0) & prev_index_close.gt(0)
    index_rows["csi300_ret"] = np.where(valid_index, index_rows["close"] / prev_index_close - 1, np.nan)
    csi300 = index_rows[["datetime", "csi300_ret"]]

    benchmarks = date_frame.merge(equal_weight, on="datetime", how="left").merge(csi300, on="datetime", how="left")
    benchmarks[["filtered_equal_ret", "csi300_ret"]] = benchmarks[["filtered_equal_ret", "csi300_ret"]].fillna(0.0)
    benchmarks["filtered_equal_equity"] = (1 + benchmarks["filtered_equal_ret"]).cumprod()
    benchmarks["csi300_equity"] = (1 + benchmarks["csi300_ret"]).cumprod()
    return benchmarks


def _build_trade_schedule(signal_dates: list[pd.Timestamp], backtest_dates: list[pd.Timestamp]) -> dict[pd.Timestamp, pd.Timestamp]:
    trade_schedule: dict[pd.Timestamp, pd.Timestamp] = {}
    calendar_index = {date: index for index, date in enumerate(backtest_dates)}
    for signal_date in signal_dates:
        idx = calendar_index.get(signal_date)
        if idx is None or idx + 1 >= len(backtest_dates):
            continue
        trade_schedule[backtest_dates[idx + 1]] = signal_date
    return trade_schedule


def _normalize_target_weights(targets: list[str] | dict[str, float]) -> dict[str, float]:
    if isinstance(targets, dict):
        clean = {symbol: float(weight) for symbol, weight in targets.items() if weight and weight > 0}
    else:
        unique = list(dict.fromkeys(targets))
        clean = {symbol: 1.0 for symbol in unique}
    total = sum(clean.values())
    if total <= 0:
        return {}
    return {symbol: weight / total for symbol, weight in clean.items()}


def run_backtest(
    name: str,
    market: pd.DataFrame,
    signal_frame: pd.DataFrame,
    score_col: str,
    backtest_dates: list[pd.Timestamp],
    select_targets: Callable[[pd.Timestamp, pd.DataFrame], list[str] | dict[str, float]],
    initial_capital: float,
    cost_bps: float,
) -> StrategyResult:
    cost_rate = cost_bps / 10000.0
    market = market.sort_values(["datetime", "symbol"]).copy()
    market_by_date = {
        date: frame.set_index("symbol", drop=False)
        for date, frame in market.groupby("datetime", observed=True)
    }
    signal_dates = select_signal_dates(backtest_dates, signal_frame["datetime"], step=1)
    trade_schedule = _build_trade_schedule(signal_dates, backtest_dates)

    cash = initial_capital
    positions: dict[str, float] = {}
    pending_exit: set[str] = set()
    last_close: dict[str, float] = {}
    buy_attempts = buy_failures = sell_attempts = sell_failures = 0
    turnover_sum = 0.0
    daily_rows: list[dict[str, object]] = []

    signals_by_date = {
        date: frame.copy()
        for date, frame in signal_frame.groupby("datetime", observed=True)
    }

    for date in backtest_dates:
        day_frame = market_by_date.get(date)
        if day_frame is None:
            continue

        equity_before = cash + sum(
            positions[symbol] * last_close.get(symbol, float(day_frame.loc[symbol, "open"]))
            for symbol in positions
            if symbol in day_frame.index
        )
        day_turnover = 0.0

        for symbol in list(pending_exit):
            if symbol not in positions or symbol not in day_frame.index:
                continue
            row = day_frame.loc[symbol]
            if bool(row["can_sell"]):
                notional = positions[symbol] * float(row["open"])
                cash += notional * (1 - cost_rate)
                day_turnover += notional
                del positions[symbol]
                pending_exit.remove(symbol)

        if date in trade_schedule:
            signal_date = trade_schedule[date]
            signal_rows = signals_by_date.get(signal_date, pd.DataFrame())
            desired_targets = _normalize_target_weights(select_targets(signal_date, signal_rows))

            for symbol in list(positions):
                if symbol not in day_frame.index:
                    continue
                sell_attempts += 1
                row = day_frame.loc[symbol]
                if bool(row["can_sell"]):
                    notional = positions[symbol] * float(row["open"])
                    cash += notional * (1 - cost_rate)
                    day_turnover += notional
                    del positions[symbol]
                    pending_exit.discard(symbol)
                else:
                    sell_failures += 1
                    pending_exit.add(symbol)

            buyable_weights: dict[str, float] = {}
            for symbol, target_weight in desired_targets.items():
                if symbol in positions or symbol not in day_frame.index:
                    continue
                buy_attempts += 1
                row = day_frame.loc[symbol]
                if bool(row["can_buy"]):
                    buyable_weights[symbol] = target_weight
                else:
                    buy_failures += 1

            buyable_weights = _normalize_target_weights(buyable_weights)
            if buyable_weights:
                for symbol, target_weight in buyable_weights.items():
                    allocation = cash * target_weight
                    price = float(day_frame.loc[symbol, "open"])
                    shares = (allocation * (1 - cost_rate)) / price if price else 0.0
                    positions[symbol] = shares
                    day_turnover += allocation
                cash = 0.0

        for symbol in positions:
            if symbol in day_frame.index:
                last_close[symbol] = float(day_frame.loc[symbol, "close"])

        equity = cash + sum(
            positions[symbol] * last_close[symbol]
            for symbol in positions
            if symbol in last_close
        )
        turnover_ratio = day_turnover / equity_before if equity_before else 0.0
        turnover_sum += turnover_ratio
        daily_rows.append({"datetime": date, "strategy": name, "equity": equity, "turnover": turnover_ratio})

    equity_curve = pd.DataFrame(daily_rows)
    equity_curve["daily_return"] = equity_curve["equity"].pct_change().fillna(0.0)
    yearly = compute_yearly_returns(equity_curve, name)

    metrics = {
        "strategy": name,
        "initial_capital": initial_capital,
        "final_equity": float(equity_curve["equity"].iloc[-1]) if not equity_curve.empty else None,
        "total_return": float(equity_curve["equity"].iloc[-1] / initial_capital - 1) if not equity_curve.empty else None,
        "annualized_return": annualized_return(equity_curve["equity"]) if not equity_curve.empty else None,
        "max_drawdown": max_drawdown(equity_curve["equity"]) if not equity_curve.empty else None,
        "turnover_ratio": float(turnover_sum / len(equity_curve)) if len(equity_curve) else None,
        "win_rate": float((equity_curve["daily_return"] > 0).mean()) if not equity_curve.empty else None,
        "buy_attempts": int(buy_attempts),
        "buy_failures": int(buy_failures),
        "sell_attempts": int(sell_attempts),
        "sell_failures": int(sell_failures),
        "buy_failure_ratio": float(buy_failures / buy_attempts) if buy_attempts else 0.0,
        "sell_failure_ratio": float(sell_failures / sell_attempts) if sell_attempts else 0.0,
    }
    return StrategyResult(name=name, equity_curve=equity_curve, metrics=metrics, yearly=yearly)
