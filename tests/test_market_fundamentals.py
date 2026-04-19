import pandas as pd

import iching_alpha.market_fundamentals as market_fundamentals_module
from iching_alpha.market_fundamentals import build_company_snapshot_bundle
from iching_alpha.market_fundamentals import build_execution_plan


def test_hk_override_price_snapshot_can_be_loaded() -> None:
    bundle = build_company_snapshot_bundle("01138.HK", "2026-04-15")

    assert bundle["price_snapshot"]["status"] == "ok"
    assert bundle["price_snapshot"]["provider"] == "yahoo-public-chart"


def test_hk_financial_snapshots_can_be_loaded_for_some_symbols() -> None:
    for symbol in ["00981.HK", "00883.HK"]:
        bundle = build_company_snapshot_bundle(symbol, "2026-04-15")
        assert bundle["valuation_snapshot"]["status"] == "ok"
        assert bundle["fundamental_snapshot"]["status"] == "ok"


def test_a_share_fundamental_snapshot_can_fallback_to_ths_abstract(monkeypatch) -> None:
    monkeypatch.setattr(
        market_fundamentals_module,
        "_load_a_share_abstract_payload",
        lambda symbol: {
            "abstract": pd.DataFrame(
                [
                    {"指标": "毛利率", "20251231": 41.2},
                    {"指标": "资产负债率", "20251231": 32.5},
                    {"指标": "每股净资产", "20251231": 12.3},
                    {"指标": "每股经营现金流", "20251231": 1.8},
                ]
            ),
            "abstract_new": pd.DataFrame(
                [
                    {"report_date": "2025-12-31", "metric_name": "index_weighted_avg_roe", "value": 18.6},
                    {"report_date": "2025-12-31", "metric_name": "calculate_operating_income_total_yoy_growth_ratio", "value": 24.5},
                    {"report_date": "2025-12-31", "metric_name": "calculate_parent_holder_net_profit_yoy_growth_ratio", "value": 31.7},
                    {"report_date": "2025-12-31", "metric_name": "basic_eps", "value": 2.4},
                ]
            ),
        },
    )

    snapshot = market_fundamentals_module._build_fundamental_snapshot_from_ths("300308", pd.Timestamp("2026-04-16"))

    assert snapshot is not None
    assert snapshot["status"] == "ok"
    assert snapshot["provider"] == "ths-abstract"
    assert snapshot["roe_dt"] == 18.6
    assert snapshot["revenue_yoy"] == 24.5
    assert snapshot["netprofit_yoy"] == 31.7
    assert snapshot["eps"] == 2.4
    assert snapshot["grossprofit_margin"] == 41.2
    assert snapshot["debt_to_assets"] == 32.5


def test_execution_plan_respects_ai_beneficiary_strength() -> None:
    price_snapshot = {"status": "ok", "latest_price": 100, "previous_close": 98}
    technical_overlay = {"trend_alignment": "顺势确认", "provider_status": "ok"}

    strong = build_execution_plan(
        "买入",
        10,
        price_snapshot,
        technical_overlay,
        {"rank": 1, "level": "直接受益"},
    )
    weak = build_execution_plan(
        "买入",
        10,
        price_snapshot,
        technical_overlay,
        {"rank": 9, "level": "弱相关"},
    )

    assert strong["suggested_buy_price"] > weak["suggested_buy_price"]
    assert strong["suggested_sell_price"] > weak["suggested_sell_price"]
    assert "AI 受益排序第 1 位" in strong["pricing_note"]
