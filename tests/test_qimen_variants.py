import pandas as pd

from iching_alpha.qimen_variants import build_qimen_selector


def test_qimen_variant_weightings_normalize() -> None:
    rows = pd.DataFrame(
        [
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000001", "industry": "电子", "qimen_palace": "离", "qimen_score": 5.0},
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000002", "industry": "电子", "qimen_palace": "离", "qimen_score": 5.0},
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000003", "industry": "通信", "qimen_palace": "离", "qimen_score": 5.0},
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000004", "industry": "银行", "qimen_palace": "乾", "qimen_score": 4.0},
        ]
    )

    stock_weights = build_qimen_selector(2, "stock")(pd.Timestamp("2024-01-01"), rows)
    industry_weights = build_qimen_selector(2, "industry")(pd.Timestamp("2024-01-01"), rows)
    palace_weights = build_qimen_selector(2, "palace")(pd.Timestamp("2024-01-01"), rows)

    assert abs(sum(stock_weights.values()) - 1.0) < 1e-9
    assert abs(sum(industry_weights.values()) - 1.0) < 1e-9
    assert abs(sum(palace_weights.values()) - 1.0) < 1e-9
    assert industry_weights["000003"] > industry_weights["000001"]
    assert palace_weights["000004"] > palace_weights["000001"]


def test_qimen_selector_supports_bottom_direction() -> None:
    rows = pd.DataFrame(
        [
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000001", "industry": "电子", "qimen_palace": "离", "qimen_score": 5.0},
            {"datetime": pd.Timestamp("2024-01-01"), "symbol": "000002", "industry": "银行", "qimen_palace": "乾", "qimen_score": 1.0},
        ]
    )
    bottom_weights = build_qimen_selector(1, "stock", direction="bottom")(pd.Timestamp("2024-01-01"), rows)
    assert set(bottom_weights) == {"000002"}
