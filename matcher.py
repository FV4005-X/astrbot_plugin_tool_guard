"""Tool name matching for restricted tool rules."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable, Pattern


@dataclass
class ToolMatcher:
    """Match tool names against configured restricted rules.

    Attributes:
        mode: Matching mode: exact, prefix, contains, or regex.
        patterns: Raw configured patterns.
        compiled_regexes: Precompiled regex patterns for regex mode.
        invalid_regexes: Regex patterns that failed to compile.
    """

    mode: str
    patterns: tuple[str, ...]
    compiled_regexes: tuple[Pattern[str], ...] = field(default_factory=tuple)
    invalid_regexes: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_config(
        cls,
        mode: str,
        restricted_tools: Iterable[object] | None,
        *,
        logger=None,
    ) -> ToolMatcher:
        """Build a matcher from plugin configuration.

        Args:
            mode: Matching mode from configuration.
            restricted_tools: Restricted tool patterns.
            logger: Optional AstrBot logger for invalid regex warnings.

        Returns:
            Configured ToolMatcher instance.
        """
        normalized_mode = (mode or "prefix").strip().lower()
        patterns = tuple(
            stripped
            for item in (restricted_tools or [])
            if isinstance(item, str) and (stripped := item.strip())
        )

        compiled: list[Pattern[str]] = []
        invalid: list[str] = []
        if normalized_mode == "regex":
            for pattern in patterns:
                try:
                    compiled.append(re.compile(pattern, re.IGNORECASE))
                except re.error:
                    invalid.append(pattern)
                    if logger is not None:
                        logger.warning(
                            "tool_guard: invalid regex pattern ignored: %s",
                            pattern,
                        )

        return cls(
            mode=normalized_mode,
            patterns=patterns,
            compiled_regexes=tuple(compiled),
            invalid_regexes=tuple(invalid),
        )

    def has_rules(self) -> bool:
        """Return whether any restricted patterns are configured."""
        return bool(self.patterns)

    def match_tool_name(self, tool_name: str | None) -> bool:
        """Return whether a tool name matches restricted rules.

        Args:
            tool_name: Tool name reported by AstrBot.

        Returns:
            True when the name matches configured restricted rules.
        """
        if not tool_name or not self.patterns:
            return False

        name = tool_name.strip()
        if not name:
            return False

        if self.mode == "exact":
            return any(name.casefold() == pattern.casefold() for pattern in self.patterns)

        if self.mode == "prefix":
            lowered_name = name.casefold()
            return any(
                lowered_name.startswith(pattern.casefold()) for pattern in self.patterns
            )

        if self.mode == "contains":
            lowered_name = name.casefold()
            return any(
                pattern.casefold() in lowered_name for pattern in self.patterns
            )

        if self.mode == "regex":
            return any(regex.search(name) for regex in self.compiled_regexes)

        return False
