from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any

import pytest

from marimo._ai._tools.base import (
    ToolBase,
    ToolContext,
    _extract_traceback_lines,
)
from marimo._ai._tools.utils.exceptions import ToolExecutionError


@dataclass
class _Args:
    value: int


@dataclass
class _Out:
    doubled: int


class _EchoTool(ToolBase[_Args, _Out]):
    """Dummy tool for testing base adapter behavior."""

    def handle(self, args: _Args) -> _Out:
        return _Out(doubled=args.value * 2)


class _ErrorTool(ToolBase[_Args, _Out]):
    """Tool that raises errors for testing."""

    def handle(self, args: _Args) -> _Out:
        if args.value < 0:
            raise ToolExecutionError(
                "Negative values not allowed", code="NEGATIVE_VALUE"
            )
        if args.value == 0:
            raise ValueError("Zero is not allowed")
        return _Out(doubled=args.value * 2)


def test_as_mcp_tool_fn_returns_async_callable() -> None:
    tool = _EchoTool(ToolContext())
    handler = tool.as_mcp_tool_fn()

    assert inspect.iscoroutinefunction(handler)


def test_handler_annotations_and_signature() -> None:
    tool = _EchoTool(ToolContext())
    handler = tool.as_mcp_tool_fn()

    annotations: dict[str, Any] = getattr(handler, "__annotations__", {})
    assert annotations.get("args") is _Args
    assert annotations.get("return") is _Out

    sig = getattr(handler, "__signature__", None)
    assert sig is not None
    params = list(sig.parameters.values())
    assert len(params) == 1
    assert params[0].name == "args"
    assert sig.return_annotation is _Out


def test_name_and_description_defaults() -> None:
    tool = _EchoTool(ToolContext())
    # Name should default from class name
    assert tool.name == "_echo_tool"
    # Description defaults to class docstring (stripped)
    assert "Dummy tool" in (tool.description or "")


async def test_tool_call_with_valid_args() -> None:
    """Test __call__ method with valid arguments."""
    tool = _EchoTool(ToolContext())
    result = await tool(_Args(value=5))
    assert result.doubled == 10


async def test_tool_call_handles_tool_execution_error() -> None:
    """Test __call__ properly propagates ToolExecutionError."""
    tool = _ErrorTool(ToolContext())
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool(_Args(value=-1))
    assert exc_info.value.code == "NEGATIVE_VALUE"


async def test_tool_call_wraps_unexpected_error() -> None:
    """Test __call__ wraps unexpected errors in ToolExecutionError."""
    tool = _ErrorTool(ToolContext())
    with pytest.raises(ToolExecutionError) as exc_info:
        await tool(_Args(value=0))
    assert exc_info.value.code == "UNEXPECTED_ERROR"


def test_tool_execution_error_basic() -> None:
    """Test basic ToolExecutionError functionality."""
    error = ToolExecutionError("Test error", code="TEST_CODE")
    assert error.message == "Test error"
    assert error.code == "TEST_CODE"
    assert error.is_retryable is False

    # Test structured message is JSON
    import json

    json.loads(str(error))  # Should not raise


def test_as_backend_tool() -> None:
    """Test as_backend_tool method."""
    tool = _EchoTool(ToolContext())
    definition, validator = tool.as_backend_tool(["ask"])

    assert definition.name == "_echo_tool"
    assert definition.source == "backend"
    assert definition.mode == ["ask"]

    # Test validator with valid args
    is_valid, msg = validator({"value": 42})
    assert is_valid is True
    assert msg == ""

    # Test validator with invalid args
    is_valid, msg = validator({"invalid": "field"})
    assert is_valid is False
    assert "Invalid arguments" in msg


# test ToolContext methods


