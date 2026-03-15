# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import marimo._utils.requests as requests
from marimo import _loggers
from marimo._ai._tools.base import ToolBase
from marimo._ai._tools.types import SuccessResult, ToolGuidelines
from marimo._utils.paths import marimo_package_path

LOGGER = _loggers.marimo_logger()

# We ship the rules with the package in _static/AGENTS.md
# If the file doesn't exist (development or edge cases), we fallback to fetching from the URL
MARIMO_RULES_URL = "https://docs.marimo.io/CLAUDE.md"
MARIMO_RULES_PATH = marimo_package_path() / "_static" / "AGENTS.md"
# Legacy path for backward compatibility with older builds
MARIMO_LEGACY_RULES_PATH = marimo_package_path() / "_static" / "CLAUDE.md"

# Topic-specific rule files shipped alongside the main rules
LLM_RULES_DIR = marimo_package_path() / "_static" / "llm_rules"

AVAILABLE_TOPICS = frozenset(
    {"visualization", "ui_elements", "sql", "data_handling"}
)


@dataclass
class GetMarimoRulesArgs:
    topic: Optional[str] = None


@dataclass
class GetMarimoRulesOutput(SuccessResult):
    rules_content: Optional[str] = None
    source_url: str = MARIMO_RULES_URL


class GetMarimoRules(ToolBase[GetMarimoRulesArgs, GetMarimoRulesOutput]):
    """Retrieve marimo rules and guidelines. Use this before any other marimo tool to understand how marimo notebooks work.

    Call with no topic to get the core rules (fundamentals, pitfalls, MCP workflow).
    Call with a specific topic for in-depth guidance on that area.

    Args:
        topic: Optional topic for detailed rules. One of: visualization, ui_elements, sql, data_handling.
            If omitted, returns the core rules.

    Returns:
        The content of the rules file.
    """

    guidelines = ToolGuidelines(
        when_to_use=[
            "ALWAYS call with no topic first to get core marimo rules",
            "Then call with a specific topic when you need in-depth guidance for that area",
        ],
        avoid_if=[
            "The rules for this topic have already been retrieved recently",
        ],
        additional_info=(
            "Available topics: visualization, ui_elements, sql, data_handling. "
            "Call with no topic to get the core rules (fundamentals, pitfalls, MCP workflow)."
        ),
    )

    def handle(self, args: GetMarimoRulesArgs) -> GetMarimoRulesOutput:
        topic = args.topic

        # Validate topic if provided
        if topic is not None and topic not in AVAILABLE_TOPICS:
            return GetMarimoRulesOutput(
                status="error",
                message=(
                    f"Unknown topic '{topic}'. "
                    f"Available topics: {', '.join(sorted(AVAILABLE_TOPICS))}. "
                    f"Call with no topic to get the core rules."
                ),
                next_steps=[
                    f"Use one of: {', '.join(sorted(AVAILABLE_TOPICS))}",
                    "Or call with no topic for core rules",
                ],
            )

        # If a topic is requested, load from the topic-specific file
        if topic is not None:
            return self._load_topic_rules(topic)

        # No topic: load core rules
        return self._load_core_rules()

    def _load_topic_rules(self, topic: str) -> GetMarimoRulesOutput:
        """Load topic-specific rules from the llm_rules directory."""
        topic_path = LLM_RULES_DIR / f"{topic}.md"

        if topic_path.exists():
            try:
                rules_content = topic_path.read_text(encoding="utf-8")
                return GetMarimoRulesOutput(
                    rules_content=rules_content,
                    source_url="bundled",
                    next_steps=[
                        f"Apply the {topic} guidelines when working with this area",
                    ],
                )
            except Exception as e:
                LOGGER.warning(
                    "Failed to read topic rules from %s: %s",
                    topic_path,
                    str(e),
                )

        return GetMarimoRulesOutput(
            status="error",
            message=f"Topic rules file not found for '{topic}'",
            next_steps=[
                "Use the core rules (call with no topic) as a fallback",
            ],
        )

    def _load_core_rules(self) -> GetMarimoRulesOutput:
        """Load core rules from bundled AGENTS.md, legacy CLAUDE.md, or URL fallback."""
        # First, try the bundled AGENTS.md
        if MARIMO_RULES_PATH.exists():
            try:
                rules_content = MARIMO_RULES_PATH.read_text(encoding="utf-8")
                return GetMarimoRulesOutput(
                    rules_content=rules_content,
                    source_url="bundled",
                    next_steps=[
                        "Follow the guidelines in the rules when working with marimo notebooks",
                        "Call get_marimo_rules with a topic for detailed guidance: visualization, ui_elements, sql, data_handling",
                    ],
                )
            except Exception as e:
                LOGGER.warning(
                    "Failed to read bundled marimo rules from %s: %s",
                    MARIMO_RULES_PATH,
                    str(e),
                )
                # Fall through to legacy path

        # Second, try legacy CLAUDE.md for backward compatibility
        if MARIMO_LEGACY_RULES_PATH.exists():
            try:
                rules_content = MARIMO_LEGACY_RULES_PATH.read_text(
                    encoding="utf-8"
                )
                return GetMarimoRulesOutput(
                    rules_content=rules_content,
                    source_url="bundled",
                    next_steps=[
                        "Follow the guidelines in the rules when working with marimo notebooks",
                    ],
                )
            except Exception as e:
                LOGGER.warning(
                    "Failed to read legacy marimo rules from %s: %s",
                    MARIMO_LEGACY_RULES_PATH,
                    str(e),
                )
                # Fall through to fetch from URL

        # Fallback: fetch from the URL
        try:
            response = requests.get(MARIMO_RULES_URL, timeout=10)
            response.raise_for_status()

            return GetMarimoRulesOutput(
                rules_content=response.text(),
                source_url=MARIMO_RULES_URL,
                next_steps=[
                    "Follow the guidelines in the rules when working with marimo notebooks",
                ],
            )

        except Exception as e:
            LOGGER.warning(
                "Failed to fetch marimo rules from %s: %s",
                MARIMO_RULES_URL,
                str(e),
            )

            return GetMarimoRulesOutput(
                status="error",
                message=f"Failed to fetch marimo rules: {str(e)}",
                source_url=MARIMO_RULES_URL,
                next_steps=[
                    "Check internet connectivity",
                    "Verify the rules URL is accessible",
                    "Try again later if the service is temporarily unavailable",
                ],
            )
