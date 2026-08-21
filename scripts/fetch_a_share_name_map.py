from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_PATH = ROOT / "news_alpha" / "catalogs" / "a_share_name_map.json"
BASE_URL = (
    "https://82.push2.eastmoney.com/api/qt/clist/get"
    "?po=1&np=1&fltt=2&invt=2&fid=f3"
    "&fs=m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23"
    "&fields=f12,f14"
)


def fetch_name_map() -> dict[str, str]:
    page_size = 100
    page = 1
    total = None
    result: dict[str, str] = {}
    while True:
        url = f"{BASE_URL}&pn={page}&pz={page_size}"
        payload = _fetch_page(url)
        data = payload.get("data", {}) or {}
        diff = data.get("diff", []) or []
        if total is None:
            total = int(data.get("total", 0) or 0)
        if not diff:
            break
        for item in diff:
            code = str(item.get("f12", "")).strip()
            name = str(item.get("f14", "")).strip()
            if code and name:
                result[code] = name
        OUTPUT_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        if len(result) >= total:
            break
        time.sleep(0.15)
        page += 1
    return result


def _fetch_page(url: str) -> dict:
    last_error: Exception | None = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Referer": "https://quote.eastmoney.com/",
                },
            )
            return json.loads(urllib.request.urlopen(request, timeout=30).read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - network retry
            last_error = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"failed to fetch {url}: {last_error}")


def main() -> None:
    name_map = fetch_name_map()
    OUTPUT_PATH.write_text(json.dumps(name_map, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVED] {OUTPUT_PATH}")
    print(f"[TOTAL] {len(name_map)}")


if __name__ == "__main__":
    main()
