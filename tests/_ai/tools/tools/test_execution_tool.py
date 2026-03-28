# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
from unittest.mock import Mock

import pytest

from marimo._ai._tools.base import ToolContext
from marimo._ai._tools.tools.execution import (
    ExecuteCells,
    ExecuteCellsArgs,
    ExecutionListener,
)
from marimo._ai._tools.utils.exceptions import ToolExecutionError
from marimo._messaging.cell_output import CellChannel
from marimo._messaging.notification import CompletedRunNotification
from marimo._messaging.serde import serialize_kernel_message
from marimo._types.ids import CellId_t, SessionId

# -- Mock helpers ------------------------------------------------------------


@dataclass
class MockCellData:
    cell_id: CellId_t
    code: str
    name: str


@dataclass
class MockCellManager:
    _cells: list[MockCellData] = field(default_factory=list)

    def cell_data(self) -> list[MockCellData]:
        return self._cells

    def get_cell_data_by_name(self, name: str) -> Optional[MockCellData]:
        for cd in self._cells:
            if cd.name == name:
                return cd
        return None

    def get_cell_code(self, cell_id: CellId_t) -> Optional[str]:
        for cd in self._cells:
            if cd.cell_id == cell_id:
                return cd.code
        return None


@dataclass
class MockOutput:
    channel: object = None
    data: object = None


@dataclass
class MockCellNotification:
    cell_id: CellId_t = CellId_t("")
    status: Optional[str] = None
    output: Optional[MockOutput] = None
    console: object = None


@dataclass
class MockSessionView:
    cell_notifications: dict[CellId_t, MockCellNotification] = field(
        default_factory=dict
    )


@dataclass
class MockInternalApp:
    cell_manager: MockCellManager = field(default_factory=MockCellManager)


@dataclass
class MockAppFileManager:
    app: MockInternalApp = field(default_factory=MockInternalApp)


@dataclass
class MockSession:
    app_file_manager: MockAppFileManager = field(
        default_factory=MockAppFileManager
    )
    _session_view: MockSessionView = field(default_factory=MockSessionView)

    @property
    def session_view(self) -> MockSessionView:
        return self._session_view

    # Track dispatched commands
    _dispatched: list[object] = field(default_factory=list)

    class _ScopedCtx:
        """Minimal context manager for session.scoped()."""

        def __init__(self, session: MockSession, listener: object) -> None:
            self._session = session
            self._listener = listener

        def __enter__(self) -> object:
            return self._listener

        def __exit__(self, *args: object) -> None:
            pass

    def scoped(self, listener: object) -> _ScopedCtx:
        return MockSession._ScopedCtx(self, listener)

    def put_control_request(
        self,
        command: object,
        **kwargs: object,  # noqa: ARG002
    ) -> None:
        self._dispatched.append(command)


_DEFAULT_SESSION_ID = SessionId("s1")


def _make_tool(
    session: MockSession, session_id: SessionId = _DEFAULT_SESSION_ID
) -> ExecuteCells:
    """Create an ExecuteCells tool with mocked context."""
    tool = ExecuteCells(ToolContext())
    context = Mock(spec=ToolContext)
    context.resolve_session_and_id.return_value = (session, session_id)
    tool.context = context  # type: ignore[assignment]
    return tool


def _make_cells(*names: str) -> list[MockCellData]:
    return [
        MockCellData(
            cell_id=CellId_t(f"c{i}"),
            code=f"# cell {name}",
            name=name,
        )
        for i, name in enumerate(names)
    ]


# -- ExecutionListener tests -------------------------------------------------


class TestExecutionListener:
    def test_completed_run_signals_queue(self) -> None:
        """CompletedRunNotification puts a sentinel on the queue."""
        listener = ExecutionListener()
        notification = serialize_kernel_message(CompletedRunNotification())

        mock_session = Mock()
        listener.on_notification_sent(mock_session, notification)

        assert not listener._queue.empty()
        assert listener._queue.get_nowait() is True

    def test_ignores_other_notifications(self) -> None:
        """Non-CompletedRunNotification messages are ignored."""
        from marimo._messaging.notification import CellNotification

        listener = ExecutionListener()
        cell_notif = CellNotification(
            cell_id=CellId_t("c0"),
            output=None,
            console=None,
            status="idle",
            timestamp=0.0,
        )
        notification = serialize_kernel_message(cell_notif)

        mock_session = Mock()
        listener.on_notification_sent(mock_session, notification)

        assert listener._queue.empty()

    @pytest.mark.asyncio
    async def test_wait_returns_on_signal(self) -> None:
        """wait() returns promptly when the sentinel arrives."""
        listener = ExecutionListener()
        listener._queue.put_nowait(True)

        await listener.wait(timeout=1.0)
        assert not listener.timed_out

    @pytest.mark.asyncio
    async def test_wait_times_out(self) -> None:
        """wait() sets timed_out when no signal arrives."""
        listener = ExecutionListener()

        await listener.wait(timeout=0.05)
        assert listener.timed_out


