import pandas as pd

from iching_alpha.calendar_features import build_calendar_features
from iching_alpha.iching import build_iching_scores


def test_forward_return_uses_next_open_to_future_open() -> None:
    dates = list(pd.date_range("2024-01-01", periods=30, freq="B"))
    market = pd.DataFrame(
        {
            "datetime": dates,
            "symbol": ["000001"] * len(dates),
            "ret_1d": [0.01] * len(dates),
            "fwd_open_return": [None] * len(dates),
        }
    )
    market["fwd_open_return"] = market["ret_1d"].shift(-6)
    calendar = build_calendar_features(dates)
    scored = build_iching_scores(market, calendar)
    first_valid = scored["iching_score"].first_valid_index()
    assert first_valid is not None
    assert scored.loc[first_valid, "fwd_open_return"] == market.loc[first_valid, "fwd_open_return"]

