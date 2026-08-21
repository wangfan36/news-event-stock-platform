# RSS 与模型配置

## RSS 行格式

每行一个源，字段使用半角竖线 `|` 分隔：

```text
URL | 名称 | 区域 | 市场 | 来源类型
```

只有 URL 必填，其余字段为空时采用默认值。规范如下：

- 支持 `http://` 和 `https://`，其他协议会忽略。
- `|` 两侧空格会自动清理；URL 内部不能有空格。
- 空行和以 `#` 开头的行会忽略。
- 重复 URL 只保留第一次出现的配置。
- 单次最多读取 50 个自定义源。
- 支持 RSS 2.0 的 `item` 和 Atom 的 `entry`。
- 发布时间优先读取 `pubDate/published/updated/date`；缺失时使用保守默认时效。

示例：

```text
# 全球市场
https://example.com/world.xml | World Desk | 全球 | A股+港股 | 国际媒体

# 只有 URL 也合法
https://example.org/atom.xml
```

## 模型配置

前台支持 OpenAI 兼容接口的 `Base URL`、`Model` 与 `API Key`。推荐在启动进程前设置环境变量，而不是把密钥写入本地数据库：

```powershell
$env:NEWS_ALPHA_API_KEY = "your-key"
.\scripts\start.ps1
```

如通过前台保存，密钥仅写入本机 `artifacts/db/news_stock.db`，API 返回时会脱敏；`artifacts/` 已被 Git 忽略。不要上传数据库、日志、截图中的密钥或 `config/local.yaml`。

模型只增强事件摘要和建议解释，不能改变规则生成的动作。请求失败时，工作区会返回 `model_runtime.status=error`，规则结果仍然有效。

如已安装 `market` 可选依赖，并希望允许系统调用网络财务接口，可显式设置 `NEWS_ALPHA_ENABLE_NETWORK_FUNDAMENTALS=1`。默认关闭，避免一次研究生成触发大量第三方请求。
