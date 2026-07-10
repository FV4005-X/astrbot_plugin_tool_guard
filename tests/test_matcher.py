"""Tests for tool name matching."""

from __future__ import annotations

from matcher import ToolMatcher


def test_exact_match() -> None:
    matcher = ToolMatcher.from_config("exact", ["luckin_order"])
    assert matcher.match_tool_name("luckin_order") is True
    assert matcher.match_tool_name("luckin_order_extra") is False


def test_prefix_match() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    assert matcher.match_tool_name("luckin_menu") is True
    assert matcher.match_tool_name("other_menu") is False


def test_contains_match() -> None:
    matcher = ToolMatcher.from_config("contains", ["coffee"])
    assert matcher.match_tool_name("get_coffee_menu") is True
    assert matcher.match_tool_name("get_tea_menu") is False


def test_regex_match_is_case_insensitive() -> None:
    matcher = ToolMatcher.from_config("regex", [r"^lk.?order"])
    assert matcher.match_tool_name("LKXorder") is True
    assert matcher.match_tool_name("menu") is False


def test_empty_rules_do_not_match() -> None:
    matcher = ToolMatcher.from_config("prefix", [])
    assert matcher.match_tool_name("anything") is False


def test_invalid_regex_is_ignored() -> None:
    matcher = ToolMatcher.from_config("regex", ["("])
    assert matcher.match_tool_name("anything") is False
    assert matcher.invalid_regexes == ("([",)


def test_empty_tool_name_does_not_match() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    assert matcher.match_tool_name("") is False
    assert matcher.match_tool_name(None) is False


def test_unrelated_tool_is_not_matched() -> None:
    matcher = ToolMatcher.from_config("prefix", ["luckin_"])
    assert matcher.match_tool_name("web_search") is False


def test_case_insensitive_prefix() -> None:
    matcher = ToolMatcher.from_config("prefix", ["Luckin_"])
    assert matcher.match_tool_name("luckin_menu") is True
