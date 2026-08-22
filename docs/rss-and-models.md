# RSS and Model Configuration

**English** | [简体中文](rss-and-models.zh-CN.md)

## Add RSS sources

1. Start the application and open `http://127.0.0.1:8000/#settings`.
2. Go to **Data & Models** (`数据与模型`) > **RSS Sources** (`RSS 数据源`).
3. Enter one source per line and enable **Prefer live RSS when generating** (`生成时优先抓取真实 RSS`).
4. Select **Save all settings** (`保存全部配置`), then **Refresh data** (`刷新数据`) to validate access or **Generate research** (`生成研究`) to run the pipeline.

Separate fields with an ASCII pipe character (`|`):

```text
URL | Name | Region | Market | Source Type
https://example.com/feed.xml | Example News | Global | A-share+Hong Kong | Financial Media
```

Only the URL is required. Both forms below are valid:

```text
# Spaces around separators are allowed
https://example.com/world.xml | World Desk | Global | A-share+Hong Kong | International Media

# URL only
https://example.org/atom.xml
```

Parsing rules:

- Only `http://` and `https://` URLs are accepted; a URL cannot contain spaces.
- Spaces around `|` are trimmed, and missing optional fields receive defaults.
- Blank lines and lines beginning with `#` are ignored.
- Duplicate URLs keep only their first occurrence.
- At most 50 custom sources are loaded at once.
- RSS 2.0 `item` and Atom `entry` elements are supported.
- Publication time is read from `pubDate`, `published`, `updated`, or `date` when available.

Use the feed URL, not the publisher's website home page. If validation fails, confirm that the URL is reachable from the local machine, returns XML without a login or CAPTCHA, and is not blocked by a proxy, firewall, or certificate policy. One failed source does not prevent the rule engine from using other sources or demo data.

## Add a model API key

News Alpha supports OpenAI-compatible endpoints. Prefer a process environment variable instead of putting a key in source code or example configuration.

PowerShell, for the current session:

```powershell
$env:NEWS_ALPHA_API_KEY = "<your-provider-api-key>"
python -m news_alpha.webapp
```

macOS or Linux:

```bash
export NEWS_ALPHA_API_KEY="<your-provider-api-key>"
python -m news_alpha.webapp
```

Then open **Data & Models** (`数据与模型`) > **Model API** (`大模型 API`):

1. Enable model enrichment.
2. Select `openai-compatible` as the provider.
3. Enter the provider's Base URL, for example `https://api.openai.com/v1`.
4. Enter a model name supported by that provider.
5. Leave the API Key field empty when using the environment variable and no key was previously saved in the UI. A previously saved local key takes precedence.
6. Save the settings and generate one research run; inspect system status for the model result.

You may instead enter the API key in the web UI. This stores it in the local `artifacts/db/news_stock.db` database; API responses mask the value, and `artifacts/` is ignored by Git. When `codex-cli` is selected, the application uses the existing local Codex login and no API key is entered in the web UI.

## Secret safety

- Never put a real key in `.env.example`, documentation, source code, issues, logs, or screenshots.
- `.env`, `config/local.yaml`, `artifacts/`, and local databases are ignored by default.
- Run `python scripts/check_secrets.py` before pushing; CI runs the same check.
- If a key was committed, revoke and rotate it immediately. Deleting it from the latest commit does not remove it from Git history.

The model only enriches structured research text and cannot change the rule engine's action direction. Rule-based results remain available when a model request fails.
