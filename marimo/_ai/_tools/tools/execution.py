# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

from marimo._ai._tools.base import ToolBase
from marimo._ai._tools.types import SuccessResult, ToolGuidelines
from marimo._ai._tools.utils.exceptions import ToolExecutionError
from marimo._messaging.cell_output import CellChannel
from marimo._messaging.notification import CompletedRunNotification
from marimo._messaging.serde import deserialize_kernel_message
from marimo._runtime.commands import (
    ExecuteCellsCommand,
    ExecuteStaleCellsCommand,
)
from marimo._session.events import SessionEventBus, SessionEventListener
from marimo._types.ids import CellId_t, ConsumerId, SessionId

if TYPE_CHECKING:
    from marimo._ast.cell_manager import CellManager
    from marimo._messaging.types import KernelMessage
    from marimo._session.session import Session


EXECUTION_TIMEOUT = 120.0  # seconds


# -- Listener ----------------------------------------------------------------


class ExecutionListener(SessionEventListener):
    """Listens for a CompletedRunNotification to signal execution is done.

    Modeled on ``ScratchCellListener`` in ``marimo/_server/scratchpad.py``
    but simpler: no SSE streaming, no cell-ID filtering.  The kernel
    broadcasts ``CompletedRunNotification`` exactly once per command
    completion (see ``runtime.py`` handlers).
    """

    def __init__(self) -> None:
        self._queue: asyncio.Queue[bool] = asyncio.Queue()
        self.timed_out = False

    def on_attach(self, session: Session, event_bus: SessionEventBus) -> None:
        del session
        self._event_bus = event_bus
        event_bus.subscribe(self)

    def on_detach(self) -> None:
        if hasattr(self, "_event_bus"):
            self._event_bus.unsubscribe(self)
            del self._event_bus

    def on_notification_sent(
        self, session: Session, notification: KernelMessage
    ) -> None:
        del session
        msg = deserialize_kernel_message(notification)
        if isinstance(msg, CompletedRunNotification):
            self._queue.put_nowait(True)

    async def wait(self, timeout: float = EXECUTION_TIMEOUT) -> None:
        """Block until execution completes or the deadline expires."""
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self.timed_out = True
                return
            try:
                await asyncio.wait_for(self._queue.get(), timeout=remaining)
                return  # got the sentinel
            except asyncio.TimeoutError:
                self.timed_out = True
                return


# -- Dataclasses -------------------------------------------------------------


@dataclass
class ExecuteCellsArgs:
    session_id: Optional[SessionId] = None
    file_path: Optional[str] = None
    scope: str = "stale"
    cell_ids: list[CellId_t] = field(default_factory=list)
    cell_names: list[str] = field(default_factory=list)
    timeout: float = EXECUTION_TIMEOUT


@dataclass
class CellExecutionStatus:
    cell_id: str
    status: Optional[str] = None
    has_errors: bool = False


@dataclass
class ExecuteCellsOutput(SuccessResult):
    scope: str = ""
    cells_executed: list[CellExecutionStatus] = field(default_factory=list)
    total_cells: int = 0
    timed_out: bool = False


# -- Tool --------------------------------------------------------------------

_VALID_SCOPES = ("cell", "stale", "all")


