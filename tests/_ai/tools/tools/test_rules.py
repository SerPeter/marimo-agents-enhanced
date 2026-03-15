# Copyright 2026 Marimo. All rights reserved.

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from marimo._ai._tools.base import ToolContext
from marimo._ai._tools.tools.rules import GetMarimoRules, GetMarimoRulesArgs


@pytest.fixture
def tool() -> GetMarimoRules:
    """Create a GetMarimoRules tool instance."""
    return GetMarimoRules(ToolContext())


def _mock_no_local_files():
    """Create mocks where no local files exist (AGENTS.md, CLAUDE.md, llm_rules/)."""
    mock_agents_path = Mock(spec=Path)
    mock_agents_path.exists.return_value = False
    mock_legacy_path = Mock(spec=Path)
    mock_legacy_path.exists.return_value = False
    mock_llm_dir_path = Mock(spec=Path)
    mock_llm_dir_path.exists.return_value = False
    mock_llm_dir = Mock(spec=Path)
    mock_llm_dir.__truediv__ = Mock(return_value=mock_llm_dir_path)
    return mock_agents_path, mock_legacy_path, mock_llm_dir


def test_get_rules_from_agents_md(tool: GetMarimoRules) -> None:
    """Test successfully loading rules from AGENTS.md."""
    mock_path = Mock(spec=Path)
    mock_path.exists.return_value = True
    mock_path.read_text.return_value = "# Agent Rules\n\nContent"

    with patch("marimo._ai._tools.tools.rules.MARIMO_RULES_PATH", mock_path):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "success"
    assert result.rules_content == "# Agent Rules\n\nContent"
    assert result.source_url == "bundled"
    assert any("Follow the guidelines" in s for s in result.next_steps)
    assert any("topic" in s for s in result.next_steps)
    mock_path.exists.assert_called_once()
    mock_path.read_text.assert_called_once_with(encoding="utf-8")


def test_get_rules_fallback_to_legacy_claude_md(
    tool: GetMarimoRules,
) -> None:
    """Test falling back to legacy CLAUDE.md when AGENTS.md doesn't exist."""
    mock_agents_path = Mock(spec=Path)
    mock_agents_path.exists.return_value = False

    mock_legacy_path = Mock(spec=Path)
    mock_legacy_path.exists.return_value = True
    mock_legacy_path.read_text.return_value = (
        "# Marimo Rules\n\nLegacy content"
    )

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "success"
    assert result.rules_content == "# Marimo Rules\n\nLegacy content"
    assert result.source_url == "bundled"


def test_get_rules_agents_read_error_fallback_to_legacy(
    tool: GetMarimoRules,
) -> None:
    """Test falling back to CLAUDE.md when AGENTS.md exists but can't be read."""
    mock_agents_path = Mock(spec=Path)
    mock_agents_path.exists.return_value = True
    mock_agents_path.read_text.side_effect = OSError("Permission denied")

    mock_legacy_path = Mock(spec=Path)
    mock_legacy_path.exists.return_value = True
    mock_legacy_path.read_text.return_value = (
        "# Marimo Rules\n\nLegacy content"
    )

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "success"
    assert result.rules_content == "# Marimo Rules\n\nLegacy content"
    assert result.source_url == "bundled"


def test_get_rules_fallback_to_url(tool: GetMarimoRules) -> None:
    """Test fetching from URL when no local files exist."""
    mock_agents_path, mock_legacy_path, _ = _mock_no_local_files()

    mock_response = Mock()
    mock_response.text.return_value = "# Marimo Rules\n\nURL content"
    mock_response.raise_for_status = Mock()

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
        patch("marimo._utils.requests.get", return_value=mock_response),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "success"
    assert result.rules_content == "# Marimo Rules\n\nURL content"
    assert result.source_url == "https://docs.marimo.io/CLAUDE.md"
    mock_response.raise_for_status.assert_called_once()


def test_get_rules_http_error(tool: GetMarimoRules) -> None:
    """Test handling HTTP errors when fetching rules from URL."""
    mock_agents_path, mock_legacy_path, _ = _mock_no_local_files()

    mock_response = Mock()
    mock_response.raise_for_status.side_effect = Exception("404 Not Found")

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
        patch("marimo._utils.requests.get", return_value=mock_response),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "error"
    assert result.rules_content is None
    assert "Failed to fetch marimo rules" in result.message
    assert "404 Not Found" in result.message
    assert result.source_url == "https://docs.marimo.io/CLAUDE.md"
    assert len(result.next_steps) == 3
    assert "Check internet connectivity" in result.next_steps[0]


def test_get_rules_network_error(tool: GetMarimoRules) -> None:
    """Test handling network errors when fetching rules from URL."""
    mock_agents_path, mock_legacy_path, _ = _mock_no_local_files()

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
        patch(
            "marimo._utils.requests.get",
            side_effect=Exception("Connection refused"),
        ),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "error"
    assert result.rules_content is None
    assert "Failed to fetch marimo rules" in result.message
    assert "Connection refused" in result.message
    assert len(result.next_steps) == 3


def test_get_rules_timeout(tool: GetMarimoRules) -> None:
    """Test handling timeout when fetching rules from URL."""
    mock_agents_path, mock_legacy_path, _ = _mock_no_local_files()

    with (
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_RULES_PATH",
            mock_agents_path,
        ),
        patch(
            "marimo._ai._tools.tools.rules.MARIMO_LEGACY_RULES_PATH",
            mock_legacy_path,
        ),
        patch(
            "marimo._utils.requests.get",
            side_effect=Exception("Request timeout"),
        ),
    ):
        result = tool.handle(GetMarimoRulesArgs())

    assert result.status == "error"
    assert result.rules_content is None
    assert "Request timeout" in result.message


def test_get_rules_with_topic(tool: GetMarimoRules) -> None:
    """Test loading topic-specific rules."""
    mock_topic_path = Mock(spec=Path)
    mock_topic_path.exists.return_value = True
    mock_topic_path.read_text.return_value = (
        "# Visualization Rules\n\nViz content"
    )

    mock_llm_dir = Mock(spec=Path)
    mock_llm_dir.__truediv__ = Mock(return_value=mock_topic_path)

    with patch("marimo._ai._tools.tools.rules.LLM_RULES_DIR", mock_llm_dir):
        result = tool.handle(GetMarimoRulesArgs(topic="visualization"))

    assert result.status == "success"
    assert result.rules_content == "# Visualization Rules\n\nViz content"
    assert result.source_url == "bundled"
    mock_llm_dir.__truediv__.assert_called_with("visualization.md")


def test_get_rules_with_invalid_topic(tool: GetMarimoRules) -> None:
    """Test error for invalid topic."""
    result = tool.handle(GetMarimoRulesArgs(topic="invalid_topic"))

    assert result.status == "error"
    assert "Unknown topic" in result.message
    assert "invalid_topic" in result.message


def test_get_rules_topic_file_not_found(tool: GetMarimoRules) -> None:
    """Test error when topic file doesn't exist."""
    mock_topic_path = Mock(spec=Path)
    mock_topic_path.exists.return_value = False

    mock_llm_dir = Mock(spec=Path)
    mock_llm_dir.__truediv__ = Mock(return_value=mock_topic_path)

    with patch("marimo._ai._tools.tools.rules.LLM_RULES_DIR", mock_llm_dir):
        result = tool.handle(GetMarimoRulesArgs(topic="visualization"))

    assert result.status == "error"
    assert "not found" in result.message
