"""A desktop-issued token holds a socket, and revoking the device takes it away.

Item E2 of `drafts/desktop_tasks_integration_plan.md` — the desktop replacing
its task poll with a socket subscription — rests on one server-side claim:
"no further server work beyond E1". These tests are that claim, written down.

A desktop access token is an ordinary user JWT with a `client_kind: "desktop"`
claim and no `aud`, so it resolves through `deps.get_current_user` like any
other, and the desktop lands in `user_{owner_id}` with nothing socket-specific
added for it. The consequence worth pinning is the *second* one: because the
socket calls `get_current_user` rather than re-decoding the token, the
desktop-client revocation check comes along for free. Revoking a device from
Settings → Channels now also kills its event stream on next connect — which
nobody wrote socket code for, and which would silently stop being true if the
socket ever grew a decode of its own.

Both tests are written from the desktop's side of the contract on purpose: if a
later change breaks them, the thing that broke is the desktop integration, not
an abstract auth rule.
"""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.stubs.socketio_stub import StubSocketIOConnector
from tests.utils.background_tasks import drain_tasks
from tests.utils.desktop_auth import obtain_desktop_tokens, revoke_desktop_client
from tests.utils.input_task import create_task, set_task_status
from tests.utils.socket_client import connect_socket, socket_is_accepted

API = settings.API_V1_STR


@pytest.fixture
def desktop(client: TestClient, superuser_token_headers: dict[str, str]) -> dict:
    """A registered desktop client with a live access token."""
    return obtain_desktop_tokens(client, superuser_token_headers, device_name="Cinna Desktop")


def test_a_desktop_token_authenticates_the_socket(
    client: TestClient, desktop: dict, superuser_token_headers: dict[str, str]
):
    """E2's premise: the desktop needs no new server surface to hold a socket."""
    owner_id = client.get(f"{API}/users/me", headers=superuser_token_headers).json()["id"]

    socket = connect_socket(client, {"token": desktop["access_token"]})

    # It is in the owner's room — the one carrying TASK_STATUS_UPDATED and the
    # task_blocked activities the desktop currently polls for.
    assert socket.emit("subscribe", {"room": f"user_{owner_id}"})["status"] == "success"


def test_revoking_the_desktop_client_closes_its_socket_on_next_connect(
    client: TestClient, desktop: dict, superuser_token_headers: dict[str, str]
):
    """The revocation check arrives through `get_current_user`, not through
    socket code — which is exactly why it must be pinned here. The access token
    is a stateless 15-minute JWT and stays cryptographically valid after the
    revoke; only the DB-backed check refuses it."""
    assert socket_is_accepted(client, {"token": desktop["access_token"]}) is True

    revoke_desktop_client(client, superuser_token_headers, desktop["client_id"])

    assert socket_is_accepted(client, {"token": desktop["access_token"]}) is False


def test_a_user_status_write_emits_into_the_room_the_desktop_socket_joined(
    client: TestClient, superuser_token_headers: dict[str, str]
):
    """The other half of E2's premise, and the half nothing covered.

    The test above proves the desktop socket is in ``user_{owner_id}``. This one
    proves that is the room a task status change is emitted to — so the two
    together close the chain the desktop would replace its poll with, without
    needing a single test to span both (the background-task collector runs each
    coroutine under its own ``asyncio.run``, so a real emit from a drained task
    cannot reach a client queue created on the TestClient's loop).

    Asserting the *room* rather than merely "an event was emitted" is the
    point: an emit that lost its ``user_id`` would still fire, still look fine
    in a stub that only counts events, and reach nobody.
    """
    owner_id = client.get(f"{API}/users/me", headers=superuser_token_headers).json()["id"]
    task = create_task(client, superuser_token_headers, title="Desktop-executed job")

    stub = StubSocketIOConnector()
    with patch("app.services.events.event_service.socketio_connector", stub):
        set_task_status(client, superuser_token_headers, task["id"], "in_progress")
        drain_tasks()

    rooms = {
        emitted["room"]
        for emitted in stub.emitted_events
        if emitted["data"].get("type") == "task_status_changed"
    }
    assert rooms == {f"user_{owner_id}"}, stub.emitted_events
