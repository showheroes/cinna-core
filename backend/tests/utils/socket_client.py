"""A minimal Socket.IO client that speaks the polling transport over ``TestClient``.

The Socket.IO app is an ASGI app mounted at ``/ws``, so it is reachable over
plain HTTP through the same ``TestClient`` every other API test uses — the
handshake, the connect packet and event acks are all ordinary GET/POST
round-trips. That keeps socket tests inside the API-only rule (no imports from
``app.services``, no reaching into handler closures) *and* means they exercise
the real mount, not a hand-called function: a regression that unmounts the app
or breaks the ASGI wiring fails these tests too.

Protocol in the two lines that matter (Engine.IO v4 / Socket.IO v5):

* ``GET  /ws/?EIO=4&transport=polling``            -> ``0{"sid": ...}``  (open)
* ``POST /ws/?...&sid=<sid>`` body ``40<json>``    -> namespace connect, auth=<json>
* the next ``GET`` returns ``40{"sid": ...}`` if the server accepted the
  connection, or ``44{"message": ...}`` if ``connect`` returned ``False``
* ``POST`` body ``42<ackId>["<event>", <data>]``   -> the next ``GET`` returns
  ``43<ackId>[<ack payload>]``

Multiple packets in one poll are separated by ``\\x1e`` (record separator).
"""

import json
from typing import Any

from fastapi.testclient import TestClient

_RECORD_SEPARATOR = "\x1e"
_PATH = "/ws/"


class SocketRejected(Exception):
    """The server refused the connection (``connect`` returned ``False``)."""


class PollingSocket:
    """One Socket.IO connection over the polling transport."""

    def __init__(self, client: TestClient):
        self._client = client
        self._sid: str | None = None
        self._ack_id = 0

    # ── transport ────────────────────────────────────────────────────────

    def _params(self) -> dict[str, str]:
        params = {"EIO": "4", "transport": "polling"}
        if self._sid:
            params["sid"] = self._sid
        return params

    def _poll(self) -> list[str]:
        response = self._client.get(_PATH, params=self._params())
        assert response.status_code == 200, response.text
        return response.text.split(_RECORD_SEPARATOR)

    def _send(self, packet: str) -> None:
        response = self._client.post(_PATH, params=self._params(), content=packet)
        assert response.status_code == 200, response.text

    # ── protocol ─────────────────────────────────────────────────────────

    def connect(self, auth: dict[str, Any] | None = None) -> None:
        """Open the transport and connect the namespace.

        Raises ``SocketRejected`` if the server refused the connection.
        """
        opening = self._client.get(_PATH, params=self._params())
        assert opening.status_code == 200, opening.text
        self._sid = json.loads(opening.text[1:])["sid"]

        self._send("40" + json.dumps(auth if auth is not None else {}))

        for packet in self._poll():
            if packet.startswith("44"):
                raise SocketRejected(packet[2:])
            if packet.startswith("40"):
                return
        raise AssertionError(f"no connect response in poll: {self._poll()!r}")

    def emit(self, event: str, data: Any) -> Any:
        """Emit ``event`` and return the handler's ack payload."""
        self._ack_id += 1
        ack_id = self._ack_id
        self._send(f"42{ack_id}" + json.dumps([event, data]))

        prefix = f"43{ack_id}"
        for packet in self._poll():
            if packet.startswith(prefix):
                payload = json.loads(packet[len(prefix):])
                return payload[0] if len(payload) == 1 else payload
        raise AssertionError(f"no ack {ack_id} for {event!r}")


def connect_socket(client: TestClient, auth: dict[str, Any] | None = None) -> PollingSocket:
    """Connect a socket, or raise ``SocketRejected``."""
    socket = PollingSocket(client)
    socket.connect(auth)
    return socket


def socket_is_accepted(client: TestClient, auth: dict[str, Any] | None = None) -> bool:
    """Whether the server accepts a connection with ``auth``."""
    try:
        connect_socket(client, auth)
        return True
    except SocketRejected:
        return False
