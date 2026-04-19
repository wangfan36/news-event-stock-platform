from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from iching_alpha.overrides import build_hk_price_overrides  # noqa: E402


if __name__ == "__main__":
    result = build_hk_price_overrides()
    print(f"[SAVED] {result['path']}")
    print(f"[COUNT] {result['count']}")
    print(f"[LATEST] {result['latest_as_of']}")
    if result["misses"]:
        print("[MISS]", ", ".join(result["misses"]))
