"""MCP / LLM tool permission guard plugin for AstrBot."""

from __future__ import annotations

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.provider import ProviderRequest
from astrbot.api.star import Context, Star
from astrbot.core.agent.tool import FunctionTool

from .auth import is_authorized
from .request_filter import ToolFilterResult, filter_request_tools
from .runtime import RUNTIME, update_runtime
from .tool_block import ensure_tool_execution_guard

# AstrBot sorts hook handlers by descending priority (larger number runs first).
HOOK_PRIORITY = 1000


class ToolGuardPlugin(Star):
    """Restrict selected MCP/LLM tools to authorized private-chat users."""

    def __init__(self, context: Context, config: AstrBotConfig | None = None) -> None:
        super().__init__(context)
        self.plugin_config = config or {}
        self._reload_runtime_config()

    def _reload_runtime_config(self) -> None:
        """Load plugin settings from AstrBotConfig with safe defaults."""
        cfg = self.plugin_config
        update_runtime(
            enabled=bool(cfg.get("enabled", True)),
            allowed_users=cfg.get("allowed_users") or [],
            tool_match_mode=str(cfg.get("tool_match_mode", "prefix")),
            restricted_tools=cfg.get("restricted_tools") or [],
            blocked_message=str(
                cfg.get("blocked_message", "该工具仅允许指定用户在私聊中使用。"),
            ),
            fail_closed=bool(cfg.get("fail_closed", True)),
            logger=logger,
        )
        self.notify_when_blocked = bool(cfg.get("notify_when_blocked", True))
        self.debug_log = bool(cfg.get("debug_log", False))

    async def initialize(self) -> None:
        """Refresh runtime config when the plugin is loaded or reloaded."""
        self._reload_runtime_config()

    def _is_sender_authorized(self, event: AstrMessageEvent) -> bool:
        """Return whether the current sender may use restricted tools."""
        return is_authorized(
            event,
            RUNTIME.allowed_users,
            fail_closed=RUNTIME.fail_closed,
        )

    def _debug_event_context(self, event: AstrMessageEvent) -> dict[str, str]:
        """Collect non-sensitive event context for debug logging."""
        return {
            "message_type": str(event.get_message_type()),
            "sender_id": str(event.get_sender_id()),
            "group_id": str(event.get_group_id()),
            "platform": str(event.get_platform_name()),
            "session_id": str(event.get_session_id()),
        }

    def _log_filter_result(
        self,
        event: AstrMessageEvent,
        result: ToolFilterResult,
    ) -> None:
        """Write sanitized debug logs for request-time filtering."""
        if not self.debug_log:
            return
        context = self._debug_event_context(event)
        logger.info(
            "tool_guard filter: authorized=%s context=%s before=%s removed=%s after=%s success=%s reason=%s",
            self._is_sender_authorized(event),
            context,
            result.before_names,
            result.removed_names,
            result.after_names,
            result.success,
            result.reason,
        )

    @filter.on_llm_request(priority=HOOK_PRIORITY)
    async def on_llm_request(
        self,
        event: AstrMessageEvent,
        req: ProviderRequest,
    ) -> None:
        """Hide restricted tools from unauthorized LLM requests."""
        if not RUNTIME.enabled or not RUNTIME.matcher.has_rules():
            return

        if self._is_sender_authorized(event):
            if self.debug_log:
                logger.info(
                    "tool_guard: authorized request, tools unchanged for sender=%s",
                    event.get_sender_id(),
                )
            return

        result = filter_request_tools(
            req,
            RUNTIME.matcher,
            should_remove=lambda _name: True,
            fail_closed=RUNTIME.fail_closed,
        )
        self._log_filter_result(event, result)

        if not result.success:
            level = logger.error if RUNTIME.fail_closed else logger.warning
            level(
                "tool_guard: request tool filtering failed; relying on execution guard. reason=%s",
                result.reason,
            )

    @filter.on_using_llm_tool(priority=HOOK_PRIORITY)
    async def on_using_llm_tool(
        self,
        event: AstrMessageEvent,
        tool: FunctionTool,
        tool_args: dict | None,
    ) -> None:
        """Block restricted tool execution when authorization fails."""
        if not RUNTIME.enabled or not RUNTIME.matcher.has_rules():
            return

        tool_name = getattr(tool, "name", "") or ""
        if not RUNTIME.matcher.match_tool_name(tool_name):
            return

        ensure_tool_execution_guard(tool)

        if self._is_sender_authorized(event):
            if self.debug_log:
                logger.info(
                    "tool_guard: authorized tool execution allowed for tool=%s sender=%s",
                    tool_name,
                    event.get_sender_id(),
                )
            return

        arg_keys = sorted((tool_args or {}).keys())
        logger.warning(
            "tool_guard: blocked restricted tool=%s sender=%s message_type=%s arg_keys=%s",
            tool_name,
            event.get_sender_id(),
            event.get_message_type(),
            arg_keys,
        )

        if self.notify_when_blocked and RUNTIME.blocked_message:
            await event.send(event.plain_result(RUNTIME.blocked_message))

    @filter.on_llm_tool_respond(priority=HOOK_PRIORITY)
    async def on_llm_tool_respond(
        self,
        event: AstrMessageEvent,
        tool: FunctionTool,
        tool_args: dict | None,
        tool_result: object | None,
    ) -> None:
        """Emit debug logs after restricted tool responses."""
        if not self.debug_log:
            return
        tool_name = getattr(tool, "name", "") or ""
        if RUNTIME.matcher.match_tool_name(tool_name):
            logger.info(
                "tool_guard: tool respond tool=%s authorized=%s",
                tool_name,
                self._is_sender_authorized(event),
            )
