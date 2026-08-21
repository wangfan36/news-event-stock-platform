from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG_PATH = ROOT / "news_alpha" / "catalogs" / "high_quality_development_universe.json"


HQD_GROUPS: dict[str, dict[str, object]] = {
    "digital_economy": {
        "label": "新一代信息技术与数字经济",
        "industries": ["电子", "计算机", "通信", "传媒"],
        "rationale": "面向数字经济、人工智能、算力基础设施、工业软件和信息网络升级。",
    },
    "advanced_manufacturing": {
        "label": "高端装备与智能制造",
        "industries": ["机械设备", "国防军工", "汽车"],
        "rationale": "面向高端装备、智能制造、机器人、航空航天、低空经济和先进交通装备。",
    },
    "green_transition": {
        "label": "绿色低碳与能源转型",
        "industries": ["电力设备", "公用事业", "环保", "有色金属", "石油石化"],
        "rationale": "面向新能源、储能、电网、节能环保和能源体系转型。",
    },
    "advanced_materials": {
        "label": "新材料与先进制造底层支撑",
        "industries": ["基础化工", "有色金属", "钢铁"],
        "rationale": "面向先进材料、化工新材料、半导体材料和高端金属材料。",
    },
    "bio_health": {
        "label": "生物医药与高端医疗器械",
        "industries": ["医药生物"],
        "rationale": "面向创新药、医疗器械、生物制造和生命健康。",
    },
    "modern_logistics": {
        "label": "现代物流与高端运输",
        "industries": ["交通运输"],
        "rationale": "面向现代物流、航运升级和产业链供应链效率提升。",
    },
}


def load_industry_mapping(path: Path) -> dict[str, str]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_instruments(path: Path) -> set[str]:
    symbols: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if parts:
            symbol = parts[0].strip().upper()
            if symbol[:2] in {"SH", "SZ", "BJ"}:
                symbol = symbol[2:]
            if symbol.isdigit() and len(symbol) == 6:
                symbols.add(symbol)
    return symbols


def build_universe(industry_mapping_path: Path, instruments_path: Path) -> dict[str, object]:
    industry_mapping = load_industry_mapping(industry_mapping_path)
    live_instruments = load_instruments(instruments_path)
    by_group: dict[str, dict[str, object]] = {}
    all_symbols: set[str] = set()

    for group_id, payload in HQD_GROUPS.items():
        industries = payload["industries"]
        group_symbols = sorted(
            symbol
            for symbol, industry in industry_mapping.items()
            if symbol in live_instruments and industry in industries
        )
        all_symbols.update(group_symbols)
        by_industry: dict[str, list[str]] = defaultdict(list)
        for symbol in group_symbols:
            by_industry[industry_mapping[symbol]].append(symbol)
        by_group[group_id] = {
            "label": payload["label"],
            "rationale": payload["rationale"],
            "industries": industries,
            "company_count": len(group_symbols),
            "symbols": group_symbols,
            "by_industry": dict(sorted(by_industry.items())),
        }

    coverage = Counter(industry_mapping[symbol] for symbol in all_symbols)
    return {
        "generated_from": str(industry_mapping_path),
        "instrument_source": str(instruments_path),
        "group_count": len(by_group),
        "total_company_count": len(all_symbols),
        "groups": by_group,
        "industry_coverage": dict(sorted(coverage.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--industry-mapping", type=Path, required=True)
    parser.add_argument("--instruments", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=CATALOG_PATH)
    args = parser.parse_args()
    payload = build_universe(args.industry_mapping, args.instruments)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[SAVED] {args.output}")
    print(f"[GROUPS] {payload['group_count']}")
    print(f"[TOTAL] {payload['total_company_count']}")
    for group_id, group in payload["groups"].items():
        print(f"[{group_id}] {group['label']} -> {group['company_count']}")


if __name__ == "__main__":
    main()