def test_get_notebook_errors_orders_by_cell_manager():
    """Test errors follow cell_manager order, not alphabetical."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    # Mock error cell_notification
    error_op = Mock()
    error_op.output = Mock()
    error_op.output.channel = CellChannel.MARIMO_ERROR
    error_op.output.data = [{"type": "Error", "msg": "test", "traceback": []}]
    error_op.console = None

    # Mock session with cells c1, c2, c3
    session = Mock()
    session_view = Mock()
    session_view.cell_notifications = {
        CellId_t("c1"): error_op,
        CellId_t("c2"): error_op,
        CellId_t("c3"): error_op,
    }
    session.session_view = session_view

    # Cell manager returns in order: c3, c2, c1 (not alphabetical)
    cell_data = [
        Mock(cell_id=CellId_t("c3")),
        Mock(cell_id=CellId_t("c2")),
        Mock(cell_id=CellId_t("c1")),
    ]
    session.app_file_manager.app.cell_manager.cell_data.return_value = (
        cell_data
    )

    context.get_session = Mock(return_value=session)
    context.resolve_session = Mock(return_value=session)

    errors = context.get_notebook_errors(
        SessionId("test"), include_stderr=False
    )

    # Should be c3, c2, c1 (not c1, c2, c3)
    assert errors[0].cell_id == CellId_t("c3")
    assert errors[1].cell_id == CellId_t("c2")
    assert errors[2].cell_id == CellId_t("c1")


def test_get_cell_errors_extracts_from_output():
    """Test get_cell_errors extracts error details from cell output."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    # Mock cell_notification with error
    cell_notification = Mock()
    cell_notification.output = Mock()
    cell_notification.output.channel = CellChannel.MARIMO_ERROR
    cell_notification.output.data = [
        {"type": "ValueError", "msg": "bad value", "traceback": ["line 1"]}
    ]

    errors = context.get_cell_errors(
        SessionId("test"),
        CellId_t("c1"),
        maybe_cell_notif=cell_notification,
    )

    assert len(errors) == 1
    assert errors[0].type == "ValueError"
    assert errors[0].message == "bad value"
    assert errors[0].traceback == ["line 1"]


def test_get_cell_console_outputs_separates_stdout_stderr():
    """Test get_cell_console_outputs separates stdout and stderr."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel

    context = ToolContext()

    # Mock cell_notification with stdout and stderr
    stdout_output = Mock()
    stdout_output.channel = CellChannel.STDOUT
    stdout_output.data = "hello"

    stderr_output = Mock()
    stderr_output.channel = CellChannel.STDERR
    stderr_output.data = "warning"

    cell_notification = Mock()
    cell_notification.console = [stdout_output, stderr_output]

    result = context.get_cell_console_outputs(cell_notification)

    assert len(result.stdout) == 1
    assert "hello" in result.stdout[0]
    assert len(result.stderr) == 1
    assert "warning" in result.stderr[0]


# --- _extract_traceback_lines tests ---


def test_extract_traceback_lines_none():
    """Returns empty list for None console."""
    assert _extract_traceback_lines(None) == []


def test_extract_traceback_lines_no_traceback():
    """Returns empty list when no traceback mimetype entries exist."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel

    output = Mock()
    output.channel = CellChannel.STDERR
    output.mimetype = "text/plain"
    output.data = "some warning"

    assert _extract_traceback_lines([output]) == []


def test_extract_traceback_lines_strips_html():
    """Strips HTML tags and extracts plain-text traceback."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel

    html_traceback = (
        '<span class="codehilite"><div class="highlight">'
        "Traceback (most recent call last):\n"
        '  File "&lt;cell-abc&gt;", line 5, in &lt;module&gt;\n'
        "    x = 1 / 0\n"
        "ZeroDivisionError: division by zero"
        "</div></span>"
    )

    output = Mock()
    output.channel = CellChannel.STDERR
    output.mimetype = "application/vnd.marimo+traceback"
    output.data = html_traceback

    lines = _extract_traceback_lines([output])

    assert len(lines) == 4
    assert lines[0] == "Traceback (most recent call last):"
    assert '"<cell-abc>", line 5' in lines[1]
    assert "x = 1 / 0" in lines[2]
    assert "ZeroDivisionError" in lines[3]


def test_extract_traceback_lines_single_output():
    """Works with a single CellOutput (not wrapped in list)."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel

    output = Mock()
    output.channel = CellChannel.STDERR
    output.mimetype = "application/vnd.marimo+traceback"
    output.data = "Traceback (most recent call last):\n  line 1"

    lines = _extract_traceback_lines(output)
    assert len(lines) == 2


