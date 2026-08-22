"""Fail when tracked repository files contain likely credentials or local data."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ALLOWED_TRACKED_PATHS = {".env.example"}
FORBIDDEN_TRACKED_PATHS = {".env", "config/local.yaml", "credentials.json", "secrets.json"}
FORBIDDEN_PREFIXES = ("artifacts/", "config/secrets.")
FORBIDDEN_SUFFIXES = (".db", ".sqlite", ".sqlite3")
BINARY_SUFFIXES = {
    ".gif",
    ".ico",
    ".jpeg",
    ".jpg",
    ".pdf",
    ".png",
    ".pyc",
    ".webp",
}
SECRET_PATTERNS = (
    ("OpenAI-style API key", re.compile(r"\bsk-(?!test\b|ant-)[A-Za-z0-9_-]{20,}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Bearer token", re.compile(r"\bBearer\s+[A-Za-z0-9._-]{24,}\b", re.IGNORECASE)),
)


def tracked_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    )
    return [root / item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def scan_file(path: Path) -> list[tuple[int, str]]:
    if path.suffix.lower() in BINARY_SUFFIXES:
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []

    findings: list[tuple[int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(line):
                findings.append((line_number, label))
    return findings


def main() -> int:
    files = tracked_files(ROOT)
    violations: list[str] = []
    for path in files:
        relative = path.relative_to(ROOT).as_posix()
        if relative not in ALLOWED_TRACKED_PATHS and (
            relative in FORBIDDEN_TRACKED_PATHS
            or relative.startswith(FORBIDDEN_PREFIXES)
            or relative.endswith(FORBIDDEN_SUFFIXES)
        ):
            violations.append(f"{relative}: local secret or runtime file is tracked")
        for line_number, label in scan_file(path):
            violations.append(f"{relative}:{line_number}: possible {label}")

    if violations:
        print("Secret scan failed. Matched values are intentionally hidden:")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print(f"Secret scan passed: {len(files)} tracked files checked.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
