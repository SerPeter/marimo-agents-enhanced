# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

import ast
from typing import TYPE_CHECKING

from marimo._ast.parse import ast_parse
from marimo._lint.diagnostic import Diagnostic, Severity
from marimo._lint.rules.base import LintRule
from marimo._lint.rules.runtime._marimo_call_utils import is_marimo_output_call

if TYPE_CHECKING:
    from marimo._lint.context import RuleContext
    from marimo._schemas.serialization import CellDef


class UnusedOutputRule(LintRule):
    """MR003: Marimo output call that is not the last expression in a cell.

    Detects ``mo.*`` output calls (like ``mo.md()``, ``mo.ui.slider()``) that
    appear as bare expression statements but are not the last expression. In
    marimo, only the last top-level expression of a cell is displayed as
    output. Earlier ``mo.*`` calls execute but their results are silently
    discarded.

    ## Why is this bad?

    The user likely intended the output to be visible. A ``mo.md("# Title")``
    in the middle of a cell creates the HTML but throws it away — a subtle bug.

    ## Examples

    **Problematic:**
    ```python
    mo.md("# Title")  # Result discarded — not displayed
    x = compute()
    x
    ```

    **Solution — assign to a variable:**
    ```python
    header = mo.md("# Title")
    x = compute()
    mo.vstack([header, x])
    ```

    **Not flagged:**
    ```python
    mo.md("# Title")  # Last expression — valid output
    header = mo.md("# Title")  # Assigned to variable
    mo.stop(not ok)  # Control flow, not output
    mo.output.append(item)  # Side-effect call
    ```

    ## References

    - [Outputs Guide](https://docs.marimo.io/guides/outputs/)
    """

    code = "MR003"
    name = "unused-marimo-output"
    description = (
        "Marimo output call is not the last expression and will be discarded"
    )
    severity = Severity.RUNTIME
    fixable = False

    async def check(self, ctx: RuleContext) -> None:
        for cell in ctx.notebook.cells:
            if not cell.code.strip():
                continue

            try:
                tree = ast_parse(cell.code)
            except SyntaxError:
                continue

            if len(tree.body) < 2:
                continue

            # Check all statements except the last
            for stmt in tree.body[:-1]:
                if not isinstance(stmt, ast.Expr):
                    continue
                if not isinstance(stmt.value, ast.Call):
                    continue
                if is_marimo_output_call(stmt.value.func):
                    await self._report(stmt, cell, ctx)

    async def _report(
        self, node: ast.stmt, cell: CellDef, ctx: RuleContext
    ) -> None:
        diagnostic = Diagnostic(
            message=(
                "This marimo output call is not the last expression in the cell "
                "and its result will be discarded. "
                "Assign it to a variable or move it to the end of the cell."
            ),
            line=cell.lineno + node.lineno - 1,
            column=node.col_offset + 1,
        )
        await ctx.add_diagnostic(diagnostic)
