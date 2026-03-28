# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from unittest.mock import Mock

import pytest

from marimo._ai._tools.base import ToolContext
from marimo._ai._tools.tools.execution import ExecutionListener
from marimo._ai._tools.tools.ui_element import (
    SetUIElementValue,
    SetUIElementValueArgs,
)
from marimo._ai._tools.utils.exceptions import ToolExecutionError
from marimo._runtime.commands import UpdateUIElementCommand
from marimo._types.ids import SessionId, UIElementId

# -- Mock helpers (minimal — no cell manager needed) -------------------------

_DEFAULT_SESSION_ID = SessionId("s1")


class _AutoSignalCtx:
    """Context manager that auto-signals an ExecutionListener on entry."""

    def __init__(self, listener: object) -> None:
        self._listener = listener

    def __enter__(self) -> object:
        if isinstance(self._listener, ExecutionListener):
            self._listener._queue.put_nowait(True)
        return self._listener

    def __exit__(self, *args: object) -> None:
        pass


class MockSession:
    """Minimal session mock for SetUIElementValue tests."""

    def __init__(self, *, auto_signal: bool = True) -> None:
        self._dispatched: list[object] = []
        self._auto_signal = auto_signal

    def scoped(self, listener: object) -> object:
        if self._auto_signal:
            return _AutoSignalCtx(listener)

        class _PassthroughCtx:
            def __enter__(self_inner) -> object:  # noqa: N805
                return listener

            def __exit__(self_inner, *args: object) -> None:  # noqa: N805
                pass

        return _PassthroughCtx()

    def put_control_request(
        self,
        command: object,
        **kwargs: object,  # noqa: ARG002
    ) -> None:
        self._dispatched.append(command)


def _make_tool(
    session: MockSession,
    session_id: SessionId = _DEFAULT_SESSION_ID,
) -> SetUIElementValue:
    tool = SetUIElementValue(ToolContext())
    context = Mock(spec=ToolContext)
    context.resolve_session_and_id.return_value = (session, session_id)
    tool.context = context  # type: ignore[assignment]
    return tool


# -- Tests -------------------------------------------------------------------


class TestSetUIElementValueDispatch:
    @pytest.mark.asyncio
    async def test_dispatches_update_command(self) -> None:
        """Dispatches UpdateUIElementCommand with correct element_id and value."""
        session = MockSession()
        tool = _make_tool(session)

        out = await tool.handle(
            SetUIElementValueArgs(
                session_id=SessionId("s1"),
                element_id="slider-1",
                value=42,
            )
        )

        assert len(session._dispatched) == 1
        cmd = session._dispatched[0]
        assert isinstance(cmd, UpdateUIElementCommand)
        assert cmd.object_ids == [UIElementId("slider-1")]
        assert cmd.values == [42]
        assert out.element_id == "slider-1"
        assert out.status == "success"

    @pytest.mark.asyncio
    async def test_success_returns_element_id(self) -> None:
        """Output contains the element_id that was set."""
        session = MockSession()
        tool = _make_tool(session)

        out = await tool.handle(
            SetUIElementValueArgs(
                session_id=SessionId("s1"),
                element_id="dropdown-abc",
                value="option_b",
            )
        )

        assert out.element_id == "dropdown-abc"
        assert out.timed_out is False

    @pytest.mark.asyncio
    async def test_various_value_types(self) -> None:
        """Values of different types are passed through to the command."""
        session = MockSession()
        tool = _make_tool(session)

        for value in [True, 3.14, "hello", [1, 2, 3], {"key": "val"}]:
            session._dispatched.clear()
            await tool.handle(
                SetUIElementValueArgs(
                    session_id=SessionId("s1"),
                    element_id="elem",
                    value=value,
                )
            )
            cmd = session._dispatched[0]
            assert isinstance(cmd, UpdateUIElementCommand)
            assert cmd.values == [value]


class TestSetUIElementValueValidation:
    @pytest.mark.asyncio
    async def test_empty_element_id_raises(self) -> None:
        session = MockSession()
        tool = _make_tool(session)

        with pytest.raises(ToolExecutionError, match="element_id is required"):
            await tool.handle(
                SetUIElementValueArgs(
                    session_id=SessionId("s1"),
                    element_id="",
                    value=42,
                )
            )

    @pytest.mark.asyncio
    async def test_missing_element_id_raises(self) -> None:
        """Default empty element_id also raises."""
        session = MockSession()
        tool = _make_tool(session)

        with pytest.raises(ToolExecutionError, match="element_id is required"):
            await tool.handle(
                SetUIElementValueArgs(
                    session_id=SessionId("s1"),
                    value=42,
                )
            )


class TestSetUIElementValueTimeout:
    @pytest.mark.asyncio
    async def test_timeout_returns_warning(self) -> None:
        session = MockSession(auto_signal=False)
        tool = _make_tool(session)

        out = await tool.handle(
            SetUIElementValueArgs(
                session_id=SessionId("s1"),
                element_id="slider-1",
                value=42,
                timeout=0.05,
            )
        )

        assert out.timed_out is True
        assert out.status == "warning"
        assert out.element_id == "slider-1"
