# Contributing

感谢参与 News Alpha。提交改动前请先创建 Issue，说明问题、数据来源和预期行为。

## 开发流程

1. Fork 仓库并从 `main` 创建功能分支。
2. 运行 `python -m pip install -e ".[dev]"`。
3. 修改代码并补充覆盖行为变化的测试。
4. 运行 `ruff check news_alpha tests scripts` 和 `python -m pytest`。
5. 提交 Pull Request，说明风险、验证方式和界面变化。

不要提交 API Key、Cookie、数据库、用户 RSS 列表、个人行情目录或受版权限制的数据。知识库条目应说明可公开验证的数据依据，不要把主观结论伪装成事实。
