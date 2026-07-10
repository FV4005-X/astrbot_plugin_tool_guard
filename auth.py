"""Authorization helpers for tool guard."""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from astrbot.core.platform.message_type import MessageType

if TYPE_CHECKING:
    from astrbot.core.platform.astr_message_event import AstrMessageEvent


def normalize_user_id(user_id: object) -> str:
    """Normalize a sender ID for whitelist comparison.

    Args:
        user_id: Raw sender identifier from the platform.

    Returns:
        Trimmed string form of the ID, or empty string when missing.
    """
    if user_id is None:
        return ""
    return str(user_id).strip()


def normalize_allowed_users(allowed_users: Iterable[object] | None) -> frozenset[str]:
    """Build a normalized whitelist set from configuration.

    Args:
        allowed_users: Configured whitelist entries.

    Returns:
        Frozenset of normalized non-empty user IDs.
    """
    if not allowed_users:
        return frozenset()
    return frozenset(
        normalized
        for item in allowed_users
        if (normalized := normalize_user_id(item))
    )


def is_private_message(event: AstrMessageEvent) -> bool | None:
    """Return whether the event is a private chat.

    Args:
        event: Current AstrBot message event.

    Returns:
        True for private chat, False for group/other, or None when unknown.
    """
    message_type = event.get_message_type()
    if message_type == MessageType.FRIEND_MESSAGE:
        return True
    if message_type in (MessageType.GROUP_MESSAGE, MessageType.OTHER_MESSAGE):
        return False
    return None


def is_authorized(
    event: AstrMessageEvent,
    allowed_users: frozenset[str],
    *,
    fail_closed: bool = True,
) -> bool:
    """Check whether the sender may use restricted tools.

    Authorization requires an explicitly private message and a whitelisted sender.

    Args:
        event: Current AstrBot message event.
        allowed_users: Normalized sender whitelist.
        fail_closed: When True, unknown states are treated as unauthorized.

    Returns:
        True only for private chat with a whitelisted sender.
    """
    private = is_private_message(event)
    if private is not True:
        if private is None and not fail_closed:
            return True
        return False

    sender_id = normalize_user_id(event.get_sender_id())
    if not sender_id:
        return not fail_closed

    if not allowed_users:
        return False

    return sender_id in allowed_users
