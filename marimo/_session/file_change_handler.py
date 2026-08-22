# Copyright 2026 Marimo. All rights reserved.
"""File change handling for marimo notebooks.

Provides strategies for handling file changes in different session modes.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional, Protocol

from marimo import _loggers
from marimo._config.manager import MarimoConfigManager
from marimo._messaging.notebook.changes import DeleteCell, Transaction
from marimo._messaging.notification import (
    NotebookDocumentTransactionNotification,
    ReloadNotification,
)
from marimo._runtime.commands import SyncGraphCommand
from marimo._session.model import SessionMode
from marimo._types.ids import CellId_t
from marimo._utils import async_path

LOGGER = _loggers.marimo_logger()

if TYPE_CHECKING:
    from pathlib import Path

    from marimo._session.types import Session


@dataclass
class FileChangeResult:
    """Result of handling a file change."""

    handled: bool
    error: str | None = None
    changed_cell_ids: set[CellId_t] | None = None


class ReloadStrategy(Protocol):
    """Protocol for file reload strategies."""

    def handle_reload(
        self,
        session: Session,
        *,
        transaction: Transaction,
        changed_cell_ids: set[CellId_t],
    ) -> None:
        """Handle reloading after file change.

        Args:
            session: The session to reload
            transaction: Pre-built diff from the pre-reload document to the
                post-reload state. Strategies that broadcast cell-level
                changes use this; full-reload strategies can ignore it.
            changed_cell_ids: Set of cell IDs that changed
        """
        ...


class EditModeReloadStrategy(ReloadStrategy):
    """Reload strategy for edit mode.

    In edit mode, we update cell IDs and codes, and optionally auto-run
    changed cells based on configuration.
    """

    def __init__(self, config_manager: MarimoConfigManager) -> None:
        self._config_manager = config_manager

    def handle_reload(
        self,
        session: Session,
        *,
        transaction: Transaction,
        changed_cell_ids: set[CellId_t],
    ) -> None:
        """Handle reload in edit mode with optional auto-run."""
        cell_manager = session.app_file_manager.app.cell_manager
        cell_ids = list(cell_manager.cell_ids())
        codes = list(cell_manager.codes())

        LOGGER.info(
            f"File changed: {session.app_file_manager.path}. "
            f"num_cell_ids: {len(cell_ids)}, num_codes: {len(codes)}, "
            f"changed_cell_ids: {changed_cell_ids}"
        )

        deleted = {
            change.cell_id
            for change in transaction.changes
            if isinstance(change, DeleteCell)
        }

        if transaction.changes:
            session.notify(
                NotebookDocumentTransactionNotification(
                    transaction=transaction
                ),
                from_consumer_id=None,
            )

        # Auto-run changed cells if configured.
        watcher_on_save = self._config_manager.get_config()["runtime"][
            "watcher_on_save"
        ]
        if watcher_on_save == "autorun":
            changed_not_deleted = list(changed_cell_ids - deleted)
            session.put_control_request(
                SyncGraphCommand(
                    cells=dict(zip(cell_ids, codes, strict=False)),
                    run_ids=changed_not_deleted,
                    delete_ids=sorted(deleted),
                ),
                from_consumer_id=None,
            )
        elif deleted:
            # Even in lazy mode, sync deletions to the kernel so removed
            # cells are cleaned up from the dependency graph.
            session.put_control_request(
                SyncGraphCommand(
                    cells=dict(zip(cell_ids, codes, strict=False)),
                    run_ids=[],
                    delete_ids=sorted(deleted),
                ),
                from_consumer_id=None,
            )


class RunModeReloadStrategy(ReloadStrategy):
    """Reload strategy for run mode.

    In run mode, we simply send a reload operation to the frontend.
    """

    def handle_reload(
        self,
        session: Session,
        *,
        transaction: Transaction,
        changed_cell_ids: set[CellId_t],
    ) -> None:
        """Handle reload in run mode by sending Reload operation."""
        del transaction, changed_cell_ids
        session.notify(ReloadNotification(), from_consumer_id=None)


class FileChangeCoordinator:
    """Coordinates file change handling with proper locking and strategies.

    This class handles the complexities of file watching, including
    preventing duplicate reloads, debouncing rapid changes, and delegating
    to mode-specific strategies.
    """

    def __init__(
        self,
        reload_strategy: ReloadStrategy,
        debounce_seconds: Optional[float] = None,
    ) -> None:
        """Initialize the file change coordinator.

        Args:
            reload_strategy: Strategy for handling reloads
            debounce_seconds: Time to wait after the last file change before
                triggering a reload. `None` or `0` disables debouncing.
        """
        self._reload_strategy = reload_strategy
        self._debounce_seconds = debounce_seconds or 0
        # Track ongoing file change operations to prevent duplicates
        self._file_change_locks: dict[str, asyncio.Lock] = {}
        # Pending debounce tasks per file path
        self._pending_tasks: dict[str, asyncio.Task[FileChangeResult]] = {}

    async def handle_change(
        self, file_path: Path, session: Session
    ) -> FileChangeResult:
        """Handle a file change for a session.

        When debouncing is enabled, rapid successive calls for the same file
        will cancel pending timers so that only the last change triggers a
        reload after the quiet period expires.

        Args:
            file_path: The path to the file that changed
            session: The session associated with the file

        Returns:
            FileChangeResult indicating success or failure
        """
        abs_file_path = await async_path.abspath(file_path)
        key = str(abs_file_path)

        if not self._debounce_seconds:
            return await self._execute_change(key, session)

        # Cancel any pending debounce for this file
        existing = self._pending_tasks.get(key)
        if existing and not existing.done():
            existing.cancel()

        task: asyncio.Task[FileChangeResult] = asyncio.create_task(
            self._debounced_change(key, session)
        )
        self._pending_tasks[key] = task
        return await task

    async def _debounced_change(
        self, key: str, session: Session
    ) -> FileChangeResult:
        """Wait for the debounce period then execute the change."""
        await asyncio.sleep(self._debounce_seconds)
        return await self._execute_change(key, session)

    async def _execute_change(
        self, key: str, session: Session
    ) -> FileChangeResult:
        """Execute the file change with proper locking."""
        if key not in self._file_change_locks:
            self._file_change_locks[key] = asyncio.Lock()

        async with self._file_change_locks[key]:
            return self._handle_file_change_locked(key, session)

    def _handle_file_change_locked(
        self, file_path: str, session: Session
    ) -> FileChangeResult:
        """Handle file change with lock already acquired.

        Args:
            file_path: Absolute path to the file that changed
            session: The session associated with the file

        Returns:
            FileChangeResult indicating success or failure
        """
        LOGGER.debug(f"{file_path} was modified, handling {session}")

        # Verify the session is for this file
        if session.app_file_manager.path != file_path:
            return FileChangeResult(
                handled=False,
                error=f"Session path mismatch: {session.app_file_manager.path} != {file_path}",
            )

        # Read the file once and run all pre-reload skip checks against
        # the same snapshot. If the read itself fails, fall through to
        # `reload()` which has its own error handling below.
        try:
            current_content = session.app_file_manager.read_file()
        except Exception as e:
            LOGGER.debug(f"Error reading {file_path}: {e}")
            current_content = None

        if current_content is not None:
            # Skip our own writes.
            if session.app_file_manager.content_matches_last_save(
                current_content
            ):
                LOGGER.debug(
                    f"File {file_path} content matches last save, "
                    "skipping reload"
                )
                return FileChangeResult(handled=False)

            # Skip when the file is mid-merge so the notebook isn't replaced
            # with unparsable cells while the user resolves conflicts (e.g.
            # via git-mediate). See issue #9613.
            if _has_conflict_markers(current_content):
                LOGGER.warning(
                    f"File {file_path} contains git conflict markers, "
                    "skipping reload until conflicts are resolved"
                )
                return FileChangeResult(handled=False)

        # Reload the file manager to get the latest code. `reload`
        # mutates the existing document in place via `apply()` and
        # returns the stamped transaction, so we just relay it.
        try:
            transaction, changed_cell_ids = (
                session.app_file_manager.reload_and_mark_content_as_last_save(
                    current_content
                )
            )
        except Exception as e:
            # If there are syntax errors, we just skip
            # and don't send the changes
            LOGGER.error(f"Error loading file: {e}")
            return FileChangeResult(handled=False, error=str(e))

        self._reload_strategy.handle_reload(
            session,
            transaction=transaction,
            changed_cell_ids=changed_cell_ids,
        )
        return FileChangeResult(
            handled=True, changed_cell_ids=changed_cell_ids
        )


def _has_conflict_markers(content: str) -> bool:
    """Return True if `content` contains a git conflict start marker.

    Git writes `<<<<<<<` at the start of a line to mark the beginning of
    a conflict hunk; that's a strong signal the file is mid-merge and
    shouldn't be reparsed as Python.
    """
    return any(line.startswith("<<<<<<<") for line in content.splitlines())


def create_reload_strategy(
    mode: SessionMode, config_manager: MarimoConfigManager
) -> ReloadStrategy:
    """Factory function to create the appropriate reload strategy.

    Args:
        mode: The session mode
        config_manager: Configuration manager

    Returns:
        The appropriate reload strategy for the mode
    """
    if mode == SessionMode.EDIT:
        return EditModeReloadStrategy(config_manager)
    else:
        return RunModeReloadStrategy()
