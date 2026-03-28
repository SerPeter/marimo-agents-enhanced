# Copyright 2026 Marimo. All rights reserved.
"""MCP tool for notebook session lifecycle management."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Optional
from uuid import uuid4

from marimo._ai._tools.base import ToolBase
from marimo._ai._tools.types import SuccessResult, ToolGuidelines
from marimo._ai._tools.utils.exceptions import ToolExecutionError
from marimo._server.models.models import InstantiateNotebookRequest
from marimo._session.headless_consumer import HeadlessSessionConsumer
from marimo._session.model import ConnectionState
from marimo._types.ids import ConsumerId, SessionId

if TYPE_CHECKING:
    from marimo._server.session_manager import SessionManager


@dataclass
class ManageSessionArgs:
    action: Literal["start", "restart", "stop"]
    file_path: Optional[str] = None
    session_id: Optional[SessionId] = None


@dataclass
class ManageSessionOutput(SuccessResult):
    session_id: Optional[SessionId] = None
    file_path: Optional[str] = None
    action_taken: str = ""


class ManageSession(ToolBase[ManageSessionArgs, ManageSessionOutput]):
    """Manage notebook session lifecycle: start, restart, or stop sessions.

    - **start**: Create a new session for a notebook file. The session starts
      with a running kernel and can be attached to from a browser.
    - **restart**: Close the existing session and create a fresh one. All
      runtime state is lost.
    - **stop**: Close a session and terminate its kernel.

    Args:
        action: One of "start", "restart", or "stop".
        file_path: Absolute path to the notebook file. Required for "start".
            Can be used as an alternative to session_id for "restart"/"stop".
        session_id: Session ID. Alternative to file_path for "restart"/"stop".
    """

    guidelines = ToolGuidelines(
        when_to_use=[
            "Start a notebook session from a file path before using other tools",
            "Restart kernel when session is in a bad state",
            "Stop a session you no longer need",
        ],
        side_effects=[
            "'start' creates a new kernel process — user can attach via browser",
            "'restart'/'stop' kill the kernel — all runtime state is lost",
        ],
    )

    def handle(self, args: ManageSessionArgs) -> ManageSessionOutput:
        if args.action == "start":
            return self._start(args)
        elif args.action == "restart":
            return self._restart(args)
        elif args.action == "stop":
            return self._stop(args)
        else:
            raise ToolExecutionError(
                f"Unknown action: {args.action}",
                code="BAD_ARGUMENTS",
                is_retryable=False,
                suggested_fix="Use one of: 'start', 'restart', 'stop'.",
            )

    def _start(self, args: ManageSessionArgs) -> ManageSessionOutput:
        if not args.file_path:
            raise ToolExecutionError(
                "file_path is required for 'start' action",
                code="BAD_ARGUMENTS",
                is_retryable=False,
                suggested_fix="Provide the absolute path to a .py marimo notebook file.",
            )

        abs_path = os.path.abspath(args.file_path)
        if not os.path.isfile(abs_path):
            raise ToolExecutionError(
                f"File not found: {abs_path}",
                code="FILE_NOT_FOUND",
                is_retryable=False,
                suggested_fix="Provide a valid path to an existing marimo notebook file.",
                meta={"file_path": abs_path},
            )

        manager = self.context.session_manager

        # Check for existing active session for this file
        existing = manager.get_sessions_by_file_path(abs_path)
        active = [
            s
            for s in existing
            if s.connection_state()
            in (ConnectionState.OPEN, ConnectionState.ORPHANED)
        ]
        if active:
            # Return existing session instead of creating a duplicate
            existing_id = manager.get_session_id_for_session(active[0])
            return ManageSessionOutput(
                session_id=existing_id,
                file_path=abs_path,
                action_taken="existing",
                message="Session already exists for this file.",
                next_steps=[
                    "Use this session_id or file_path with other tools",
                ],
            )

        return self._create_session(manager, abs_path)

    def _restart(self, args: ManageSessionArgs) -> ManageSessionOutput:
        session, session_id = self.context.resolve_session_and_id(
            args.session_id, args.file_path
        )
        file_path = session.app_file_manager.path
        if not file_path:
            raise ToolExecutionError(
                "Cannot restart: session has no associated file path",
                code="NO_FILE_PATH",
                is_retryable=False,
                suggested_fix="This session is unsaved. Save it first, then restart.",
            )

        manager = self.context.session_manager
        manager.close_session(session_id)
        return self._create_session(manager, file_path)

    def _stop(self, args: ManageSessionArgs) -> ManageSessionOutput:
        session, session_id = self.context.resolve_session_and_id(
            args.session_id, args.file_path
        )
        file_path = session.app_file_manager.path

        manager = self.context.session_manager
        closed = manager.close_session(session_id)
        if not closed:
            raise ToolExecutionError(
                f"Failed to close session {session_id}",
                code="SESSION_CLOSE_FAILED",
                is_retryable=True,
                suggested_fix="The session may have already been closed.",
            )

        return ManageSessionOutput(
            session_id=session_id,
            file_path=file_path,
            action_taken="stopped",
            message="Session stopped. Kernel terminated.",
        )

    def _create_session(
        self,
        manager: SessionManager,
        file_path: str,
    ) -> ManageSessionOutput:
        """Create a new session and immediately orphan it for browser attachment."""
        session_id = SessionId(str(uuid4()))
        consumer = HeadlessSessionConsumer(
            consumer_id=ConsumerId(f"mcp-{session_id}")
        )

        session = manager.create_session(
            session_id=session_id,
            session_consumer=consumer,
            query_params={},
            file_key=file_path,
            auto_instantiate=True,
        )

        # Run all cells (same pattern as the export flow in
        # marimo/_server/export/__init__.py:524).
        session.instantiate(
            InstantiateNotebookRequest(object_ids=[], values=[]),
            http_request=None,
        )

        # Disconnect the headless consumer so the session enters ORPHANED
        # state. This allows a browser to resume it via the normal WebSocket
        # flow (EditModeResumeStrategy finds ORPHANED sessions by file path).
        session.disconnect_main_consumer()

        return ManageSessionOutput(
            session_id=session_id,
            file_path=file_path,
            action_taken="started",
            message="Session started. All cells are executing.",
            next_steps=[
                "Use this session_id or file_path with other tools",
                "Open the notebook in a browser to see the UI",
            ],
        )
