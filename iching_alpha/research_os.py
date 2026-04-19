"""News-driven stock selection system v1."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from .catalogs import (
    A_SHARE_NAME_MAP as FILE_A_SHARE_NAME_MAP,
    COMPANY_CATALOG as FILE_COMPANY_CATALOG,
    EVENT_BLUEPRINTS as FILE_EVENT_BLUEPRINTS,
    HIGH_QUALITY_DEVELOPMENT_UNIVERSE as FILE_HIGH_QUALITY_DEVELOPMENT_UNIVERSE,
    INDUSTRY_CATALOG as FILE_INDUSTRY_CATALOG,
)
from .ai_research_pipeline import build_ai_research_pipeline
from .config import AppConfig
from .data import load_universe_symbols, normalize_symbol
from .event_engine import (
    build_event_identity,
    build_event_profit_propagation,
    build_industry_profit_map,
)
from .market_fundamentals import build_company_snapshot_bundle, build_execution_plan
from .model_client import refine_workspace_with_model
from .news_pipeline import deduplicate_and_cluster_news, load_demo_raw_news_feed
from .news_sources import fetch_live_raw_news_feed, parse_custom_rss_sources
from .portfolio_manager import build_portfolio_plan
from .recommendation_manager import synthesize_recommendation
from .storage import default_db_path, load_recent_crowding_context
from .technical_provider import build_market_snapshot, get_symbol_technical_overlay


REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS_DIR = REPO_ROOT / "artifacts"
BANNED_COPY_TERMS = ("稳赚", "自动荐股", "AI顾问", "AI 顾问", "保收益")


@dataclass(frozen=True)
class HoldingInput:
    symbol: str
    name: str
    position_pct: float
    thesis: str

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "HoldingInput":
        raw_symbol = str(payload.get("symbol", ""))
        symbol = normalize_symbol(raw_symbol)
        if not symbol:
            raise ValueError("Each watchlist entry needs a symbol.")
        profile = _company_profile(symbol)
        default_name = profile["name"] if profile else symbol
        return cls(
            symbol=symbol,
            name=str(payload.get("name") or default_name),
            position_pct=max(0.0, float(payload.get("position_pct", 0.0) or 0.0)),
            thesis=str(payload.get("thesis", "")).strip(),
        )


@dataclass(frozen=True)
class RiskThresholds:
    single_name_limit_pct: float
    sector_limit_pct: float
    negative_event_score_threshold: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any] | None) -> "RiskThresholds":
        data = payload or {}
        return cls(
            single_name_limit_pct=float(data.get("single_name_limit_pct", 15.0) or 15.0),
            sector_limit_pct=float(data.get("sector_limit_pct", 30.0) or 30.0),
            negative_event_score_threshold=int(data.get("negative_event_score_threshold", 70) or 70),
        )


@dataclass(frozen=True)
class ResearchRequest:
    watchlist: tuple[HoldingInput, ...]
    focus_topics: tuple[str, ...]
    risk_thresholds: RiskThresholds
    personal_notes: str
    use_live_news: bool
    rss_sources_text: str
    technical_settings: dict[str, Any]
    model_settings: dict[str, Any]
    recommendation_limit: int

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "ResearchRequest":
        watchlist = tuple(HoldingInput.from_dict(item) for item in payload.get("watchlist", []))
        focus_topics = tuple(_clean_topic(topic) for topic in payload.get("focus_topics", []) if _clean_topic(topic))
        risk_thresholds = RiskThresholds.from_dict(payload.get("risk_thresholds"))
        personal_notes = str(payload.get("personal_notes", "")).strip()
        return cls(
            watchlist=watchlist,
            focus_topics=focus_topics,
            risk_thresholds=risk_thresholds,
            personal_notes=personal_notes,
            use_live_news=bool(payload.get("use_live_news", False)),
            rss_sources_text=str(payload.get("rss_sources_text", "")).strip(),
            technical_settings=dict(payload.get("technical_settings", {}) or {}),
            model_settings=dict(payload.get("model_settings", {}) or {}),
            recommendation_limit=max(1, int(payload.get("recommendation_limit", 10) or 10)),
        )


INDUSTRY_CATALOG: dict[str, dict[str, Any]] = {
    "ai_optics": {
        "name": "AI 光模块与交换链",
        "description": "海外云厂商 capex 驱动的高速光模块、交换机和连接器链条。",
        "current_state": "订单景气仍高，但市场开始区分真实上量与提前备货。",
        "policy_dependency": "主要受海外云厂商资本开支影响，对国内政策依赖有限。",
        "import_export_dependency": "出口占比较高，海外需求波动会直接传导到交付节奏。",
        "structural_notes": [
            "高速光模块是利润中心，龙头集中度最高。",
            "上游光芯片仍有海外技术约束，国产替代在推进中。",
        ],
        "supply_chain": [
            {
                "node_id": "optical_chip",
                "name": "光芯片 / DSP",
                "stage": "上游",
                "concentration": "海外技术集中度高，国产突破仍在爬坡。",
                "value_contribution": "约占方案价值的 25%-35%。",
                "profit_level": "毛利率较高，但受技术代际切换影响大。",
                "demand_state": "受云厂商升级节奏驱动，景气维持高位。",
                "dependency_note": "海外供给和关键 IP 约束明显。",
                "representative_companies": ["300502", "00981.HK"],
            },
            {
                "node_id": "optical_module",
                "name": "高速光模块",
                "stage": "中游",
                "concentration": "龙头集中度高。",
                "value_contribution": "约占方案价值的 35%-45%。",
                "profit_level": "景气向上时利润弹性最大。",
                "demand_state": "当前是最直接的订单承接环节。",
                "dependency_note": "受交付能力、海外认证和良率影响。",
                "representative_companies": ["300308", "300502"],
            },
            {
                "node_id": "switch_interconnect",
                "name": "交换机 / 连接器",
                "stage": "下游配套",
                "concentration": "交换机格局稳固，连接器细分环节分散。",
                "value_contribution": "约占方案价值的 15%-25%。",
                "profit_level": "交换机利润稳定，连接器利润弹性更高。",
                "demand_state": "随着 cluster 扩容同步抬升。",
                "dependency_note": "交付节奏跟随整体网络升级。",
                "representative_companies": ["000063", "603083"],
            },
        ],
    },
    "semi_equipment": {
        "name": "半导体设备与国产替代",
        "description": "设备、零部件、晶圆厂共同构成的国产替代链条。",
        "current_state": "政策支持增强，但订单兑现仍要看晶圆厂 capex 与验证节奏。",
        "policy_dependency": "对设备更新、贴息和国产替代政策敏感。",
        "import_export_dependency": "关键零部件仍有进口依赖。",
        "structural_notes": [
            "设备龙头集中度高，零部件弹性更强但兑现更慢。",
            "晶圆厂是景气锚点，不是设备链利润中心。",
        ],
        "supply_chain": [
            {
                "node_id": "wafer_fab_equipment",
                "name": "刻蚀 / 薄膜 / 清洗设备",
                "stage": "中游核心",
                "concentration": "龙头集中，订单向头部聚集。",
                "value_contribution": "约占全链价值的 40%-50%。",
                "profit_level": "利润率较高，取决于产品验证进度。",
                "demand_state": "政策刺激下预期改善，兑现仍要看扩产。",
                "dependency_note": "验证周期长，受晶圆厂资本开支影响大。",
                "representative_companies": ["002371", "688981"],
            },
            {
                "node_id": "semi_parts",
                "name": "零部件",
                "stage": "上游",
                "concentration": "细分分散，但国产替代空间大。",
                "value_contribution": "约占全链价值的 15%-20%。",
                "profit_level": "批量导入后弹性明显。",
                "demand_state": "跟随设备订单释放。",
                "dependency_note": "依赖头部设备厂验证通过。",
                "representative_companies": ["688012", "002371"],
            },
            {
                "node_id": "wafer_fab",
                "name": "晶圆厂",
                "stage": "下游需求方",
                "concentration": "资本开支集中于头部晶圆厂。",
                "value_contribution": "决定订单持续性，不是设备链利润中心。",
                "profit_level": "利润率随景气波动较大。",
                "demand_state": "先进制程和成熟制程分化明显。",
                "dependency_note": "投资节奏决定设备链订单兑现速度。",
                "representative_companies": ["688981", "00981.HK"],
            },
        ],
    },
    "energy_storage": {
        "name": "储能电池与系统集成",
        "description": "由并网、招标和出海需求驱动的储能链。",
        "current_state": "招标节奏回升，市场关注从叙事转向订单兑现与利润弹性。",
        "policy_dependency": "高度依赖并网政策、电价机制和地方示范项目推进。",
        "import_export_dependency": "出海比例高，欧美储能政策与贸易环境重要。",
        "structural_notes": [
            "电芯和系统集成是价值贡献最高的环节。",
            "PCS/BMS 集中度高但利润弹性低于电芯。",
        ],
        "supply_chain": [
            {
                "node_id": "battery_cell",
                "name": "储能电芯",
                "stage": "中游核心",
                "concentration": "龙头主导，二线厂商依赖价格策略抢份额。",
                "value_contribution": "约占方案价值的 35%-45%。",
                "profit_level": "规模效应显著，毛利率受锂价影响。",
                "demand_state": "国内示范项目和海外订单共同拉动。",
                "dependency_note": "锂价和招标节奏是关键变量。",
                "representative_companies": ["300750", "300014"],
            },
            {
                "node_id": "pcs_bms",
                "name": "PCS / BMS",
                "stage": "配套环节",
                "concentration": "逆变器与 BMS 龙头集中度较高。",
                "value_contribution": "约占方案价值的 15%-20%。",
                "profit_level": "利润率稳定但弹性较弱。",
                "demand_state": "跟随系统集成同步确认。",
                "dependency_note": "项目并网和认证周期影响较大。",
                "representative_companies": ["300827", "688390"],
            },
            {
                "node_id": "system_integration",
                "name": "系统集成 / 电站交付",
                "stage": "下游交付",
                "concentration": "项目制特征明显，区域玩家较多。",
                "value_contribution": "约占方案价值的 25%-35%。",
                "profit_level": "净利率较低，但订单能见度强时弹性可观。",
                "demand_state": "审批与招标恢复后最先体现。",
                "dependency_note": "现金流和项目回款很关键。",
                "representative_companies": ["300693", "600406"],
            },
        ],
    },
    "shipping_energy": {
        "name": "油运与能源航运",
        "description": "地缘冲突、原油贸易流重构和运价波动共同驱动。",
        "current_state": "绕航与贸易流重构抬升运价，但市场担心持续性。",
        "policy_dependency": "受国际航运政策影响，但核心仍是地缘与供需。",
        "import_export_dependency": "国际贸易链条依赖度极高。",
        "structural_notes": [
            "船东利润弹性最大，船舶制造的兑现更滞后。",
            "上游油气资源更偏防御，不等于运价弹性。",
        ],
        "supply_chain": [
            {
                "node_id": "tanker_operator",
                "name": "油运船东",
                "stage": "核心运营",
                "concentration": "头部船东集中度提升。",
                "value_contribution": "约占全链利润兑现的 45%-55%。",
                "profit_level": "利润弹性极高。",
                "demand_state": "地缘冲突和贸易改道驱动运价抬升。",
                "dependency_note": "对运价和船舶供给极其敏感。",
                "representative_companies": ["600026", "01138.HK"],
            },
            {
                "node_id": "oil_major",
                "name": "上游油气资源",
                "stage": "上游资源",
                "concentration": "三桶油与国际巨头集中。",
                "value_contribution": "受益于油价和销量，不等同于运价弹性。",
                "profit_level": "现金流强，分红稳定。",
                "demand_state": "油价高位时提供安全垫。",
                "dependency_note": "地缘与 OPEC 政策是主变量。",
                "representative_companies": ["600938", "00883.HK"],
            },
            {
                "node_id": "shipyard",
                "name": "船舶制造",
                "stage": "上游供给",
                "concentration": "大型船厂集中，订单周期长。",
                "value_contribution": "兑现慢于运价，但受造船景气驱动。",
                "profit_level": "利润率中等。",
                "demand_state": "运价高位会带动新船订单。",
                "dependency_note": "交付周期长，适合中期观察。",
                "representative_companies": ["600150", "00317.HK"],
            },
        ],
    },
}


COMPANY_CATALOG: dict[str, dict[str, Any]] = {
    "300308": {"name": "中际旭创", "market": "A股", "industry_id": "ai_optics", "chain_roles": ["optical_module"], "business": "高速光模块龙头，直接受益于海外 AI 集群扩容。", "revenue_mix": ["数通光模块", "高速光器件"], "competition": "头部客户与交付能力构成壁垒。", "elasticity": "订单景气向上时利润弹性强。", "valuation_band": "高景气龙头估值区间。", "event_sensitivity": "对海外 capex、订单排产和 ASP 极敏感。", "ah_linkage": "与中芯国际、运营商链条存在景气联动。", "recent_vectors": ["800G/1.6T 交付节奏", "海外订单可见度", "ASP 稳定性"], "linkage_hint": "leader"},
    "300502": {"name": "新易盛", "market": "A股", "industry_id": "ai_optics", "chain_roles": ["optical_chip", "optical_module"], "business": "高速光模块与核心器件双覆盖，景气上行阶段业绩弹性高。", "revenue_mix": ["高速光模块", "有源器件"], "competition": "弹性强于绝对龙头，但对订单节奏更敏感。", "elasticity": "高 beta，适合作为景气交易的弹性标的。", "valuation_band": "估值跟随景气起伏明显。", "event_sensitivity": "对海外 capex 和客户切换更敏感。", "ah_linkage": "无直接 A/H 对应。", "recent_vectors": ["交付节奏", "新客户导入", "利润率修复"], "linkage_hint": "elastic"},
    "000063": {"name": "中兴通讯", "market": "A股", "industry_id": "ai_optics", "chain_roles": ["switch_interconnect"], "business": "交换机与网络设备龙头，受 AI 网络升级和运营商投资共振影响。", "revenue_mix": ["运营商网络", "数据中心网络"], "competition": "平台型公司，受益更偏稳健。", "elasticity": "业绩弹性低于纯光模块，但确定性更高。", "valuation_band": "估值相对稳健。", "event_sensitivity": "对网络升级和运营商资本开支敏感。", "ah_linkage": "A/H 两地投资者均关注。", "recent_vectors": ["数据中心交换机", "运营商订单"], "linkage_hint": "theme"},
    "603083": {"name": "剑桥科技", "market": "A股", "industry_id": "ai_optics", "chain_roles": ["switch_interconnect"], "business": "连接器与光通信配套环节受益者。", "revenue_mix": ["光模块配套", "高速连接"], "competition": "体量小于龙头，弹性强但稳定性弱。", "elasticity": "典型弹性标的。", "valuation_band": "估值对情绪敏感。", "event_sensitivity": "对主题热度和订单能见度敏感。", "ah_linkage": "无。", "recent_vectors": ["连接器订单", "主题热度"], "linkage_hint": "elastic"},
    "002371": {"name": "北方华创", "market": "A股", "industry_id": "semi_equipment", "chain_roles": ["wafer_fab_equipment", "semi_parts"], "business": "国产半导体设备龙头，订单和估值最能反映国产替代预期。", "revenue_mix": ["刻蚀", "薄膜沉积", "清洗"], "competition": "龙头地位清晰，验证进度决定估值中枢。", "elasticity": "政策强化时先反应，业绩兑现后具备持续性。", "valuation_band": "高端制造龙头估值区间。", "event_sensitivity": "对设备更新政策、晶圆厂 capex 和招标非常敏感。", "ah_linkage": "与中芯国际资本开支存在强联动。", "recent_vectors": ["订单验证", "零部件导入"], "linkage_hint": "leader"},
    "688981": {"name": "中芯国际", "market": "A股", "industry_id": "semi_equipment", "chain_roles": ["wafer_fab"], "business": "晶圆制造核心平台，是设备链订单持续性的关键需求方。", "revenue_mix": ["晶圆代工", "成熟制程"], "competition": "行业平台属性强。", "elasticity": "偏趋势型，承担景气锚点作用。", "valuation_band": "更看扩产与稼动率。", "event_sensitivity": "对扩产周期和供需格局敏感。", "ah_linkage": "与港股 00981.HK 为同主体两地上市。", "recent_vectors": ["产能利用率", "资本开支"], "linkage_hint": "theme"},
    "00981.HK": {"name": "中芯国际-H", "market": "港股", "industry_id": "semi_equipment", "chain_roles": ["wafer_fab"], "business": "港股视角下的晶圆制造龙头，估值弹性更高。", "revenue_mix": ["晶圆代工", "成熟制程"], "competition": "与 A 股同体，市场定价弹性更高。", "elasticity": "港股估值波动更大。", "valuation_band": "港股科技制造估值区间。", "event_sensitivity": "对政策与外资风格变化更敏感。", "ah_linkage": "与 A 股 688981 联动明显。", "recent_vectors": ["港股科技风险偏好", "资本开支"], "linkage_hint": "theme"},
    "300750": {"name": "宁德时代", "market": "A股", "industry_id": "energy_storage", "chain_roles": ["battery_cell"], "business": "储能电芯龙头，订单确定性和盈利兑现能力最强。", "revenue_mix": ["动力电池", "储能电池"], "competition": "全球龙头，规模与成本优势显著。", "elasticity": "项目放量时稳健受益。", "valuation_band": "龙头估值中枢相对稳定。", "event_sensitivity": "对项目招标、并网节奏和碳酸锂敏感。", "ah_linkage": "与新能源港股情绪联动。", "recent_vectors": ["储能出海", "电芯报价"], "linkage_hint": "leader"},
    "300014": {"name": "亿纬锂能", "market": "A股", "industry_id": "energy_storage", "chain_roles": ["battery_cell"], "business": "储能和动力双轮驱动，项目放量时业绩弹性更明显。", "revenue_mix": ["储能电池", "动力电池"], "competition": "二线龙头，弹性高于绝对龙头。", "elasticity": "储能景气上行时弹性强。", "valuation_band": "估值对出货兑现较敏感。", "event_sensitivity": "对招标价格与利润率波动敏感。", "ah_linkage": "无直接 A/H 对应。", "recent_vectors": ["储能项目拿单", "盈利修复"], "linkage_hint": "runner_up"},
    "300693": {"name": "盛弘股份", "market": "A股", "industry_id": "energy_storage", "chain_roles": ["system_integration", "pcs_bms"], "business": "系统集成和配套环节受益于储能项目放量。", "revenue_mix": ["PCS", "储能系统"], "competition": "中游配套，项目交付和回款决定质量。", "elasticity": "弹性高于龙头，但现金流要跟踪。", "valuation_band": "估值弹性较大。", "event_sensitivity": "对项目审批与并网时间很敏感。", "ah_linkage": "无。", "recent_vectors": ["项目中标", "并网"], "linkage_hint": "elastic"},
    "600026": {"name": "中远海能", "market": "A股", "industry_id": "shipping_energy", "chain_roles": ["tanker_operator"], "business": "油运龙头，地缘与运价冲击下利润弹性最直接。", "revenue_mix": ["VLCC", "成品油轮"], "competition": "运力和运营效率构成核心优势。", "elasticity": "运价上行阶段的核心弹性龙头。", "valuation_band": "周期股估值偏低。", "event_sensitivity": "对绕航、运价指数和制裁政策极敏感。", "ah_linkage": "与港股同板块龙头联动强。", "recent_vectors": ["运价指数", "航线重构"], "linkage_hint": "leader"},
    "01138.HK": {"name": "中远海能-H", "market": "港股", "industry_id": "shipping_energy", "chain_roles": ["tanker_operator"], "business": "港股视角下的油运龙头，弹性更受全球航运情绪影响。", "revenue_mix": ["油轮运输", "LNG 运输"], "competition": "运价上行时港股修复弹性通常更快。", "elasticity": "更偏事件交易型。", "valuation_band": "港股航运估值折价明显。", "event_sensitivity": "对运价和外资风险偏好极敏感。", "ah_linkage": "与 A 股 600026 强联动。", "recent_vectors": ["BDTI/BCTI", "港股资金风格"], "linkage_hint": "runner_up"},
    "00883.HK": {"name": "中国海洋石油", "market": "港股", "industry_id": "shipping_energy", "chain_roles": ["oil_major"], "business": "上游油气资源龙头，更多承担高油价与分红防御属性。", "revenue_mix": ["原油", "天然气"], "competition": "成本优势和分红能力突出。", "elasticity": "防御强于交易弹性。", "valuation_band": "高股息估值框架。", "event_sensitivity": "对油价更敏感，对运价次敏感。", "ah_linkage": "与 A 股能源链存在情绪联动。", "recent_vectors": ["油价", "分红"], "linkage_hint": "theme"},
    "600150": {"name": "中国船舶", "market": "A股", "industry_id": "shipping_energy", "chain_roles": ["shipyard"], "business": "船舶制造龙头，受益于航运高景气带来的新船订单周期。", "revenue_mix": ["民船", "军船"], "competition": "长周期订单驱动，兑现节奏慢于航运股。", "elasticity": "更适合中期主题跟踪。", "valuation_band": "订单周期估值框架。", "event_sensitivity": "对新船订单和造船价格敏感。", "ah_linkage": "与港股船舶制造板块联动较弱。", "recent_vectors": ["新船订单", "船价"], "linkage_hint": "weak"},
}


EVENT_BLUEPRINTS: dict[str, dict[str, Any]] = {
    "event_ai_capex": {"cluster_id": "cluster_ai_capex", "title": "海外 AI 资本开支维持高位，光模块与交换链景气延续", "event_type": "海外科技资本开支", "stage": "验证强化", "direction": "positive", "summary": "海外云厂商资本开支并未回落，A/H 市场中最直接的映射在高速光模块、交换机和上游核心器件。", "progression": {"base_case": "未来 1-4 周内，订单能见度继续强化，市场优先交易确定性最高的龙头。", "bull_case": "若更多云厂商上修指引或 1.6T 提前放量，龙头将从订单验证切换到估值拔升。", "bear_case": "若大厂强调资本纪律或价格明显松动，情绪会先于报表转弱。"}, "watchpoints": ["云厂商业绩会 capex 指引", "1.6T 渗透率", "ASP 是否稳定", "交付周期是否继续拉长"], "time_window": "5-20 个交易日", "catalysts": ["海外云厂商业绩会", "核心客户追加订单", "高速链路新品验证"], "invalidations": ["云厂商下修 capex", "高端链路 ASP 快速下滑", "交付周期明显缩短"], "impacts": [{"industry_id": "ai_optics", "node_id": "optical_module", "relation_type": "直接受益", "direction": "positive", "impact_strength": 92, "duration_days": 20, "rationale": "订单最先传导到高速光模块，利润兑现也最直接。"}, {"industry_id": "ai_optics", "node_id": "optical_chip", "relation_type": "直接受益", "direction": "positive", "impact_strength": 78, "duration_days": 18, "rationale": "上游芯片与 DSP 环节受益于量价和国产替代预期。"}, {"industry_id": "ai_optics", "node_id": "switch_interconnect", "relation_type": "间接受益", "direction": "positive", "impact_strength": 68, "duration_days": 18, "rationale": "交换机和连接器跟随网络升级，兑现略慢于光模块。"}], "version_log": [{"version": "v1", "timestamp": "T-1", "view_change": "仅定义为主题热点，未上修盈利预测。"}, {"version": "v2", "timestamp": "T0", "view_change": "随着 capex 指引确认，上调为可执行的龙头买入逻辑。"}]},
    "event_semi_policy": {"cluster_id": "cluster_semi_policy", "title": "设备更新与扩产招标共振，半导体设备国产替代进入验证段", "event_type": "国内产业政策", "stage": "从预期走向验证", "direction": "positive", "summary": "政策支持继续发力，同时晶圆厂扩产节奏边际修复，设备链逻辑从宏大叙事转向订单和验证节奏。", "progression": {"base_case": "1-6 周内，龙头设备股优先受益，零部件和晶圆厂作为跟随映射。", "bull_case": "若更多晶圆厂披露扩产和招标恢复，设备龙头会进入业绩和估值双击。", "bear_case": "若政策落地但晶圆厂资本开支不跟进，行情会退回主题层。"}, "watchpoints": ["设备招标量", "晶圆厂 capex", "设备验证节点", "订单转收入速度"], "time_window": "10-30 个交易日", "catalysts": ["政策细则落地", "设备订单公告", "晶圆厂扩产披露"], "invalidations": ["晶圆厂 capex 再度下修", "验证进度不及预期", "订单兑现明显延后"], "impacts": [{"industry_id": "semi_equipment", "node_id": "wafer_fab_equipment", "relation_type": "直接受益", "direction": "positive", "impact_strength": 88, "duration_days": 25, "rationale": "设备龙头最能吸收政策和扩产预期。"}, {"industry_id": "semi_equipment", "node_id": "semi_parts", "relation_type": "间接受益", "direction": "positive", "impact_strength": 72, "duration_days": 25, "rationale": "零部件环节在设备放量后获得更高弹性，但兑现滞后。"}, {"industry_id": "semi_equipment", "node_id": "wafer_fab", "relation_type": "主题映射", "direction": "positive", "impact_strength": 61, "duration_days": 20, "rationale": "晶圆厂更多承担景气锚点和资本开支验证作用。"}], "version_log": [{"version": "v1", "timestamp": "T-3", "view_change": "只定义为政策交易，建议观察。"}, {"version": "v2", "timestamp": "T0", "view_change": "因招标节奏恢复，设备龙头升级为持有偏买入。"}]},
    "event_storage": {"cluster_id": "cluster_storage", "title": "国内并网提速叠加海外报价企稳，储能链进入订单兑现窗口", "event_type": "项目与渠道共振", "stage": "兑现窗口打开", "direction": "positive", "summary": "储能行业出现国内并网加快与海外报价企稳的双重验证，市场会从政策主题切换到订单和利润质量。", "progression": {"base_case": "未来 2-6 周内，龙头电芯与订单更透明的系统集成商先表现。", "bull_case": "若电芯报价稳住且并网持续提速，龙头和二线弹性股都会扩散。", "bear_case": "若锂价再次上行或价格战重启，利润兑现会低于订单兑现。"}, "watchpoints": ["并网节奏", "招标价格", "欧洲渠道库存", "项目回款"], "time_window": "8-25 个交易日", "catalysts": ["项目并网公告", "储能招标结果", "海外渠道补库"], "invalidations": ["锂价快速上行", "系统报价再度下滑", "并网节奏重新放缓"], "impacts": [{"industry_id": "energy_storage", "node_id": "battery_cell", "relation_type": "直接受益", "direction": "positive", "impact_strength": 84, "duration_days": 24, "rationale": "电芯价值量最大，订单确认时龙头最先兑现利润弹性。"}, {"industry_id": "energy_storage", "node_id": "system_integration", "relation_type": "直接受益", "direction": "positive", "impact_strength": 73, "duration_days": 18, "rationale": "系统集成最先体现收入确认。"}, {"industry_id": "energy_storage", "node_id": "pcs_bms", "relation_type": "间接受益", "direction": "positive", "impact_strength": 64, "duration_days": 18, "rationale": "PCS/BMS 跟随交付节奏受益，但利润弹性低于电芯。"}], "version_log": [{"version": "v1", "timestamp": "T-2", "view_change": "政策主题阶段，建议观察。"}, {"version": "v2", "timestamp": "T0", "view_change": "因开标与并网提速，龙头和系统集成升级为可跟踪买点。"}]},
    "event_shipping": {"cluster_id": "cluster_shipping", "title": "地缘扰动延续与贸易流重构共振，油运股进入事件驱动窗口", "event_type": "地缘冲突", "stage": "高敏感期", "direction": "positive", "summary": "中东航线扰动并未缓解，原油贸易流重构导致运输距离拉长，油运运价中枢上移成为 A/H 航运链最强催化。", "progression": {"base_case": "未来 1-3 周，市场先交易运价弹性最高的船东，再扩散到资源与船舶制造。", "bull_case": "若扰动持续且运价指数继续上行，龙头油运股可能从事件交易扩展到业绩交易。", "bear_case": "若地缘风险快速缓和，运价回落会让高弹性交易迅速降温。"}, "watchpoints": ["BDTI/BCTI 运价指数", "绕航持续时间", "油价", "新船订单"], "time_window": "3-15 个交易日", "catalysts": ["运价指数再创新高", "航线继续绕行", "油轮供给紧张"], "invalidations": ["地缘风险缓和", "运价回落", "贸易流恢复常态"], "impacts": [{"industry_id": "shipping_energy", "node_id": "tanker_operator", "relation_type": "直接受益", "direction": "positive", "impact_strength": 90, "duration_days": 15, "rationale": "运价上行直接映射船东利润，弹性最大。"}, {"industry_id": "shipping_energy", "node_id": "oil_major", "relation_type": "间接受益", "direction": "positive", "impact_strength": 58, "duration_days": 12, "rationale": "高油价提供安全垫，但不等同于运价弹性。"}, {"industry_id": "shipping_energy", "node_id": "shipyard", "relation_type": "主题映射", "direction": "positive", "impact_strength": 49, "duration_days": 30, "rationale": "若航运景气持续，新船订单才会后续受益。"}], "version_log": [{"version": "v1", "timestamp": "T-1", "view_change": "把该事件定义为短线催化，优先观察运价。"}, {"version": "v2", "timestamp": "T0", "view_change": "贸易流重构确认后，油运龙头上调为短中线买入。"}]},
    "event_budget_risk": {"cluster_id": "cluster_budget_risk", "title": "预算释放偏慢成为反证信号，政策链短期要降低预期", "event_type": "宏观资金节奏", "stage": "风险提示", "direction": "negative", "summary": "地方预算释放慢于预期意味着一部分政策驱动链条会从预期差回到兑现检验，短期不宜给过高估值溢价。", "progression": {"base_case": "未来 1-2 周，政策链内部会出现强弱分化，只有订单能兑现的方向能走出来。", "bull_case": "若专项债投放恢复，风险会快速缓和并对设备、项目链条形成二次催化。", "bear_case": "若预算持续拖延，将压制纯主题映射品种并触发估值回撤。"}, "watchpoints": ["专项债投放", "地方财政节奏", "招标恢复"], "time_window": "5-10 个交易日", "catalysts": ["财政投放恢复", "项目招标回暖"], "invalidations": ["预算释放回暖", "重点省份项目恢复明显"], "impacts": [{"industry_id": "semi_equipment", "node_id": "wafer_fab_equipment", "relation_type": "待验证", "direction": "negative", "impact_strength": 46, "duration_days": 8, "rationale": "预算链拖延会压制设备链短期估值扩张。"}, {"industry_id": "energy_storage", "node_id": "system_integration", "relation_type": "待验证", "direction": "negative", "impact_strength": 42, "duration_days": 8, "rationale": "项目型公司更依赖预算与回款节奏，短期需降预期。"}], "version_log": [{"version": "v1", "timestamp": "T0", "view_change": "新增预算反证，要求所有政策链观点附带失效条件。"}]},
}


INDUSTRY_CATALOG = FILE_INDUSTRY_CATALOG
COMPANY_CATALOG = FILE_COMPANY_CATALOG
EVENT_BLUEPRINTS = FILE_EVENT_BLUEPRINTS
HIGH_QUALITY_DEVELOPMENT_UNIVERSE = FILE_HIGH_QUALITY_DEVELOPMENT_UNIVERSE
A_SHARE_NAME_MAP = FILE_A_SHARE_NAME_MAP

HQD_INDUSTRY_MAPPING: dict[str, list[str]] = {
    "ai_optics": ["电子", "通信", "计算机"],
    "semi_equipment": ["机械设备", "电子"],
    "energy_storage": ["电力设备", "公用事业", "环保"],
    "shipping_energy": ["交通运输", "石油石化"],
}


def _clean_topic(topic: Any) -> str:
    return str(topic).replace("，", ",").strip()


def default_demo_request() -> dict[str, Any]:
    return {
        "watchlist": [
            {"symbol": "300308", "name": "中际旭创", "position_pct": 8.0, "thesis": "跟踪海外 AI capex 是否继续强化到 1.6T 订单。"},
            {"symbol": "002371", "name": "北方华创", "position_pct": 10.0, "thesis": "政策能否传导到设备订单和晶圆厂扩产。"},
            {"symbol": "00981.HK", "name": "中芯国际-H", "position_pct": 6.0, "thesis": "把它作为设备链持续性的景气锚点。"},
            {"symbol": "600026", "name": "中远海能", "position_pct": 5.0, "thesis": "关注中东扰动和油运运价能否延续。"},
        ],
        "focus_topics": ["AI算力", "国产替代", "航运", "储能"],
        "risk_thresholds": {"single_name_limit_pct": 15, "sector_limit_pct": 22, "negative_event_score_threshold": 70},
        "personal_notes": "优先要有证据链和失效条件；如果只是宏大叙事没有订单兑现，请自动降权。预算释放变慢或 capex 下修要直接打风险标签。",
        "use_live_news": True,
        "rss_sources_text": "",
        "technical_settings": {
            "provider": "mock",
            "endpoint": "",
            "timeout_seconds": 8,
            "fallback_to_mock": True
        },
        "model_settings": {
            "enabled": False,
            "provider": "openai-compatible",
            "base_url": "",
            "model_name": "",
            "api_key": "",
            "system_prompt": "",
            "temperature": 0.2,
            "timeout_seconds": 20
        },
        "recommendation_limit": 10,
    }


def build_product_overview() -> dict[str, Any]:
    overview = {
        "name": "新闻驱动选股系统",
        "tagline": "把全球/国内热点压成事件、产业链和 A/H 个股建议。",
        "pricing": {"monthly_rmb": 699, "trial_days": 7},
        "positioning": "事件驱动投研与建议平台",
        "inputs": ["全球/国内新闻", "观察池", "主题偏好", "风险阈值", "个人研究笔记"],
        "outputs": ["热点事件流", "事件详情", "产业链分析", "候选股票池", "个股建议", "版本回溯"],
        "agent_roles": ["新闻采集 agent", "事件推演 agent", "产业映射 agent", "产业链拆解 agent", "公司画像 agent", "建议生成 agent"],
        "north_star_metrics": ["热点到事件归并准确率 >= 80%", "建议可追溯率 = 100%", "日度报告完成时延 <= 15 分钟", "盘中事件触发延迟 <= 5 分钟"],
        "compliance_boundary": "输出的是结构化研究建议，不含自动下单、不承诺收益、不替代投资者自主决策。",
        "coverage": ["A股", "港股"],
        "delivery_modes": ["盘中事件触发", "日度复盘与次日建议"],
    }
    overview["compliance"] = audit_copy_payload(" ".join(str(value) for value in overview.values()))
    return overview


def audit_copy_payload(copy_text: str) -> dict[str, Any]:
    hits = [term for term in BANNED_COPY_TERMS if term in copy_text]
    return {"is_compliant": not hits, "blocked_terms": hits, "banned_terms": list(BANNED_COPY_TERMS)}


def load_internal_lab_snapshot(artifacts_dir: Path | None = None) -> dict[str, Any]:
    base_dir = artifacts_dir or ARTIFACTS_DIR
    if not base_dir.exists():
        return {"status": "missing", "title": "后台实验层未发现可展示产出", "strategies": [], "note": "当前没有可读的实验指标文件。"}
    metric_files = sorted(base_dir.rglob("*_metrics.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    strategies: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in metric_files:
        data = json.loads(path.read_text(encoding="utf-8"))
        strategy_name = str(data.get("strategy") or path.stem.replace("_metrics", ""))
        if strategy_name in seen:
            continue
        seen.add(strategy_name)
        strategies.append({"strategy": strategy_name, "status": "internal-only", "validation_conclusion": data.get("validation_conclusion", "仅内部观察"), "total_return": data.get("total_return"), "max_drawdown": data.get("max_drawdown"), "path": str(path.relative_to(REPO_ROOT))})
        if len(strategies) >= 3:
            break
    return {"status": "internal-only", "title": "后台实验层", "note": "现有策略实验只作为内部验证，不直接参与对外建议生成。", "strategies": strategies}


def build_research_workspace(request: ResearchRequest, as_of: date | None = None) -> dict[str, Any]:
    run_date = as_of or date.today()
    run_clock = datetime.combine(run_date, time(hour=8, minute=45))
    as_of_str = run_date.isoformat()
    watchlist = _normalize_watchlist(request.watchlist)
    focus_topics = tuple(topic for topic in request.focus_topics if topic)
    notes = request.personal_notes
    ai_company_pool = _build_ai_company_pool(watchlist, focus_topics, notes)
    news_items = _collect_news_items(
        run_clock,
        watchlist,
        focus_topics,
        notes,
        request.use_live_news,
        request.rss_sources_text,
    )
    ai_research_pipeline = build_ai_research_pipeline(
        news_items=news_items,
        watchlist=watchlist,
        focus_topics=focus_topics,
        personal_notes=notes,
        company_pool=ai_company_pool,
        model_settings=request.model_settings,
    )
    news_items = _merge_ai_news_localization(news_items, ai_research_pipeline)
    hotspot_events = _build_event_cases(news_items, watchlist, focus_topics, notes)
    industry_views = _build_industry_views(hotspot_events, ai_research_pipeline)
    candidate_stocks = _build_candidate_stocks(
        hotspot_events,
        watchlist,
        focus_topics,
        notes,
        ai_research_pipeline,
    )
    crowding_context = load_recent_crowding_context(default_db_path(REPO_ROOT))
    recommendation_views = _build_recommendations(
        candidate_stocks,
        hotspot_events,
        watchlist,
        request.technical_settings,
        as_of_str,
        request.recommendation_limit,
        crowding_context,
        ai_research_pipeline,
    )
    market_snapshot = build_market_snapshot([item["symbol"] for item in recommendation_views], request.technical_settings)
    news_stream = _build_news_stream(news_items, hotspot_events)
    intraday_dispatch = _build_intraday_dispatch(hotspot_events, recommendation_views)
    daily_digest = _build_daily_digest(run_clock, hotspot_events, recommendation_views, focus_topics)
    recommendation_history = _build_recommendation_history(recommendation_views, hotspot_events)
    scorecards = _build_event_scorecards(hotspot_events)
    risk_cards = _build_risk_cards(recommendation_views, watchlist, request.risk_thresholds)
    weekly_review = _build_weekly_review(hotspot_events, recommendation_views, risk_cards, notes)
    portfolio_plan = build_portfolio_plan(
        recommendations=recommendation_views,
        watchlist=_build_watchlist_portfolio_inputs(watchlist),
        risk_thresholds=request.risk_thresholds.__dict__,
    )
    source_diagnostics = _build_source_diagnostics(news_items)
    ai_participation_status = _build_ai_participation_status(ai_research_pipeline)
    product_overview = build_product_overview()
    compliance = audit_copy_payload(" ".join([daily_digest["summary"], *(event["event_summary"] for event in hotspot_events), *(rec["core_logic"] for rec in recommendation_views)]))
    compliance["boundary"] = product_overview["compliance_boundary"]
    workspace = {
        "generated_at": run_clock.isoformat(timespec="minutes"),
        "product_overview": product_overview,
        "compliance": compliance,
        "input_profile": {
            "watchlist": [holding.__dict__ for holding in watchlist],
            "focus_topics": list(focus_topics),
            "risk_thresholds": request.risk_thresholds.__dict__,
            "personal_notes": notes,
            "use_live_news": request.use_live_news,
            "rss_sources_text": request.rss_sources_text,
            "technical_settings": request.technical_settings,
        },
        "news_stream": news_stream,
        "hotspot_events": hotspot_events,
        "event_details": hotspot_events,
        "industry_views": industry_views,
        "candidate_stocks": candidate_stocks,
        "recommendation_views": recommendation_views,
        "recommendation_history": recommendation_history,
        "market_snapshot": market_snapshot,
        "intraday_dispatch": intraday_dispatch,
        "daily_digest": daily_digest,
        "daily_brief": {"headline": daily_digest["headline"], "summary": daily_digest["summary"], "must_watch": daily_digest["must_watch"], "follow_up_questions": daily_digest["follow_up_questions"], "delivery_channels": daily_digest["delivery_channels"]},
        "event_alerts": intraday_dispatch["alerts"],
        "scorecards": scorecards,
        "risk_cards": risk_cards,
        "weekly_review": weekly_review,
        "portfolio_plan": portfolio_plan,
        "source_diagnostics": source_diagnostics,
        "ai_participation_status": ai_participation_status,
        "ai_research_pipeline": ai_research_pipeline,
        "agent_trace": _build_agent_trace(hotspot_events, industry_views, candidate_stocks, recommendation_views),
        "lab_snapshot": load_internal_lab_snapshot(),
    }
    return refine_workspace_with_model(workspace, request.model_settings)


def _normalize_watchlist(watchlist: tuple[HoldingInput, ...]) -> tuple[HoldingInput, ...]:
    if watchlist:
        return tuple(
            HoldingInput(
                symbol=holding.symbol,
                name=holding.name or (_company_profile(holding.symbol) or {}).get("name", holding.symbol),
                position_pct=holding.position_pct,
                thesis=holding.thesis,
            )
            for holding in watchlist
        )
    return tuple(HoldingInput.from_dict(item) for item in default_demo_request()["watchlist"])


def _build_watchlist_portfolio_inputs(watchlist: tuple[HoldingInput, ...]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for holding in watchlist:
        profile = _company_profile(holding.symbol) or {}
        items.append(
            {
                "symbol": holding.symbol,
                "name": holding.name,
                "position_pct": holding.position_pct,
                "industry_name": _industry_name(profile.get("industry_id", "")) if profile else "未知行业",
            }
        )
    return items


def _collect_news_items(run_clock: datetime, watchlist: tuple[HoldingInput, ...], focus_topics: tuple[str, ...], notes: str, use_live_news: bool = False, rss_sources_text: str = "") -> list[dict[str, Any]]:
    keywords = _extract_keywords(notes, watchlist, focus_topics)
    watch_symbols = {holding.symbol for holding in watchlist}
    watch_industries = {
        profile["industry_id"]
        for holding in watchlist
        for profile in [(_company_profile(holding.symbol) or {})]
        if profile.get("industry_id")
    }
    use_live = use_live_news or os.getenv("NEWS_USE_LIVE", "0") == "1"
    raw_feed = load_demo_raw_news_feed()
    custom_sources = parse_custom_rss_sources(rss_sources_text)
    if use_live:
        try:
            live_items = fetch_live_raw_news_feed(sources=custom_sources or None)
            if live_items:
                raw_feed = live_items
        except Exception:
            raw_feed = load_demo_raw_news_feed()
    clustered_feed = deduplicate_and_cluster_news(raw_feed, run_clock)
    scored: list[dict[str, Any]] = []
    for seed in clustered_feed:
        score = seed["credibility_score"] + max(0, 24 - seed["published_offset_hours"])
        if set(seed["cluster_tags"]).intersection(focus_topics):
            score += 14
        if any(tag.lower() in keywords for tag in seed["cluster_tags"]):
            score += 6
        event = _event_by_cluster(seed["cluster_id"])
        if event:
            industries = {impact["industry_id"] for impact in event["impacts"]}
            if watch_industries.intersection(industries):
                score += 10
            companies = {code for impact in event["impacts"] for code in _node_companies(impact["industry_id"], impact["node_id"])}
            if watch_symbols.intersection(companies):
                score += 10
        scored.append(
            {
                **seed,
                "tags": seed["cluster_tags"],
                "hot_score": min(100, round(score)),
            }
        )
    return sorted(scored, key=lambda item: item["hot_score"], reverse=True)


def _build_event_cases(news_items: list[dict[str, Any]], watchlist: tuple[HoldingInput, ...], focus_topics: tuple[str, ...], notes: str) -> list[dict[str, Any]]:
    del notes
    news_by_cluster: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in news_items:
        news_by_cluster[item["cluster_id"]].append(item)
    watch_symbols = {holding.symbol for holding in watchlist}
    events: list[dict[str, Any]] = []
    for event_id, blueprint in EVENT_BLUEPRINTS.items():
        support_news = sorted(news_by_cluster.get(blueprint["cluster_id"], []), key=lambda item: item["hot_score"], reverse=True)
        if not support_news:
            continue
        identity = build_event_identity(
            event_type=blueprint["event_type"],
            cluster_id=blueprint["cluster_id"],
            title=blueprint["title"],
            stage=blueprint["stage"],
            supporting_news=support_news,
        )
        source_coverage = _build_source_coverage(support_news)
        companies = {code for impact in blueprint["impacts"] for code in _node_companies(impact["industry_id"], impact["node_id"])}
        overlap_bonus = 12 if watch_symbols.intersection(companies) else 0
        overlap_bonus += 8 if set(focus_topics).intersection({tag for item in support_news for tag in item["tags"]}) else 0
        impacts = []
        profit_segments = []
        for impact in blueprint["impacts"]:
            node = _find_node(impact["industry_id"], impact["node_id"])
            impact_with_node = {
                **impact,
                "industry_name": INDUSTRY_CATALOG[impact["industry_id"]]["name"],
                "node_name": node["name"],
                "evidence_chain": [item["news_id"] for item in support_news],
            }
            impacts.append(impact_with_node)
            profit_segments.append(
                {
                    **impact_with_node,
                    "stage": node["stage"],
                    "concentration": node["concentration"],
                    "profit_pool_weight": node["value_contribution"],
                    "value_pool": node["profit_level"],
                    "representative_companies": node["representative_companies"],
                }
            )
        profit_propagation = build_event_profit_propagation(
            event_master_id=identity["event_master_id"],
            event_instance_id=identity["event_instance_id"],
            event_title=blueprint["title"],
            segments=profit_segments,
        )
        events.append(
            {
                "event_id": event_id,
                **identity,
                "title": blueprint["title"],
                "event_type": blueprint["event_type"],
                "stage": blueprint["stage"],
                "direction": blueprint["direction"],
                "heat_score": min(100, max(item["hot_score"] for item in support_news) + overlap_bonus),
                "event_summary": blueprint["summary"],
                "progression": blueprint["progression"],
                "key_watchpoints": blueprint["watchpoints"],
                "time_window": blueprint["time_window"],
                "catalysts": blueprint["catalysts"],
                "invalidation_conditions": blueprint["invalidations"],
                "supporting_news": support_news,
                "industry_impacts": impacts,
                "markets": sorted({(_company_profile(code) or {}).get("market", "A股") for code in companies}),
                "watchlist_overlap": sorted(watch_symbols.intersection(companies)),
                "version_log": blueprint["version_log"],
                "cluster_id": blueprint["cluster_id"],
                "profit_propagation": profit_propagation,
                "source_diversity_score": source_coverage["score"],
                "source_diversity_label": source_coverage["label"],
                "source_diversity_detail": source_coverage["detail"],
                "coverage_gap_warning": source_coverage["warning"],
                "coverage_gap_warnings": source_coverage["warnings"],
            }
        )
    return sorted(events, key=lambda item: item["heat_score"], reverse=True)


def _build_industry_views(
    hotspot_events: list[dict[str, Any]],
    ai_research_pipeline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    impacts_by_industry: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in hotspot_events:
        for impact in event["industry_impacts"]:
            impacts_by_industry[impact["industry_id"]].append(impact | {"event_id": event["event_id"], "event_title": event["title"]})
    views: list[dict[str, Any]] = []
    for industry_id, impacts in impacts_by_industry.items():
        blueprint = INDUSTRY_CATALOG[industry_id]
        impacted_nodes = {impact["node_id"] for impact in impacts}
        linked_companies = []
        seen: set[str] = set()
        for node in blueprint["supply_chain"]:
            for code in node["representative_companies"]:
                if code in COMPANY_CATALOG and code not in seen:
                    seen.add(code)
                    linked_companies.append(_company_snapshot(code))
        industry_profit_segments = []
        for impact in impacts:
            node = _find_node(industry_id, impact["node_id"])
            industry_profit_segments.append(
                {
                    **impact,
                    "industry_id": industry_id,
                    "industry_name": blueprint["name"],
                    "stage": node["stage"],
                    "concentration": node["concentration"],
                    "profit_pool_weight": node["value_contribution"],
                    "value_pool": node["profit_level"],
                    "representative_companies": node["representative_companies"],
                }
            )
        views.append(
            {
                "industry_id": industry_id,
                "industry_name": blueprint["name"],
                "description": blueprint["description"],
                "current_state": blueprint["current_state"],
                "policy_dependency": blueprint["policy_dependency"],
                "import_export_dependency": blueprint["import_export_dependency"],
                "structural_notes": blueprint["structural_notes"],
                "event_ids": sorted({impact["event_id"] for impact in impacts}),
                "impact_summary": [{"event_id": impact["event_id"], "event_title": impact["event_title"], "node_name": impact["node_name"], "relation_type": impact["relation_type"], "impact_direction": impact["direction"], "impact_strength": impact["impact_strength"]} for impact in sorted(impacts, key=lambda item: item["impact_strength"], reverse=True)],
                "supply_chain": [
                    {
                        **node,
                        "representative_companies": [_company_snapshot(code) for code in node["representative_companies"] if code in COMPANY_CATALOG],
                        "is_impacted": node["node_id"] in impacted_nodes,
                    }
                    for node in blueprint["supply_chain"]
                ],
                "linked_companies": linked_companies,
                "profit_propagation": build_industry_profit_map(
                    industry_id=industry_id,
                    industry_name=blueprint["name"],
                    segments=industry_profit_segments,
                ),
                "ai_generated": False,
                "ai_summary": "",
                "ai_chain_expansion": [],
            }
        )
    return _merge_ai_industry_views(views, ai_research_pipeline or {})


def _build_candidate_stocks(
    hotspot_events: list[dict[str, Any]],
    watchlist: tuple[HoldingInput, ...],
    focus_topics: tuple[str, ...],
    notes: str,
    ai_research_pipeline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    focus_set = set(focus_topics)
    keywords = _extract_keywords(notes, watchlist, focus_topics)
    watch_map = {holding.symbol: holding for holding in watchlist}
    candidates: dict[str, dict[str, Any]] = {}
    for event in hotspot_events:
        for impact in event["industry_impacts"]:
            for code in _node_companies(impact["industry_id"], impact["node_id"]):
                profile = _company_profile(code, fallback_industry_id=impact["industry_id"], node_name=impact["node_name"])
                if not profile:
                    continue
                base = impact["impact_strength"]
                profit_alignment = _find_event_profit_alignment(event, impact["node_id"])
                if profit_alignment.get("profit_role") == "利润中心":
                    base += 7
                elif profit_alignment.get("profit_role") == "收入承接":
                    base += 4
                elif profit_alignment.get("beneficiary_type") in {"主题映射", "弱相关"}:
                    base -= 3
                if int(profit_alignment.get("concentration_score", 0) or 0) >= 75:
                    base += 2
                if code in watch_map:
                    base += 10
                if set(profile["revenue_mix"]).intersection(focus_set):
                    base += 6
                if any(word.lower() in keywords for word in profile["revenue_mix"]):
                    base += 4
                if profile["linkage_hint"] == "leader":
                    base += 6
                elif profile["linkage_hint"] == "runner_up":
                    base += 3
                elif profile["linkage_hint"] == "weak":
                    base -= 8
                if impact["direction"] == "negative":
                    base -= 8
                bucket = candidates.setdefault(
                    code,
                    {
                        "symbol": code,
                        "name": profile["name"],
                        "market": profile["market"],
                        "industry_id": profile["industry_id"],
                        "industry_name": INDUSTRY_CATALOG[profile["industry_id"]]["name"],
                        "supply_chain_roles": profile["chain_roles"],
                        "events": [],
                        "direct_nodes": set(),
                        "match_score": 0,
                        "is_watchlist": code in watch_map,
                    },
                )
                bucket["match_score"] = max(bucket["match_score"], min(100, round(base)))
                bucket["events"].append({
                    "event_id": event["event_id"],
                    "event_master_id": event.get("event_master_id"),
                    "event_title": event["title"],
                    "impact_direction": impact["direction"],
                    "impact_strength": impact["impact_strength"],
                    "node_name": impact["node_name"],
                    "relation_type": impact["relation_type"],
                    "profit_role": profit_alignment.get("profit_role", ""),
                    "profit_pool_weight_numeric": profit_alignment.get("profit_pool_weight_numeric", 0),
                    "concentration_score": profit_alignment.get("concentration_score", 0),
                })
                bucket["direct_nodes"].add(impact["node_name"])
                bucket["selection_mode"] = "event_mapped"

    _inject_watchlist_and_topic_candidates(
        candidates=candidates,
        watchlist=watchlist,
        focus_topics=focus_topics,
        keywords=keywords,
    )
    _inject_ai_pipeline_candidates(
        candidates=candidates,
        ai_research_pipeline=ai_research_pipeline or {},
        focus_topics=focus_topics,
        keywords=keywords,
    )
    result = []
    for code, item in candidates.items():
        profile = _company_profile(
            code,
            fallback_industry_id=item["industry_id"],
            node_name=(sorted(item["direct_nodes"])[0] if item["direct_nodes"] else ""),
        )
        if not profile:
            continue
        linkage_type = _linkage_type(profile["linkage_hint"])
        events = sorted(item["events"], key=lambda raw: raw["impact_strength"], reverse=True)
        if events:
            rationale = (
                f"{profile['name']} 属于{linkage_type}，当前最强映射来自 {events[0]['event_title']}，"
                f"直接对应 {events[0]['node_name']} 环节。{profile['elasticity']}"
            )
        else:
            rationale = item.get(
                "fallback_rationale",
                f"{profile['name']} 当前进入候选池主要因为观察池/主题扫描命中，后续仍需要新增事件或公告证据强化。"
            )
        result.append(
            {
                **item,
                "events": events,
                "direct_nodes": sorted(item["direct_nodes"]),
                "relation_types": sorted({raw.get("relation_type", "") for raw in events if raw.get("relation_type")}),
                "linkage_type": linkage_type,
                "business_summary": profile["business"],
                "competition": profile["competition"],
                "valuation_band": profile["valuation_band"],
                "event_sensitivity": profile["event_sensitivity"],
                "ah_linkage": profile["ah_linkage"],
                "recent_vectors": profile["recent_vectors"],
                "rationale": rationale,
            }
        )
    return sorted(result, key=lambda item: item["match_score"], reverse=True)


def _find_event_profit_alignment(event: dict[str, Any], node_id: str) -> dict[str, Any]:
    propagation = event.get("profit_propagation", {}) if isinstance(event, dict) else {}
    for segment in propagation.get("segments", []) if isinstance(propagation, dict) else []:
        if str(segment.get("node_id", "") or "") == node_id:
            return segment
    return {}


def _build_recommendations(
    candidate_stocks: list[dict[str, Any]],
    hotspot_events: list[dict[str, Any]],
    watchlist: tuple[HoldingInput, ...],
    technical_settings: dict[str, Any] | None = None,
    as_of: str | None = None,
    recommendation_limit: int = 10,
    crowding_context: dict[str, Any] | None = None,
    ai_research_pipeline: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    watch_map = {holding.symbol: holding for holding in watchlist}
    event_map = {event["event_id"]: event for event in hotspot_events}
    ai_ranked_map = {item["symbol"]: item for item in _extract_ai_ranked_companies(ai_research_pipeline or {})}
    recommendations: list[dict[str, Any]] = []
    for candidate in candidate_stocks[:recommendation_limit]:
        positive = sum(item["impact_strength"] for item in candidate["events"] if item["impact_direction"] == "positive")
        negative = sum(item["impact_strength"] for item in candidate["events"] if item["impact_direction"] == "negative")
        related_events = [event_map[item["event_id"]] for item in candidate["events"][:2] if item["event_id"] in event_map]
        source_coverage = _build_source_coverage(
            _merge_event_supporting_news(related_events)
        )
        raw_score = max(0, min(100, round(candidate["match_score"] * 0.55 + (positive - negative) * 0.35 + (12 if candidate["is_watchlist"] else 4))))
        crowding_penalty = _build_crowding_penalty(candidate, related_events, crowding_context or {})
        beneficiary_score = _build_beneficiary_score(candidate["symbol"], ai_ranked_map)
        score = max(0, raw_score - crowding_penalty["penalty"] + beneficiary_score["boost"])
        action = _recommendation_action(score, negative, candidate["is_watchlist"])
        core_logic = _recommendation_logic(
            candidate["name"],
            candidate["industry_name"],
            related_events,
            action,
            beneficiary_score,
        )
        catalysts = _merge_unique([event["catalysts"] for event in related_events])[:3]
        risks = _merge_unique([event["invalidation_conditions"] for event in related_events])[:3]
        technical_overlay = get_symbol_technical_overlay(candidate["symbol"], action, score, technical_settings)
        snapshots = build_company_snapshot_bundle(candidate["symbol"], as_of or date.today().isoformat())
        risk_score = _build_risk_analyst_score(
            candidate=candidate,
            watch_map=watch_map,
            price_snapshot=snapshots["price_snapshot"],
            fundamental_snapshot=snapshots["fundamental_snapshot"],
            technical_overlay=technical_overlay,
            source_coverage=source_coverage,
            crowding_penalty=crowding_penalty,
        )
        execution_plan = build_execution_plan(
            action,
            _target_return_pct(action, score),
            snapshots["price_snapshot"],
            technical_overlay,
            beneficiary_score,
        )
        confidence_gate = _build_high_confidence_gate(
            source_coverage=source_coverage,
            price_snapshot=snapshots["price_snapshot"],
            fundamental_snapshot=snapshots["fundamental_snapshot"],
            ai_research_pipeline=ai_research_pipeline or {},
            candidate=candidate,
            related_events=related_events,
        )
        decision = synthesize_recommendation(
            candidate=candidate,
            base_action=action,
            base_score=score,
            related_events=related_events,
            technical_overlay=technical_overlay,
            market_score=snapshots["market_score"],
            fundamental_score=snapshots["fundamental_score"],
            beneficiary_score=beneficiary_score,
            risk_score=risk_score,
            execution_plan=execution_plan,
        )
        gated_action = _apply_confidence_gate_to_action(
            action=decision["manager_action"],
            confidence_gate=confidence_gate,
            is_watchlist=candidate.get("is_watchlist", False),
        )
        confidence = _recommendation_confidence(score, source_coverage["score"], confidence_gate)
        profit_focus = _recommendation_profit_focus(related_events)
        recommendations.append(
            {
                "symbol": candidate["symbol"],
                "name": candidate["name"],
                "market": candidate["market"],
                "action": gated_action,
                "base_action": action,
                "raw_score": raw_score,
                "score": score,
                "final_score": decision["final_score"],
                "confidence": confidence,
                "ai_beneficiary_rank": beneficiary_score.get("rank"),
                "ai_beneficiary_level": beneficiary_score.get("level"),
                "ai_ranking_rationale": beneficiary_score.get("reason"),
                "ai_beneficiary_boost": beneficiary_score.get("boost"),
                "profit_focus_summary": profit_focus["summary"],
                "profit_focus_nodes": profit_focus["nodes"],
                "core_logic": core_logic,
                "thesis": candidate["business_summary"],
                "related_events": [
                    {
                        "event_id": event["event_id"],
                        "event_master_id": event.get("event_master_id"),
                        "event_instance_id": event.get("event_instance_id"),
                        "title": event["title"],
                        "direction": event["direction"],
                    }
                    for event in related_events
                ],
                "related_industries": sorted({candidate["industry_name"], *[impact["industry_name"] for event in related_events for impact in event["industry_impacts"]]}),
                "supply_chain_position": candidate["direct_nodes"],
                "relation_types": candidate.get("relation_types", []),
                "linkage_type": candidate.get("linkage_type", ""),
                "selection_mode": candidate.get("selection_mode", ""),
                "catalysts": catalysts,
                "risks": risks,
                "target_return_pct": _target_return_pct(action, score),
                "odds_label": _odds_label(score),
                "invalidation_conditions": risks,
                "effective_window": related_events[0]["time_window"] if related_events else "5-15 个交易日",
                "technical_overlay": technical_overlay,
                "execution_plan": execution_plan,
                "price_snapshot": snapshots["price_snapshot"],
                "valuation_snapshot": snapshots["valuation_snapshot"],
                "fundamental_snapshot": snapshots["fundamental_snapshot"],
                "market_score": snapshots["market_score"],
                "fundamental_score": snapshots["fundamental_score"],
                "risk_score": risk_score,
                "confidence_gate": confidence_gate,
                "company_profile": _build_runtime_company_profile(candidate["symbol"], candidate.get("industry_id")),
                "analyst_signals": decision["analyst_signals"],
                "manager_summary": _augment_manager_summary_with_gate(decision["manager_summary"], confidence_gate, gated_action),
                "manager_rationale": _augment_manager_rationale_with_gate(decision["manager_rationale"], confidence_gate),
                "source_diversity_score": source_coverage["score"],
                "source_diversity_label": source_coverage["label"],
                "source_diversity_detail": source_coverage["detail"],
                "coverage_gap_warning": source_coverage["warning"],
                "coverage_gap_warnings": source_coverage["warnings"],
                "crowding_penalty": crowding_penalty,
                "evidence_chain": {
                    "news_ids": _merge_unique([[item["news_id"] for item in event["supporting_news"]] for event in related_events]),
                    "event_ids": [event["event_id"] for event in related_events],
                    "event_master_ids": [event.get("event_master_id") for event in related_events if event.get("event_master_id")],
                    "industry_ids": sorted({impact["industry_id"] for event in related_events for impact in event["industry_impacts"]}),
                    "company_symbol": candidate["symbol"],
                },
                "watchlist_status": "在观察池中" if candidate["is_watchlist"] else "候选映射标的",
                "position_note": watch_map[candidate["symbol"]].thesis if candidate["symbol"] in watch_map else "尚未持有，适合作为事件驱动候选。",
            }
        )
    return sorted(
        recommendations,
        key=lambda item: (
            int(item.get("final_score", item.get("score", 0))),
            float(item.get("confidence", 0)),
            int(item.get("source_diversity_score", 0)),
            int(item.get("technical_overlay", {}).get("technical_score", 0)),
        ),
        reverse=True,
    )


def _build_news_stream(news_items: list[dict[str, Any]], hotspot_events: list[dict[str, Any]]) -> dict[str, Any]:
    coverage = _build_source_coverage(news_items)
    return {
        "intraday": news_items[:6],
        "daily": news_items,
        "source_diversity_score": coverage["score"],
        "source_diversity_label": coverage["label"],
        "source_diversity_detail": coverage["detail"],
        "coverage_gap_warning": coverage["warning"],
        "coverage_gap_warnings": coverage["warnings"],
        "clusters": [
            {
                "cluster_id": event["cluster_id"],
                "event_id": event["event_id"],
                "event_master_id": event.get("event_master_id"),
                "title": event["title"],
                "heat_score": event["heat_score"],
                "news_count": len(event["supporting_news"]),
                "direction": event["direction"],
                "source_diversity_score": event["source_diversity_score"],
                "coverage_gap_warning": event["coverage_gap_warning"],
            }
            for event in hotspot_events
        ],
    }


def _build_intraday_dispatch(hotspot_events: list[dict[str, Any]], recommendation_views: list[dict[str, Any]]) -> dict[str, Any]:
    alerts = []
    for event in hotspot_events[:4]:
        affected = [f"{rec['name']}({rec['symbol']}) {rec['action']}" for rec in recommendation_views if event["event_id"] in rec["evidence_chain"]["event_ids"]][:4]
        alerts.append({"event_master_id": event.get("event_master_id"), "title": event["title"], "trigger": "风险预警" if event["direction"] == "negative" else "盘中催化", "priority_score": event["heat_score"], "source": "；".join(item["source_name"] for item in event["supporting_news"][:2]), "summary": event["event_summary"], "affected_stocks": affected, "needs_confirmation": event["key_watchpoints"][:2]})
    return {"dispatch_note": "盘中模式优先给方向、受影响标的和待确认点。", "alerts": alerts, "top_actions": [{"symbol": rec["symbol"], "name": rec["name"], "action": rec["action"], "confidence": rec["confidence"]} for rec in recommendation_views[:5]]}


def _build_daily_digest(run_clock: datetime, hotspot_events: list[dict[str, Any]], recommendation_views: list[dict[str, Any]], focus_topics: tuple[str, ...]) -> dict[str, Any]:
    top_events = hotspot_events[:3]
    top_recs = recommendation_views[:3]
    focus_text = "、".join(focus_topics[:4]) if focus_topics else "事件强度、兑现节奏和失效条件"
    coverage_scores = [event["source_diversity_score"] for event in top_events] or [0]
    coverage_warnings = _merge_unique([[warning for warning in event.get("coverage_gap_warnings", [])] for event in top_events])[:4]
    avg_coverage = round(sum(coverage_scores) / len(coverage_scores))
    return {
        "headline": f"{run_clock.strftime('%m 月 %d 日')} 新闻驱动选股日报",
        "summary": f"今日优先围绕 {focus_text} 展开。事件层面最强的是 {top_events[0]['title'] if top_events else '暂无热点'}，建议层面优先检查 {top_recs[0]['name'] if top_recs else '暂无标的'} 的证据链完整度。",
        "must_watch": [event["title"] for event in top_events],
        "follow_up_questions": [event["key_watchpoints"][0] for event in top_events if event["key_watchpoints"]],
        "delivery_channels": ["桌面 Web", "邮件摘要", "飞书提醒"],
        "top_recommendations": [f"{item['name']}({item['symbol']}) {item['action']} / 置信度 {item['confidence']}" for item in top_recs],
        "tomorrow_focus": _merge_unique([event["catalysts"] for event in top_events])[:4],
        "source_diversity_score": avg_coverage,
        "coverage_overview": f"头部事件平均来源多样性 {avg_coverage}/100。",
        "coverage_gaps": coverage_warnings,
    }


def _build_source_diagnostics(news_items: list[dict[str, Any]]) -> dict[str, Any]:
    layer_counts: dict[str, int] = defaultdict(int)
    source_counts: dict[str, int] = defaultdict(int)
    missing_url_count = 0
    for item in news_items:
        layer = str(item.get("source_layer", "media") or "media")
        layer_counts[layer] += 1
        source_counts[str(item.get("source_name", "未知来源"))] += 1
        if not str(item.get("source_url", "") or "").strip():
            missing_url_count += 1
    preferred_order = ["policy", "filing", "industry_data", "media"]
    return {
        "total_news_count": len(news_items),
        "layer_counts": {key: layer_counts.get(key, 0) for key in preferred_order if layer_counts.get(key, 0)},
        "source_counts": dict(sorted(source_counts.items(), key=lambda kv: kv[1], reverse=True)[:8]),
        "missing_url_count": missing_url_count,
    }


def _build_ai_participation_status(ai_research_pipeline: dict[str, Any]) -> dict[str, Any]:
    stage_order = [
        "news_localization",
        "event_understanding",
        "scenario_analysis",
        "supply_chain_expansion",
        "company_beneficiary_ranking",
    ]
    stages = []
    success = 0
    failed = 0
    disabled = 0
    for key in stage_order:
        stage = ai_research_pipeline.get(key, {}) if isinstance(ai_research_pipeline, dict) else {}
        status = str(stage.get("status", "unknown") or "unknown")
        if status == "ok":
            success += 1
        elif status in {"error", "invalid_response", "quota_exceeded", "auth_error", "rate_limited", "provider_timeout", "provider_unavailable"}:
            failed += 1
        elif status in {"disabled", "missing_credentials", "blocked"}:
            disabled += 1
        stages.append(
            {
                "key": key,
                "title": str(stage.get("stage", key)),
                "status": status,
                "message": str(stage.get("message", "") or ""),
            }
        )
    return {
        "enabled": bool(ai_research_pipeline.get("enabled")),
        "status": str(ai_research_pipeline.get("status", "disabled")),
        "success_count": success,
        "failed_count": failed,
        "disabled_count": disabled,
        "stages": stages,
    }


def _build_recommendation_history(recommendation_views: list[dict[str, Any]], hotspot_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_map = {event["event_id"]: event for event in hotspot_events}
    history = []
    for rec in recommendation_views[:6]:
        versions = []
        for event_id in rec["evidence_chain"]["event_ids"]:
            for version in event_map.get(event_id, {}).get("version_log", []):
                versions.append({"event_id": event_id, "event_title": event_map[event_id]["title"], "version": version["version"], "timestamp": version["timestamp"], "view_change": version["view_change"]})
        history.append({"symbol": rec["symbol"], "name": rec["name"], "current_action": rec["action"], "current_score": rec["score"], "versions": versions})
    return history


def _build_event_scorecards(hotspot_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"event_id": event["event_id"], "event_master_id": event.get("event_master_id"), "direction": event["direction"], "event_what": event["title"], "why_it_matters": event["event_summary"], "impacted_targets": sorted({f"{impact['industry_name']} / {impact['node_name']}" for impact in event["industry_impacts"]}), "priority_score": event["heat_score"], "raw_source": "；".join(f"{item['source_name']} {item['published_at'][5:16]}" for item in event["supporting_news"][:2]), "disconfirming_signal": "；".join(event["invalidation_conditions"]), "next_question": "；".join(event["key_watchpoints"][:2]), "summary": event["event_summary"], "matched_symbols": event["watchlist_overlap"], "matched_topics": sorted({tag for item in event["supporting_news"] for tag in item["tags"]})} for event in hotspot_events]


def _build_risk_cards(recommendation_views: list[dict[str, Any]], watchlist: tuple[HoldingInput, ...], thresholds: RiskThresholds) -> list[dict[str, Any]]:
    risk_cards = []
    for holding in watchlist:
        if holding.position_pct >= thresholds.single_name_limit_pct:
            risk_cards.append({"risk_type": "单名仓位超阈值", "target": _security_label(holding.symbol), "reason": f"当前仓位 {holding.position_pct:.1f}% 已高于阈值 {thresholds.single_name_limit_pct:.1f}%。", "action_question": "是否需要提高反证材料权重或拆分持仓节奏？"})
    sector_weights: dict[str, float] = defaultdict(float)
    for holding in watchlist:
        profile = _company_profile(holding.symbol)
        if profile and profile.get("industry_id") in INDUSTRY_CATALOG:
            sector_weights[INDUSTRY_CATALOG[profile["industry_id"]]["name"]] += holding.position_pct
    for sector, weight in sector_weights.items():
        if weight >= thresholds.sector_limit_pct:
            risk_cards.append({"risk_type": "行业暴露集中", "target": sector, "reason": f"该行业观察池权重 {weight:.1f}% 已高于阈值 {thresholds.sector_limit_pct:.1f}%。", "action_question": "是否补一个独立于主题叙事的退出条件？"})
    for rec in recommendation_views:
        if rec["action"] == "卖出" and rec["score"] <= thresholds.negative_event_score_threshold:
            risk_cards.append({"risk_type": "负面事件驱动", "target": f"{rec['name']}({rec['symbol']})", "reason": rec["core_logic"], "action_question": "；".join(rec["invalidation_conditions"])})
    return risk_cards[:6]


def _build_risk_analyst_score(
    *,
    candidate: dict[str, Any],
    watch_map: dict[str, HoldingInput],
    price_snapshot: dict[str, Any],
    fundamental_snapshot: dict[str, Any],
    technical_overlay: dict[str, Any],
    source_coverage: dict[str, Any],
    crowding_penalty: dict[str, Any],
) -> dict[str, Any]:
    score = 70
    reasons: list[str] = []
    holding = watch_map.get(candidate["symbol"])
    if holding and holding.position_pct >= 15:
        score -= 15
        reasons.append("单票仓位接近或超过阈值")
    if price_snapshot.get("status") != "ok":
        score -= 15
        reasons.append("价格快照缺失")
    elif abs(price_snapshot.get("day_change_pct") or 0) >= 6:
        score -= 8
        reasons.append("短期波动偏大")
    if fundamental_snapshot.get("status") != "ok":
        score -= 10
        reasons.append("财务快照缺失")
    if str(technical_overlay.get("provider_status", "")).startswith("fallback:"):
        score -= 8
        reasons.append("技术信号来自回退源")
    if candidate.get("market") == "港股":
        score -= 5
        reasons.append("港股覆盖层仍不完整")
    if source_coverage.get("score", 50) < 55:
        score -= 12
        reasons.append("证据来源多样性不足")
    elif source_coverage.get("warning"):
        score -= 6
        reasons.append("证据覆盖仍偏窄")
    if crowding_penalty.get("penalty", 0) >= 8:
        score -= 10
        reasons.append(crowding_penalty.get("reason", "近期重复霸榜，拥挤度升高"))
    elif crowding_penalty.get("penalty", 0) > 0:
        score -= 5
        reasons.append(crowding_penalty.get("reason", "近期重复出现，拥挤度上升"))
    score = max(0, min(100, score))
    return {
        "score": score,
        "label": _odds_label(score),
        "reason": "；".join(reasons) if reasons else "当前风险可控",
    }


def _build_crowding_penalty(
    candidate: dict[str, Any],
    related_events: list[dict[str, Any]],
    crowding_context: dict[str, Any],
) -> dict[str, Any]:
    symbol_counts = dict(crowding_context.get("symbol_counts", {}) or {})
    event_counts = dict(crowding_context.get("event_counts", {}) or {})
    lookback_runs = int(crowding_context.get("lookback_runs", 0) or 0)
    symbol_hits = int(symbol_counts.get(candidate["symbol"], 0))
    related_event_hits = max(
        (
            int(
                event_counts.get(
                    str(event.get("event_master_id") or event.get("event_id") or ""),
                    0,
                )
            )
            for event in related_events
        ),
        default=0,
    )
    penalty = 0
    reasons: list[str] = []
    if symbol_hits >= 3:
        penalty += min(9, (symbol_hits - 2) * 3)
        reasons.append(f"近 {lookback_runs} 次运行中该标的有 {symbol_hits} 次进入前排")
    elif symbol_hits == 2:
        penalty += 2
        reasons.append(f"近 {lookback_runs} 次运行中该标的已连续出现")
    if related_event_hits >= 4:
        penalty += min(6, related_event_hits - 3)
        reasons.append("同一主事件在最近多次运行中持续主导")
    penalty = max(0, min(15, penalty))
    return {
        "penalty": penalty,
        "symbol_hits": symbol_hits,
        "event_hits": related_event_hits,
        "lookback_runs": lookback_runs,
        "reason": "；".join(reasons) if reasons else "近期未见明显拥挤",
    }


def _build_source_coverage(news_items: list[dict[str, Any]]) -> dict[str, Any]:
    if not news_items:
        return {
            "score": 0,
            "label": "无覆盖",
            "detail": "没有可用新闻来源。",
            "warning": "当前没有新闻证据，无法完成多源验证。",
            "warnings": ["当前没有新闻证据，无法完成多源验证。"],
        }
    source_names = sorted({str(item.get("source_name", "")).strip() for item in news_items if str(item.get("source_name", "")).strip()})
    source_kinds = sorted({str(item.get("source_kind", "")).strip() for item in news_items if str(item.get("source_kind", "")).strip()})
    regions = sorted({str(item.get("region", "")).strip() for item in news_items if str(item.get("region", "")).strip()})
    market_scopes = sorted({str(item.get("market_scope", "")).strip() for item in news_items if str(item.get("market_scope", "")).strip()})
    score = 18
    score += min(4, len(source_names)) * 14
    score += min(3, len(source_kinds)) * 14
    score += min(3, len(regions)) * 7
    score += min(3, len(market_scopes)) * 5
    score += 8 if len(news_items) >= 3 else 0
    warnings: list[str] = []
    if len(source_names) <= 1:
        warnings.append("主要依赖单一媒体或单一路径。")
    elif len(source_names) <= 2:
        warnings.append("来源媒体仍偏少。")
    if len(source_kinds) <= 1:
        warnings.append("证据类型单一，缺少公告/政策/公司原文。")
    if source_kinds and set(source_kinds) == {"RSS"}:
        warnings.append("当前主要来自媒体 RSS，容易形成信息回音室。")
    if len(regions) <= 1 and len(news_items) >= 3:
        warnings.append("地域覆盖偏窄，跨市场交叉验证不足。")
    score = max(0, min(100, score))
    if score >= 80:
        label = "多源验证"
    elif score >= 60:
        label = "中等覆盖"
    else:
        label = "覆盖偏窄"
    detail = f"{len(source_names)} 个来源 / {len(source_kinds)} 类证据 / {len(regions)} 个区域 / {len(news_items)} 条样本"
    return {
        "score": score,
        "label": label,
        "detail": detail,
        "warning": "；".join(warnings[:2]) if warnings else "",
        "warnings": warnings,
    }


def _merge_event_supporting_news(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for event in events:
        for item in event.get("supporting_news", []):
            news_id = str(item.get("news_id", ""))
            if not news_id:
                continue
            existing = merged.get(news_id)
            if existing is None or item.get("hot_score", 0) > existing.get("hot_score", 0):
                merged[news_id] = item
    return list(merged.values())


def _recommendation_confidence(
    score: int,
    source_diversity_score: int,
    confidence_gate: dict[str, Any] | None = None,
) -> float:
    base = max(0.35, min(0.94, score / 100))
    if source_diversity_score < 50:
        base -= 0.12
    elif source_diversity_score < 65:
        base -= 0.06
    confidence_gate = confidence_gate or {}
    if not confidence_gate.get("high_confidence_eligible", True):
        base = min(base, 0.64)
        if confidence_gate.get("strict_block"):
            base = min(base, 0.56)
    return round(max(0.35, min(0.94, base)), 2)


def _build_weekly_review(hotspot_events: list[dict[str, Any]], recommendation_views: list[dict[str, Any]], risk_cards: list[dict[str, Any]], notes: str) -> dict[str, Any]:
    positive = [rec for rec in recommendation_views if rec["action"] == "买入"][:3]
    negative = [rec for rec in recommendation_views if rec["action"] == "卖出"][:3]
    return {"week_focus": "重点复盘证据链最强和最弱的事件。", "convictions_to_retest": [f"{item['name']}({item['symbol']}) {item['core_logic']}" for item in positive], "disconfirmations": [item["core_logic"] for item in negative] or ["暂无强制卖出逻辑，继续跟踪失效条件。"], "risk_summary": [card["reason"] for card in risk_cards] or ["本周未出现超过阈值的结构性风险。"], "thesis_memory": [{"target": f"{rec['name']}({rec['symbol']})", "thesis": rec["core_logic"]} for rec in recommendation_views[:5]], "research_note": notes or "暂无额外主观研究笔记。", "event_replay": [{"event_id": event["event_id"], "title": event["title"], "version_count": len(event["version_log"])} for event in hotspot_events[:5]]}


def _build_agent_trace(hotspot_events: list[dict[str, Any]], industry_views: list[dict[str, Any]], candidate_stocks: list[dict[str, Any]], recommendation_views: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {"agent": "新闻采集 agent", "responsibility": "聚合全球与国内热点，并按新闻簇去重与排序。", "output_summary": f"生成 {sum(len(event['supporting_news']) for event in hotspot_events)} 条新闻样本，归并成 {len(hotspot_events)} 个事件。"},
        {"agent": "事件推演 agent", "responsibility": "对每个热点事件生成阶段判断、推演路径、催化剂和失效条件。", "output_summary": f"完成 {len(hotspot_events)} 个事件的结构化推演。"},
        {"agent": "产业映射 agent", "responsibility": "把事件映射到行业、主题与产业链节点。", "output_summary": f"命中 {len(industry_views)} 个行业视图，并区分直接受益与间接受益。"},
        {"agent": "产业链拆解 agent", "responsibility": "输出供需、集中度、价值贡献和利润情况。", "output_summary": f"共展开 {sum(len(view['supply_chain']) for view in industry_views)} 个产业链节点。"},
        {"agent": "公司画像 agent", "responsibility": "把产业链节点映射到 A/H 公司，并生成公司分析卡。", "output_summary": f"产出 {len(candidate_stocks)} 个候选股票分析对象。"},
        {"agent": "建议生成 agent", "responsibility": "基于事件强度、产业位置、公司弹性和风险生成买卖建议。", "output_summary": f"输出 {len(recommendation_views)} 条个股建议，并保留历史版本差异。"},
    ]


def _extract_keywords(notes: str, watchlist: tuple[HoldingInput, ...], focus_topics: tuple[str, ...]) -> set[str]:
    candidates = {topic.lower() for topic in focus_topics}
    for holding in watchlist:
        candidates.add(holding.symbol.lower())
        candidates.add(holding.name.lower())
        profile = _company_profile(holding.symbol)
        if profile:
            candidates.update(word.lower() for word in profile["revenue_mix"])
            candidates.update(word.lower() for word in profile["chain_roles"])
    candidates.update(word.lower() for word in re.split(r"[\s,，。；;]+", notes) if len(word) >= 2)
    return {item for item in candidates if item}


def _event_by_cluster(cluster_id: str) -> dict[str, Any] | None:
    for event in EVENT_BLUEPRINTS.values():
        if event["cluster_id"] == cluster_id:
            return event
    return None


def _find_node(industry_id: str, node_id: str) -> dict[str, Any]:
    for node in INDUSTRY_CATALOG[industry_id]["supply_chain"]:
        if node["node_id"] == node_id:
            return node
    raise KeyError(f"Unknown node {node_id} in industry {industry_id}")


def _node_companies(industry_id: str, node_id: str) -> list[str]:
    candidates: list[str] = []
    for code in _find_node(industry_id, node_id)["representative_companies"]:
        if code not in candidates:
            candidates.append(code)
    for code, profile in COMPANY_CATALOG.items():
        if profile.get("industry_id") != industry_id:
            continue
        if node_id not in profile.get("chain_roles", []):
            continue
        if code not in candidates:
            candidates.append(code)
    for sw_industry in HQD_INDUSTRY_MAPPING.get(industry_id, []):
        for code in _hqd_industry_symbols(sw_industry):
            if code not in candidates:
                candidates.append(code)
    return candidates


def _company_snapshot(code: str) -> dict[str, str]:
    profile = COMPANY_CATALOG[code]
    return {"symbol": code, "name": profile["name"], "market": profile["market"]}


def _linkage_type(hint: str) -> str:
    return {"leader": "龙头", "runner_up": "次龙头", "elastic": "弹性标的", "theme": "主题映射标的", "weak": "弱相关标的"}.get(hint, "主题映射标的")


def _recommendation_action(score: int, negative: int, is_watchlist: bool) -> str:
    if negative >= 55 and score <= 55:
        return "卖出"
    if score >= 82:
        return "买入"
    if score >= 66:
        return "持有" if is_watchlist else "观察"
    if negative >= 40:
        return "卖出" if is_watchlist else "观察"
    return "观察"


def _target_return_pct(action: str, score: int) -> float:
    if action == "买入":
        return round(8 + score * 0.12, 1)
    if action == "持有":
        return round(3 + score * 0.05, 1)
    if action == "卖出":
        return round(-4 - max(0, 70 - score) * 0.08, 1)
    return round(1 + score * 0.03, 1)


def _recommendation_logic(
    name: str,
    industry_name: str,
    related_events: list[dict[str, Any]],
    action: str,
    beneficiary_score: dict[str, Any] | None = None,
) -> str:
    beneficiary_score = beneficiary_score or {}
    if not related_events:
        if beneficiary_score.get("rank"):
            return (
                f"{name} 缺少直接事件证据链，但 AI 公司受益排序把它排在第 {beneficiary_score['rank']} 位，"
                f"当前先按主题映射观察，后续需要公告或订单继续确认。"
            )
        return f"{name} 缺少足够强的事件证据链，当前只保留在观察列表。"
    event_titles = "、".join(event["title"] for event in related_events[:2])
    profit_clause = _profit_focus_logic_clause(related_events)
    ai_clause = _beneficiary_logic_clause(beneficiary_score)
    if action == "买入":
        return f"{event_titles} 共同强化了 {name} 在 {industry_name} 的受益逻辑，且映射环节更靠近利润中心。{profit_clause}{ai_clause}"
    if action == "卖出":
        return f"{event_titles} 提供了反证信号，{name} 当前更容易受到预期下修影响。{profit_clause}{ai_clause}"
    if action == "持有":
        return f"{event_titles} 仍支持 {name} 的主逻辑，但性价比略低于更强的龙头。{profit_clause}{ai_clause}"
    return f"{event_titles} 让 {name} 进入候选池，但还需要更多订单或价格验证。{profit_clause}{ai_clause}"


def _odds_label(score: int) -> str:
    if score >= 85:
        return "高赔率/高确定性"
    if score >= 70:
        return "中高赔率"
    if score >= 55:
        return "中性赔率"
    return "低赔率/高不确定性"


def _beneficiary_logic_clause(beneficiary_score: dict[str, Any]) -> str:
    rank = beneficiary_score.get("rank")
    level = str(beneficiary_score.get("level", "") or "")
    reason = str(beneficiary_score.get("reason", "") or "")
    if not rank:
        return ""
    if level in {"直接受益", "核心受益", "高优先级"}:
        return f" AI 排名把它列为第 {rank} 受益标的，判断其属于更直接的利润承接方。"
    if level in {"主题映射", "间接受益"}:
        return f" AI 排名把它列为第 {rank} 位，但更偏{level}，说明受益需要二次传导。"
    if level in {"弱相关", "低优先级"}:
        return f" AI 排名认为它仅属{level}，受益更多来自主题外溢而非直接利润兑现。"
    if reason:
        return f" AI 公司排序补充判断：{reason}"
    return f" AI 排名把它列为第 {rank} 位受益标的。"


def _profit_focus_logic_clause(related_events: list[dict[str, Any]]) -> str:
    if not related_events:
        return ""
    primary_segments = []
    for event in related_events:
        propagation = event.get("profit_propagation", {}) if isinstance(event, dict) else {}
        primary_segments.extend(propagation.get("primary_profit_centers", [])[:2] if isinstance(propagation, dict) else [])
    if not primary_segments:
        return ""
    names: list[str] = []
    weak_links: list[str] = []
    for item in primary_segments:
        name = str(item.get("node_name", "") or "").strip()
        role = str(item.get("profit_role", "") or "").strip()
        if name and name not in names:
            names.append(name)
        if role in {"主题映射", "弱相关映射"} and name and name not in weak_links:
            weak_links.append(name)
    if not names:
        return ""
    main_text = "、".join(names[:2])
    if weak_links:
        return f" 当前利润更集中在 {main_text}，但其中部分链条仍偏主题映射。"
    return f" 当前利润更集中在 {main_text} 等环节。"


def _recommendation_profit_focus(related_events: list[dict[str, Any]]) -> dict[str, Any]:
    nodes: list[str] = []
    for event in related_events:
        propagation = event.get("profit_propagation", {}) if isinstance(event, dict) else {}
        for item in propagation.get("primary_profit_centers", [])[:2] if isinstance(propagation, dict) else []:
            name = str(item.get("node_name", "") or "").strip()
            if name and name not in nodes:
                nodes.append(name)
    if not nodes:
        return {"summary": "利润重心未生成", "nodes": []}
    return {
        "summary": "、".join(nodes[:3]),
        "nodes": nodes[:3],
    }


def _merge_unique(values: list[list[str]]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for group in values:
        for value in group:
            if value in seen:
                continue
            seen.add(value)
            result.append(value)
    return result


def _inject_watchlist_and_topic_candidates(
    *,
    candidates: dict[str, dict[str, Any]],
    watchlist: tuple[HoldingInput, ...],
    focus_topics: tuple[str, ...],
    keywords: set[str],
) -> None:
    watch_map = {holding.symbol: holding for holding in watchlist}
    normalized_topics = {topic.lower() for topic in focus_topics}
    for code, profile in COMPANY_CATALOG.items():
        if code in candidates:
            continue
        focus_score = _topic_alignment_score(profile, normalized_topics, keywords)
        is_watchlist = code in watch_map
        if not is_watchlist and focus_score < 48:
            continue
        base_score = max(focus_score, 58 if is_watchlist else 0)
        rationale = (
            f"{profile['name']} 当前没有直接新闻映射，但命中观察池或主题扫描，"
            f"先作为扩展候选保留。需要后续公告、财报或订单证据继续确认。"
        )
        candidates[code] = {
            "symbol": code,
            "name": profile["name"],
            "market": profile["market"],
            "industry_id": profile["industry_id"],
            "industry_name": INDUSTRY_CATALOG[profile["industry_id"]]["name"],
            "supply_chain_roles": profile["chain_roles"],
            "events": [],
            "direct_nodes": set(profile["chain_roles"]),
            "match_score": min(100, round(base_score)),
            "is_watchlist": is_watchlist,
            "selection_mode": "watchlist" if is_watchlist else "topic_scan",
            "fallback_rationale": rationale,
        }


def _build_ai_company_pool(
    watchlist: tuple[HoldingInput, ...],
    focus_topics: tuple[str, ...],
    notes: str,
    *,
    limit: int = 160,
) -> list[dict[str, Any]]:
    keywords = _extract_keywords(notes, watchlist, focus_topics)
    normalized_topics = {topic.lower() for topic in focus_topics}
    watch_symbols = {holding.symbol for holding in watchlist}
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add_symbol(code: str, reason: str) -> None:
        if code in seen:
            return
        profile = _company_profile(code)
        if not profile:
            return
        seen.add(code)
        pool.append(
            {
                "symbol": code,
                "company_name": profile["name"],
                "market": profile["market"],
                "industry_name": _industry_name(profile["industry_id"]),
                "chain_roles": profile.get("chain_roles", []),
                "business": profile.get("business", ""),
                "pool_reason": reason,
            }
        )

    for holding in watchlist:
        add_symbol(holding.symbol, "watchlist")

    for code, profile in COMPANY_CATALOG.items():
        score = _topic_alignment_score(profile, normalized_topics, keywords)
        if score >= 32:
            add_symbol(code, "manual-company-catalog")
        if len(pool) >= limit:
            return pool[:limit]

    for group in HIGH_QUALITY_DEVELOPMENT_UNIVERSE.get("groups", {}).values():
        by_industry = group.get("by_industry", {}) if isinstance(group, dict) else {}
        for sw_industry, symbols in by_industry.items():
            if len(pool) >= limit:
                return pool[:limit]
            if not any(token in sw_industry.lower() for token in normalized_topics) and not any(token in sw_industry.lower() for token in keywords):
                continue
            for code in symbols[:80]:
                add_symbol(code, f"hqd:{sw_industry}")
                if len(pool) >= limit:
                    return pool[:limit]

    return pool[:limit]


def _inject_ai_pipeline_candidates(
    *,
    candidates: dict[str, dict[str, Any]],
    ai_research_pipeline: dict[str, Any],
    focus_topics: tuple[str, ...],
    keywords: set[str],
) -> None:
    if ai_research_pipeline.get("status") not in {"ok", "partial"}:
        return
    matched_internal, matched_sw = _extract_ai_pipeline_targets(ai_research_pipeline)
    ranked_companies = _extract_ai_ranked_companies(ai_research_pipeline)
    if not matched_internal and not matched_sw:
        if not ranked_companies:
            return

    normalized_topics = {topic.lower() for topic in focus_topics}
    target_symbols: dict[str, tuple[str, str]] = {}
    for industry_id in matched_internal:
        for sw_industry in HQD_INDUSTRY_MAPPING.get(industry_id, []):
            for code in _hqd_industry_symbols(sw_industry):
                target_symbols.setdefault(code, (industry_id, sw_industry))
    for sw_industry in matched_sw:
        fallback_industry_id = _fallback_industry_id_for_sw(sw_industry)
        for code in _hqd_industry_symbols(sw_industry):
            target_symbols.setdefault(code, (fallback_industry_id, sw_industry))

    for code, (industry_id, sw_industry) in target_symbols.items():
        profile = _company_profile(code, fallback_industry_id=industry_id, node_name=sw_industry)
        if not profile:
            continue
        ai_score = max(42, min(82, 46 + _topic_alignment_score(profile, normalized_topics, keywords)))
        if code in candidates:
            candidates[code]["match_score"] = max(candidates[code]["match_score"], ai_score)
            candidates[code]["selection_mode"] = (
                "event_mapped+ai_pipeline" if candidates[code].get("selection_mode") == "event_mapped" else "ai_pipeline"
            )
            continue
        candidates[code] = {
            "symbol": code,
            "name": profile["name"],
            "market": profile["market"],
            "industry_id": profile["industry_id"],
            "industry_name": _industry_name(profile["industry_id"]),
            "supply_chain_roles": profile["chain_roles"],
            "events": [],
            "direct_nodes": set(profile["chain_roles"] or [sw_industry]),
            "match_score": ai_score,
            "is_watchlist": False,
            "selection_mode": "ai_pipeline",
            "fallback_rationale": (
                f"{profile['name']} 因 AI 产业链展开命中 {sw_industry} 扩展进入候选池。"
                "当前仍需要公告、订单、财报或产业数据继续验证。"
            ),
        }

    for item in ranked_companies:
        code = item["symbol"]
        profile = _company_profile(code)
        if not profile:
            continue
        ai_rank_score = max(55, 96 - item["beneficiary_rank"] * 6)
        if code in candidates:
            candidates[code]["match_score"] = max(candidates[code]["match_score"], ai_rank_score)
            candidates[code]["selection_mode"] = (
                candidates[code].get("selection_mode", "event_mapped") + "+ai_ranking"
            )
            candidates[code]["ai_beneficiary_rank"] = item["beneficiary_rank"]
            candidates[code]["ai_beneficiary_level"] = item["beneficiary_level"]
            candidates[code]["ai_ranking_rationale"] = item["ranking_rationale"]
            candidates[code]["fallback_rationale"] = item["ranking_rationale"]
            continue
        candidates[code] = {
            "symbol": code,
            "name": profile["name"],
            "market": profile["market"],
            "industry_id": profile["industry_id"],
            "industry_name": _industry_name(profile["industry_id"]),
            "supply_chain_roles": profile["chain_roles"],
            "events": [],
            "direct_nodes": set(profile["chain_roles"]),
            "match_score": ai_rank_score,
            "is_watchlist": False,
            "selection_mode": "ai_ranking",
            "ai_beneficiary_rank": item["beneficiary_rank"],
            "ai_beneficiary_level": item["beneficiary_level"],
            "ai_ranking_rationale": item["ranking_rationale"],
            "fallback_rationale": item["ranking_rationale"],
        }


def _topic_alignment_score(profile: dict[str, Any], focus_topics: set[str], keywords: set[str]) -> int:
    haystack = [
        profile.get("industry_id", ""),
        profile.get("business", ""),
        profile.get("competition", ""),
        profile.get("event_sensitivity", ""),
        *profile.get("revenue_mix", []),
        *profile.get("chain_roles", []),
        *profile.get("recent_vectors", []),
    ]
    text = " ".join(str(item).lower() for item in haystack if item)
    score = 0
    for topic in focus_topics:
        if topic and topic in text:
            score += 18
    for keyword in keywords:
        if keyword and keyword in text:
            score += 5
    if profile.get("linkage_hint") == "leader":
        score += 8
    elif profile.get("linkage_hint") == "runner_up":
        score += 5
    elif profile.get("linkage_hint") == "elastic":
        score += 4
    return min(100, score)


def _merge_ai_industry_views(
    base_views: list[dict[str, Any]],
    ai_research_pipeline: dict[str, Any],
) -> list[dict[str, Any]]:
    ai_items = _extract_ai_industry_items(ai_research_pipeline)
    if not ai_items:
        return sorted(base_views, key=lambda item: len(item["event_ids"]), reverse=True)

    merged = [dict(item) for item in base_views]
    by_id = {item["industry_id"]: item for item in merged}

    for ai_item in ai_items:
        industry_id = ai_item["industry_id"]
        if industry_id in by_id:
            _apply_ai_industry_overlay(by_id[industry_id], ai_item)
            continue
        merged.append(_build_ai_only_industry_view(ai_item))

    return sorted(
        merged,
        key=lambda item: (
            len(item.get("event_ids", [])),
            1 if item.get("ai_generated") else 0,
        ),
        reverse=True,
    )


def _merge_ai_news_localization(
    news_items: list[dict[str, Any]],
    ai_research_pipeline: dict[str, Any],
) -> list[dict[str, Any]]:
    stage = ai_research_pipeline.get("news_localization", {})
    payload = stage.get("data", {}) if isinstance(stage, dict) else {}
    localized_items = payload.get("items", [])
    if not isinstance(localized_items, list):
        return news_items
    localized_map = {str(item.get("news_id", "")): item for item in localized_items if isinstance(item, dict)}
    merged: list[dict[str, Any]] = []
    for item in news_items:
        localized = localized_map.get(str(item.get("news_id", "")), {})
        merged.append(
            {
                **item,
                "translated_headline": str(localized.get("translated_headline", "") or "").strip(),
                "translated_summary": str(localized.get("translated_summary", "") or "").strip(),
                "translation_note": str(localized.get("translation_note", "") or "").strip(),
                "language": str(localized.get("language", "") or "").strip(),
            }
        )
    return merged


def _extract_ai_industry_items(ai_research_pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    if ai_research_pipeline.get("status") not in {"ok", "partial"}:
        return []
    payload = ai_research_pipeline.get("supply_chain_expansion", {}).get("data", {}) or {}
    raw_items: list[dict[str, Any]] = []
    for key in ("industries", "chains", "supply_chains"):
        value = payload.get(key)
        if isinstance(value, list):
            raw_items.extend(item for item in value if isinstance(item, dict))

    results: list[dict[str, Any]] = []
    for item in raw_items:
        matched = _match_ai_industry(item)
        if not matched:
            continue
        chain_nodes = _extract_ai_chain_nodes(item)
        results.append(
            {
                "industry_id": matched,
                "industry_name": INDUSTRY_CATALOG[matched]["name"] if matched in INDUSTRY_CATALOG else str(item.get("industry_name", "")),
                "summary": str(
                    item.get("summary")
                    or item.get("industry_summary")
                    or item.get("description")
                    or item.get("event_interpretation")
                    or ""
                ).strip(),
                "current_state": str(item.get("current_state") or item.get("stage") or "").strip(),
                "structural_notes": _normalize_string_list(
                    item.get("structural_notes")
                    or item.get("key_points")
                    or item.get("key_links")
                    or item.get("profit_pool")
                    or []
                ),
                "chain_nodes": chain_nodes,
            }
        )
    return results


def _apply_ai_industry_overlay(base_view: dict[str, Any], ai_item: dict[str, Any]) -> None:
    base_view["ai_generated"] = True
    if ai_item.get("summary"):
        base_view["ai_summary"] = ai_item["summary"]
    if ai_item.get("current_state"):
        base_view["current_state"] = ai_item["current_state"]
    if ai_item.get("structural_notes"):
        base_view["structural_notes"] = _merge_flat_lists(base_view.get("structural_notes", []), ai_item["structural_notes"])
    existing_supply = list(base_view.get("supply_chain", []))
    known_names = {str(node.get("name", "")).strip() for node in existing_supply}
    added_nodes: list[dict[str, Any]] = []
    for node in ai_item.get("chain_nodes", []):
        if node["name"] in known_names:
            continue
        known_names.add(node["name"])
        added_nodes.append(
            {
                "node_id": _slugify_text(node["name"]),
                "name": node["name"],
                "stage": node["stage"],
                "concentration": node["concentration"],
                "value_contribution": node["profit_pool_weight"],
                "profit_level": node["value_pool"],
                "demand_state": node["beneficiary_type"],
                "dependency_note": node["note"],
                "representative_companies": [],
                "is_impacted": True,
                "ai_generated": True,
            }
        )
    if added_nodes:
        base_view["supply_chain"] = existing_supply + added_nodes
        base_view["ai_chain_expansion"] = [node["name"] for node in added_nodes]
    existing_segments = list((base_view.get("profit_propagation") or {}).get("segments", []))
    ai_segments = [
        {
            "industry_id": base_view["industry_id"],
            "industry_name": base_view["industry_name"],
            "node_id": _slugify_text(node["name"]),
            "node_name": node["name"],
            "stage": node["stage"],
            "relation_type": node["beneficiary_type"],
            "impact_strength": 54,
            "profit_pool_weight": node["profit_pool_weight"],
            "value_pool": node["value_pool"],
            "concentration": node["concentration"],
            "representative_companies": [],
            "rationale": node["note"],
        }
        for node in ai_item.get("chain_nodes", [])
    ]
    if ai_segments:
        base_view["profit_propagation"] = build_industry_profit_map(
            industry_id=base_view["industry_id"],
            industry_name=base_view["industry_name"],
            segments=existing_segments + ai_segments,
        )


def _build_ai_only_industry_view(ai_item: dict[str, Any]) -> dict[str, Any]:
    ai_segments = [
        {
            "industry_id": ai_item["industry_id"],
            "industry_name": ai_item["industry_name"],
            "node_id": _slugify_text(node["name"]),
            "node_name": node["name"],
            "stage": node["stage"],
            "relation_type": node["beneficiary_type"],
            "impact_strength": 54,
            "profit_pool_weight": node["profit_pool_weight"],
            "value_pool": node["value_pool"],
            "concentration": node["concentration"],
            "representative_companies": [],
            "rationale": node["note"],
        }
        for node in ai_item.get("chain_nodes", [])
    ]
    return {
        "industry_id": ai_item["industry_id"],
        "industry_name": ai_item["industry_name"],
        "description": ai_item.get("summary", ""),
        "current_state": ai_item.get("current_state", ""),
        "policy_dependency": "AI 研究链生成，待进一步验证。",
        "import_export_dependency": "AI 研究链生成，待进一步验证。",
        "structural_notes": ai_item.get("structural_notes", []),
        "event_ids": [],
        "impact_summary": [],
        "supply_chain": [
            {
                "node_id": _slugify_text(node["name"]),
                "name": node["name"],
                "stage": node["stage"],
                "concentration": node["concentration"],
                "value_contribution": node["profit_pool_weight"],
                "profit_level": node["value_pool"],
                "demand_state": node["beneficiary_type"],
                "dependency_note": node["note"],
                "representative_companies": [],
                "is_impacted": True,
                "ai_generated": True,
            }
            for node in ai_item.get("chain_nodes", [])
        ],
        "linked_companies": [],
        "profit_propagation": build_industry_profit_map(
            industry_id=ai_item["industry_id"],
            industry_name=ai_item["industry_name"],
            segments=ai_segments,
        ),
        "ai_generated": True,
        "ai_summary": ai_item.get("summary", ""),
        "ai_chain_expansion": [node["name"] for node in ai_item.get("chain_nodes", [])],
    }


def _extract_ai_chain_nodes(item: dict[str, Any]) -> list[dict[str, str]]:
    nodes = item.get("chain_nodes") or item.get("nodes") or item.get("segments") or item.get("links") or []
    if not isinstance(nodes, list):
        return []
    result: list[dict[str, str]] = []
    for node in nodes:
        if isinstance(node, str):
            name = node.strip()
            if not name:
                continue
            result.append(
                {
                    "name": name,
                    "stage": "AI 推演环节",
                    "value_pool": "",
                    "profit_pool_weight": "",
                    "concentration": "",
                    "beneficiary_type": "",
                    "note": "",
                }
            )
            continue
        if not isinstance(node, dict):
            continue
        name = str(node.get("name") or node.get("node_name") or node.get("segment_name") or "").strip()
        if not name:
            continue
        result.append(
            {
                "name": name,
                "stage": str(node.get("stage") or node.get("relation_type") or "AI 推演环节").strip(),
                "value_pool": str(node.get("value_pool") or node.get("profit_center") or "").strip(),
                "profit_pool_weight": str(node.get("profit_pool_weight") or node.get("profit_weight") or "").strip(),
                "concentration": str(node.get("concentration_view") or node.get("concentration") or "").strip(),
                "beneficiary_type": str(node.get("beneficiary_type") or node.get("relation_type") or "").strip(),
                "note": str(node.get("note") or node.get("rationale") or "").strip(),
            }
        )
    return result


def _match_ai_industry(item: dict[str, Any]) -> str | None:
    haystack = " ".join(
        str(item.get(key, "") or "")
        for key in ("industry_name", "name", "sector", "chain_name", "summary", "description")
    )
    haystack = haystack.lower()
    alias_map = {
        "ai_optics": ["光模块", "交换链", "算力网络", "数据中心网络", "光器件", "服务器网络"],
        "semi_equipment": ["半导体设备", "晶圆厂", "刻蚀", "薄膜", "清洗设备", "前道设备"],
        "energy_storage": ["储能", "电网", "并网", "电池系统", "pcs", "逆变器"],
        "shipping_energy": ["油运", "航运", "运价", "绕航", "船东", "能源航运"],
    }
    for industry_id, aliases in alias_map.items():
        if any(alias.lower() in haystack for alias in aliases):
            return industry_id
    return None


def _normalize_string_list(raw: Any) -> list[str]:
    if isinstance(raw, str):
        value = raw.strip()
        return [value] if value else []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _merge_flat_lists(left: list[str], right: list[str]) -> list[str]:
    merged: list[str] = []
    for item in [*(left or []), *(right or [])]:
        text = str(item).strip()
        if text and text not in merged:
            merged.append(text)
    return merged


def _slugify_text(value: str) -> str:
    lowered = re.sub(r"\s+", "-", str(value).strip().lower())
    lowered = re.sub(r"[^a-z0-9\-\u4e00-\u9fff]+", "", lowered)
    return lowered[:64] or "ai-node"


def _extract_ai_pipeline_targets(ai_research_pipeline: dict[str, Any]) -> tuple[set[str], set[str]]:
    matched_internal: set[str] = set()
    matched_sw: set[str] = set()
    text = json.dumps(
        {
            "event_understanding": ai_research_pipeline.get("event_understanding", {}).get("data", {}),
            "scenario_analysis": ai_research_pipeline.get("scenario_analysis", {}).get("data", {}),
            "supply_chain_expansion": ai_research_pipeline.get("supply_chain_expansion", {}).get("data", {}),
        },
        ensure_ascii=False,
    )
    for industry_id, aliases in {
        "ai_optics": ["ai 光模块", "光模块", "交换链", "数据中心网络", "算力网络"],
        "semi_equipment": ["半导体设备", "晶圆厂", "刻蚀", "薄膜沉积", "清洗设备", "国产替代"],
        "energy_storage": ["储能", "电网", "并网", "pcs", "逆变器", "电池系统"],
        "shipping_energy": ["油运", "航运", "运价", "贸易流", "绕航", "船东"],
    }.items():
        if any(alias in text for alias in aliases):
            matched_internal.add(industry_id)
    sw_industries = set(HIGH_QUALITY_DEVELOPMENT_UNIVERSE.get("industry_coverage", {}).keys())
    for sw_industry in sw_industries:
        if sw_industry and sw_industry in text:
            matched_sw.add(sw_industry)
    return matched_internal, matched_sw


def _extract_ai_ranked_companies(ai_research_pipeline: dict[str, Any]) -> list[dict[str, Any]]:
    stage = ai_research_pipeline.get("company_beneficiary_ranking", {})
    payload = stage.get("data", {}) if isinstance(stage, dict) else {}
    companies = payload.get("companies", [])
    if not isinstance(companies, list):
        return []
    results: list[dict[str, Any]] = []
    reverse_name_map = {name: symbol for symbol, name in A_SHARE_NAME_MAP.items()}
    reverse_name_map.update({profile["name"]: symbol for symbol, profile in COMPANY_CATALOG.items()})
    for item in companies:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        company_name = str(item.get("company_name", "")).strip()
        if not symbol and company_name:
            symbol = reverse_name_map.get(company_name, "")
        symbol = normalize_symbol(symbol)
        if not symbol:
            continue
        try:
            beneficiary_rank = int(item.get("beneficiary_rank", 99))
        except (TypeError, ValueError):
            beneficiary_rank = 99
        results.append(
            {
                "symbol": symbol,
                "company_name": company_name or (_company_profile(symbol) or {}).get("name", symbol),
                "beneficiary_rank": beneficiary_rank,
                "beneficiary_level": str(item.get("beneficiary_level", "")).strip(),
                "ranking_rationale": str(item.get("ranking_rationale", "")).strip(),
                "key_profit_link": str(item.get("key_profit_link", "")).strip(),
                "caution": str(item.get("caution", "")).strip(),
            }
        )
    return sorted(results, key=lambda item: item["beneficiary_rank"])


def _build_high_confidence_gate(
    *,
    source_coverage: dict[str, Any],
    price_snapshot: dict[str, Any],
    fundamental_snapshot: dict[str, Any],
    ai_research_pipeline: dict[str, Any],
    candidate: dict[str, Any],
    related_events: list[dict[str, Any]],
) -> dict[str, Any]:
    reasons: list[str] = []
    strict_block = False
    if source_coverage.get("score", 0) < 60:
        reasons.append("来源多样性不足")
    if source_coverage.get("warning"):
        reasons.append("证据覆盖存在缺口")
    if price_snapshot.get("status") != "ok":
        reasons.append("价格快照缺失")
        strict_block = True
    if fundamental_snapshot.get("status") != "ok":
        reasons.append("财务快照缺失")
    if ai_research_pipeline.get("enabled"):
        ai_status = str(ai_research_pipeline.get("status", "") or "")
        if ai_status not in {"ok", "partial"}:
            reasons.append("AI 研究链未成功完成")
            strict_block = True
        elif any(
            stage.get("status") in {"error", "invalid_response"}
            for stage in (ai_research_pipeline.get("company_beneficiary_ranking", {}), ai_research_pipeline.get("supply_chain_expansion", {}))
            if isinstance(stage, dict)
        ):
            reasons.append("AI 关键排序阶段失败")
    if candidate.get("selection_mode") in {"topic_scan", "watchlist", "ai_pipeline"} and not related_events:
        reasons.append("缺少直接事件映射")
    eligible = not reasons
    gate_level = "open" if eligible else ("strict" if strict_block else "soft")
    return {
        "high_confidence_eligible": eligible,
        "strict_block": strict_block,
        "gate_level": gate_level,
        "reasons": reasons,
        "summary": "满足高置信度门槛。" if eligible else "；".join(reasons[:3]),
    }


def _apply_confidence_gate_to_action(
    *,
    action: str,
    confidence_gate: dict[str, Any],
    is_watchlist: bool,
) -> str:
    if confidence_gate.get("high_confidence_eligible", True):
        return action
    if action != "买入":
        return action
    if is_watchlist and not confidence_gate.get("strict_block"):
        return "持有"
    return "观察"


def _augment_manager_summary_with_gate(
    manager_summary: str,
    confidence_gate: dict[str, Any],
    action: str,
) -> str:
    if confidence_gate.get("high_confidence_eligible", True):
        return manager_summary
    return f"{manager_summary} 当前高置信度门槛未满足，因此收口动作保持为 {action}。"


def _augment_manager_rationale_with_gate(
    manager_rationale: list[str],
    confidence_gate: dict[str, Any],
) -> list[str]:
    if confidence_gate.get("high_confidence_eligible", True):
        return manager_rationale
    return [f"高置信度门槛: {confidence_gate.get('summary', '')}", *manager_rationale]


def _build_beneficiary_score(symbol: str, ai_ranked_map: dict[str, dict[str, Any]]) -> dict[str, Any]:
    item = ai_ranked_map.get(symbol)
    if not item:
        return {
            "score": 50,
            "rank": None,
            "level": "",
            "boost": 0,
            "reason": "AI 公司受益排序未覆盖该标的。",
        }
    rank = int(item.get("beneficiary_rank", 99) or 99)
    boost = max(0, 14 - rank * 2)
    score = max(45, min(96, 98 - rank * 8))
    reason = (
        f"AI 排名第 {rank} 位 / {item.get('beneficiary_level', '')} / "
        f"{item.get('ranking_rationale', '') or item.get('key_profit_link', '')}"
    )
    return {
        "score": score,
        "rank": rank,
        "level": item.get("beneficiary_level", ""),
        "boost": boost,
        "reason": reason.strip(),
    }


def _security_label(symbol: str) -> str:
    profile = _company_profile(symbol)
    if profile:
        return f"{profile['name']}({symbol})"
    return symbol


def _hqd_industry_symbols(sw_industry: str) -> list[str]:
    result: list[str] = []
    groups = HIGH_QUALITY_DEVELOPMENT_UNIVERSE.get("groups", {})
    allowed = _runtime_candidate_universe()
    for group in groups.values():
        by_industry = group.get("by_industry", {}) if isinstance(group, dict) else {}
        for code in by_industry.get(sw_industry, []):
            if code in allowed and code not in result:
                result.append(code)
    return result


@lru_cache(maxsize=1)
def _runtime_candidate_universe() -> set[str]:
    config = AppConfig.from_file(REPO_ROOT / "config" / "default.yaml")
    return set(load_universe_symbols(config.qlib_provider_uri, config.universe))


def _build_runtime_company_profile(symbol: str, fallback_industry_id: str | None = None) -> dict[str, Any]:
    profile = _company_profile(symbol, fallback_industry_id=fallback_industry_id)
    if not profile:
        return {}
    return {
        "symbol": symbol,
        "name": profile["name"],
        "market": profile["market"],
        "industry_id": profile["industry_id"],
        "industry_name": _industry_name(profile["industry_id"]),
        "business_segments": profile.get("business_segments", []),
        "profit_segments": profile.get("profit_segments", []),
        "historical_event_sensitivity": profile.get("historical_event_sensitivity", {}),
        "ah_pair_symbol": profile.get("ah_pair_symbol"),
        "ah_pair_name": profile.get("ah_pair_name"),
        "profile_completeness": profile.get("profile_completeness", 0),
        "event_sensitivity": profile.get("event_sensitivity", ""),
        "valuation_band": profile.get("valuation_band", ""),
        "linkage_hint": profile.get("linkage_hint", ""),
    }


def _company_profile(symbol: str, fallback_industry_id: str | None = None, node_name: str = "") -> dict[str, Any] | None:
    if symbol in COMPANY_CATALOG:
        return _enrich_company_profile(symbol, dict(COMPANY_CATALOG[symbol]))
    name = A_SHARE_NAME_MAP.get(symbol)
    if not name:
        return None
    industry_id = fallback_industry_id or "unknown_hqd"
    industry_name = INDUSTRY_CATALOG[industry_id]["name"] if industry_id in INDUSTRY_CATALOG else "高质量发展行业"
    return _enrich_company_profile(symbol, {
        "name": name,
        "market": "A股",
        "industry_id": industry_id,
        "chain_roles": [node_name] if node_name else [],
        "business": f"{name} 当前通过高质量发展行业池纳入候选，属于 {industry_name} 扩展范围。",
        "revenue_mix": [industry_name],
        "competition": "暂无结构化公司画像，后续需要补行业竞争地位和订单证据。",
        "elasticity": "作为行业扩展候选，先看公告、订单和业绩确认，不直接给龙头同级权重。",
        "valuation_band": "待补充",
        "event_sensitivity": f"对 {industry_name} 的政策、订单和景气变化敏感。",
        "ah_linkage": "待补充",
        "recent_vectors": [node_name or industry_name],
        "linkage_hint": "theme",
    })


def _enrich_company_profile(symbol: str, profile: dict[str, Any]) -> dict[str, Any]:
    revenue_mix = [str(item).strip() for item in profile.get("revenue_mix", []) if str(item).strip()]
    chain_roles = [str(item).strip() for item in profile.get("chain_roles", []) if str(item).strip()]
    recent_vectors = [str(item).strip() for item in profile.get("recent_vectors", []) if str(item).strip()]
    profile["business_segments"] = revenue_mix or [str(profile.get("business", "")).strip()]
    profile["profit_segments"] = chain_roles or recent_vectors[:2]
    sensitivity_text = str(profile.get("event_sensitivity", "") or "")
    profile["historical_event_sensitivity"] = {
        "level": _event_sensitivity_level(sensitivity_text),
        "summary": sensitivity_text,
        "drivers": recent_vectors[:3],
    }
    ah_pair_symbol = _extract_ah_pair_symbol(symbol, str(profile.get("ah_linkage", "") or ""))
    profile["ah_pair_symbol"] = ah_pair_symbol
    profile["ah_pair_name"] = (_company_profile_name_only(ah_pair_symbol) if ah_pair_symbol else None)
    completeness_fields = [
        bool(str(profile.get("business", "")).strip()),
        bool(revenue_mix),
        bool(chain_roles),
        bool(str(profile.get("competition", "")).strip()),
        bool(str(profile.get("valuation_band", "")).strip() and str(profile.get("valuation_band")) != "待补充"),
        bool(sensitivity_text),
        bool(recent_vectors),
    ]
    profile["profile_completeness"] = round(sum(1 for item in completeness_fields if item) / len(completeness_fields) * 100)
    return profile


def _company_profile_name_only(symbol: str | None) -> str | None:
    if not symbol:
        return None
    if symbol in COMPANY_CATALOG:
        return str(COMPANY_CATALOG[symbol].get("name") or symbol)
    return A_SHARE_NAME_MAP.get(symbol)


def _extract_ah_pair_symbol(symbol: str, ah_linkage: str) -> str | None:
    if not ah_linkage or "无" in ah_linkage or "待补充" in ah_linkage:
        return None
    matches = re.findall(r"\b\d{6}\b|\b\d{5}\.HK\b|\b\d{5}\b", ah_linkage)
    normalized = [normalize_symbol(item) for item in matches]
    normalized = [item for item in normalized if item and item != symbol]
    return normalized[0] if normalized else None


def _event_sensitivity_level(text: str) -> str:
    value = str(text or "")
    if any(token in value for token in ("极敏感", "非常敏感", "强联动")):
        return "高"
    if any(token in value for token in ("敏感", "联动")):
        return "中高"
    if any(token in value for token in ("跟踪", "观察")):
        return "中"
    return "待补充"


def _fallback_industry_id_for_sw(sw_industry: str) -> str:
    for industry_id, sw_industries in HQD_INDUSTRY_MAPPING.items():
        if sw_industry in sw_industries:
            return industry_id
    return "unknown_hqd"


def _industry_name(industry_id: str) -> str:
    if industry_id in INDUSTRY_CATALOG:
        return INDUSTRY_CATALOG[industry_id]["name"]
    return "高质量发展行业"
