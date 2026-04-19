"""Qimen Dunjia signal generation."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from kinqimen.kinqimen import Qimen

from .constants import (
    GAN_TO_ELEMENT,
    NINE_PALACES,
    PALACE_NORMALIZATION,
    QIMEN_CHANGSHENG_SCORES,
    QIMEN_GATE_SCORES,
    QIMEN_GOD_SCORES,
    QIMEN_STAR_SCORES,
)
from .iching import relationship_score


def load_industry_palace_map(path: Path) -> dict[str, str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {industry: PALACE_NORMALIZATION[palace] for industry, palace in raw.items()}


def _normalize_palace(value: str | None) -> str | None:
    if value is None:
        return None
    return PALACE_NORMALIZATION.get(value, value)


def score_pan_for_date(date: pd.Timestamp, hour: int, minute: int) -> pd.DataFrame:
    pan = Qimen(date.year, date.month, date.day, hour, minute).pan(1)

    gate_map = {_normalize_palace(key): value for key, value in pan["門"].items()}
    star_map = {_normalize_palace(key): value for key, value in pan["星"].items()}
    god_map = {_normalize_palace(key): value for key, value in pan["神"].items()}
    sky_map = {_normalize_palace(key): value for key, value in pan["天盤"].items()}
    earth_map = {_normalize_palace(key): value for key, value in pan["地盤"].items()}
    changsheng_map = {
        _normalize_palace(key): next(iter(value.values()))
        for key, value in pan["長生運"]["天盤"].items()
    }
    zhifu_palace = _normalize_palace(pan["值符值使"]["值符星宮"][1])
    zhishi_palace = _normalize_palace(pan["值符值使"]["值使門宮"][1])

    rows: list[dict[str, object]] = []
    for palace in NINE_PALACES:
        sky_stem = sky_map.get(palace)
        earth_stem = earth_map.get(palace)
        stem_score = 0.0
        if sky_stem and earth_stem:
            stem_score = relationship_score(GAN_TO_ELEMENT[sky_stem], GAN_TO_ELEMENT[earth_stem])

        gate_score = float(QIMEN_GATE_SCORES.get(gate_map.get(palace, ""), 0))
        star_score = float(QIMEN_STAR_SCORES.get(star_map.get(palace, ""), 0))
        god_score = float(QIMEN_GOD_SCORES.get(god_map.get(palace, ""), 0))
        zhifu_bonus = 2.0 if palace == zhifu_palace else 0.0
        zhishi_bonus = 1.0 if palace == zhishi_palace else 0.0
        changsheng_score = float(QIMEN_CHANGSHENG_SCORES.get(changsheng_map.get(palace, ""), 0))
        palace_score = gate_score + star_score + god_score + zhifu_bonus + zhishi_bonus + stem_score + changsheng_score

        rows.append(
            {
                "datetime": date,
                "qimen_palace": palace,
                "qimen_gate": gate_map.get(palace),
                "qimen_star": star_map.get(palace),
                "qimen_god": god_map.get(palace),
                "qimen_sky_stem": sky_stem,
                "qimen_earth_stem": earth_stem,
                "qimen_changsheng": changsheng_map.get(palace),
                "qimen_zhifu_palace": zhifu_palace,
                "qimen_zhishi_palace": zhishi_palace,
                "qimen_gate_score": gate_score,
                "qimen_star_score": star_score,
                "qimen_god_score": god_score,
                "qimen_zhifu_bonus": zhifu_bonus,
                "qimen_zhishi_bonus": zhishi_bonus,
                "qimen_stem_relation_score": stem_score,
                "qimen_changsheng_score": changsheng_score,
                "qimen_score": palace_score,
            }
        )
    return pd.DataFrame(rows)


def build_qimen_scores(
    dates: list[pd.Timestamp],
    market_meta: pd.DataFrame,
    industry_palace_map: dict[str, str],
    qimen_time: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    hour, minute = [int(part) for part in qimen_time.split(":", 1)]
    palace_scores = pd.concat(
        [score_pan_for_date(date, hour, minute) for date in dates],
        ignore_index=True,
    )

    symbol_meta = market_meta[["symbol", "industry"]].dropna().drop_duplicates()
    symbol_meta["qimen_palace"] = symbol_meta["industry"].map(industry_palace_map)
    stock_scores = symbol_meta.merge(palace_scores, on="qimen_palace", how="left")
    return palace_scores, stock_scores

