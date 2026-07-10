"""ProviderRequest tool-set filtering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from astrbot.core.agent.tool import FunctionTool, ToolSet
from astrbot.core.provider.entities import ProviderRequest

from .matcher import ToolMatcher

if TYPE_CHECKING:
    from collections.abc import Callable


@dataclass(frozen=True)
class ToolFilterResult:
    """Result of filtering tools on a single ProviderRequest.

    Attributes:
        success: Whether filtering completed without structural errors.
        before_names: Tool names before filtering.
        removed_names: Restricted tool names removed from the request.
        after_names: Tool names after filtering.
        reason: Diagnostic message when filtering did not complete.
        modified: Whether the request tool set was replaced.
    """

    success: bool
    before_names: list[str]
    removed_names: list[str]
    after_names: list[str]
    reason: str = ""
    modified: bool = False


def _tool_names(tool_set: ToolSet | None) -> list[str]:
    """Extract tool names from a ToolSet."""
    if tool_set is None:
        return []
    return tool_names_from_tools(tool_set.tools)


def tool_names_from_tools(tools: list[FunctionTool]) -> list[str]:
    """Extract names from a list of FunctionTool objects."""
    return [tool.name for tool in tools if getattr(tool, "name", None)]


def get_request_tool_set(req: ProviderRequest) -> ToolSet | None:
    """Read the tool set field used by the current AstrBot version.

    AstrBot v4.26.x stores per-request tools on ``ProviderRequest.func_tool``.

    Args:
        req: Provider request about to be sent to the LLM.

    Returns:
        The request-scoped ToolSet, or None when absent.
    """
    return getattr(req, "func_tool", None)


def set_request_tool_set(req: ProviderRequest, tool_set: ToolSet | None) -> None:
    """Assign the request-scoped tool set for the current AstrBot version.

    Args:
        req: Provider request about to be sent to the LLM.
        tool_set: Filtered ToolSet instance for this request only.
    """
    req.func_tool = tool_set


def copy_tool_set(tool_set: ToolSet) -> ToolSet:
    """Create a request-local ToolSet copy without mutating the source container.

    Tool objects themselves remain shared references, matching AstrBot core behavior
    in ``_plugin_tool_fix``. Only the ToolSet container is copied.

    Args:
        tool_set: Source tool set attached to a ProviderRequest.

    Returns:
        New ToolSet containing the same tool object references.
    """
    copied = ToolSet()
    for tool in tool_set.tools:
        copied.add_tool(tool)
    return copied


def filter_tool_set(
    tool_set: ToolSet,
    matcher: ToolMatcher,
    should_remove: Callable[[str], bool],
) -> tuple[ToolSet, list[str], list[str]]:
    """Filter a ToolSet copy by removing matched tool names.

    Args:
        tool_set: Source tool set.
        matcher: Restricted-tool matcher.
        should_remove: Predicate that decides whether a matched tool is removed.

    Returns:
        Tuple of filtered ToolSet, removed names, and kept names.
    """
    filtered = ToolSet()
    removed_names: list[str] = []
    kept_names: list[str] = []

    for tool in tool_set.tools:
        name = getattr(tool, "name", "") or ""
        if matcher.match_tool_name(name) and should_remove(name):
            removed_names.append(name)
            continue
        filtered.add_tool(tool)
        kept_names.append(name)

    return filtered, removed_names, kept_names


def filter_request_tools(
    req: ProviderRequest,
    matcher: ToolMatcher,
    *,
    should_remove: Callable[[str], bool],
    fail_closed: bool,
) -> ToolFilterResult:
    """Remove restricted tools from a single ProviderRequest.

    Args:
        req: Provider request about to be sent to the LLM.
        matcher: Restricted-tool matcher.
        should_remove: Predicate indicating whether matched tools should be removed.
        fail_closed: Whether unknown structures should be treated as failures.

    Returns:
        Structured filtering result for logging and diagnostics.
    """
    tool_set = get_request_tool_set(req)
    before_names = _tool_names(tool_set)

    if tool_set is None:
        return ToolFilterResult(
            success=True,
            before_names=before_names,
            removed_names=[],
            after_names=[],
            reason="no func_tool on ProviderRequest",
            modified=False,
        )

    if not isinstance(tool_set, ToolSet):
        reason = f"unsupported func_tool type: {type(tool_set).__name__}"
        return ToolFilterResult(
            success=not fail_closed,
            before_names=before_names,
            removed_names=[],
            after_names=before_names,
            reason=reason,
            modified=False,
        )

    if not matcher.has_rules():
        return ToolFilterResult(
            success=True,
            before_names=before_names,
            removed_names=[],
            after_names=before_names,
            reason="no restricted tool rules configured",
            modified=False,
        )

    try:
        filtered_set, removed_names, kept_names = filter_tool_set(
            copy_tool_set(tool_set),
            matcher,
            should_remove,
        )
    except Exception as exc:  # noqa: BLE001 - must not crash plugin load path
        reason = f"failed to copy/filter ToolSet: {exc}"
        return ToolFilterResult(
            success=not fail_closed,
            before_names=before_names,
            removed_names=[],
            after_names=before_names,
            reason=reason,
            modified=False,
        )

    modified = bool(removed_names)
    if modified:
        set_request_tool_set(req, filtered_set if filtered_set.tools else ToolSet())

    return ToolFilterResult(
        success=True,
        before_names=before_names,
        removed_names=removed_names,
        after_names=kept_names,
        modified=modified,
    )
