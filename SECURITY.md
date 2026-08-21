# Security Policy

## Supported versions

当前只维护最新的 `main` 分支。

## Reporting

请不要为密钥泄露、任意文件访问、命令执行或依赖漏洞创建公开 Issue。请通过 GitHub Security Advisories 的私密报告功能联系维护者，并提供复现步骤、影响范围和建议修复方式。

## Local secrets

运行数据保存在 `artifacts/`，个人配置保存在 `config/local.yaml` 或环境变量中，这些路径默认不会被 Git 跟踪。前台保存的模型密钥会存在本机 SQLite 中；共享电脑上优先使用 `NEWS_ALPHA_API_KEY` 环境变量。
