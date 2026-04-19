import pandas as pd

from iching_alpha.qimen import score_pan_for_date


def test_qimen_pan_extracts_required_fields() -> None:
    scored = score_pan_for_date(pd.Timestamp("2024-04-08"), 15, 0)
    assert len(scored) == 9
    assert scored["qimen_score"].notna().all()
    assert scored["qimen_zhifu_palace"].notna().all()
    assert scored["qimen_zhishi_palace"].notna().all()

