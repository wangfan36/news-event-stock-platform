from pathlib import Path

from iching_alpha.config import AppConfig
from iching_alpha.data import load_json


def test_industry_palace_mapping_covers_sw_l1() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    config = AppConfig.from_file(repo_root / "config" / "default.yaml")
    industry_map = load_json(config.industry_mapping_path)
    palace_map = load_json(config.industry_palace_map_path)

    industries = set(industry_map.values())
    assert len(industries) == 31
    assert industries == set(palace_map.keys())
    assert len(set(palace_map.values())) == 9

