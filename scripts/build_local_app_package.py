"""Build a portable local trial package without private data."""

from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DIST_DIR = ROOT / "dist"
PACKAGE_NAME = "新闻事件推演选股平台-local"
PACKAGE_DIR = DIST_DIR / PACKAGE_NAME
ZIP_PATH = DIST_DIR / f"{PACKAGE_NAME}.zip"

COPY_DIRS = ("iching_alpha", "config", "scripts")
COPY_FILES = (
    "README.md",
    "README_TRIAL.md",
    "requirements.txt",
    "00_install_dependencies.bat",
    "01_check_environment.bat",
    "02_start_app.bat",
    "03_stop_app.bat",
)
EXCLUDED_DIR_NAMES = {"__pycache__", ".pytest_cache"}
EXCLUDED_SUFFIXES = {".pyc", ".pyo"}


def main() -> int:
    DIST_DIR.mkdir(exist_ok=True)
    if PACKAGE_DIR.exists():
        shutil.rmtree(PACKAGE_DIR)
    PACKAGE_DIR.mkdir(parents=True)

    for dirname in COPY_DIRS:
        source = ROOT / dirname
        target = PACKAGE_DIR / dirname
        if source.exists():
            shutil.copytree(source, target, ignore=_ignore)

    for filename in COPY_FILES:
        source = ROOT / filename
        if source.exists():
            shutil.copy2(source, PACKAGE_DIR / filename)

    for child in ("db", "cache", "logs", "backups"):
        (PACKAGE_DIR / "artifacts" / child).mkdir(parents=True, exist_ok=True)
        (PACKAGE_DIR / "artifacts" / child / ".gitkeep").write_text("", encoding="utf-8")

    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    shutil.make_archive(str(ZIP_PATH.with_suffix("")), "zip", PACKAGE_DIR)
    print(f"已生成目录: {PACKAGE_DIR}")
    print(f"已生成压缩包: {ZIP_PATH}")
    return 0


def _ignore(directory: str, names: list[str]) -> set[str]:
    ignored: set[str] = set()
    for name in names:
        path = Path(directory) / name
        if name in EXCLUDED_DIR_NAMES:
            ignored.add(name)
        elif path.suffix in EXCLUDED_SUFFIXES:
            ignored.add(name)
    return ignored


if __name__ == "__main__":
    raise SystemExit(main())
