from news_alpha.model_client import _effective_temperature
from news_alpha.storage import (
    get_user_settings,
    prepare_settings_for_storage,
    sanitize_settings_for_output,
    save_user_settings,
)


def test_settings_roundtrip_masks_api_key(tmp_path) -> None:
    db_path = tmp_path / "settings.db"
    prepared = prepare_settings_for_storage(
        {
            "rss_sources_text": "https://example.com/rss | 我的源 | 全球 | A股+港股",
            "technical_settings": {
                "provider": "akshare",
                "endpoint": "",
            },
            "model_settings": {
                "enabled": True,
                "provider": "openai-compatible",
                "base_url": "https://api.example.com/v1",
                "model_name": "demo-model",
                "api_key": "secret-key-123456",
            },
        }
    )
    save_user_settings(db_path, prepared)

    loaded = get_user_settings(db_path)
    assert loaded["rss_sources_text"].startswith("https://example.com/rss")
    assert loaded["technical_settings"]["provider"] == "akshare"
    assert loaded["model_settings"]["api_key"] == "secret-key-123456"

    sanitized = sanitize_settings_for_output(loaded)
    assert sanitized["model_settings"]["has_api_key"] is True
    assert "api_key" not in sanitized["model_settings"]


def test_kimi_temperature_is_forced_to_one() -> None:
    assert _effective_temperature(
        "kimi-k2.5",
        "https://api.moonshot.cn/v1",
        {"temperature": 0.2},
    ) == 1.0


def test_openai_compatible_temperature_preserves_config() -> None:
    assert _effective_temperature(
        "gpt-5.4",
        "https://api.openai.com/v1",
        {"temperature": 0.2},
    ) == 0.2
