# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from marimo._lint.rules.base import LintRule
from marimo._lint.rules.runtime.branch_expression import BranchExpressionRule
from marimo._lint.rules.runtime.nested_output import NestedOutputRule
from marimo._lint.rules.runtime.self_import import SelfImportRule
from marimo._lint.rules.runtime.unused_output import UnusedOutputRule

RUNTIME_RULE_CODES: dict[str, type[LintRule]] = {
    "MR001": SelfImportRule,
    "MR002": BranchExpressionRule,
    "MR003": UnusedOutputRule,
    "MR004": NestedOutputRule,
}

__all__ = [
    "BranchExpressionRule",
    "NestedOutputRule",
    "SelfImportRule",
    "UnusedOutputRule",
    "RUNTIME_RULE_CODES",
]
