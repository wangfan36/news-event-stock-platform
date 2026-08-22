from datetime import datetime

from news_alpha.news_pipeline import normalize_news_item
from news_alpha.news_sources import _parse_publication_date, parse_custom_rss_sources


def test_custom_rss_parser_trims_fields_ignores_comments_and_deduplicates() -> None:
    raw = """
    # one feed per line
      https://example.com/feed.xml   |  Example News  | 全球 | A股+港股 | 财经媒体

    https://example.com/feed.xml | Duplicate
    ftp://example.com/invalid.xml | Invalid
    https://example.com/invalid feed.xml | Invalid whitespace
    https://example.org/rss
    """

    sources = parse_custom_rss_sources(raw)

    assert len(sources) == 2
    assert sources[0]["url"] == "https://example.com/feed.xml"
    assert sources[0]["label"] == "Example News"
    assert sources[0]["source_kind"] == "财经媒体"
    assert sources[1]["label"] == "Custom RSS 8"


def test_rfc822_publication_date_is_preserved_by_normalization() -> None:
    published_at = _parse_publication_date("Wed, 20 Aug 2026 01:30:00 GMT")
    item = normalize_news_item(
        {
            "source_id": "source-1",
            "headline": "测试新闻",
            "published_at": published_at,
        },
        datetime(2026, 8, 20, 10, 30),
    )

    assert published_at == "2026-08-20T01:30+00:00"
    assert item["published_at"] == "2026-08-20T09:30+08:00"
    assert item["published_offset_hours"] == 1
