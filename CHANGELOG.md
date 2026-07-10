# Changelog

本文件记录 [astrbot_plugin_tool_guard](https://github.com/FV4005-X/astrbot_plugin_tool_guard) 的版本变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [v1.0.2] - 2026-07-10

### Fixed

- 修复 MCP 工具（如 `queryShopList`）在授权用户调用时抛出 `Tool xxx has no handler` 的问题。根因是旧版 guard 对 `handler=None` 的工具强行注入 `guarded_handler`，与 AstrBot `_execute_local` 的入口优先级（handler > call > run）及 `_PermissionGuardedTool` 设计冲突。
- 执行期 guard 现仅包装工具原有的执行入口（`handler` / 重写的 `call` / `run`），与 `FunctionToolExecutor` 分派逻辑一致。
- 修复 `tests/test_matcher.py` 中无效正则测试用例的语法错误。

### Added

- 插件 `terminate()` 生命周期回调：卸载或重载时恢复共享 tool 对象的原始入口，避免包装残留。
- 扩充 `tests/test_tool_block.py`（handler / call / run / 异步生成器 / 恢复 / `queryShopList` 等场景）。
- 改进 `tests/conftest.py`，支持插件模块相对导入。

### Changed

- 第二层拦截说明：包装目标由固定的 `call` / `handler` 调整为按工具类型选择单一入口。

### Notes

- 从 v1.0.0 升级后建议 **重载插件或重启 AstrBot**，以清理旧版错误注入的 handler 包装。
- 兼容 AstrBot `>=4.23.1,<5`（已在 v4.26.5 验证）。

## [v1.0.0] - 2026-07-09

### Added

- 初始发布：LLM 请求前隐藏受限工具（`on_llm_request`）+ 工具执行前二次校验（`on_using_llm_tool`）。
- 支持私聊 + 用户白名单 + 工具名匹配（exact / prefix / contains / regex）。
- 默认 fail-closed 安全策略与可配置拦截提示。
