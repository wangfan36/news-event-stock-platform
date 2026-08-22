from scripts.check_secrets import scan_file


def test_secret_scan_accepts_documentation_placeholders(tmp_path) -> None:
    sample = tmp_path / "example.env"
    sample.write_text('NEWS_ALPHA_API_KEY="<your-provider-api-key>"\n', encoding="utf-8")

    assert scan_file(sample) == []


def test_secret_scan_reports_likely_key_without_returning_value(tmp_path) -> None:
    sample = tmp_path / "unsafe.env"
    key = "sk-" + "A" * 24
    sample.write_text(f"NEWS_ALPHA_API_KEY={key}\n", encoding="utf-8")

    findings = scan_file(sample)

    assert findings == [(1, "OpenAI-style API key")]
    assert key not in repr(findings)
