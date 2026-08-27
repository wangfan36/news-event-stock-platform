from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SHOWCASE = PROJECT_ROOT / "index.html"


def test_showcase_has_required_product_sections() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert '<html lang="zh-CN">' in page
    assert 'id="main"' in page
    for section_id in ("chain", "workspace", "output", "install", "principles"):
        assert f'id="{section_id}"' in page


def test_showcase_is_accessible_and_self_contained() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert 'aria-live="polite"' in page
    assert 'role="tablist"' in page
    assert "prefers-reduced-motion" in page
    assert "<noscript>" in page
    assert '<script src=' not in page
    assert '<link rel="stylesheet"' not in page
    assert "fetch(" not in page
    assert "localStorage" not in page
    assert "sessionStorage" not in page


def test_showcase_assets_and_pages_marker_exist() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert "./docs/images/dashboard.png" in page
    assert (PROJECT_ROOT / "docs" / "images" / "dashboard.png").is_file()
    assert (PROJECT_ROOT / ".nojekyll").is_file()


def test_showcase_does_not_contain_api_credentials() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert "sk-" not in page
    assert "NEWS_ALPHA_API_KEY=" not in page
