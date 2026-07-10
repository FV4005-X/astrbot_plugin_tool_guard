"""Tests for execution-time tool blocking."""

from __future__ import annotations

from dataclasses import dataclass
from unittest.mock import AsyncMock

import pytest

from astrbot.core.agent.run_context import ContextWrapper
from astrbot.core.astr_agent_context import AstrAgentContext
from astrbot.core.platform.message_type import MessageType
from runtime import update_runtime
from tool_block import ensure_tool_execution_guard


class FakeEvent:
    """Minimal event object for tool execution tests."""

    def __init__(self, message_type: MessageType, sender_id: str) -> None:
        self._message_type = message_type
        self._sender_id = sender_id

    def get_message_type(self) -> MessageType:
        return self._message_type

    def get_sender_id(self) -> str:
        return self._sender_id


@dataclass
class DummyTool:
    """Minimal tool object with call/handler hooks."""

    name: str
    call: object = None
    handler: object = None


@pytest.fixture(autouse=True)
def _configure_runtime() -> None:
    update_runtime(
        enabled=True,
        allowed_users=["123"],
        tool_match_mode="prefix",
        restricted_tools=["luckin_"],
        blocked_message="blocked",
        fail_closed=True,
    )


@pytest.mark.asyncio
async def test_unauthorized_restricted_tool_does_not_call_original() -> None:
    original_call = AsyncMock(return_value="executed")
    tool = DummyTool(name="luckin_menu", call=original_call)
    ensure_tool_execution_guard(tool)  # type: ignore[arg-type]

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    context = ContextWrapper(
        AstrAgentContext(event=event, context=None),  # type: ignore[arg-type]
    )

    result = await tool.call(context)

    assert getattr(result, "isError", False) is True
    original_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_authorized_restricted_tool_calls_original() -> None:
    original_call = AsyncMock(return_value="executed")
    tool = DummyTool(name="luckin_menu", call=original_call)
    ensure_tool_execution_guard(tool)  # type: ignore[arg-type]

    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123")
    context = ContextWrapper(
        AstrAgentContext(event=event, context=None),  # type: ignore[arg-type]
    )

    result = await tool.call(context)

    assert result == "executed"
    original_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_unrestricted_tool_calls_original() -> None:
    original_call = AsyncMock(return_value="executed")
    tool = DummyTool(name="web_search", call=original_call)
    ensure_tool_execution_guard(tool)  # type: ignore[arg-type]

    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="999")
    context = ContextWrapper(
        AstrAgentContext(event=event, context=None),  # type: ignore[arg-type]
    )

    result = await tool.call(context)

    assert result == "executed"
    original_call.assert_awaited_once()
