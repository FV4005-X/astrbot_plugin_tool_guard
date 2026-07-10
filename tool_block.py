"""Execution-time blocking helpers for restricted tools."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable
from typing import TYPE_CHECKING, Any

import mcp.types

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.agent.tool import FunctionTool, ToolExecResult
from astrbot.core.astr_agent_context import AstrAgentContext

from .auth import is_authorized
from .runtime import RUNTIME

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent

_WRAPPED_ATTR = "_tool_guard_wrapped"
_ORIG_CALL_ATTR = "_tool_guard_orig_call"
_ORIG_HANDLER_ATTR = "_tool_guard_orig_handler"


def build_blocked_tool_result(message: str) -> mcp.types.CallToolResult:
    """Build a safe MCP-style blocked-tool result.

    Args:
        message: User-visible or model-visible block message.

    Returns:
        CallToolResult containing only the block message text.
    """
    return mcp.types.CallToolResult(
        content=[mcp.types.TextContent(type="text", text=message)],
        isError=True,
    )


def _extract_event(
    context: ContextWrapper[AstrAgentContext] | AstrMessageEvent | None,
) -> AstrMessageEvent | None:
    """Resolve the AstrMessageEvent from tool execution context."""
    if context is None:
        return None
    if hasattr(context, "get_sender_id"):
        return context  # type: ignore[return-value]
    inner = getattr(context, "context", None)
    if inner is not None and hasattr(inner, "event"):
        return inner.event
    return None


def _should_block(event: AstrMessageEvent | None, tool_name: str) -> bool:
    """Return whether the current tool execution must be blocked."""
    if not RUNTIME.enabled or not RUNTIME.matcher.has_rules():
        return False
    if not RUNTIME.matcher.match_tool_name(tool_name):
        return False
    if event is None:
        return RUNTIME.fail_closed
    return not is_authorized(
        event,
        RUNTIME.allowed_users,
        fail_closed=RUNTIME.fail_closed,
    )


async def _await_handler_result(result: Any) -> ToolExecResult:
    """Normalize decorator-style handler return values."""
    if inspect.isasyncgen(result):
        last_item: ToolExecResult | None = None
        async for item in result:
            if item is not None:
                last_item = item
        return last_item or ""
    if isinstance(result, Awaitable):
        return await result
    return result


def ensure_tool_execution_guard(tool: FunctionTool) -> None:
    """Wrap a shared tool once so execution can be blocked per event.

    AstrBot v4.26.x does not stop tool execution when ``event.stop_event()`` is
    called inside ``on_using_llm_tool``. The wrapper intercepts ``call`` and
    ``handler`` at execution time and reads the latest values from ``RUNTIME``.

    Args:
        tool: Tool object shared by AstrBot's global registry.
    """
    if getattr(tool, _WRAPPED_ATTR, False):
        return

    original_call = tool.call
    original_handler = tool.handler

    async def guarded_call(
        context: ContextWrapper[AstrAgentContext],
        **kwargs: Any,
    ) -> ToolExecResult:
        event = _extract_event(context)
        if _should_block(event, tool.name):
            return build_blocked_tool_result(RUNTIME.blocked_message)
        return await original_call(context, **kwargs)

    async def guarded_handler(event: AstrMessageEvent, **kwargs: Any) -> ToolExecResult:
        if _should_block(event, tool.name):
            return build_blocked_tool_result(RUNTIME.blocked_message)
        if original_handler is None:
            raise ValueError(f"Tool {tool.name} has no handler.")
        return await _await_handler_result(original_handler(event, **kwargs))

    setattr(tool, _ORIG_CALL_ATTR, original_call)
    setattr(tool, _ORIG_HANDLER_ATTR, original_handler)
    tool.call = guarded_call  # type: ignore[method-assign]
    tool.handler = guarded_handler
    setattr(tool, _WRAPPED_ATTR, True)
