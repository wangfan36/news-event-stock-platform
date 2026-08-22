# RSS 与模型配置

[English](rss-and-models.md) | **简体中文**

## 添加 RSS 源

1. 启动应用并打开 `http://127.0.0.1:8000/#settings`。
2. 进入 **数据与模型 > RSS 数据源**。
3. 每行填写一个源，并勾选 **生成时优先抓取真实 RSS**。
4. 点击 **保存全部配置**，再点击 **刷新数据** 验证可访问性，或点击 **生成研究** 运行完整链路。

每行使用半角竖线 `|` 分隔：

```text
URL | 名称 | 区域 | 市场 | 来源类型
https://example.com/feed.xml | Example News | 全球 | A股+港股 | 财经媒体
```

只有 URL 必填。以下两种写法都有效：

```text
# 分隔符两侧可以有空格
https://example.com/world.xml | World Desk | 全球 | A股+港股 | 国际媒体

# 只填写 URL
https://example.org/atom.xml
```

解析规则：

- 仅接受 `http://` 和 `https://` URL，URL 内部不能有空格。
- `|` 两侧空格会自动移除，缺少的可选字段使用默认值。
- 空行和以 `#` 开头的注释行会被忽略。
- 重复 URL 只保留第一次出现的配置。
- 一次最多读取 50 个自定义源。
- 支持 RSS 2.0 `item` 和 Atom `entry`。
- 发布时间依次尝试 `pubDate`、`published`、`updated` 和 `date`。

请填写订阅 Feed 地址，而不是新闻网站首页。若检查失败，请确认 URL 在本机网络中可访问、返回 XML、没有登录或验证码要求，并检查代理、防火墙和证书设置。单个源失败不会阻止规则引擎使用其他源或演示数据。

## 添加大模型 API Key

系统支持 OpenAI 兼容接口。推荐把密钥放在启动进程的环境变量中，而不是源码或配置样例中。

PowerShell 当前会话：

```powershell
$env:NEWS_ALPHA_API_KEY = "<your-provider-api-key>"
python -m news_alpha.webapp
```

macOS 或 Linux：

```bash
export NEWS_ALPHA_API_KEY="<your-provider-api-key>"
python -m news_alpha.webapp
```

然后打开 **数据与模型 > 大模型 API**：

1. 启用模型增强。
2. Provider 选择 `openai-compatible`。
3. 填写服务商提供的 Base URL，例如 `https://api.openai.com/v1`。
4. 填写服务商支持的模型名称。
5. 使用环境变量且前台从未保存过密钥时，保持 API Key 输入框为空。前台已保存的本机密钥优先级更高。
6. 保存配置并生成一次研究，在系统状态中检查模型运行结果。

也可以直接在前台输入 API Key。该方式会把密钥写入本机 `artifacts/db/news_stock.db`；API 返回时会脱敏，且 `artifacts/` 默认不被 Git 跟踪。若 Provider 选择 `codex-cli`，系统使用本机现有的 Codex 登录，不需要在网页中填写 API Key。

## 密钥安全

- 不要把真实密钥写入 `.env.example`、README、源码、Issue、日志或截图。
- `.env`、`config/local.yaml`、`artifacts/` 和本地数据库默认已被 Git 忽略。
- 推送前运行 `python scripts/check_secrets.py`；CI 会执行同一检查。
- 如果密钥曾被提交，应立即在服务商控制台撤销并轮换。仅删除最新提交中的文本无法清除 Git 历史。

模型只增强结构化研究文本，不能改变规则引擎生成的动作方向。模型请求失败时，规则结果仍可使用。