class ExecuteCells(ToolBase[ExecuteCellsArgs, ExecuteCellsOutput]):
    """Execute cells in a notebook, triggering the reactive graph.

    Supports three scopes:
    - "cell"  — run specific cells (+ downstream dependents)
    - "stale" — run all stale/dirty cells (default)
    - "all"   — re-execute every cell

    Args:
        session_id: Session to execute in.
        file_path: Alternative to session_id.
        scope: Execution scope ("cell", "stale", or "all").
        cell_ids: Cell IDs to run (required when scope="cell").
        cell_names: Cell function names, resolved to IDs.
        timeout: Max seconds to wait for completion.

    Returns:
        Per-cell execution status with error flags.
    """

    guidelines = ToolGuidelines(
        when_to_use=[
            "After editing notebook cells to verify changes run correctly",
            "To bring a notebook to a consistent state after modifications",
            "When you need to trigger the reactive execution graph",
        ],
        prerequisites=[
            "A valid session_id or file_path for an active notebook",
            "For scope='cell', you must provide cell_ids or cell_names",
        ],
        side_effects=[
            "Cells will be executed in the kernel; outputs and state will change",
        ],
    )

    async def handle(self, args: ExecuteCellsArgs) -> ExecuteCellsOutput:  # type: ignore[override]
        session, session_id = self.context.resolve_session_and_id(
            args.session_id, args.file_path
        )

        if args.scope not in _VALID_SCOPES:
            raise ToolExecutionError(
                f"Invalid scope '{args.scope}'. Must be one of: {', '.join(_VALID_SCOPES)}",
                code="BAD_ARGUMENTS",
                is_retryable=False,
            )

        cell_manager = session.app_file_manager.app.cell_manager
        command: ExecuteCellsCommand | ExecuteStaleCellsCommand

        if args.scope == "cell":
            cell_ids = self._resolve_cell_ids(args, cell_manager)
            codes = self._get_codes(cell_ids, cell_manager)
            command = ExecuteCellsCommand(cell_ids=cell_ids, codes=codes)
            target_cell_ids = cell_ids

        elif args.scope == "stale":
            command = ExecuteStaleCellsCommand()
            target_cell_ids = [cd.cell_id for cd in cell_manager.cell_data()]

        else:  # "all"
            all_cells = list(cell_manager.cell_data())
            cell_ids = [cd.cell_id for cd in all_cells]
            codes = [cd.code for cd in all_cells]
            command = ExecuteCellsCommand(cell_ids=cell_ids, codes=codes)
            target_cell_ids = cell_ids

        # Dispatch and wait
        listener = ExecutionListener()
        with session.scoped(listener):
            session.put_control_request(
                command,
                from_consumer_id=ConsumerId(session_id),
            )
            await listener.wait(timeout=args.timeout)

        # Read results
        cells_executed = self._read_cell_statuses(session, target_cell_ids)
        has_errors = any(c.has_errors for c in cells_executed)

        if listener.timed_out:
            return ExecuteCellsOutput(
                status="warning",
                scope=args.scope,
                cells_executed=cells_executed,
                total_cells=len(cells_executed),
                timed_out=True,
                message=f"Execution timed out after {args.timeout}s. Cells may still be running.",
                next_steps=[
                    "Check cell status with get_cell_runtime_data",
                    "Increase timeout if needed",
                ],
            )

        return ExecuteCellsOutput(
            scope=args.scope,
            cells_executed=cells_executed,
            total_cells=len(cells_executed),
            next_steps=(
                [
                    "Use get_notebook_errors to inspect failures",
                    "Use get_cell_runtime_data to see details",
                ]
                if has_errors
                else ["Execution completed successfully"]
            ),
        )

    # -- Helpers --------------------------------------------------------------

    @staticmethod
    def _resolve_cell_ids(
        args: ExecuteCellsArgs, cell_manager: CellManager
    ) -> list[CellId_t]:
        """Merge cell_ids and cell_names into a deduplicated list."""
        seen: set[CellId_t] = set()
        result: list[CellId_t] = []

        for cid in args.cell_ids:
            if cid not in seen:
                seen.add(cid)
                result.append(cid)

        for name in args.cell_names:
            cell_data = cell_manager.get_cell_data_by_name(name)
            if cell_data is None:
                raise ToolExecutionError(
                    f"Cell name '{name}' not found",
                    code="CELL_NOT_FOUND",
                    is_retryable=False,
                    suggested_fix="Use get_lightweight_cell_map to find valid cell names",
                )
            if cell_data.cell_id not in seen:
                seen.add(cell_data.cell_id)
                result.append(cell_data.cell_id)

        if not result:
            raise ToolExecutionError(
                "scope='cell' requires cell_ids or cell_names",
                code="BAD_ARGUMENTS",
                is_retryable=False,
            )
        return result

    @staticmethod
    def _get_codes(
        cell_ids: list[CellId_t], cell_manager: CellManager
    ) -> list[str]:
        """Retrieve current code for each cell ID."""

        codes: list[str] = []
        for cid in cell_ids:
            code = cell_manager.get_cell_code(cid)
            if code is None:
                raise ToolExecutionError(
                    f"Cell ID '{cid}' not found",
                    code="CELL_NOT_FOUND",
                    is_retryable=False,
                    suggested_fix="Use get_lightweight_cell_map to find valid cell IDs",
                )
            codes.append(code)
        return codes

    @staticmethod
    def _read_cell_statuses(
        session: Session, cell_ids: list[CellId_t]
    ) -> list[CellExecutionStatus]:
        """Read execution status for each cell from session view."""
        results: list[CellExecutionStatus] = []
        for cid in cell_ids:
            cell_notif = session.session_view.cell_notifications.get(cid)
            status: Optional[str] = None
            has_errors = False
            if cell_notif is not None:
                status = cell_notif.status
                has_errors = (
                    cell_notif.output is not None
                    and cell_notif.output.channel == CellChannel.MARIMO_ERROR
                )
            results.append(
                CellExecutionStatus(
                    cell_id=str(cid),
                    status=status,
                    has_errors=has_errors,
                )
            )
        return results
