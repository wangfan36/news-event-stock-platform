# Security Policy

## Supported versions

Only the latest `main` branch is supported.

## Reporting

Do not open a public issue for exposed credentials, arbitrary file access, command execution, or dependency vulnerabilities. Use GitHub Security Advisories to report the issue privately, including reproduction steps, impact, and a suggested remediation when possible.

## Local secrets

Runtime data is stored under `artifacts/`, while personal configuration belongs in `config/local.yaml` or environment variables. These paths are ignored by Git. A model key entered in the web UI is stored in the local SQLite database and masked in API responses; prefer the `NEWS_ALPHA_API_KEY` process environment on shared machines.

Before every push, run `python scripts/check_secrets.py`. The same tracked-file scan runs in CI. It reports only the file, line, and credential type, never the matched value.

If a real key is committed, revoke and rotate it immediately. Removing it from the latest commit is not sufficient because the value remains in Git history; report the incident privately and clean the history before publishing again.

Setup instructions are available in the [RSS and model guide](docs/rss-and-models.md) and its [Chinese translation](docs/rss-and-models.zh-CN.md).