def test_extract_traceback_lines_skips_non_stderr():
    """Ignores stdout entries even with traceback mimetype."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel

    output = Mock()
    output.channel = CellChannel.STDOUT
    output.mimetype = "application/vnd.marimo+traceback"
    output.data = "should be ignored"

    assert _extract_traceback_lines([output]) == []


# --- get_cell_errors traceback population tests ---


def test_get_cell_errors_populates_traceback_from_console():
    """Test that traceback is populated from console when error has none."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    # Console with traceback
    tb_output = Mock()
    tb_output.channel = CellChannel.STDERR
    tb_output.mimetype = "application/vnd.marimo+traceback"
    tb_output.data = (
        "Traceback (most recent call last):\n"
        '  File "<cell-c1>", line 3, in <module>\n'
        "ValueError: bad"
    )

    cell_notification = Mock()
    cell_notification.output = Mock()
    cell_notification.output.channel = CellChannel.MARIMO_ERROR
    cell_notification.output.data = [{"type": "ValueError", "msg": "bad"}]
    cell_notification.console = [tb_output]

    errors = context.get_cell_errors(
        SessionId("test"),
        CellId_t("c1"),
        maybe_cell_notif=cell_notification,
    )

    assert len(errors) == 1
    assert errors[0].type == "ValueError"
    assert len(errors[0].traceback) == 3
    assert "Traceback" in errors[0].traceback[0]
    assert "line 3" in errors[0].traceback[1]


def test_get_cell_errors_preserves_existing_traceback():
    """Test that existing traceback in error data is preserved."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    cell_notification = Mock()
    cell_notification.output = Mock()
    cell_notification.output.channel = CellChannel.MARIMO_ERROR
    cell_notification.output.data = [
        {
            "type": "ValueError",
            "msg": "bad",
            "traceback": ["existing line"],
        }
    ]
    cell_notification.console = None

    errors = context.get_cell_errors(
        SessionId("test"),
        CellId_t("c1"),
        maybe_cell_notif=cell_notification,
    )

    assert errors[0].traceback == ["existing line"]


# --- get_notebook_errors cell_ids filtering tests ---


def test_get_notebook_errors_filters_by_cell_ids():
    """Test that cell_ids parameter filters errors."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    def make_error_notif():
        notif = Mock()
        notif.output = Mock()
        notif.output.channel = CellChannel.MARIMO_ERROR
        notif.output.data = [{"type": "Error", "msg": "test"}]
        notif.console = None
        return notif

    session = Mock()
    session_view = Mock()
    session_view.cell_notifications = {
        CellId_t("c1"): make_error_notif(),
        CellId_t("c2"): make_error_notif(),
        CellId_t("c3"): make_error_notif(),
    }
    session.session_view = session_view

    cell_data = [
        Mock(cell_id=CellId_t("c1")),
        Mock(cell_id=CellId_t("c2")),
        Mock(cell_id=CellId_t("c3")),
    ]
    session.app_file_manager.app.cell_manager.cell_data.return_value = (
        cell_data
    )
    context.get_session = Mock(return_value=session)

    # Filter to only c2
    errors = context.get_notebook_errors(
        SessionId("test"),
        include_stderr=False,
        cell_ids=[CellId_t("c2")],
    )

    assert len(errors) == 1
    assert errors[0].cell_id == CellId_t("c2")


def test_get_notebook_errors_no_filter_returns_all():
    """Test that no cell_ids returns all errors."""
    from unittest.mock import Mock

    from marimo._messaging.cell_output import CellChannel
    from marimo._types.ids import CellId_t, SessionId

    context = ToolContext()

    def make_error_notif():
        notif = Mock()
        notif.output = Mock()
        notif.output.channel = CellChannel.MARIMO_ERROR
        notif.output.data = [{"type": "Error", "msg": "test"}]
        notif.console = None
        return notif

    session = Mock()
    session_view = Mock()
    session_view.cell_notifications = {
        CellId_t("c1"): make_error_notif(),
        CellId_t("c2"): make_error_notif(),
    }
    session.session_view = session_view

    cell_data = [
        Mock(cell_id=CellId_t("c1")),
        Mock(cell_id=CellId_t("c2")),
    ]
    session.app_file_manager.app.cell_manager.cell_data.return_value = (
        cell_data
    )
    context.get_session = Mock(return_value=session)

    errors = context.get_notebook_errors(
        SessionId("test"), include_stderr=False
    )

    assert len(errors) == 2
