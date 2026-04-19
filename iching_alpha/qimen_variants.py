"""Qimen portfolio-construction variants."""

from __future__ import annotations

from typing import Callable

import pandas as pd


def build_qimen_selector(
    top_palaces: int,
    weighting: str,
    direction: str = "top",
) -> Callable[[pd.Timestamp, pd.DataFrame], dict[str, float]]:
    if top_palaces <= 0:
        raise ValueError("top_palaces must be positive.")
    if weighting not in {"stock", "industry", "palace"}:
        raise ValueError("weighting must be one of: stock, industry, palace.")
    if direction not in {"top", "bottom"}:
        raise ValueError("direction must be one of: top, bottom.")

    def select(signal_date: pd.Timestamp, signal_rows: pd.DataFrame) -> dict[str, float]:
        palace_scores = (
            signal_rows[["qimen_palace", "qimen_score"]]
            .dropna()
            .drop_duplicates()
            .sort_values("qimen_score", ascending=(direction == "bottom"))
        )
        if palace_scores.empty:
            return {}
        selected_palaces = palace_scores.head(top_palaces)["qimen_palace"].tolist()
        selected = signal_rows[signal_rows["qimen_palace"].isin(selected_palaces)].dropna(subset=["industry"])
        if selected.empty:
            return {}

        if weighting == "stock":
            symbols = selected["symbol"].drop_duplicates().tolist()
            if not symbols:
                return {}
            weight = 1.0 / len(symbols)
            return {symbol: weight for symbol in symbols}

        if weighting == "industry":
            target_weights: dict[str, float] = {}
            industry_groups = selected.groupby("industry", observed=True)
            industry_weight = 1.0 / len(industry_groups)
            for _, group in industry_groups:
                symbols = group["symbol"].drop_duplicates().tolist()
                if not symbols:
                    continue
                stock_weight = industry_weight / len(symbols)
                for symbol in symbols:
                    target_weights[symbol] = stock_weight
            return target_weights

        target_weights: dict[str, float] = {}
        palace_groups = selected.groupby("qimen_palace", observed=True)
        palace_weight = 1.0 / len(palace_groups)
        for _, palace_group in palace_groups:
            industry_groups = palace_group.groupby("industry", observed=True)
            industry_weight = palace_weight / len(industry_groups)
            for _, industry_group in industry_groups:
                symbols = industry_group["symbol"].drop_duplicates().tolist()
                if not symbols:
                    continue
                stock_weight = industry_weight / len(symbols)
                for symbol in symbols:
                    target_weights[symbol] = stock_weight
        return target_weights

    return select
