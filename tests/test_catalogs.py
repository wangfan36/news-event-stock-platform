from news_alpha.catalogs import COMPANY_CATALOG, EVENT_BLUEPRINTS, INDUSTRY_CATALOG


def test_external_catalogs_load_expected_core_entries() -> None:
    assert "ai_optics" in INDUSTRY_CATALOG
    assert INDUSTRY_CATALOG["ai_optics"]["supply_chain"][0]["node_id"] == "optical_chip"

    assert "300308" in COMPANY_CATALOG
    assert COMPANY_CATALOG["300308"]["industry_id"] == "ai_optics"

    assert "event_ai_capex" in EVENT_BLUEPRINTS
    assert EVENT_BLUEPRINTS["event_ai_capex"]["cluster_id"] == "cluster_ai_capex"
