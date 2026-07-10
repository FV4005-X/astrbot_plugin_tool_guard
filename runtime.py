"""Shared runtime state for tool guard hooks and execution wrappers."""

from __future__ import annotations

from dataclasses import dataclass, field

from .auth import normalize_allowed_users
from .matcher import ToolMatcher


@dataclass
class GuardRuntime:
    """Mutable runtime configuration shared by hooks and tool wrappers.

    Attributes:
        enabled: Whether the plugin is active.
        allowed_users: Normalized sender whitelist.
        blocked_message: Message returned when a tool execution is blocked.
        fail_closed: Whether unknown states should default to deny.
        matcher: Restricted tool matcher built from current config.
    """

    enabled: bool = True
    allowed_users: frozenset[str] = field(default_factory=frozenset)
    blocked_message: str = "该工具仅允许指定用户在私聊中使用。"
    fail_closed: bool = True
    matcher: ToolMatcher = field(
        default_factory=lambda: ToolMatcher.from_config("prefix", [])
    )


RUNTIME = GuardRuntime()


def update_runtime(
    *,
    enabled: bool,
    allowed_users: object,
    tool_match_mode: str,
    restricted_tools: object,
    blocked_message: str,
    fail_closed: bool,
    logger=None,
) -> None:
    """Refresh module-level runtime state after config load or plugin reload.

    Args:
        enabled: Whether the plugin is active.
        allowed_users: Raw whitelist from plugin config.
        tool_match_mode: Tool matching mode from plugin config.
        restricted_tools: Restricted tool patterns from plugin config.
        blocked_message: User-visible block message.
        fail_closed: Whether unknown states should default to deny.
        logger: Optional AstrBot logger for matcher warnings.
    """
    RUNTIME.enabled = enabled
    RUNTIME.allowed_users = normalize_allowed_users(allowed_users)  # type: ignore[arg-type]
    RUNTIME.blocked_message = blocked_message
    RUNTIME.fail_closed = fail_closed
    RUNTIME.matcher = ToolMatcher.from_config(
        tool_match_mode,
        restricted_tools,  # type: ignore[arg-type]
        logger=logger,
    )