# -- ExecuteCells tool tests -------------------------------------------------


class TestExecuteCellsScopeCell:
    @pytest.mark.asyncio
    async def test_dispatches_execute_cells_command(self) -> None:
        """scope='cell' dispatches ExecuteCellsCommand with correct ids/codes."""
        from marimo._runtime.commands import ExecuteCellsCommand

        cells = _make_cells("setup", "compute")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        # Pre-fill the listener queue so wait() returns immediately
        original_handle = tool.handle

        async def patched_handle(args: ExecuteCellsArgs) -> object:
            # Monkey-patch session.scoped to also signal the listener
            orig_scoped = session.scoped

            class AutoSignalCtx:
                def __init__(self, listener: object) -> None:
                    self._listener = listener

                def __enter__(self) -> object:
                    if isinstance(self._listener, ExecutionListener):
                        self._listener._queue.put_nowait(True)
                    return self._listener

                def __exit__(self, *args: object) -> None:
                    pass

            session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]
            result = await original_handle(args)
            session.scoped = orig_scoped  # type: ignore[assignment]
            return result

        out = await patched_handle(
            ExecuteCellsArgs(
                session_id=SessionId("s1"),
                scope="cell",
                cell_ids=[CellId_t("c0"), CellId_t("c1")],
            )
        )

        assert len(session._dispatched) == 1
        cmd = session._dispatched[0]
        assert isinstance(cmd, ExecuteCellsCommand)
        assert cmd.cell_ids == [CellId_t("c0"), CellId_t("c1")]
        assert cmd.codes == ["# cell setup", "# cell compute"]
        assert out.scope == "cell"
        assert out.total_cells == 2

    @pytest.mark.asyncio
    async def test_cell_name_resolution(self) -> None:
        """cell_names are resolved to cell_ids."""
        cells = _make_cells("setup", "compute")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        # Auto-signal listener
        orig_scoped = session.scoped

        class AutoSignalCtx:
            def __init__(self, listener: object) -> None:
                self._listener = listener

            def __enter__(self) -> object:
                if isinstance(self._listener, ExecutionListener):
                    self._listener._queue.put_nowait(True)
                return self._listener

            def __exit__(self, *args: object) -> None:
                pass

        session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]

        out = await tool.handle(
            ExecuteCellsArgs(
                session_id=SessionId("s1"),
                scope="cell",
                cell_names=["compute"],
            )
        )

        from marimo._runtime.commands import ExecuteCellsCommand

        cmd = session._dispatched[0]
        assert isinstance(cmd, ExecuteCellsCommand)
        assert cmd.cell_ids == [CellId_t("c1")]
        assert out.total_cells == 1

        session.scoped = orig_scoped  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_invalid_cell_name_raises(self) -> None:
        cells = _make_cells("setup")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        with pytest.raises(ToolExecutionError, match="not found"):
            await tool.handle(
                ExecuteCellsArgs(
                    session_id=SessionId("s1"),
                    scope="cell",
                    cell_names=["nonexistent"],
                )
            )

    @pytest.mark.asyncio
    async def test_empty_ids_scope_cell_raises(self) -> None:
        cells = _make_cells("setup")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        with pytest.raises(ToolExecutionError, match="requires"):
            await tool.handle(
                ExecuteCellsArgs(
                    session_id=SessionId("s1"),
                    scope="cell",
                )
            )


