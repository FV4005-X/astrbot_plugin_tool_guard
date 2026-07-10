"""Tests for execution-time tool blocking."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import mcp.types
import pytest
from runtime import update_runtime
from tool_block import (
    build_blocked_tool_result,
    ensure_tool_execution_guard,
    restore_all_tool_execution_guards,
    restore_tool_execution_guard,
)

from astrbot.core.agent.tool import FunctionTool
from astrbot.core.platform.message_type import MessageType


class FakeEvent:
    """Minimal event object for tool execution tests."""

    def __init__(self, message_type: MessageType, sender_id: str) -> None:
        self._message_type = message_type
        self._sender_id = sender_id

    def get_message_type(self) -> MessageType:
        return self._message_type

    def get_sender_id(self) -> str:
        return self._sender_id


def _context(event: FakeEvent | None) -> SimpleNamespace:
    """Build a minimal ContextWrapper-like object for call-path tests."""
    return SimpleNamespace(context=SimpleNamespace(event=event))


@pytest.fixture(autouse=True)
def _configure_runtime() -> None:
    restore_all_tool_execution_guards()
    update_runtime(
        enabled=True,
        allowed_users=["123"],
        tool_match_mode="prefix",
        restricted_tools=["luckin_", "queryShop"],
        blocked_message="blocked",
        fail_closed=True,
    )
    yield
    restore_all_tool_execution_guards()


class HandlerTool(FunctionTool):
    """Local tool that executes through ``handler``."""

    def __init__(self, name: str, handler: object) -> None:
        super().__init__(
            name=name,
            description="handler tool",
            parameters={"type": "object", "properties": {}},
            handler=handler,
        )


class CallOverrideTool(FunctionTool):
    """MCP-style tool that executes through overridden ``call``."""

    def __init__(self, name: str, impl: object) -> None:
        super().__init__(
            name=name,
            description="call tool",
            parameters={"type": "object", "properties": {}},
            handler=None,
        )
        self._impl = impl

    async def call(self, context, **kwargs: Any):  # noqa: ANN001
        return await self._impl(context, **kwargs)


class RunTool(FunctionTool):
    """Legacy tool that executes through ``run``."""

    def __init__(self, name: str, impl: object) -> None:
        super().__init__(
            name=name,
            description="run tool",
            parameters={"type": "object", "properties": {}},
            handler=None,
        )
        self._impl = impl

    async def run(self, event, **kwargs: Any):  # noqa: ANN001
        return await self._impl(event, **kwargs)


@pytest.mark.asyncio
async def test_handler_tool_authorized_executes_original() -> None:
    handler = AsyncMock(return_value="handler-ok")
    tool = HandlerTool("luckin_menu", handler)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.handler(event)

    assert result == "handler-ok"
    handler.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_handler_tool_unauthorized_is_blocked() -> None:
    handler = AsyncMock(return_value="handler-ok")
    tool = HandlerTool("luckin_menu", handler)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    result = await tool.handler(event)

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.isError is True
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_call_override_tool_authorized_executes_original() -> None:
    original_call = AsyncMock(return_value="call-ok")
    tool = CallOverrideTool("queryShopList", original_call)
    assert tool.handler is None

    ensure_tool_execution_guard(tool)
    assert tool.handler is None

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.call(_context(event))

    assert result == "call-ok"
    original_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_call_override_tool_unauthorized_is_blocked() -> None:
    original_call = AsyncMock(return_value="call-ok")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    result = await tool.call(_context(event))

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.isError is True
    original_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_tool_authorized_executes_original() -> None:
    original_run = AsyncMock(return_value="run-ok")
    tool = RunTool("luckin_run", original_run)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.run(event)

    assert result == "run-ok"
    original_run.assert_awaited_once_with(event)


@pytest.mark.asyncio
async def test_run_tool_unauthorized_is_blocked() -> None:
    original_run = AsyncMock(return_value="run-ok")
    tool = RunTool("luckin_run", original_run)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    result = await tool.run(event)

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.isError is True
    original_run.assert_not_awaited()


@pytest.mark.asyncio
async def test_async_generator_handler_returns_last_item() -> None:
    async def gen_handler(event, **kwargs):  # noqa: ANN001
        yield "A"
        yield "C"

    tool = HandlerTool("luckin_gen", gen_handler)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.handler(event)

    assert result == "C"


@pytest.mark.asyncio
async def test_async_generator_run_returns_last_item() -> None:
    class GenRunTool(FunctionTool):
        """Tool whose ``run`` is an async generator."""

        async def run(self, event, **kwargs):  # noqa: ANN001
            yield "first"
            yield "last"

    tool = GenRunTool(
        name="luckin_gen_run",
        description="run tool",
        parameters={"type": "object", "properties": {}},
        handler=None,
    )
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.run(event)

    assert result == "last"


@pytest.mark.asyncio
async def test_ensure_tool_execution_guard_is_idempotent() -> None:
    original_call = AsyncMock(return_value="once")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)
    first_call = tool.call
    ensure_tool_execution_guard(tool)

    assert tool.call is first_call
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    await tool.call(_context(event))
    original_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_restore_tool_execution_guard_restores_original_entry() -> None:
    original_call = AsyncMock(return_value="restored")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)
    guarded_call = tool.call

    restore_tool_execution_guard(tool)

    assert tool.call is not guarded_call
    assert tool.handler is None
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.call(_context(event))
    assert result == "restored"


@pytest.mark.asyncio
async def test_restore_all_tool_execution_guards_is_idempotent() -> None:
    original_call = AsyncMock(return_value="restored")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)
    restore_all_tool_execution_guards()
    restore_all_tool_execution_guards()

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.call(_context(event))
    assert result == "restored"


@pytest.mark.asyncio
async def test_query_shop_list_does_not_raise_no_handler() -> None:
    original_call = AsyncMock(
        return_value=mcp.types.CallToolResult(
            content=[mcp.types.TextContent(type="text", text="shop-list")],
        ),
    )
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    result = await tool.call(_context(event))

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.content[0].text == "shop-list"  # type: ignore[union-attr]


@pytest.mark.asyncio
async def test_future_task_context_unauthorized_still_blocks_restricted_tool() -> None:
    """Simulate an indirect cron/future_task execution path with a guarded tool."""
    original_call = AsyncMock(return_value="should-not-run")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)

    cron_event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="123")
    result = await tool.call(_context(cron_event))

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.isError is True
    original_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_unrestricted_tool_calls_original() -> None:
    original_call = AsyncMock(return_value="executed")
    tool = CallOverrideTool("web_search", original_call)
    ensure_tool_execution_guard(tool)

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    result = await tool.call(_context(event))

    assert result == "executed"
    original_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_fail_closed_without_event_blocks_call_tool() -> None:
    original_call = AsyncMock(return_value="executed")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)

    result = await tool.call(_context(None))

    assert isinstance(result, mcp.types.CallToolResult)
    assert result.isError is True
    original_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_fail_open_without_event_allows_call_tool() -> None:
    update_runtime(
        enabled=True,
        allowed_users=["123"],
        tool_match_mode="prefix",
        restricted_tools=["queryShop"],
        blocked_message="blocked",
        fail_closed=False,
    )
    original_call = AsyncMock(return_value="executed")
    tool = CallOverrideTool("queryShopList", original_call)
    ensure_tool_execution_guard(tool)

    result = await tool.call(_context(None))

    assert result == "executed"
    original_call.assert_awaited_once()


def test_build_blocked_tool_result_shape() -> None:
    result = build_blocked_tool_result("denied")
    assert result.isError is True
    assert result.content[0].text == "denied"  # type: ignore[union-attr]
