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
_ORIG_RUN_ATTR = "_tool_guard_orig_run"
_WRAP_HANDLER_ATTR = "_tool_guard_wrap_handler"
_WRAP_CALL_ATTR = "_tool_guard_wrap_call"
_WRAP_RUN_ATTR = "_tool_guard_wrap_run"
_GUARDED_HANDLER_ATTR = "_tool_guard_guarded_handler"
_GUARDED_CALL_ATTR = "_tool_guard_guarded_call"
_GUARDED_RUN_ATTR = "_tool_guard_guarded_run"

_WRAPPED_TOOLS: dict[int, FunctionTool] = {}


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
    """Resolve the AstrMessageEvent from tool execution context.

    Args:
        context: Tool execution context or a raw event object.

    Returns:
        Resolved message event, or None when unavailable.
    """
    if context is None:
        return None
    if hasattr(context, "get_sender_id"):
        return context  # type: ignore[return-value]
    inner = getattr(context, "context", None)
    if inner is not None and hasattr(inner, "event"):
        return inner.event
    return None


def _should_block(event: AstrMessageEvent | None, tool_name: str) -> bool:
    """Return whether the current tool execution must be blocked.

    Args:
        event: Current message event, if any.
        tool_name: Tool name being executed.

    Returns:
        True when execution must be blocked before reaching the original tool.
    """
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
    """Normalize handler/run return values.

    Args:
        result: Raw return value from a handler or run entry point.

    Returns:
        Final tool execution result after awaiting async values.
    """
    if inspect.isasyncgen(result):
        last_item: ToolExecResult | None = None
        async for item in result:
            if item is not None:
                last_item = item
        return last_item or ""
    if isinstance(result, Awaitable):
        return await result
    return result


def _tool_overrides_call(tool: FunctionTool) -> bool:
    """Return whether the tool class overrides ``FunctionTool.call``.

    Args:
        tool: Tool object from AstrBot's registry.

    Returns:
        True when the concrete tool type provides its own ``call`` implementation.
    """
    for ty in type(tool).mro():
        if "call" in ty.__dict__ and ty.__dict__["call"] is not FunctionTool.call:
            return True
    return False


def _resolve_execution_entry(tool: FunctionTool) -> str | None:
    """Pick the execution entry used by ``FunctionToolExecutor``.

    The priority matches ``FunctionToolExecutor._execute_local``:
    handler, overridden ``call``, then ``run``.

    Args:
        tool: Tool object from AstrBot's registry.

    Returns:
        ``handler``, ``call``, ``run``, or None when no entry is available.
    """
    if tool.handler is not None:
        return "handler"
    if _tool_overrides_call(tool):
        return "call"
    if callable(getattr(tool, "run", None)):
        return "run"
    return None


def ensure_tool_execution_guard(tool: FunctionTool) -> None:
    """Wrap a shared tool once so execution can be blocked per event.

    Only the tool's original execution entry is wrapped. Tools that execute via
    overridden ``call`` (including MCP tools) must not receive a synthetic
    ``handler``, because AstrBot would then route through the handler path.

    Args:
        tool: Tool object shared by AstrBot's global registry.
    """
    if getattr(tool, _WRAPPED_ATTR, False):
        return

    entry = _resolve_execution_entry(tool)
    if entry is None:
        return

    original_call = tool.call
    original_handler = tool.handler
    original_run = getattr(tool, "run", None)

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
        return await _await_handler_result(original_handler(event, **kwargs))

    async def guarded_run(event: AstrMessageEvent, **kwargs: Any) -> ToolExecResult:
        if _should_block(event, tool.name):
            return build_blocked_tool_result(RUNTIME.blocked_message)
        return await _await_handler_result(original_run(event, **kwargs))

    setattr(tool, _ORIG_CALL_ATTR, original_call)
    setattr(tool, _ORIG_HANDLER_ATTR, original_handler)
    setattr(tool, _ORIG_RUN_ATTR, original_run)

    if entry == "handler":
        setattr(tool, _GUARDED_HANDLER_ATTR, guarded_handler)
        tool.handler = guarded_handler
        setattr(tool, _WRAP_HANDLER_ATTR, True)
    elif entry == "call":
        setattr(tool, _GUARDED_CALL_ATTR, guarded_call)
        tool.call = guarded_call  # type: ignore[method-assign]
        setattr(tool, _WRAP_CALL_ATTR, True)
    elif entry == "run":
        setattr(tool, _GUARDED_RUN_ATTR, guarded_run)
        tool.run = guarded_run  # type: ignore[attr-defined]
        setattr(tool, _WRAP_RUN_ATTR, True)

    setattr(tool, _WRAPPED_ATTR, True)
    _WRAPPED_TOOLS[id(tool)] = tool


def restore_tool_execution_guard(tool: FunctionTool) -> None:
    """Restore original tool entry points when this plugin still owns the wrappers.

    Restoration is skipped for an entry when another component replaced the
    guarded method after this plugin installed it.

    Args:
        tool: Previously guarded tool object.
    """
    if not getattr(tool, _WRAPPED_ATTR, False):
        return

    if getattr(tool, _WRAP_HANDLER_ATTR, False):
        guarded = getattr(tool, _GUARDED_HANDLER_ATTR, None)
        if guarded is not None and tool.handler is guarded:
            tool.handler = getattr(tool, _ORIG_HANDLER_ATTR, None)
        for attr in (
            _WRAP_HANDLER_ATTR,
            _GUARDED_HANDLER_ATTR,
            _ORIG_HANDLER_ATTR,
        ):
            if hasattr(tool, attr):
                delattr(tool, attr)

    if getattr(tool, _WRAP_CALL_ATTR, False):
        guarded = getattr(tool, _GUARDED_CALL_ATTR, None)
        if guarded is not None and tool.call is guarded:
            tool.call = getattr(tool, _ORIG_CALL_ATTR, FunctionTool.call)  # type: ignore[method-assign]
        for attr in (_WRAP_CALL_ATTR, _GUARDED_CALL_ATTR, _ORIG_CALL_ATTR):
            if hasattr(tool, attr):
                delattr(tool, attr)

    if getattr(tool, _WRAP_RUN_ATTR, False):
        guarded = getattr(tool, _GUARDED_RUN_ATTR, None)
        original_run = getattr(tool, _ORIG_RUN_ATTR, None)
        current_run = getattr(tool, "run", None)
        if guarded is not None and current_run is guarded and original_run is not None:
            tool.run = original_run  # type: ignore[attr-defined]
        for attr in (_WRAP_RUN_ATTR, _GUARDED_RUN_ATTR, _ORIG_RUN_ATTR):
            if hasattr(tool, attr):
                delattr(tool, attr)

    if hasattr(tool, _WRAPPED_ATTR):
        delattr(tool, _WRAPPED_ATTR)
    _WRAPPED_TOOLS.pop(id(tool), None)


def restore_all_tool_execution_guards() -> None:
    """Restore every tool still tracked by this plugin."""
    for tool in list(_WRAPPED_TOOLS.values()):
        restore_tool_execution_guard(tool)
