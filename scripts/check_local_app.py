"""Validate the local runtime without requiring optional market data."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_MODULES = ("flask", "pandas", "yaml")
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    print("News Alpha - local environment check")
    print(f"Project: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    failed = sys.version_info < (3, 10)
    if failed:
        print("[FAIL] Python 3.10 or newer is required")

    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
            print(f"[OK] dependency: {module_name}")
        except Exception as exc:
            failed = True
            print(f"[FAIL] dependency: {module_name} / {exc}")

    for child in ("db", "cache", "logs", "data"):
        path = ROOT / "artifacts" / child
        path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] writable: {path.relative_to(ROOT)}")

    try:
        from news_alpha.webapp import create_app

        client = create_app().test_client()
        response = client.get("/api/health")
        if response.status_code != 200:
            raise RuntimeError(f"health endpoint returned {response.status_code}")
        print("[OK] application health endpoint")
    except Exception as exc:
        failed = True
        print(f"[FAIL] application import/health: {exc}")

    print("FAILED" if failed else "READY: run python -m news_alpha.webapp")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
