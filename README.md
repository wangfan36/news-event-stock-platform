# 新闻驱动选股系统 MVP

这个仓库现在包含两层能力：

- `iching_alpha/` 里的原始 A 股研究实验层，继续保留为内部因子与策略实验。
- `iching_alpha/research_os.py` 和 `iching_alpha/webapp.py` 提供新闻驱动选股系统 MVP，用来把全球/国内热点压缩成事件、产业链分析、候选股票池和 A 股/港股个股建议。
- `iching_alpha/catalogs/` 存放行业、公司和事件模板数据，后续扩充映射优先改这里，不再直接改 Python 常量。
- `iching_alpha/storage.py` 和 `iching_alpha/model_client.py` 现在支持保存用户自定义 RSS 源、OpenAI 兼容模型 API，并在生成时优先使用这些配置。
- `iching_alpha/technical_provider.py` 现在提供技术确认抽象层，支持 `mock / akshare / tradingview-mcp` 三档 provider。

## 运行方式

1. 安装依赖：

```bash
python -m pip install -r requirements.txt
```

2. 启动 Web 应用：

```bash
python -m iching_alpha.webapp
```

3. 打开浏览器访问：

```text
http://127.0.0.1:8000
```

## 主要接口

- `GET /`：中文落地页和新闻驱动工作台
- `GET /api/product/overview`：产品定位、定价和北极星指标
- `GET /api/demo-profile`：演示观察池
- `GET /api/news/stream`：演示热点事件流
- `GET /api/events`：演示热点事件列表
- `GET /api/events/<event_id>`：单个事件详情
- `GET /api/industries/<industry_id>`：单个产业链视图
- `GET /api/recommendations`：演示个股建议列表
- `GET /api/history/runs`：已落库的历史运行列表
- `GET /api/history/runs/<run_id>`：单次运行快照回放
- `GET /api/history/recommendations/<symbol>`：个股建议历史
- `GET /api/settings`：读取用户保存的 RSS / 模型配置
- `POST /api/settings`：保存用户自定义 RSS / 模型配置
- `POST /api/research/generate`：根据观察池生成工作台并自动写入 SQLite
- `POST /api/compliance/audit`：检查文案是否命中禁用词

## 当前持久化

- SQLite 数据库默认写入 `artifacts/db/news_stock.db`
- 当前会持久化研究运行快照、新闻项、事件对象和个股建议
- 新闻入口先经过原始 feed -> 标准化 -> 去重 -> 聚类，再进入研究链路
- `artifacts/cache/` 保存新闻刷新缓存
- `artifacts/logs/` 可放本地运行日志
- `artifacts/backups/` 可放备份文件

## 真实新闻模式

- 表单里勾选“优先抓取真实 RSS 新闻”后，系统会尝试抓取真实 RSS 源
- 也可以设置环境变量 `NEWS_USE_LIVE=1`
- 当前接入的是多路 RSS 源，抓取失败时会自动回退到内置演示源
- 用户也可以在前台填入自己的 RSS 地址，格式为 `URL | 名称 | 区域 | 市场`

## 用户模型配置

- 前台支持填写 OpenAI 兼容模型的 `base_url`、`model_name`、`api_key`
- 保存后，生成流程会优先使用你的模型对事件摘要和建议逻辑做润色增强
- 当前返回给前台的是脱敏后的 key 状态，不会直接回显原始 key

## 技术确认 Provider

- 前台支持选择 `mock`、`akshare`、`tradingview-mcp`
- `mock`：本地演示用，稳定、不依赖外部接口
- `akshare`：通过 AKShare 拉取 A 股 / 港股历史行情并生成技术确认
- `tradingview-mcp`：当前先保留为桥接位，后续可接真实 MCP bridge endpoint

## 2026data 独立补数层

- 目录：`D:\Github_Program\qlib_data\2026data`
- 这层只作为当前新闻驱动前端的补数覆盖层，不修改训练中的 `qlib_format`
- 当前已支持写入 `yahoo_price_overrides.json`
- 生成方式：运行 `scripts/build_2026data_overrides.py`
- 当前用途：优先补港股价格快照；估值和财务仍保持缺失原因提示

## 测试

```bash
pytest
```

## 合规边界

产品输出结构化研究建议和证据链，不做自动下单，不代客交易，不承诺收益。
