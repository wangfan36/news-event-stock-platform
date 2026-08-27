# Changelog

本文档遵循 Keep a Changelog，版本号遵循 Semantic Versioning。

## [Unreleased]

### Added

- 新增零构建依赖的 GitHub Pages 产品展示页，介绍研究证据链、终端界面、本地部署方式与安全边界。

### Changed

- 重设计 GitHub Pages 展示页，采用暗金、朱红、墨色和暖纸白的研究简报视觉，移除点阵、霓虹和伪终端装饰。
- 优化展示页中文字体与语义换行，并为导航、研究简报和部署面板增加可降级的玻璃拟态与克制动效。
- 将展示页独立控件与完整面板的边框统一为 20px 圆角，并保留组合组件的清晰分隔线。

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
