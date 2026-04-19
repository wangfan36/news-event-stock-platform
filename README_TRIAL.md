# 新闻事件推演选股平台 - 本地试用包说明

这是 Windows 本地试用版。它包含程序、前端、后端、配置模板和启动脚本，但不包含大型股票数据仓。

## 目录内容

- `iching_alpha/`: 后端与前端代码
- `config/default.yaml`: 本地数据路径配置
- `artifacts/`: 本地运行记录、缓存和日志目录
- `00_install_dependencies.bat`: 安装依赖
- `01_check_environment.bat`: 检查环境和数据路径
- `02_start_app.bat`: 启动应用
- `03_stop_app.bat`: 停止应用

## 使用前准备

1. 安装 Python 3.10 或更高版本。
2. 准备本地股票数据目录，默认路径为：

```text
D:\Github_Program\qlib_data
```

3. 如果数据目录不在默认位置，请修改：

```text
config/default.yaml
```

至少确认这些路径正确：

```text
qlib_provider_uri
parquet_path
industry_mapping_path
```

## 第一次启动

按顺序双击：

1. `00_install_dependencies.bat`
2. `01_check_environment.bat`
3. `02_start_app.bat`

启动后浏览器访问：

```text
http://127.0.0.1:8000/
```

组合终端访问：

```text
http://127.0.0.1:8000/portfolio
```

## 模型配置

支持两种模式：

1. `openai-compatible`
   - 需要填写兼容 OpenAI 的 `Base URL`
   - 需要填写对应 API Key

2. `codex-cli`
   - 适合本机已登录 Codex / ChatGPT 的用户
   - 先在本机终端执行 `codex login`
   - 前台 Provider 选择 `codex-cli`
   - `Base URL` 和 `API Key` 留空

## 数据与隐私

试用包不会自带你的历史数据库和 API Key。

用户自己的配置会保存在：

```text
artifacts/db/news_stock.db
```

## 常见问题

### 页面打不开

先双击：

```text
02_start_app.bat
```

如果仍打不开，检查是否有其他程序占用了 `8000` 端口。

### 股票数据读取失败

运行：

```text
01_check_environment.bat
```

检查 `config/default.yaml` 中的数据路径。

### RSS 没新闻

公共 RSSHub 源可能会被 403 拦截。建议使用页面中已经配置的 Google News 中文搜索源，或自行部署 RSSHub。

### AI 超时

如果使用 `codex-cli`，建议把前台 `AI 超时（秒）` 调到 `180` 或 `300`。
