"""Tests for authorization helpers."""

from __future__ import annotations

from auth import is_authorized, normalize_allowed_users, normalize_user_id
from astrbot.core.platform.message_type import MessageType


class FakeEvent:
    """Minimal AstrMessageEvent stand-in for unit tests."""

    def __init__(
        self,
        message_type: MessageType,
        sender_id: object = "",
        group_id: str = "",
    ) -> None:
        self._message_type = message_type
        self._sender_id = sender_id
        self._group_id = group_id

    def get_message_type(self) -> MessageType:
        return self._message_type

    def get_sender_id(self) -> str:
        return str(self._sender_id)

    def get_group_id(self) -> str:
        return self._group_id


def test_private_whitelisted_user_is_authorized() -> None:
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123456789")
    allowed = normalize_allowed_users(["123456789"])
    assert is_authorized(event, allowed, fail_closed=True) is True


def test_private_non_whitelisted_user_is_denied() -> None:
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="111")
    allowed = normalize_allowed_users(["222"])
    assert is_authorized(event, allowed, fail_closed=True) is False


def test_group_whitelisted_user_is_denied() -> None:
    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="123456789", group_id="999")
    allowed = normalize_allowed_users(["123456789"])
    assert is_authorized(event, allowed, fail_closed=True) is False


def test_group_non_whitelisted_user_is_denied() -> None:
    event = FakeEvent(MessageType.GROUP_MESSAGE, sender_id="111", group_id="999")
    allowed = normalize_allowed_users(["222"])
    assert is_authorized(event, allowed, fail_closed=True) is False


def test_other_message_is_denied_by_default() -> None:
    event = FakeEvent(MessageType.OTHER_MESSAGE, sender_id="123456789")
    allowed = normalize_allowed_users(["123456789"])
    assert is_authorized(event, allowed, fail_closed=True) is False


def test_empty_whitelist_denies_everyone() -> None:
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id="123456789")
    assert is_authorized(event, frozenset(), fail_closed=True) is False


def test_numeric_and_string_ids_match() -> None:
    event = FakeEvent(MessageType.FRIEND_MESSAGE, sender_id=123456789)
    allowed = normalize_allowed_users(["123456789"])
    assert is_authorized(event, allowed, fail_closed=True) is True


def test_normalize_user_id_strips_spaces() -> None:
    assert normalize_user_id(" 123 ") == "123"
