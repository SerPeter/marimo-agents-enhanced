# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from marimo._lint.rules.base import LintRule
from marimo._lint.rules.runtime.branch_expression import BranchExpressionRule
from marimo._lint.rules.runtime.nested_output import NestedOutputRule
from marimo._lint.rules.runtime.private_import_alias import (
    PrivateImportAliasRule,
)
from marimo._lint.rules.runtime.reusable_definition_order import (
    ReusableDefinitionOrderRule,
)
from marimo._lint.rules.runtime.self_import import SelfImportRule
from marimo._lint.rules.runtime.unused_output import UnusedOutputRule

RUNTIME_RULE_CODES: dict[str, type[LintRule]] = {
    "MR001": SelfImportRule,
    "MR002": BranchExpressionRule,
    "MR003": ReusableDefinitionOrderRule,
    "MR004": PrivateImportAliasRule,
    "MR005": UnusedOutputRule,
    "MR006": NestedOutputRule,
}

__all__ = [
    "RUNTIME_RULE_CODES",
    "BranchExpressionRule",
    "NestedOutputRule",
    "PrivateImportAliasRule",
    "ReusableDefinitionOrderRule",
    "SelfImportRule",
    "UnusedOutputRule",
]
