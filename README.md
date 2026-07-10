# MCP 工具权限控制

仓库：[FV4005-X/astrbot_plugin_tool_guard](https://github.com/FV4005-X/astrbot_plugin_tool_guard)

AstrBot 插件：根据会话类型、用户白名单和工具名称，在 LLM 请求前隐藏受限 MCP/LLM 工具，并在工具执行前进行二次权限校验。

## 插件简介

本插件用于限制一组 MCP / LLM 工具仅能在 **私聊** 且 **发送者在白名单中** 时暴露和调用。典型场景包括瑞幸咖啡 MCP、订单/支付类 MCP、OAuth 绑定类 MCP 等，但插件本身不包含任何业务硬编码，所有规则均通过配置指定。

## 安全模型

采用 **默认拒绝（fail-closed）** 策略：

1. 必须 **明确识别为私聊**（`MessageType.FRIEND_MESSAGE`）。
2. 发送者 ID 必须位于 `allowed_users` 白名单。
3. 两项 **同时满足** 才允许暴露/调用受限工具。
4. `allowed_users` 为空时，表示 **没有任何用户** 可以使用受限工具。
5. 无法识别消息类型、缺少 sender ID、或无法处理工具集合结构时，在 `fail_closed=true` 下默认拒绝。

## 工作原理

### 第一层：LLM 请求前隐藏工具

钩子：`@filter.on_llm_request`

- 对未授权会话，从当前 `ProviderRequest.func_tool` 中 **移除** 匹配的受限工具。
- 仅修改 **当前这一次** LLM 请求的工具集合，不修改全局工具注册表。
- **不修改** `system_prompt`、人格提示词，也不向提示词追加“禁止使用某 MCP”等文字。
- 未授权会话在请求阶段 **不会** 主动发送拦截提示，避免群聊普通对话产生干扰。

### 第二层：工具执行前兜底

钩子：`@filter.on_using_llm_tool`

- 若模型仍尝试调用受限工具，则在工具真正执行前再次校验权限。
- 拦截时可根据 `notify_when_blocked` 向用户发送 `blocked_message`。
- 由于 AstrBot v4.26.x 在 `on_using_llm_tool` 阶段 **不会** 因 `event.stop_event()` 而跳过工具执行，本插件通过对共享工具对象安装 **一次性执行期包装器**，在 `call` / `handler` 入口返回错误结果，从而避免 MCP/本地工具真正执行。

## 文件结构

```text
astrbot_plugin_tool_guard/
├── main.py              # 插件入口，注册 on_llm_request / on_using_llm_tool 钩子
├── auth.py              # 私聊 + 白名单授权判断
├── matcher.py           # 工具名匹配（exact/prefix/contains/regex）
├── request_filter.py    # ProviderRequest.func_tool 请求级过滤
├── runtime.py           # 可热重载的运行时配置
├── tool_block.py        # 工具执行期拦截包装器
├── _conf_schema.json    # WebUI 配置 Schema
├── metadata.yaml        # 插件元数据
├── requirements.txt     # 无第三方依赖，保留空文件
├── README.md
├── LICENSE
└── tests/               # 单元测试
```

## 安装方式

1. 将本仓库放入 AstrBot 的 `data/plugins/` 目录，例如：

   ```text
   AstrBot/data/plugins/astrbot_plugin_tool_guard/
   ```

2. 启动 AstrBot：

   ```bash
   uv sync
   uv run main.py
   ```

3. 打开 WebUI → **插件**，找到 **MCP 工具权限控制**，启用并重载。

## 配置说明

配置文件由 AstrBot 自动生成：`data/config/astrbot_plugin_tool_guard_config.json`

| 配置项 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `enabled` | bool | `true` | 是否启用插件 |
| `allowed_users` | list[string] | `[]` | 允许使用受限工具的发送者 ID 白名单 |
| `tool_match_mode` | string | `prefix` | `exact` / `prefix` / `contains` / `regex` |
| `restricted_tools` | list[string] | `[]` | 受限工具名、前缀或正则 |
| `blocked_message` | string | 见 schema | 执行前拦截时的用户提示 |
| `notify_when_blocked` | bool | `true` | 执行前拦截时是否发送提示 |
| `debug_log` | bool | `false` | 是否输出调试日志 |
| `fail_closed` | bool | `true` | 异常/未知状态时是否默认拒绝 |

### 瑞幸 MCP 示例配置

> **注意：** 以下工具前缀仅为示例。MCP 工具在 AstrBot 中通常直接使用 MCP 服务器返回的原始工具名，**不保证** 一定带有 `luckin_` 等前缀。请先开启 `debug_log` 确认实际名称。

```json
{
  "enabled": true,
  "allowed_users": [
    "123456789"
  ],
  "tool_match_mode": "prefix",
  "restricted_tools": [
    "luckin_",
    "lkcoffee_"
  ],
  "notify_when_blocked": true,
  "blocked_message": "该工具仅允许指定用户在私聊中使用。",
  "debug_log": true,
  "fail_closed": true
}
```

## 如何确认实际 MCP 工具名

1. 将 `debug_log` 设为 `true`。
2. 使用白名单 QQ 私聊机器人，触发一次会调用 MCP 的对话。
3. 在 AstrBot 日志中搜索 `tool_guard filter`，查看 `before=` 列表中的工具名称。
4. 根据实际名称填写 `restricted_tools`，优先使用 **完整工具名** 或 **唯一前缀**，避免使用 `order`、`menu`、`user` 等过于宽泛的词。

## 如何判断私聊和发送者 ID

- 私聊判断使用 AstrBot 官方 `event.get_message_type()`，仅当返回 `MessageType.FRIEND_MESSAGE` 时视为私聊。
- 发送者 ID 使用 `event.get_sender_id()`，并与 `allowed_users` 中的字符串（去首尾空格）比较。
- `group_id` 为空 **不能** 作为授权依据，只会在调试日志中作为辅助信息输出。

## 兼容版本

- AstrBot：`>=4.23.1,<5`（依赖 `on_using_llm_tool` / `on_llm_tool_respond`）
- 已在本地源码 v4.26.5 上确认：
  - 请求工具字段：`ProviderRequest.func_tool: ToolSet | None`
  - Hook 优先级：**数值越大越先执行**
  - `on_using_llm_tool` 中 `event.stop_event()` **不能** 阻止工具执行

## 热重载

WebUI → 插件 → **MCP 工具权限控制** → `...` → **重载插件**

## 测试

插件自带纯函数/单元测试，可在 **任意能安装 AstrBot 依赖的环境** 中运行，不要求本机连接 QQ。

```bash
cd data/plugins/astrbot_plugin_tool_guard
pytest tests/
```

或在 AstrBot 项目根目录：

```bash
uv run pytest data/plugins/astrbot_plugin_tool_guard/tests -q
```

本仓库已完成逻辑层单元测试编写；联调请在可连接 QQ / MCP 的部署环境中进行。

## 手工验证流程

1. 启用插件。
2. 在 `allowed_users` 中配置一个白名单 QQ 号。
3. 开启 `debug_log`。
4. 白名单用户私聊机器人，确认日志中 `before=` 仍包含目标 MCP 工具。
5. 非白名单用户私聊机器人，确认日志中 `removed=` 包含目标 MCP 工具。
6. 在群聊中请求与受限 MCP 相关的能力，确认 `removed=` 中出现目标工具。
7. 尝试通过历史上下文或明确工具名诱导调用，确认第二层拦截日志出现且 MCP 未真正执行。
8. 再次由白名单用户私聊调用，确认工具仍可用。
9. 检查日志中没有 Token、Cookie、Authorization、完整工具参数或订单敏感数据。

## 已知限制

1. **执行期包装器** 安装在 AstrBot 全局共享的工具对象上（与核心 `_plugin_tool_fix` 相同级别的对象共享模型）。包装器通过当前 `event` 上下文判断授权，正常情况下可并发工作，但属于对 AstrBot 当前架构的兼容方案。
2. `event.stop_event()` 在 `on_using_llm_tool` 中 **无法** 阻止工具执行，本插件已改用执行期拦截。
3. 若未来 AstrBot 更改 `ProviderRequest` 工具字段名或 `ToolSet` 结构，需要更新 `request_filter.py` 中的版本适配层。
4. 第一层过滤依赖 `on_llm_request`；若某些第三方 Agent 运行器绕过该钩子，第二层仍尽量阻止真实执行，但模型可能仍看到工具（取决于运行器实现）。

## 安全提示

- MCP 可能涉及 OAuth、Cookie、订单和支付信息，不应在群聊中暴露。
- 建议使用唯一工具前缀或完整工具名，不要使用过于宽泛的模糊匹配。
- 白名单为空即表示全员禁止，请勿把空列表理解为“允许所有私聊用户”。
- 调试日志仅输出工具名和参数 **键名**，不会输出完整敏感参数。

## 推荐的首次调试配置

```json
{
  "enabled": true,
  "allowed_users": ["你的QQ号"],
  "tool_match_mode": "prefix",
  "restricted_tools": [],
  "debug_log": true,
  "fail_closed": true,
  "notify_when_blocked": true
}
```

先保持 `restricted_tools` 为空，确认插件加载正常；再通过 `debug_log` 获取真实工具名后填入规则。

## License

See [LICENSE](LICENSE).
