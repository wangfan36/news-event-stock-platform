"""Data loading and market feature preparation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AppConfig


@dataclass
class MarketBundle:
    market: pd.DataFrame
    backtest_dates: list[pd.Timestamp]
    full_calendar: list[pd.Timestamp]
    universe_symbols: list[str]
    industry_map: dict[str, str]


def normalize_symbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    match = re.fullmatch(r"(SH|SZ|BJ)?([0-9]{6})", value)
    if match:
        return match.group(2)
    return value


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_universe_symbols(provider_uri: Path, universe: str) -> list[str]:
    universe_path = provider_uri / "instruments" / f"{universe}.txt"
    symbols: list[str] = []
    with universe_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.strip().split("\t")
            if not parts:
                continue
            symbol = normalize_symbol(parts[0])
            if re.fullmatch(r"[0-9]{6}", symbol):
                symbols.append(symbol)
    return sorted(set(symbols))


def load_calendar(provider_uri: Path) -> list[pd.Timestamp]:
    calendar_path = provider_uri / "calendars" / "day.txt"
    return [
        pd.Timestamp(line.strip())
        for line in calendar_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _load_industry_map(path: Path) -> dict[str, str]:
    raw = load_json(path)
    return {normalize_symbol(symbol): industry for symbol, industry in raw.items()}


def _load_qlib_series_frame(
    provider_uri: Path,
    full_calendar: list[pd.Timestamp],
    raw_symbol: str,
) -> pd.DataFrame:
    instruments_path = provider_uri / "instruments" / "all.txt"
    start_date: pd.Timestamp | None = None
    end_date: pd.Timestamp | None = None
    with instruments_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.strip().split("\t")
            if len(parts) < 3:
                continue
            if parts[0].upper() == raw_symbol.upper():
                start_date = pd.Timestamp(parts[1])
                end_date = pd.Timestamp(parts[2])
                break
    if start_date is None or end_date is None:
        raise FileNotFoundError(f"Unable to locate {raw_symbol} in qlib instruments file.")

    feature_dir = provider_uri / "features" / raw_symbol
    dates = [date for date in full_calendar if start_date <= date <= end_date]

    def load_feature(name: str) -> np.ndarray:
        candidates = [
            feature_dir / f"${name}.day.bin",
            feature_dir / f"{name}.day.bin",
        ]
        file_path = next((path for path in candidates if path.exists()), None)
        if file_path is None:
            raise FileNotFoundError(f"Missing qlib feature for {raw_symbol}: {name}")
        values = np.fromfile(file_path, dtype=np.float32)
        if len(values) and values[0] == 0:
            values = values[1:]
        return values

    columns = {
        "open": load_feature("open"),
        "close": load_feature("close"),
        "high": load_feature("high"),
        "low": load_feature("low"),
        "volume": load_feature("volume"),
    }
    frame = pd.DataFrame(columns)
    frame["datetime"] = dates[: len(frame)]
    frame["symbol"] = normalize_symbol(raw_symbol)
    frame["amount"] = 0.0
    frame["turnover"] = 0.0
    return frame


def _slice_calendar(
    full_calendar: list[pd.Timestamp],
    start_date: str,
    end_date: str,
    lookback_days: int,
) -> tuple[list[pd.Timestamp], pd.Timestamp]:
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    eligible = [date for date in full_calendar if start <= date <= end]
    if not eligible:
        raise ValueError("No trading dates fall inside the requested backtest window.")
    start_idx = full_calendar.index(eligible[0])
    load_idx = max(0, start_idx - lookback_days)
    return eligible, full_calendar[load_idx]


def load_market_bundle(config: AppConfig) -> MarketBundle:
    full_calendar = load_calendar(config.qlib_provider_uri)
    backtest_dates, load_start = _slice_calendar(
        full_calendar,
        config.start_date,
        config.end_date,
        config.lookback_days,
    )
    universe_symbols = load_universe_symbols(config.qlib_provider_uri, config.universe)
    industry_map = _load_industry_map(config.industry_mapping_path)

    required_symbols = set(universe_symbols)
    required_symbols.add(normalize_symbol(config.csi300_symbol))
    df = pd.read_parquet(
        config.parquet_path,
        columns=[
            "datetime",
            "instrument",
            "$open",
            "$close",
            "$high",
            "$low",
            "$volume",
            "$amount",
            "$turnover",
        ],
    )
    df = df.rename(
        columns={
            "instrument": "symbol",
            "$open": "open",
            "$close": "close",
            "$high": "high",
            "$low": "low",
            "$volume": "volume",
            "$amount": "amount",
            "$turnover": "turnover",
        }
    )
    df["datetime"] = pd.to_datetime(df["datetime"])
    df["symbol"] = df["symbol"].map(normalize_symbol)
    df = df[df["symbol"].isin(required_symbols)]
    df = df[(df["datetime"] >= load_start) & (df["datetime"] <= pd.Timestamp(config.end_date))]
    df = df.sort_values(["symbol", "datetime"]).reset_index(drop=True)

    csi_symbol = normalize_symbol(config.csi300_symbol)
    if csi_symbol not in set(df["symbol"].unique()):
        index_frame = _load_qlib_series_frame(config.qlib_provider_uri, full_calendar, f"SH{csi_symbol}")
        index_frame = index_frame[
            (index_frame["datetime"] >= load_start) & (index_frame["datetime"] <= pd.Timestamp(config.end_date))
        ]
        df = pd.concat([df, index_frame], ignore_index=True).sort_values(["symbol", "datetime"]).reset_index(drop=True)

    df["industry"] = df["symbol"].map(industry_map)
    df["prev_close"] = df.groupby("symbol", observed=True)["close"].shift(1)
    valid_close = df["close"].gt(0) & df["prev_close"].gt(0)
    df["ret_1d"] = np.where(valid_close, df["close"] / df["prev_close"] - 1, np.nan)
    df["tradable"] = (
        df["open"].gt(0)
        & df["close"].gt(0)
        & df["high"].gt(0)
        & df["low"].gt(0)
        & df["volume"].gt(0)
    )

    up_proxy = df["prev_close"].gt(0) & ((df["open"] / df["prev_close"] - 1) >= config.limit_move_threshold)
    down_proxy = df["prev_close"].gt(0) & ((df["open"] / df["prev_close"] - 1) <= -config.limit_move_threshold)
    df["can_buy"] = df["tradable"] & ~(df["open"].ge(df["high"]) & up_proxy)
    df["can_sell"] = df["tradable"] & ~(df["open"].le(df["low"]) & down_proxy)
    next_open = df.groupby("symbol", observed=True)["open"].shift(-1)
    exit_open = df.groupby("symbol", observed=True)["open"].shift(-(config.hold_days + 1))
    valid_forward = next_open.gt(0) & exit_open.gt(0)
    df["fwd_open_return"] = np.where(valid_forward, exit_open / next_open - 1, np.nan)

    return MarketBundle(
        market=df,
        backtest_dates=backtest_dates,
        full_calendar=full_calendar,
        universe_symbols=universe_symbols,
        industry_map=industry_map,
    )
