from datetime import datetime

from news_alpha.news_pipeline import (
    deduplicate_and_cluster_news,
    load_demo_raw_news_feed,
    summarize_clusters,
)


def test_demo_news_feed_is_deduplicated_and_clustered() -> None:
    clustered = deduplicate_and_cluster_news(
        load_demo_raw_news_feed(),
        datetime(2026, 4, 9, 8, 45),
    )

    assert len(clustered) == 9
    assert len({item["cluster_id"] for item in clustered}) == 5
    assert sum(1 for item in clustered if item["cluster_id"] == "cluster_ai_capex") == 2


def test_cluster_summary_aggregates_metadata() -> None:
    clustered = deduplicate_and_cluster_news(
        load_demo_raw_news_feed(),
        datetime(2026, 4, 9, 8, 45),
    )
    summary = summarize_clusters(clustered)

    ai_cluster = next(item for item in summary if item["cluster_id"] == "cluster_ai_capex")
    assert ai_cluster["news_count"] == 2
    assert "AI算力" in ai_cluster["tags"]
