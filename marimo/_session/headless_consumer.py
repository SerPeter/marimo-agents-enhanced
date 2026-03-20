# Copyright 2026 Marimo. All rights reserved.
"""Headless session consumer for programmatic session creation.

Used by MCP tools to bootstrap sessions without a WebSocket connection.
The consumer is immediately disconnected after session creation so the
session enters ORPHANED state, making it resumable by a browser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from marimo._session.consumer import SessionConsumer
from marimo._session.model import ConnectionState
from marimo._types.ids import ConsumerId

if TYPE_CHECKING:
    from marimo._messaging.types import KernelMessage
    from marimo._session.events import SessionEventBus
    from marimo._session.session import Session


class HeadlessSessionConsumer(SessionConsumer):
    """Temporary SessionConsumer for programmatic session creation.

    Used to bootstrap a session via create_session(), then immediately
    disconnected so the session enters ORPHANED state. A browser can
    later resume the orphaned session via the normal WebSocket flow.
    """

    def __init__(self, consumer_id: ConsumerId) -> None:
        self._consumer_id = consumer_id

    @property
    def consumer_id(self) -> ConsumerId:
        return self._consumer_id

    def notify(self, notification: KernelMessage) -> None:
        # No-op: consumer is short-lived and disconnected immediately
        # after session creation. Kernel state is captured in SessionView.
        del notification

    def connection_state(self) -> ConnectionState:
        return ConnectionState.OPEN

    def on_attach(self, session: Session, event_bus: SessionEventBus) -> None:
        del session
        del event_bus

    def on_detach(self) -> None:
        return None
