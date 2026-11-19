# .github/workflows/
> L2 | Parent: ../AGENTS.md

release.yml: 仅监听 release: published；校验上一稳定包摘要，容器验收升级回退并上传 arm64 附件。
checks.yml: push/PR 运行版本、Ruff 与逐文件隔离测试；不生成 deb。

[PROTOCOL]: Update this header on change, then check AGENTS.md
