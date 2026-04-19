from datetime import date

from iching_alpha.research_os import ResearchRequest, build_research_workspace, default_demo_request
from iching_alpha.storage import get_symbol_history, get_workspace_run, list_workspace_runs, persist_workspace


def test_workspace_can_be_persisted_and_loaded(tmp_path) -> None:
    db_path = tmp_path / "workspace.db"
    workspace = build_research_workspace(
        ResearchRequest.from_dict(default_demo_request()),
        as_of=date(2026, 4, 9),
    )

    run_id = persist_workspace(workspace, db_path)

    loaded = get_workspace_run(db_path, run_id)
    assert loaded is not None
    assert loaded["generated_at"] == workspace["generated_at"]

    runs = list_workspace_runs(db_path)
    assert runs[0]["run_id"] == run_id

    symbol = workspace["recommendation_views"][0]["symbol"]
    history = get_symbol_history(db_path, symbol)
    assert history[0]["symbol"] == symbol
