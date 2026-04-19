"""I Ching signal generation."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .constants import (
    ELEMENT_GENERATES,
    ELEMENT_OVERCOMES,
    TRIGRAM_CODE_TO_NAME,
    TRIGRAM_TO_ELEMENT,
)


def relationship_score(source: str, target: str) -> float:
    if not source or not target:
        return np.nan
    if source == target:
        return 1.0
    if ELEMENT_GENERATES[source] == target:
        return 1.0
    if ELEMENT_GENERATES[target] == source:
        return 0.0
    if ELEMENT_OVERCOMES[source] == target or ELEMENT_OVERCOMES[target] == source:
        return -1.0
    return 0.0


_RELATION_LOOKUP = {
    f"{source}->{target}": relationship_score(source, target)
    for source in ELEMENT_GENERATES
    for target in ELEMENT_GENERATES
}


def _map_relation(source: pd.Series, target: pd.Series) -> pd.Series:
    return (source.astype(str) + "->" + target.astype(str)).map(_RELATION_LOOKUP)


def _map_trigram(code: pd.Series) -> pd.Series:
    return code.map(TRIGRAM_CODE_TO_NAME)


def build_iching_scores(market: pd.DataFrame, calendar_features: pd.DataFrame) -> pd.DataFrame:
    df = market[["datetime", "symbol", "ret_1d", "fwd_open_return"]].copy()
    df = df.merge(calendar_features, on="datetime", how="left")
    grouped_ret = df.groupby("symbol", observed=True)["ret_1d"]

    df["abs_ret_1d"] = df["ret_1d"].abs()
    df["moving_threshold"] = grouped_ret.transform(lambda s: s.abs().rolling(20, min_periods=20).median())
    df["ret_positive"] = (df["ret_1d"] >= 0).astype(float)
    df["moving_flag"] = (df["abs_ret_1d"] > df["moving_threshold"]).astype(float)

    grouped_sign = df.groupby("symbol", observed=True)["ret_positive"]
    grouped_move = df.groupby("symbol", observed=True)["moving_flag"]
    for index, lag in enumerate(range(5, -1, -1), start=1):
        df[f"line_{index}"] = grouped_sign.shift(lag)
        df[f"move_{index}"] = grouped_move.shift(lag)

    component_cols = [f"line_{index}" for index in range(1, 7)] + [f"move_{index}" for index in range(1, 7)]
    valid_mask = df[component_cols].notna().all(axis=1)

    line_cols = [f"line_{index}" for index in range(1, 7)]
    move_cols = [f"move_{index}" for index in range(1, 7)]
    weights = np.array([1, 2, 4])

    lower_code = (df[line_cols[:3]].fillna(0).to_numpy() * weights).sum(axis=1).astype(int)
    upper_code = (df[line_cols[3:]].fillna(0).to_numpy() * weights).sum(axis=1).astype(int)

    changed_lines = np.logical_xor(
        df[line_cols].fillna(0).to_numpy().astype(int),
        df[move_cols].fillna(0).to_numpy().astype(int),
    ).astype(int)
    changed_lower_code = (changed_lines[:, :3] * weights).sum(axis=1).astype(int)
    changed_upper_code = (changed_lines[:, 3:] * weights).sum(axis=1).astype(int)

    df["lower_trigram"] = _map_trigram(pd.Series(lower_code, index=df.index))
    df["upper_trigram"] = _map_trigram(pd.Series(upper_code, index=df.index))
    df["changed_lower_trigram"] = _map_trigram(pd.Series(changed_lower_code, index=df.index))
    df["changed_upper_trigram"] = _map_trigram(pd.Series(changed_upper_code, index=df.index))
    df["lower_element"] = df["lower_trigram"].map(TRIGRAM_TO_ELEMENT)
    df["upper_element"] = df["upper_trigram"].map(TRIGRAM_TO_ELEMENT)
    df["changed_lower_element"] = df["changed_lower_trigram"].map(TRIGRAM_TO_ELEMENT)
    df["changed_upper_element"] = df["changed_upper_trigram"].map(TRIGRAM_TO_ELEMENT)
    df["moving_line_count"] = df[move_cols].fillna(0).sum(axis=1).astype("Int64")
    df["hexagram_id"] = df["upper_trigram"] + "_" + df["lower_trigram"]
    df["changed_hexagram_id"] = df["changed_upper_trigram"] + "_" + df["changed_lower_trigram"]

    score_components = pd.concat(
        [
            _map_relation(df["day_element"], df["upper_element"]),
            _map_relation(df["season_element"], df["lower_element"]),
            _map_relation(df["day_element"], df["changed_upper_element"]),
            _map_relation(df["season_element"], df["changed_lower_element"]),
        ],
        axis=1,
    )
    df["iching_score"] = score_components.mean(axis=1)
    df.loc[~valid_mask, ["iching_score", "hexagram_id", "changed_hexagram_id"]] = np.nan
    df.loc[~valid_mask, "moving_line_count"] = pd.NA

    return df[
        [
            "datetime",
            "symbol",
            "day_ganzhi",
            "day_stem",
            "day_branch",
            "solar_term",
            "season_element",
            "hexagram_id",
            "changed_hexagram_id",
            "moving_line_count",
            "iching_score",
            "fwd_open_return",
        ]
    ]

