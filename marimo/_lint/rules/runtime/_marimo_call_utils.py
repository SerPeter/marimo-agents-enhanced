# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

import ast


def is_marimo_output_call(func: ast.expr) -> bool:
    """Check if a call is a marimo output function (mo.md, mo.ui.*, etc.).

    Excludes control flow and side-effect calls like mo.stop() and mo.output.*.
    """
    if isinstance(func, ast.Attribute):
        # Direct mo.* calls (mo.md, mo.Html, etc.)
        if isinstance(func.value, ast.Name) and func.value.id == "mo":
            # Exclude mo.stop()
            if func.attr == "stop":
                return False
            return True

        # mo.ui.* or other nested mo.* calls
        if isinstance(func.value, ast.Attribute):
            if (
                isinstance(func.value.value, ast.Name)
                and func.value.value.id == "mo"
            ):
                # Exclude mo.output.* calls (append, replace, clear)
                if func.value.attr == "output":
                    return False
                return True

    return False
