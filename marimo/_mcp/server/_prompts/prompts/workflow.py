# Copyright 2026 Marimo. All rights reserved.
"""MCP Prompt for agent workflow guidance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from marimo._mcp.server._prompts.base import PromptBase

if TYPE_CHECKING:
    from mcp.types import PromptMessage

WORKFLOW_GUIDANCE = """\
## Recommended MCP Tool Workflow

1. **get_marimo_rules** — Call once per session to learn marimo's reactive model and pitfalls.
2. **get_active_notebooks** — Get session IDs and file paths. Required by all other tools.
3. **get_lightweight_cell_map** — The notebook's table of contents. Find cells by preview, type, and status.
4. **Inspect as needed:**
   - **get_cell_runtime_data** — Full code, errors, variables for specific cells.
   - **get_cell_outputs** — Visual output (HTML/charts) and console streams (stdout/stderr).
   - **get_tables_and_variables** — In-memory DataFrame schemas and Python variable values.
   - **get_database_tables** — SQL connection schemas (before writing queries).
   - **get_cell_dependency_graph** — Dataflow relationships (before editing shared variables).
5. **Edit the notebook file directly** using the file path from step 2.
6. **lint_notebook** — ALWAYS lint after every edit. Catches breaking issues early.
7. **get_notebook_errors** — Check for runtime errors after re-execution.

## Decision Tree

- Need session IDs? → `get_active_notebooks`
- Need notebook overview? → `get_lightweight_cell_map`
- Need full cell code/variables? → `get_cell_runtime_data`
- Need cell display output? → `get_cell_outputs`
- Need DataFrame/variable info? → `get_tables_and_variables`
- Need SQL schema? → `get_database_tables`
- Need cell dependencies? → `get_cell_dependency_graph`
- Need to check errors? → `get_notebook_errors`
- Need to validate edits? → `lint_notebook`
- Need marimo rules? → `get_marimo_rules`

## Common Agent Mistakes

1. **Skipping get_active_notebooks** — All tools require a session_id from it.
2. **Not linting after edits** — Always lint_notebook after file changes. Catches MultipleDefinitionError and cycles early.
3. **Jumping to get_cell_runtime_data** — Use get_lightweight_cell_map first to find the right cells.
4. **Confusing database vs. in-memory data** — get_database_tables for SQL connections, get_tables_and_variables for Python variables/DataFrames.
5. **Ignoring stale_inputs** — When true, cell output is outdated. The notebook needs to re-run.
6. **Not checking errors after edits** — After editing and linting, call get_notebook_errors to catch runtime issues.
"""


class WorkflowGuidance(PromptBase):
    """Recommended workflow sequence and decision tree for using marimo MCP tools effectively."""

    def handle(self) -> list[PromptMessage]:
        from mcp.types import PromptMessage, TextContent

        return [
            PromptMessage(
                role="user",
                content=TextContent(
                    type="text",
                    text=WORKFLOW_GUIDANCE,
                ),
            )
        ]
