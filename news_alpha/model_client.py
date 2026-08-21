"""OpenAI-compatible model client for optional workspace refinement."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


def refine_workspace_with_model(workspace: dict[str, Any], model_settings: dict[str, Any]) -> dict[str, Any]:
    if not model_settings.get("enabled"):
        workspace["model_runtime"] = {"enabled": False, "status": "disabled"}
        return workspace

    provider = str(model_settings.get("provider", "openai-compatible") or "openai-compatible").strip()
    api_key = str(model_settings.get("api_key", "") or os.getenv("NEWS_ALPHA_API_KEY", "")).strip()
    base_url = str(model_settings.get("base_url", "")).strip()
    model_name = str(model_settings.get("model_name", "")).strip()
    if provider == "codex-cli":
        workspace["model_runtime"] = {
            "enabled": True,
            "status": "skipped",
            "provider": provider,
            "model_name": model_name or "gpt-5.4",
            "message": "codex-cli 模式已跳过最终文案润色，避免慢速 CLI 调用覆盖规则结果。",
        }
        return workspace
    if provider != "codex-cli" and (not api_key or not base_url or not model_name):
        workspace["model_runtime"] = {"enabled": True, "status": "missing_credentials"}
        return workspace
    if provider == "codex-cli" and not model_name:
        model_name = "gpt-5.4"

    prompt = {
        "daily_digest": workspace.get("daily_digest", {}),
        "hotspot_events": [
            {
                "event_id": item["event_id"],
                "title": item["title"],
                "summary": item["event_summary"],
                "catalysts": item["catalysts"],
                "invalidation_conditions": item["invalidation_conditions"],
            }
            for item in workspace.get("hotspot_events", [])[:3]
        ],
        "recommendation_views": [
            {
                "symbol": item["symbol"],
                "name": item["name"],
                "action": item["action"],
                "core_logic": item["core_logic"],
                "catalysts": item["catalysts"],
                "risks": item["risks"],
            }
            for item in workspace.get("recommendation_views", [])[:5]
        ],
    }

    system_prompt = str(model_settings.get("system_prompt", "")).strip() or (
        "你是中文财经投研助手。请在不改变原始方向判断的前提下，把事件摘要和个股建议改写得更像产品前台可直接展示的内容。"
        "输出必须是 JSON，字段包括 daily_digest_summary, events, recommendations。"
    )
    user_prompt = (
        "请基于以下输入，返回 JSON："
        '{"daily_digest_summary":"...",'
        '"events":[{"event_id":"...","event_summary":"..."}],'
        '"recommendations":[{"symbol":"...","core_logic":"..."}]}。'
        "不要改 action，只能润色 summary 和 core_logic。\n\n"
        + json.dumps(prompt, ensure_ascii=False)
    )

    try:
        response_text = _chat_completion(base_url, api_key, model_name, system_prompt, user_prompt, model_settings)
        parsed = _extract_json(response_text)
    except Exception as exc:
        workspace["model_runtime"] = {"enabled": True, "status": "error", "message": str(exc)}
        return workspace

    if not isinstance(parsed, dict):
        workspace["model_runtime"] = {"enabled": True, "status": "invalid_response"}
        return workspace

    daily_summary = parsed.get("daily_digest_summary")
    if isinstance(daily_summary, str) and daily_summary.strip():
        workspace.setdefault("daily_digest", {})["summary"] = daily_summary.strip()
        workspace.setdefault("daily_brief", {})["summary"] = daily_summary.strip()

    event_map = {
        str(item.get("event_id")): item
        for item in parsed.get("events", [])
        if isinstance(item, dict)
    }
    for event in workspace.get("hotspot_events", []):
        event_update = event_map.get(event["event_id"])
        if event_update and isinstance(event_update.get("event_summary"), str) and event_update["event_summary"].strip():
            event["event_summary"] = event_update["event_summary"].strip()

    recommendation_map = {
        str(item.get("symbol")): item
        for item in parsed.get("recommendations", [])
        if isinstance(item, dict)
    }
    for item in workspace.get("recommendation_views", []):
        rec_update = recommendation_map.get(item["symbol"])
        if rec_update and isinstance(rec_update.get("core_logic"), str) and rec_update["core_logic"].strip():
            item["core_logic"] = rec_update["core_logic"].strip()

    workspace["model_runtime"] = {
        "enabled": True,
        "status": "ok",
        "provider": provider,
        "model_name": model_name,
    }
    return workspace


def _chat_completion(
    base_url: str,
    api_key: str,
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    model_settings: dict[str, Any],
) -> str:
    provider = str(model_settings.get("provider", "openai-compatible") or "openai-compatible").strip()
    if provider == "codex-cli":
        return _codex_cli_completion(model_name, system_prompt, user_prompt, model_settings)
    endpoint = _normalize_chat_url(base_url)
    payload = {
        "model": model_name,
        "temperature": _effective_temperature(model_name, base_url, model_settings),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    }
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "User-Agent": "Mozilla/5.0 (Codex Model Client)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=float(model_settings.get("timeout_seconds", 20) or 20)) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise RuntimeError(f"HTTP {exc.code}: {detail[:200]}") from exc
    content = body["choices"][0]["message"]["content"]
    if not isinstance(content, str):
        raise RuntimeError("Model response content is not text.")
    return content


def _codex_cli_completion(
    model_name: str,
    system_prompt: str,
    user_prompt: str,
    model_settings: dict[str, Any],
) -> str:
    repo_root = Path(__file__).resolve().parent.parent
    timeout_seconds = float(model_settings.get("timeout_seconds", 60) or 60)
    combined_prompt = (
        "You are assisting a local finance research application. "
        "Return only the final answer for the task below.\n\n"
        "System instructions:\n"
        f"{system_prompt}\n\n"
        "User task:\n"
        f"{user_prompt}"
    )
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".prompt.txt", encoding="utf-8") as prompt_handle:
        prompt_handle.write(combined_prompt)
        prompt_path = prompt_handle.name
    with tempfile.NamedTemporaryFile("w+", delete=False, suffix=".txt", encoding="utf-8") as handle:
        output_path = handle.name
    command = [
        "codex",
        "exec",
        "--skip-git-repo-check",
        "-C",
        str(repo_root),
        "-o",
        output_path,
        "-m",
        model_name or "gpt-5.4",
        "-",
    ]
    if os.name == "nt":
        escaped_prompt = prompt_path.replace("'", "''")
        escaped_repo = str(repo_root).replace("'", "''")
        escaped_output = output_path.replace("'", "''")
        escaped_model = (model_name or "gpt-5.4").replace("'", "''")
        command = [
            "powershell",
            "-NoProfile",
            "-Command",
            f"$prompt = Get-Content -Raw -Encoding UTF8 -LiteralPath '{escaped_prompt}'; "
            f"$prompt | & codex exec --skip-git-repo-check -C '{escaped_repo}' "
            f"-o '{escaped_output}' -m '{escaped_model}' -",
        ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=False,
        timeout=timeout_seconds,
        cwd=str(repo_root),
        input=None if os.name == "nt" else combined_prompt.encode("utf-8"),
    )
    stdout_text = _decode_process_output(result.stdout)
    stderr_text = _decode_process_output(result.stderr)
    try:
        content = _sanitize_codex_cli_output(Path(output_path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        content = ""
    finally:
        try:
            Path(output_path).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            Path(prompt_path).unlink(missing_ok=True)
        except Exception:
            pass
    if result.returncode != 0 and not content:
        detail = (stderr_text or "").strip() or (stdout_text or "").strip() or "codex exec failed"
        raise RuntimeError(detail[:300])
    if not content:
        detail = (stderr_text or "").strip() or (stdout_text or "").strip() or "codex exec returned empty output"
        raise RuntimeError(detail[:300])
    return content


def _decode_process_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    for encoding in ("utf-8", "utf-8-sig", "gbk"):
        try:
            return value.decode(encoding)
        except Exception:
            continue
    return value.decode("utf-8", errors="ignore")


def _sanitize_codex_cli_output(raw: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines()]
    cleaned: list[str] = []
    skip_prefixes = (
        "OpenAI Codex",
        "workdir:",
        "model:",
        "provider:",
        "approval:",
        "sandbox:",
        "reasoning effort:",
        "reasoning summaries:",
        "session id:",
        "warning:",
        "mcp:",
        "mcp startup:",
        "tokens used",
    )
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == "--------" or stripped in {"user", "codex"}:
            continue
        if stripped.startswith("202") and ("WARN" in stripped or "ERROR" in stripped):
            continue
        if any(stripped.startswith(prefix) for prefix in skip_prefixes):
            continue
        cleaned.append(line)
    sanitized = "\n".join(cleaned).strip()
    if not sanitized:
        return text
    json_start = min(
        [index for index in (sanitized.find("{"), sanitized.find("[")) if index != -1],
        default=-1,
    )
    json_end = max(sanitized.rfind("}"), sanitized.rfind("]"))
    if json_start != -1 and json_end >= json_start:
        return sanitized[json_start : json_end + 1].strip()
    return sanitized


def _normalize_chat_url(base_url: str) -> str:
    trimmed = base_url.strip().rstrip("/")
    if trimmed.endswith("/chat/completions"):
        return trimmed
    if trimmed.endswith("/v1"):
        return trimmed + "/chat/completions"
    parsed = urllib.parse.urlparse(trimmed)
    if parsed.scheme and parsed.netloc:
        return trimmed + "/v1/chat/completions"
    raise RuntimeError("Invalid model base_url.")


def _effective_temperature(model_name: str, base_url: str, model_settings: dict[str, Any]) -> float:
    model_key = str(model_name or "").lower()
    base_key = str(base_url or "").lower()
    if "kimi" in model_key or "moonshot" in base_key:
        return 1.0
    return float(model_settings.get("temperature", 0.2) or 0.2)


def _extract_json(text: str) -> Any:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if "\n" in stripped:
            stripped = stripped.split("\n", 1)[1]
        if stripped.endswith("```"):
            stripped = stripped[:-3]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise RuntimeError("Model did not return JSON.")
    return json.loads(stripped[start : end + 1])
