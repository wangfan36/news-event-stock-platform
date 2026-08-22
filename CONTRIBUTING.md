# Contributing

感谢参与 News Alpha。提交改动前请先创建 Issue，说明问题、数据来源和预期行为。

## 开发流程

1. Fork 仓库并从 `main` 创建功能分支。
2. 运行 `python -m pip install -e ".[dev]"`。
3. 修改代码并补充覆盖行为变化的测试。
4. 运行 `ruff check news_alpha tests scripts` 和 `python -m pytest`。
5. 提交 Pull Request，说明风险、验证方式和界面变化。

不要提交 API Key、Cookie、数据库、用户 RSS 列表、个人行情目录或受版权限制的数据。知识库条目应说明可公开验证的数据依据，不要把主观结论伪装成事实。

## 贡献许可

本项目当前按 [PolyForm Noncommercial License 1.0.0](LICENSE) 提供，是源码可见软件，不是 OSI 定义的开源软件。提交代码、文档或其他材料，即表示你确认有权提交这些内容，并同意你的贡献按本项目收到贡献时适用的许可证发布。不要提交许可证不兼容、来源不明或你无权授权的内容。

商业授权只覆盖版权所有者有权许可的内容。外部贡献不会因为合入项目而自动授予维护者超出贡献者明确许可范围的商业再授权权利；如未来需要纳入商业授权，将另行取得相应贡献者的书面同意。完整边界见 [授权说明](LICENSING.zh-CN.md)。
