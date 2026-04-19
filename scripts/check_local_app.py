"""Local trial package environment checks."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config" / "default.yaml"
REQUIRED_MODULES = ("flask", "pandas", "yaml", "akshare")


def main() -> int:
    print("新闻事件推演选股平台 - 本地环境检查")
    print(f"项目目录: {ROOT}")
    print(f"Python: {sys.version.split()[0]}")
    failed = False

    for module_name in REQUIRED_MODULES:
        try:
            importlib.import_module(module_name)
            print(f"[OK] Python 依赖: {module_name}")
        except Exception as exc:
            failed = True
            print(f"[FAIL] Python 依赖: {module_name} / {exc}")

    if not CONFIG_PATH.exists():
        print(f"[FAIL] 配置文件不存在: {CONFIG_PATH}")
        return 1

    config = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    path_keys = ("qlib_provider_uri", "parquet_path", "industry_mapping_path")
    for key in path_keys:
        raw_value = str(config.get(key, "") or "")
        path = Path(raw_value)
        if path.exists():
            print(f"[OK] {key}: {path}")
        else:
            failed = True
            print(f"[FAIL] {key}: {path}")

    artifacts = ROOT / "artifacts"
    for child in ("db", "cache", "logs", "backups"):
        path = artifacts / child
        path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] artifacts/{child}")

    if failed:
        print("")
        print("检查未通过。请先确认 requirements 已安装，并在 config/default.yaml 中配置正确的 qlib_data 路径。")
        return 1

    print("")
    print("检查通过。可以双击 02_start_app.bat 启动。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
