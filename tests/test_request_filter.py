"""Tests for ProviderRequest tool filtering."""

from __future__ import annotations

from dataclasses import dataclass

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import ProviderRequest
from matcher import ToolMatcher
from request_filter import copy_tool_set, filter_request_tools


@dataclass
class DummyTool(FunctionTool):
    """Simple FunctionTool stand-in for tests."""

    async def call(self, context, **kwargs):  # noqa: ANN001
        return "ok"


def _make_tool(name: str) -> DummyTool:
    return DummyTool(
        name=name,
        description="test tool",
        parameters={"type": "object", "properties": {}},
    )


def test_unauthorized_request_removes_only_matched_tools() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    shared = ToolSet(
        [
            _make_tool("luckin_menu"),
            _make_tool("web_search"),
        ]
    )
    req = ProviderRequest(func_tool=shared)

    result = filter_request_tools(
        req,
        matcher,
        should_remove=lambda _name: True,
        fail_closed=True,
    )

    assert result.success is True
    assert result.removed_names == ["luckin_menu"]
    assert result.after_names == ["web_search"]
    assert req.func_tool is not None
    assert req.func_tool.names() == ["web_search"]
    assert shared.names() == ["luckin_menu", "web_search"]


def test_authorized_filter_predicate_can_keep_tools() -> None:
    matcher = ToolMatcher.from_config("exact", ["luckin_menu"])
    req = ProviderRequest(func_tool=ToolSet([_make_tool("luckin_menu")]))

    result = filter_request_tools(
        req,
        matcher,
        should_remove=lambda _name: False,
        fail_closed=True,
    )

    assert result.removed_names == []
    assert req.func_tool is not None
    assert req.func_tool.names() == ["luckin_menu"]


def test_shared_tool_set_is_not_mutated() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    shared = ToolSet([_make_tool("luckin_a"), _make_tool("keep_me")])
    req_a = ProviderRequest(func_tool=copy_tool_set(shared))
    req_b = ProviderRequest(func_tool=copy_tool_set(shared))

    filter_request_tools(req_a, matcher, should_remove=lambda _name: True, fail_closed=True)
    assert req_a.func_tool is not None
    assert req_a.func_tool.names() == ["keep_me"]
    assert req_b.func_tool is not None
    assert req_b.func_tool.names() == ["luckin_a", "keep_me"]


def test_empty_tool_set_does_not_error() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    req = ProviderRequest(func_tool=ToolSet())

    result = filter_request_tools(
        req,
        matcher,
        should_remove=lambda _name: True,
        fail_closed=True,
    )

    assert result.success is True
    assert result.before_names == []
    assert result.after_names == []


def test_missing_func_tool_is_successful_noop() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    req = ProviderRequest()

    result = filter_request_tools(
        req,
        matcher,
        should_remove=lambda _name: True,
        fail_closed=True,
    )

    assert result.success is True
    assert req.func_tool is None


def test_unsupported_func_tool_type_fails_closed() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    req = ProviderRequest()
    req.func_tool = ["not-a-toolset"]  # type: ignore[assignment]

    result = filter_request_tools(
        req,
        matcher,
        should_remove=lambda _name: True,
        fail_closed=True,
    )

    assert result.success is False
    assert "unsupported func_tool type" in result.reason
