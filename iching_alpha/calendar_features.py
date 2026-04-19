"""Daily Ganzhi and solar-term features."""

from __future__ import annotations

import pandas as pd
from lunar_python import Solar

from .constants import GAN_TO_ELEMENT, SOLAR_TERM_TO_SEASON_ELEMENT


def build_calendar_features(dates: list[pd.Timestamp]) -> pd.DataFrame:
    rows: list[dict[str, str | pd.Timestamp]] = []
    for date in dates:
        solar = Solar.fromYmdHms(date.year, date.month, date.day, 15, 0, 0)
        lunar = solar.getLunar()
        jieqi_obj = lunar.getCurrentJieQi() or lunar.getPrevJieQi(True)
        solar_term = jieqi_obj.getName() if jieqi_obj else ""
        day_ganzhi = lunar.getDayInGanZhi()
        rows.append(
            {
                "datetime": date,
                "day_ganzhi": day_ganzhi,
                "day_stem": day_ganzhi[0],
                "day_branch": day_ganzhi[1],
                "month_ganzhi": lunar.getMonthInGanZhi(),
                "year_ganzhi": lunar.getYearInGanZhi(),
                "solar_term": solar_term,
                "season_element": SOLAR_TERM_TO_SEASON_ELEMENT.get(solar_term, "土"),
                "day_element": GAN_TO_ELEMENT[day_ganzhi[0]],
            }
        )
    return pd.DataFrame(rows)
