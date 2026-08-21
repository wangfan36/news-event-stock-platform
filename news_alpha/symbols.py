"""Stock symbol normalization and optional universe loading."""

from __future__ import annotations

import re
from pathlib import Path


def normalize_symbol(symbol: str) -> str:
    value = str(symbol).strip().upper()
    match = re.fullmatch(r"(?:SH|SZ|BJ)?([0-9]{6})", value)
    if match:
        return match.group(1)
    hk_match = re.fullmatch(r"([0-9]{1,5})(?:\.HK)?", value)
    if hk_match and (value.endswith(".HK") or len(hk_match.group(1)) == 5):
        return hk_match.group(1).zfill(5) + ".HK"
    return value


def load_universe_symbols(path: Path | None) -> list[str]:
    if path is None or not path.exists():
        return []
    symbols: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        token = line.strip().split("\t", maxsplit=1)[0]
        symbol = normalize_symbol(token)
        if re.fullmatch(r"[0-9]{6}|[0-9]{5}\.HK", symbol):
            symbols.append(symbol)
    return sorted(set(symbols))