class TestExecuteCellsScopeStale:
    @pytest.mark.asyncio
    async def test_dispatches_stale_command(self) -> None:
        from marimo._runtime.commands import ExecuteStaleCellsCommand

        cells = _make_cells("a", "b")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        class AutoSignalCtx:
            def __init__(self, listener: object) -> None:
                if isinstance(listener, ExecutionListener):
                    listener._queue.put_nowait(True)

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]

        out = await tool.handle(
            ExecuteCellsArgs(session_id=SessionId("s1"), scope="stale")
        )

        assert len(session._dispatched) == 1
        assert isinstance(session._dispatched[0], ExecuteStaleCellsCommand)
        assert out.scope == "stale"


class TestExecuteCellsScopeAll:
    @pytest.mark.asyncio
    async def test_dispatches_all_cells(self) -> None:
        from marimo._runtime.commands import ExecuteCellsCommand

        cells = _make_cells("a", "b", "c")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        class AutoSignalCtx:
            def __init__(self, listener: object) -> None:
                if isinstance(listener, ExecutionListener):
                    listener._queue.put_nowait(True)

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]

        out = await tool.handle(
            ExecuteCellsArgs(session_id=SessionId("s1"), scope="all")
        )

        cmd = session._dispatched[0]
        assert isinstance(cmd, ExecuteCellsCommand)
        assert len(cmd.cell_ids) == 3
        assert out.scope == "all"
        assert out.total_cells == 3


class TestExecuteCellsEdgeCases:
    @pytest.mark.asyncio
    async def test_invalid_scope_raises(self) -> None:
        session = MockSession()
        tool = _make_tool(session)

        with pytest.raises(ToolExecutionError, match="Invalid scope"):
            await tool.handle(
                ExecuteCellsArgs(session_id=SessionId("s1"), scope="invalid")
            )

    @pytest.mark.asyncio
    async def test_timeout_returns_warning(self) -> None:
        cells = _make_cells("slow")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        # Don't signal the listener — it will time out
        out = await tool.handle(
            ExecuteCellsArgs(
                session_id=SessionId("s1"),
                scope="stale",
                timeout=0.05,
            )
        )

        assert out.timed_out is True
        assert out.status == "warning"

    @pytest.mark.asyncio
    async def test_error_detection(self) -> None:
        """Cells with MARIMO_ERROR output are flagged."""
        cells = _make_cells("ok", "broken")
        error_output = MockOutput(channel=CellChannel.MARIMO_ERROR)
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
            _session_view=MockSessionView(
                cell_notifications={
                    CellId_t("c0"): MockCellNotification(
                        cell_id=CellId_t("c0"), status="idle"
                    ),
                    CellId_t("c1"): MockCellNotification(
                        cell_id=CellId_t("c1"),
                        status="idle",
                        output=error_output,
                    ),
                }
            ),
        )
        tool = _make_tool(session)

        class AutoSignalCtx:
            def __init__(self, listener: object) -> None:
                if isinstance(listener, ExecutionListener):
                    listener._queue.put_nowait(True)

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]

        out = await tool.handle(
            ExecuteCellsArgs(session_id=SessionId("s1"), scope="stale")
        )

        statuses = {c.cell_id: c for c in out.cells_executed}
        assert statuses["c0"].has_errors is False
        assert statuses["c1"].has_errors is True

    @pytest.mark.asyncio
    async def test_deduplicates_cell_ids(self) -> None:
        """Duplicate cell IDs from ids + names are deduplicated."""
        cells = _make_cells("setup")
        session = MockSession(
            app_file_manager=MockAppFileManager(
                app=MockInternalApp(cell_manager=MockCellManager(cells))
            ),
        )
        tool = _make_tool(session)

        class AutoSignalCtx:
            def __init__(self, listener: object) -> None:
                if isinstance(listener, ExecutionListener):
                    listener._queue.put_nowait(True)

            def __enter__(self) -> object:
                return self

            def __exit__(self, *args: object) -> None:
                pass

        session.scoped = lambda listener: AutoSignalCtx(listener)  # type: ignore[assignment]

        out = await tool.handle(
            ExecuteCellsArgs(
                session_id=SessionId("s1"),
                scope="cell",
                cell_ids=[CellId_t("c0")],
                cell_names=["setup"],  # same cell
            )
        )

        from marimo._runtime.commands import ExecuteCellsCommand

        cmd = session._dispatched[0]
        assert isinstance(cmd, ExecuteCellsCommand)
        assert cmd.cell_ids == [CellId_t("c0")]
        assert out.total_cells == 1
