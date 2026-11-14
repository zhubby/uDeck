---
status: complete
priority: p2
issue_id: "018"
tags: [terminal, device, regression]
dependencies: []
---

# uTerminal 实机功能审查和修复

## Problem Statement

用户要求在 uConsole 上测试 uTerminal 的功能，修复复现的问题。此前已确认当前设置只提供字号调整，尚不能手动选择字体。

## Findings

- 当前实机安装 0.2.13，正常 labwc/Wayland 会话可通过 SSH 访问。
- 现有 native/PTY、QML 生命周期、设备键盘/TUI 和输入路由探针可作为基线。
- 当前工作树另有用户要求的平台首页五列改动；本任务保留该改动。

## Proposed Solutions

1. 复用现有探针并补充真实会话的操作检查；对确认的缺陷先建立失败回归，再做最小修复。
2. 使用模拟预览进行审查：速度快，但无法验证设备原生插件和实际输入路径，不能满足本次要求。

## Recommended Action

执行方案 1。保留现有会话、默认终端和系统设置，使用独立窗口与临时文件；验证候选源码并明确区分安装版、候选版与人手验收。

## Acceptance Criteria

- [x] 保存安装版实机基线和可复现的问题证据。
- [x] 覆盖输入、原生 PTY、会话/窗口、菜单、历史/复制、搜索、危险粘贴、字体、焦点和退出。
- [x] 为确认的产品缺陷补充有意义的失败回归并修复根因。
- [x] 相关自动回归、Ruff 和候选实机验证通过。
- [x] 完成审查，保存截图与报告，核对用户现有会话和系统设置。

## Work Log

### 2026-11-14

- 开始安装版实机基线与源码调查；按 systematic-debugging 流程处理异常，不把探针竞态当作产品缺陷。
- 复现并修复多窗口字号不同步、隐藏搜索框持有焦点、普通启动未恢复 Wayland 前台三个问题，均保留失败和通过证据。
- 本地终端组 98 passed / 4 native skipped；设备上加载原生插件的相同组 102 passed。最终菜单原生包装器复核 1 passed；本地外观与活动顺序回归 11 passed。
- 实际 CLI/D-Bus、同名窗口切换、内核虚拟键盘输入、Vim/less/tmux/Codex TUI 和退出检查通过；无真人实按或实际中文输入法候选窗验收声明。
- Ruff、diff 检查和代码审查完成；报告及截图见 `docs/udeck/terminal-device-audit-2026-11-14.md`。
- 核对现有安装版进程、子进程、窗口/会话、默认终端和用户配置保持一致；安装仍为 0.2.13，本轮未提交、推送或部署。
