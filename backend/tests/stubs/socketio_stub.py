"""
Socket.IO test stub matching the SocketIOConnector interface.

StubSocketIOConnector captures emitted events for assertion.
Follows the same pattern as StubSMTPConnector / StubIMAPConnector.
"""


class StubSocketIOConnector:
    """Captures emitted Socket.IO events. No real server."""

    def __init__(self):
        self.emitted_events: list[dict] = []

    async def emit(self, event: str, data, room: str | None = None):
        self.emitted_events.append({"event": event, "data": data, "room": room})

    def get_asgi_app(self):
        return None
