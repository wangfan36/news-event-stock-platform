# Changelog

本文档遵循 Keep a Changelog，版本号遵循 Semantic Versioning。

## [Unreleased]

## [1.1.0] - 2026-08-22

### Changed

- 后续版本从 MIT 调整为 PolyForm Noncommercial License 1.0.0，仅授权符合条款的非商业用途。
- 项目定位改为“源码可见”而不是 OSI 定义的“开源”。
- 新增中英文授权说明、商业使用边界、法律资料与历史 MIT 版本说明。
- `v1.0.0` 及截至提交 `0c895e8` 的版本继续适用其发布时的 MIT 许可证。

## [1.0.0] - 2026-08-21

### Added

- 本地新闻事件研究前台、API、SQLite 历史回放和组合研究视图。
- 自定义 RSS/Atom、OpenAI 兼容模型、AKShare 与可选 Parquet 数据源。
- 可解释事件、产业链、公司和建议证据链。
- 可移植配置、Windows 安装脚本、CI 和项目治理文档。

### Changed

- Python 包从历史实验名迁移为 `news_alpha`。
- 删除易经、奇门、旧回测等与正式产品无关的实验模块。
- 本地行情从强制依赖改为可选增强，移除个人硬盘路径。
- RSS 使用真实发布时间，失败时保留上次有效缓存。

[Unreleased]: https://github.com/wangfan36/news-event-stock-platform/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/wangfan36/news-event-stock-platform/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/wangfan36/news-event-stock-platform/releases/tag/v1.0.0
