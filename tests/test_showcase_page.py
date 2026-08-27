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


def test_showcase_uses_financial_editorial_visual_language() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert "--gold:" in page
    assert "--red:" in page
    assert 'class="research-cover"' in page
    assert "#5bc9b3" not in page
    assert "terminal-frame" not in page
    assert "repeating-radial-gradient" not in page


def test_showcase_has_semantic_wrapping_glass_and_motion_fallbacks() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert "--display:" in page
    assert page.count('class="heading-line"') == 2
    assert "backdrop-filter: blur" in page
    assert "prefers-reduced-transparency" in page
    assert "prefers-reduced-motion" in page
    assert "@keyframes coverIn" in page


def test_showcase_uses_consistent_twenty_pixel_rounded_borders() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    assert "--radius: 20px;" in page
    assert page.count("border-radius: var(--radius);") >= 10
    assert ".recommendation-stamp" in page
    assert "border-radius: 50%;" in page


def test_showcase_does_not_use_chinese_order_labels() -> None:
    page = SHOWCASE.read_text(encoding="utf-8")

    for label in ("壹", "贰", "叁", "肆", "伍"):
        assert label not in page
