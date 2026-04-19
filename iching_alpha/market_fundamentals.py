"""Price, valuation, and fundamental snapshots from local qlib_data assets."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from .config import AppConfig


CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "default.yaml"
OVERRIDE_DIR = Path(r"D:\Github_Program\qlib_data\2026data")
PRICE_OVERRIDE_PATH = OVERRIDE_DIR / "yahoo_price_overrides.json"


@lru_cache(maxsize=1)
def load_app_config() -> AppConfig:
    return AppConfig.from_file(CONFIG_PATH)


def build_company_snapshot_bundle(symbol: str, as_of: str) -> dict[str, Any]:
    normalized = str(symbol).strip().upper()
    if normalized.endswith(".HK"):
        override = _load_hk_price_override(normalized)
        return _build_hk_bundle(normalized, override, pd.Timestamp(as_of))

    instrument = _to_instrument(normalized)
    ts_code = _to_ts_code(normalized)
    as_of_ts = pd.Timestamp(as_of)

    price_snapshot = _build_price_snapshot(instrument, as_of_ts)
    valuation_snapshot = _build_valuation_snapshot(ts_code, as_of_ts)
    fundamental_snapshot = _build_fundamental_snapshot(ts_code, normalized, as_of_ts)

    return {
        "price_snapshot": price_snapshot,
        "valuation_snapshot": valuation_snapshot,
        "fundamental_snapshot": fundamental_snapshot,
        "market_score": _build_market_score(price_snapshot, valuation_snapshot),
        "fundamental_score": _build_fundamental_score(fundamental_snapshot, valuation_snapshot),
    }


def _build_price_snapshot(instrument: str, as_of_ts: pd.Timestamp) -> dict[str, Any]:
    config = load_app_config()
    try:
        df = pd.read_parquet(
            config.parquet_path,
            filters=[("instrument", "==", instrument), ("datetime", "<=", as_of_ts)],
            columns=["datetime", "instrument", "$close", "$high", "$low", "$turnover"],
        )
    except Exception:
        df = pd.read_parquet(
            config.parquet_path,
            columns=["datetime", "instrument", "$close", "$high", "$low", "$turnover"],
        )
        df = df[(df["instrument"] == instrument) & (pd.to_datetime(df["datetime"]) <= as_of_ts)]

    if df.empty:
        return {"status": "missing", "reason": "price data unavailable"}

    df["datetime"] = pd.to_datetime(df["datetime"])
    df = df.sort_values("datetime")
    latest = df.iloc[-1]
    closes = df["$close"].astype(float)
    latest_close = float(latest["$close"])
    prev_close = float(closes.iloc[-2]) if len(closes) >= 2 else latest_close
    close_20 = closes.tail(20)
    close_60 = closes.tail(60)
    return {
        "status": "ok",
        "as_of": latest["datetime"].strftime("%Y-%m-%d"),
        "latest_price": round(latest_close, 3),
        "previous_close": round(prev_close, 3) if prev_close else None,
        "day_change_pct": round(((latest_close / prev_close) - 1) * 100, 2) if prev_close else 0.0,
        "position_20d_pct": _window_position(close_20),
        "position_60d_pct": _window_position(close_60),
        "sma20": round(float(close_20.mean()), 3),
        "sma60": round(float(close_60.mean()), 3),
        "turnover": round(float(latest["$turnover"]), 3) if not pd.isna(latest["$turnover"]) else None,
    }


def _build_valuation_snapshot(ts_code: str, as_of_ts: pd.Timestamp) -> dict[str, Any]:
    config = load_app_config()
    daily_basic_path = config.parquet_path.parent / "fundamental" / "daily_basic.parquet"
    if not daily_basic_path.exists():
        return {"status": "missing", "reason": "daily_basic.parquet unavailable"}

    try:
        df = pd.read_parquet(
            daily_basic_path,
            filters=[("ts_code", "==", ts_code), ("trade_date", "<=", as_of_ts)],
            columns=["ts_code", "trade_date", "pe_ttm", "pb", "ps_ttm", "total_mv", "circ_mv", "turnover_rate_f"],
        )
    except Exception:
        df = pd.read_parquet(daily_basic_path)
        df["trade_date"] = pd.to_datetime(df["trade_date"])
        df = df[(df["ts_code"] == ts_code) & (df["trade_date"] <= as_of_ts)]

    if df.empty:
        return {"status": "missing", "reason": "valuation data unavailable"}

    df["trade_date"] = pd.to_datetime(df["trade_date"])
    latest = df.sort_values("trade_date").iloc[-1]
    return {
        "status": "ok",
        "as_of": latest["trade_date"].strftime("%Y-%m-%d"),
        "pe_ttm": _safe_round(latest.get("pe_ttm")),
        "pb": _safe_round(latest.get("pb")),
        "ps_ttm": _safe_round(latest.get("ps_ttm")),
        "total_mv": _safe_round(latest.get("total_mv")),
        "circ_mv": _safe_round(latest.get("circ_mv")),
        "turnover_rate_f": _safe_round(latest.get("turnover_rate_f")),
    }


def _build_fundamental_snapshot(ts_code: str, symbol: str, as_of_ts: pd.Timestamp) -> dict[str, Any]:
    config = load_app_config()
    fundamental_dir = config.parquet_path.parent / "fundamental"
    fina_path = fundamental_dir / "fina_indicator.parquet"
    if not fina_path.exists():
        partial = fundamental_dir / "fina_indicator_partial.parquet"
        fina_path = partial if partial.exists() else fina_path
    if not fina_path.exists():
        return {"status": "missing", "reason": "fina indicator parquet unavailable"}

    try:
        df = pd.read_parquet(fina_path)
    except Exception as exc:
        return {"status": "missing", "reason": f"failed to read fundamentals: {exc}"}

    df["ann_date"] = pd.to_datetime(df["ann_date"], format="%Y%m%d", errors="coerce")
    filtered = df[(df["ts_code"] == ts_code) & (df["ann_date"] <= as_of_ts)]
    if filtered.empty:
        fallback = _build_fundamental_snapshot_from_ths(symbol, as_of_ts)
        if fallback:
            return fallback
        return {"status": "missing", "reason": "fundamental snapshot unavailable"}

    latest = filtered.sort_values(["ann_date", "end_date"]).iloc[-1]
    return {
        "status": "ok",
        "provider": "local-parquet",
        "announce_date": latest["ann_date"].strftime("%Y-%m-%d") if pd.notna(latest["ann_date"]) else None,
        "report_period": str(latest.get("end_date", "")),
        "roe_dt": _safe_round(latest.get("roe_dt")),
        "roa": _safe_round(latest.get("roa")),
        "grossprofit_margin": _safe_round(latest.get("grossprofit_margin")),
        "netprofit_yoy": _safe_round(latest.get("netprofit_yoy")),
        "revenue_yoy": _safe_round(latest.get("or_yoy")),
        "operating_profit_yoy": _safe_round(latest.get("op_yoy")),
        "eps": _safe_round(latest.get("eps")),
        "bps": _safe_round(latest.get("bps")),
        "cfps": _safe_round(latest.get("cfps")),
        "debt_to_assets": _safe_round(latest.get("debt_to_assets")),
    }


@lru_cache(maxsize=64)
def _load_a_share_abstract_payload(symbol: str) -> dict[str, Any] | None:
    try:
        import akshare as ak
    except ModuleNotFoundError:
        return None

    abstract = None
    abstract_new = None
    try:
        abstract = ak.stock_financial_abstract(symbol=symbol)
    except Exception:
        abstract = None
    try:
        abstract_new = ak.stock_financial_abstract_new_ths(symbol=symbol)
    except Exception:
        abstract_new = None

    if abstract is None and abstract_new is None:
        return None
    return {"abstract": abstract, "abstract_new": abstract_new}


def _build_fundamental_snapshot_from_ths(symbol: str, as_of_ts: pd.Timestamp) -> dict[str, Any] | None:
    payload = _load_a_share_abstract_payload(symbol)
    if not payload:
        return None

    report_period = _latest_report_period(payload, as_of_ts)
    if report_period is None:
        return None

    report_key = report_period.strftime("%Y%m%d")
    abstract = payload.get("abstract")
    abstract_new = payload.get("abstract_new")

    roe_dt = _ths_new_value(abstract_new, report_period, ["index_weighted_avg_roe", "index_full_diluted_roe"])
    gross_margin = _first_not_none(
        _ths_abstract_value(abstract, "毛利率", report_key),
        _ths_new_value(abstract_new, report_period, ["sale_gross_margin"]),
    )
    netprofit_yoy = _ths_new_value(
        abstract_new,
        report_period,
        ["calculate_parent_holder_net_profit_yoy_growth_ratio", "deduct_net_profit_yoy_growth_ratio"],
    )
    revenue_yoy = _ths_new_value(
        abstract_new,
        report_period,
        ["calculate_operating_income_total_yoy_growth_ratio"],
    )
    eps = _first_not_none(
        _ths_abstract_value(abstract, "每股收益", report_key),
        _ths_new_value(abstract_new, report_period, ["basic_eps"]),
    )
    bps = _first_not_none(
        _ths_abstract_value(abstract, "每股净资产", report_key),
        _ths_new_value(abstract_new, report_period, ["calc_per_net_assets"]),
    )
    cfps = _ths_abstract_value(abstract, "每股经营现金流", report_key)
    debt_to_assets = _first_not_none(
        _ths_abstract_value(abstract, "资产负债率", report_key),
        _ths_new_value(abstract_new, report_period, ["assets_debt_ratio"]),
    )

    populated = [
        roe_dt,
        gross_margin,
        netprofit_yoy,
        revenue_yoy,
        eps,
        bps,
        cfps,
        debt_to_assets,
    ]
    if not any(value is not None for value in populated):
        return None

    return {
        "status": "ok",
        "provider": "ths-abstract",
        "announce_date": report_period.strftime("%Y-%m-%d"),
        "report_period": report_key,
        "roe_dt": _safe_round(roe_dt),
        "roa": None,
        "grossprofit_margin": _safe_round(gross_margin),
        "netprofit_yoy": _safe_round(netprofit_yoy),
        "revenue_yoy": _safe_round(revenue_yoy),
        "operating_profit_yoy": None,
        "eps": _safe_round(eps),
        "bps": _safe_round(bps),
        "cfps": _safe_round(cfps),
        "debt_to_assets": _safe_round(debt_to_assets),
    }


def _latest_report_period(payload: dict[str, Any], as_of_ts: pd.Timestamp) -> pd.Timestamp | None:
    candidates: list[pd.Timestamp] = []
    abstract = payload.get("abstract")
    if isinstance(abstract, pd.DataFrame):
        for column in abstract.columns:
            text = str(column)
            if len(text) == 8 and text.isdigit():
                ts = pd.to_datetime(text, format="%Y%m%d", errors="coerce")
                if pd.notna(ts) and ts <= as_of_ts:
                    candidates.append(ts)
    abstract_new = payload.get("abstract_new")
    if isinstance(abstract_new, pd.DataFrame) and "report_date" in abstract_new.columns:
        dates = pd.to_datetime(abstract_new["report_date"], errors="coerce")
        for ts in dates.dropna().unique().tolist():
            stamp = pd.Timestamp(ts)
            if stamp <= as_of_ts:
                candidates.append(stamp)
    if not candidates:
        return None
    return max(candidates)


def _ths_abstract_value(df: pd.DataFrame | None, metric_name: str, report_key: str) -> float | None:
    if not isinstance(df, pd.DataFrame) or metric_name not in set(df.get("指标", [])) or report_key not in df.columns:
        return None
    row = df[df["指标"] == metric_name]
    if row.empty:
        return None
    return _to_float(row.iloc[0].get(report_key))


def _ths_new_value(df: pd.DataFrame | None, report_period: pd.Timestamp, metric_names: list[str]) -> float | None:
    if not isinstance(df, pd.DataFrame) or "report_date" not in df.columns or "metric_name" not in df.columns:
        return None
    frame = df.copy()
    frame["report_date"] = pd.to_datetime(frame["report_date"], errors="coerce")
    report_day = pd.Timestamp(report_period).normalize()
    filtered = frame[
        (frame["report_date"].dt.normalize() == report_day)
        & (frame["metric_name"].isin(metric_names))
    ]
    if filtered.empty:
        return None
    for metric_name in metric_names:
        sub = filtered[filtered["metric_name"] == metric_name]
        if sub.empty:
            continue
        value = _to_float(sub.iloc[0].get("value"))
        if value is not None:
            return value
    return None


def _to_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_not_none(*values: Any) -> Any:
    for value in values:
        if value is not None:
            return value
    return None


def _build_market_score(price_snapshot: dict[str, Any], valuation_snapshot: dict[str, Any]) -> dict[str, Any]:
    if price_snapshot.get("status") != "ok":
        return {"score": 50, "label": "未生成", "reason": "缺少价格快照"}
    score = 50
    if price_snapshot["latest_price"] >= price_snapshot["sma20"]:
        score += 12
    if price_snapshot["position_20d_pct"] <= 80:
        score += 8
    if abs(price_snapshot["day_change_pct"]) <= 4:
        score += 5
    if valuation_snapshot.get("status") == "ok" and valuation_snapshot.get("turnover_rate_f") is not None:
        if valuation_snapshot["turnover_rate_f"] <= 8:
            score += 5
    score = max(0, min(100, score))
    return {"score": score, "label": _score_label(score), "reason": "价格位置、均线关系和换手率综合评估"}


def _build_fundamental_score(fundamental_snapshot: dict[str, Any], valuation_snapshot: dict[str, Any]) -> dict[str, Any]:
    if fundamental_snapshot.get("status") != "ok":
        return {"score": 50, "label": "未生成", "reason": "缺少财务快照"}
    score = 45
    if (fundamental_snapshot.get("roe_dt") or 0) >= 8:
        score += 12
    if (fundamental_snapshot.get("netprofit_yoy") or 0) >= 0:
        score += 10
    if (fundamental_snapshot.get("revenue_yoy") or 0) >= 0:
        score += 8
    debt_to_assets = fundamental_snapshot.get("debt_to_assets")
    if debt_to_assets is not None and debt_to_assets <= 65:
        score += 8
    pe_ttm = valuation_snapshot.get("pe_ttm") if valuation_snapshot.get("status") == "ok" else None
    if pe_ttm is not None and 0 < pe_ttm <= 40:
        score += 7
    score = max(0, min(100, score))
    return {"score": score, "label": _score_label(score), "reason": "盈利增速、ROE、负债率和估值综合评估"}


def _build_hk_bundle(symbol: str, price_override: dict[str, Any] | None, as_of_ts: pd.Timestamp) -> dict[str, Any]:
    valuation_snapshot, fundamental_snapshot = _build_hk_financial_snapshots(symbol, as_of_ts)
    if price_override:
        return {
            "price_snapshot": price_override,
            "valuation_snapshot": valuation_snapshot,
            "fundamental_snapshot": fundamental_snapshot,
            "market_score": _build_market_score(price_override, valuation_snapshot),
            "fundamental_score": _build_fundamental_score(fundamental_snapshot, valuation_snapshot),
        }
    placeholder = {"status": "missing", "reason": f"{symbol} 暂未接入港股价格快照覆盖数据"}
    return {
        "price_snapshot": placeholder,
        "valuation_snapshot": valuation_snapshot,
        "fundamental_snapshot": fundamental_snapshot,
        "market_score": {"score": 50, "label": "未生成", "reason": "港股数据快照待接入"},
        "fundamental_score": _build_fundamental_score(fundamental_snapshot, valuation_snapshot),
    }


@lru_cache(maxsize=1)
def _load_hk_override_document() -> dict[str, Any]:
    if not PRICE_OVERRIDE_PATH.exists():
        return {}
    try:
        import json

        return json.loads(PRICE_OVERRIDE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_hk_price_override(symbol: str) -> dict[str, Any] | None:
    document = _load_hk_override_document()
    items = document.get("items", {}) if isinstance(document, dict) else {}
    payload = items.get(symbol)
    if not isinstance(payload, dict):
        return None
    return payload


@lru_cache(maxsize=32)
def _load_hk_indicator_payload(symbol: str) -> dict[str, Any] | None:
    code = _to_hk_code(symbol)
    try:
        import akshare as ak
    except ModuleNotFoundError:
        return None

    # Try the simpler consolidated endpoint first.
    try:
        df = ak.stock_hk_financial_indicator_em(symbol=code)
        if not df.empty:
            return {"source": "stock_hk_financial_indicator_em", "row": df.iloc[0].to_dict()}
    except Exception:
        pass

    try:
        df = ak.stock_financial_hk_analysis_indicator_em(symbol=code)
        if not df.empty:
            df["REPORT_DATE"] = pd.to_datetime(df["REPORT_DATE"], errors="coerce")
            row = df.sort_values("REPORT_DATE").iloc[-1].to_dict()
            return {"source": "stock_financial_hk_analysis_indicator_em", "row": row}
    except Exception:
        pass

    return None


def _build_hk_financial_snapshots(symbol: str, as_of_ts: pd.Timestamp) -> tuple[dict[str, Any], dict[str, Any]]:
    del as_of_ts
    payload = _load_hk_indicator_payload(symbol)
    if not payload:
        missing = {"status": "missing", "reason": f"{symbol} 港股估值/财务接口暂未返回结果"}
        return missing, missing

    row = payload["row"]
    source = payload["source"]
    valuation = {
        "status": "ok",
        "as_of": _hk_report_date(row),
        "pe_ttm": _safe_round(row.get("市盈率") or row.get("PE_TTM")),
        "pb": _safe_round(row.get("市净率") or row.get("PB_TTM")),
        "ps_ttm": None,
        "total_mv": _safe_round(row.get("总市值(港元)") or row.get("TOTAL_MARKET_CAP")),
        "circ_mv": _safe_round(row.get("港股市值(港元)") or row.get("HKSK_MARKET_CAP")),
        "turnover_rate_f": None,
        "provider": source,
    }
    fundamental = {
        "status": "ok",
        "announce_date": _hk_report_date(row),
        "report_period": _hk_report_date(row),
        "roe_dt": _safe_round(row.get("股东权益回报率(%)") or row.get("ROE_AVG")),
        "roa": _safe_round(row.get("总资产回报率(%)") or row.get("ROA")),
        "grossprofit_margin": _safe_round(row.get("毛利率") or row.get("GROSS_PROFIT_RATIO")),
        "netprofit_yoy": _safe_round(row.get("净利润滚动环比增长(%)") or row.get("HOLDER_PROFIT_YOY")),
        "revenue_yoy": _safe_round(row.get("营业总收入滚动环比增长(%)") or row.get("OPERATE_INCOME_YOY")),
        "operating_profit_yoy": None,
        "eps": _safe_round(row.get("基本每股收益(元)") or row.get("BASIC_EPS")),
        "bps": _safe_round(row.get("每股净资产(元)") or row.get("BPS")),
        "cfps": _safe_round(row.get("每股经营现金流(元)") or row.get("PER_NETCASH_OPERATE")),
        "debt_to_assets": _safe_round(row.get("资产负债率") or row.get("DEBT_ASSET_RATIO")),
        "provider": source,
    }
    return valuation, fundamental


def build_execution_plan(
    action: str,
    target_return_pct: float,
    price_snapshot: dict[str, Any],
    technical_overlay: dict[str, Any],
    beneficiary_score: dict[str, Any] | None = None,
) -> dict[str, Any]:
    beneficiary_score = beneficiary_score or {}
    if price_snapshot.get("status") != "ok":
        return {
            "status": "missing",
            "reason": price_snapshot.get("reason", "缺少价格快照，无法生成建议价位"),
        }

    latest_price = float(price_snapshot.get("latest_price") or 0)
    previous_close = price_snapshot.get("previous_close")
    if previous_close is None:
        previous_close = price_snapshot.get("prev_close")
    if previous_close is None:
        previous_close = latest_price
    entry_discount = 0.99 if action in {"买入", "持有"} else 1.0
    beneficiary_level = str(beneficiary_score.get("level", "") or "")
    beneficiary_rank = int(beneficiary_score.get("rank") or 99)
    if beneficiary_level in {"直接受益", "核心受益", "高优先级"} and beneficiary_rank <= 3:
        entry_discount += 0.005
    elif beneficiary_level in {"弱相关", "低优先级"}:
        entry_discount -= 0.02
    elif beneficiary_level in {"主题映射", "间接受益"}:
        entry_discount -= 0.01
    if technical_overlay.get("provider_status", "").startswith("fallback:"):
        entry_discount -= 0.01
    suggested_buy = round(latest_price * entry_discount, 3) if action in {"买入", "持有", "观察"} else None
    target_gain = max(0.03, min(0.18, float(target_return_pct or 0) / 100))
    if beneficiary_level in {"直接受益", "核心受益", "高优先级"} and beneficiary_rank <= 3:
        target_gain = min(0.22, target_gain + 0.02)
    elif beneficiary_level in {"弱相关", "低优先级"}:
        target_gain = max(0.02, target_gain - 0.03)
    elif beneficiary_level in {"主题映射", "间接受益"}:
        target_gain = max(0.03, target_gain - 0.02)
    suggested_sell = round(latest_price * (1 + target_gain), 3) if action != "卖出" else round(latest_price * 0.99, 3)
    return {
        "status": "ok",
        "yesterday_close": round(float(previous_close), 3),
        "latest_available_close": round(latest_price, 3),
        "suggested_buy_price": suggested_buy,
        "suggested_sell_price": suggested_sell,
        "pricing_note": _pricing_note(action, technical_overlay, beneficiary_score),
    }


def _pricing_note(action: str, technical_overlay: dict[str, Any], beneficiary_score: dict[str, Any]) -> str:
    trend = technical_overlay.get("trend_alignment", "未生成")
    beneficiary_level = str(beneficiary_score.get("level", "") or "")
    beneficiary_rank = beneficiary_score.get("rank")
    rank_note = ""
    if beneficiary_rank:
        rank_note = f"；AI 受益排序第 {beneficiary_rank} 位 / {beneficiary_level or '未分类'}"
    if action == "买入":
        return f"建议靠近支撑位分批买入，当前技术状态：{trend}{rank_note}"
    if action == "持有":
        return f"建议等待回踩确认后再加仓，当前技术状态：{trend}{rank_note}"
    if action == "卖出":
        return f"建议优先在反弹或弱势确认时卖出，当前技术状态：{trend}{rank_note}"
    return f"先观察，不追高，当前技术状态：{trend}{rank_note}"


def _hk_report_date(row: dict[str, Any]) -> str | None:
    value = row.get("REPORT_DATE")
    if value is None or pd.isna(value):
        return None
    return pd.to_datetime(value).strftime("%Y-%m-%d")


def _to_hk_code(symbol: str) -> str:
    code = str(symbol).strip().upper().replace(".HK", "")
    return code.zfill(5)


def _to_instrument(symbol: str) -> str:
    if symbol.startswith("6"):
        return "SH" + symbol
    return "SZ" + symbol


def _to_ts_code(symbol: str) -> str:
    if symbol.startswith("6"):
        return symbol + ".SH"
    return symbol + ".SZ"


def _window_position(series: pd.Series) -> float | None:
    if series.empty:
        return None
    highest = float(series.max())
    lowest = float(series.min())
    latest = float(series.iloc[-1])
    if highest == lowest:
        return 50.0
    return round((latest - lowest) / (highest - lowest) * 100, 1)


def _safe_round(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 3)


def _score_label(score: int) -> str:
    if score >= 80:
        return "强"
    if score >= 65:
        return "较强"
    if score >= 50:
        return "中性"
    return "偏弱"
