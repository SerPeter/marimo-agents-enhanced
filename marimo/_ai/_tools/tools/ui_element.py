# Copyright 2026 Marimo. All rights reserved.
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from marimo._ai._tools.base import ToolBase
from marimo._ai._tools.tools.execution import (
    EXECUTION_TIMEOUT,
    ExecutionListener,
)
from marimo._ai._tools.types import SuccessResult, ToolGuidelines
from marimo._ai._tools.utils.exceptions import ToolExecutionError
from marimo._runtime.commands import UpdateUIElementCommand
from marimo._types.ids import ConsumerId, SessionId, UIElementId

# -- Dataclasses -------------------------------------------------------------


@dataclass
class SetUIElementValueArgs:
    session_id: Optional[SessionId] = None
    file_path: Optional[str] = None
    element_id: str = ""
    value: Any = None
    timeout: float = EXECUTION_TIMEOUT


@dataclass
class SetUIElementValueOutput(SuccessResult):
    element_id: str = ""
    timed_out: bool = False


# -- Tool --------------------------------------------------------------------


class SetUIElementValue(
    ToolBase[SetUIElementValueArgs, SetUIElementValueOutput]
):
    """Set the value of a UI element, triggering reactive updates.

    Programmatically updates a UI element (slider, dropdown, text input, etc.)
    as if the user interacted with it in the browser.  Downstream cells that
    depend on the element are re-executed automatically.

    Args:
        session_id: Session containing the element.
        file_path: Alternative to session_id.
        element_id: The UI element's object ID.
        value: New value for the element.
        timeout: Max seconds to wait for reactive execution to complete.

    Returns:
        Confirmation with the element_id and timeout status.
    """

    guidelines = ToolGuidelines(
        when_to_use=[
            "To programmatically change a slider, dropdown, or other UI element",
            "To explore different parameter values without user interaction",
            "To trigger button-driven workflows from an agent",
        ],
        prerequisites=[
            "A valid session_id or file_path for an active notebook",
            "The element_id of the target UI element (use get_cell_outputs to discover elements)",
        ],
        side_effects=[
            "The element's value will change and dependent cells will re-execute",
        ],
    )

    async def handle(
        self, args: SetUIElementValueArgs
    ) -> SetUIElementValueOutput:  # type: ignore[override]
        session, session_id = self.context.resolve_session_and_id(
            args.session_id, args.file_path
        )

        if not args.element_id:
            raise ToolExecutionError(
                "element_id is required",
                code="BAD_ARGUMENTS",
                is_retryable=False,
            )

        command = UpdateUIElementCommand.from_ids_and_values(
            [(UIElementId(args.element_id), args.value)]
        )

        listener = ExecutionListener()
        with session.scoped(listener):
            session.put_control_request(
                command,
                from_consumer_id=ConsumerId(session_id),
            )
            await listener.wait(timeout=args.timeout)

        if listener.timed_out:
            return SetUIElementValueOutput(
                status="warning",
                element_id=args.element_id,
                timed_out=True,
                message=f"Reactive execution timed out after {args.timeout}s. Cells may still be running.",
                next_steps=[
                    "Check cell status with get_cell_runtime_data",
                    "Increase timeout if needed",
                ],
            )

        return SetUIElementValueOutput(
            element_id=args.element_id,
            next_steps=[
                "Use get_cell_outputs to verify the updated state",
            ],
        )
