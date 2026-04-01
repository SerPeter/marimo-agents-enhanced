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

# AST node types that introduce a nested scope where output calls are invalid.
_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.While,
    ast.With,
    ast.AsyncFor,
    ast.AsyncWith,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.Try,
    ast.Match,
)


class NestedOutputRule(LintRule):
    """MR004: Marimo output call nested inside control flow without assignment.

    Detects ``mo.*`` output calls (``mo.md()``, ``mo.ui.slider()``, etc.)
    that appear as bare expression statements inside ``if``, ``for``,
    ``while``, ``with``, ``def``, ``class``, ``try``, or ``match`` blocks.
    These calls create output objects that are immediately discarded because
    they are neither assigned to a variable nor returned.

    ## Why is this bad?

    The user almost certainly intended the output to be visible. A
    ``mo.md("Hello")`` inside an ``if`` block executes but produces no
    visible result — a subtle, confusing bug.

    ## Examples

    **Problematic:**
    ```python
    if condition:
        mo.md("Hello")  # Created then discarded
    ```

    ```python
    for i in items:
        mo.ui.slider(i, 100)  # Created then discarded
    ```

    **Solution — assign to a variable:**
    ```python
    if condition:
        result = mo.md("Hello")
    result
    ```

    **Not flagged:**
    ```python
    if condition:
        result = mo.md("Hello")  # Assigned


    def helper():
        return mo.md("Inside")  # Returned


    mo.stop(mo.md("Unauthorized"))  # mo.stop() argument

    mo.md("# Title")  # Top-level (see MR003)
    ```

    ## References

    - [Outputs Guide](https://docs.marimo.io/guides/outputs/)
    """

    code = "MR004"
    name = "nested-marimo-output"
    description = "Marimo output call inside control flow is not assigned and will be discarded"
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

            # Collect diagnostics from sync recursive walk, then add them
            diagnostics: list[Diagnostic] = []
            for stmt in tree.body:
                if isinstance(stmt, _NESTING_NODES):
                    self._check_nested(stmt, cell, diagnostics)

            for diagnostic in diagnostics:
                await ctx.add_diagnostic(diagnostic)

    def _check_nested(
        self,
        node: ast.AST,
        cell: CellDef,
        diagnostics: list[Diagnostic],
    ) -> None:
        """Recursively check for bare mo.* calls inside a nested scope."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Expr) and isinstance(
                child.value, ast.Call
            ):
                if is_marimo_output_call(child.value.func):
                    diagnostics.append(
                        Diagnostic(
                            message=(
                                "This marimo output call is inside a control flow "
                                "block and its result is not assigned to a variable. "
                                "The output will be created but not displayed. "
                                "Assign it to a variable or return it."
                            ),
                            line=cell.lineno + child.lineno - 1,
                            column=child.col_offset + 1,
                        )
                    )

            # Recurse into deeper nesting
            if isinstance(child, _NESTING_NODES):
                self._check_nested(child, cell, diagnostics)
