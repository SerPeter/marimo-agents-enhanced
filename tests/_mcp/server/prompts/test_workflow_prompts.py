import pytest

pytest.importorskip("mcp", reason="MCP requires Python 3.10+")

from unittest.mock import Mock

from marimo._mcp.server._prompts.prompts.workflow import WorkflowGuidance


def test_workflow_guidance_includes_all_tools():
    """Test that the workflow guidance prompt mentions all MCP tools."""
    context = Mock()

    prompt = WorkflowGuidance(context=context)
    messages = prompt.handle()
    text = "\n".join(
        msg.content.text  # type: ignore[attr-defined]
        for msg in messages
        if hasattr(msg.content, "text")
    )

    # All tool names must be present
    assert "get_active_notebooks" in text
    assert "get_lightweight_cell_map" in text
    assert "get_cell_runtime_data" in text
    assert "get_cell_outputs" in text
    assert "get_tables_and_variables" in text
    assert "get_database_tables" in text
    assert "get_cell_dependency_graph" in text
    assert "get_notebook_errors" in text
    assert "lint_notebook" in text
    assert "get_marimo_rules" in text

    # Key sections must be present
    assert "Decision Tree" in text
    assert "Common Agent Mistakes" in text
