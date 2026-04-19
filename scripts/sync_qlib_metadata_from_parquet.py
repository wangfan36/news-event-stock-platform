from __future__ import annotations

from pathlib import Path

import pandas as pd


DATA_ROOT = Path(r"D:\Github_Program\qlib_data")
PARQUET_PATH = DATA_ROOT / "daily_pv_akshare.parquet"
QLIB_DIR = DATA_ROOT / "qlib_format"
CALENDAR_PATH = QLIB_DIR / "calendars" / "day.txt"
INSTRUMENTS_DIR = QLIB_DIR / "instruments"


def main() -> None:
    df = pd.read_parquet(PARQUET_PATH, columns=["datetime", "instrument"])
    df["datetime"] = pd.to_datetime(df["datetime"])
    stats = (
        df.groupby("instrument")["datetime"]
        .agg(["min", "max"])
        .sort_index()
        .reset_index()
    )
    stats["symbol"] = stats["instrument"].astype(str).str[-6:]
    symbol_map = {
        row["symbol"]: {
            "start": pd.Timestamp(row["min"]).strftime("%Y-%m-%d"),
            "end": pd.Timestamp(row["max"]).strftime("%Y-%m-%d"),
        }
        for _, row in stats.iterrows()
    }

    write_calendar(df["datetime"].drop_duplicates().sort_values())
    write_all_instruments(symbol_map)
    update_existing_universe_files(symbol_map)

    print("[OK] qlib metadata synced from parquet")
    print(f"calendar_last={max(symbol_map.values(), key=lambda item: item['end'])['end']}")
    print(f"all_symbols={len(symbol_map)}")


def write_calendar(dates: pd.Series) -> None:
    CALENDAR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR_PATH.write_text(
        "\n".join(pd.Series(dates).dt.strftime("%Y-%m-%d").tolist()) + "\n",
        encoding="utf-8",
    )


def write_all_instruments(symbol_map: dict[str, dict[str, str]]) -> None:
    INSTRUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        f"{symbol}\t{meta['start']}\t{meta['end']}"
        for symbol, meta in sorted(symbol_map.items())
    ]
    existing_all = INSTRUMENTS_DIR / "all.txt"
    if existing_all.exists():
        existing_rows = [line.strip() for line in existing_all.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in existing_rows:
            parts = row.split("\t")
            code = parts[0].strip()
            if code.isdigit():
                continue
            if any(line.startswith(code + "\t") for line in lines):
                continue
            if len(parts) >= 3:
                lines.append(f"{code}\t{parts[1].strip()}\t{parts[2].strip()}")
    (INSTRUMENTS_DIR / "all.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def update_existing_universe_files(symbol_map: dict[str, dict[str, str]]) -> None:
    for path in INSTRUMENTS_DIR.glob("*.txt"):
        if path.name == "all.txt":
            continue
        rows = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        updated: list[str] = []
        for row in rows:
            parts = row.split("\t")
            symbol = parts[0].strip().zfill(6)
            if symbol not in symbol_map:
                continue
            meta = symbol_map[symbol]
            updated.append(f"{symbol}\t{meta['start']}\t{meta['end']}")
        path.write_text("\n".join(updated) + ("\n" if updated else ""), encoding="utf-8")


if __name__ == "__main__":
    main()
