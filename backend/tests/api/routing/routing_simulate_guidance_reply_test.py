"""`POST /admin/routing/simulate` shows the guidance reply and sends nothing.

Channel routing guidance, Phase 2. A decision that routes nowhere but answers
(`outcome="guided"`) carries the reply the sender *would* have been sent as
`guidance_reply` on the simulate response (`RoutingSimulatePublic`) — composed
by the same function the webhook path uses, never stored and never sent. Its
markdown follows the named channel's transport as the webhook's does (plain on
email, markdown on Google Chat), and stays markdown when no channel is named.
Trace reads (`GET /admin/routing/traces/{id}`) do not carry the key at all.
`CHANNEL_ROUTING_GUIDANCE_ENABLED=False` makes it `null`, like the webhook's
reply falls back to the no-match sentence.

The webhook half — what a real sender receives on Google Chat and email — is
`tests/api/server_channels/server_channels_routing_guidance_test.py`; the
composer itself is `tests/unit/test_channel_routing_guidance.py`.
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.email_channel import create_email_channel
from tests.utils.mail_server import create_imap_server, create_smtp_server
from tests.utils.routing import (
    classification,
    classifier_answer,
    get_routing_trace,
    patched_routing_externals,
    simulate_routing,
)
from tests.utils.server_channel import create_server_channel
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.utils import random_lower_string

_GUIDANCE_SETTING = "app.core.config.settings.CHANNEL_ROUTING_GUIDANCE_ENABLED"
HELP_HEAD = "Here's who I can hand your message to:"


def _user_with_two_agents(client, superuser_headers):
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    agents = []
    for prefix, trigger in (("Joker", "Tells jokes"), ("HRHelper", "Leave and payroll")):
        agent = create_agent_via_api(client, headers, name=f"{prefix}-{random_lower_string()[:6]}")
        drain_tasks()
        set_router_trigger_prompt(client, headers, agent["id"], trigger)
        agents.append((agent, trigger))
    return user, headers, agents


def _channel_of_type(client, superuser_headers, channel_type: str) -> dict:
    if channel_type == "email":
        imap = create_imap_server(client, superuser_headers)
        smtp = create_smtp_server(client, superuser_headers)
        return create_email_channel(
            client,
            superuser_headers,
            incoming_server_id=imap["id"],
            outgoing_server_id=smtp["id"],
            incoming_mailbox=f"support-{random_lower_string()[:8]}@corp.example",
            auto_register_users=True,
        )
    return create_server_channel(
        client, superuser_headers, auto_register_users=True, email_whitelist="*"
    )


@pytest.mark.parametrize(
    "intent,head",
    [
        ("help", HELP_HEAD),
        ("none", "I couldn't find an assistant for that. I can hand your message to:"),
    ],
)
def test_simulate_returns_the_guidance_reply_and_sends_nothing(
    client: TestClient, superuser_token_headers: dict[str, str], intent: str, head: str
) -> None:
    """
      1. Simulate a message the classifier answers `help` / `none` over a
         user's two agents.
      2. The response is `guided` and carries the reply, in markdown, listing
         both agents.
      3. Nothing was sent and no session exists.
      4. The stored trace read back through the trace API carries no
         `guidance_reply` key, while its stage still says which guidance ran.
    """
    user, headers, agents = _user_with_two_agents(client, superuser_token_headers)

    with patched_routing_externals(classify_result=classifier_answer(intent=intent)) as send_mock:
        result = simulate_routing(
            client, superuser_token_headers, message="what can you do?", as_user_id=user["id"]
        )

    assert result["outcome"] == "guided", result
    lines = (result["guidance_reply"] or "").splitlines()
    assert lines[0] == head, lines
    assert sorted(lines[1:-1]) == sorted(
        f"- **{agent['name']}** — {trigger}" for agent, trigger in agents
    ), lines

    assert send_mock.call_count == 0
    assert list_sessions(client, headers) == []

    stored = get_routing_trace(client, superuser_token_headers, result["id"])
    assert "guidance_reply" not in stored, stored.keys()
    assert stored["outcome"] == "guided"
    pass1 = next(s for s in stored["stages"] if s["stage"] == "pass_1")
    assert pass1["guidance_kind"] == intent, pass1
    assert {o["ref_id"] for o in pass1["guidance_options"]} == {a["id"] for a, _ in agents}


@pytest.mark.parametrize("channel_type,markdown", [("google_chat", True), ("email", False)])
def test_simulate_on_a_channel_shows_the_reply_in_that_channels_markup(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    channel_type: str,
    markdown: bool,
) -> None:
    """Email sends text/plain, so its reply names the agents without `**`;
    Google Chat renders markdown and keeps them. Simulate reads the named
    channel's transport as the webhook does rather than always showing
    markdown, so an admin sees the text the sender would get."""
    user, _, agents = _user_with_two_agents(client, superuser_token_headers)
    channel = _channel_of_type(client, superuser_token_headers, channel_type)

    with patched_routing_externals(classify_result=classifier_answer(intent="help")):
        result = simulate_routing(
            client,
            superuser_token_headers,
            message="what can you do?",
            as_user_id=user["id"],
            channel_id=channel["id"],
        )

    assert result["outcome"] == "guided", result
    reply = result["guidance_reply"] or ""
    lines = reply.splitlines()
    assert lines[0] == HELP_HEAD, lines
    label = "**{}**" if markdown else "{}"
    assert sorted(lines[1:-1]) == sorted(
        f"- {label.format(agent['name'])} — {trigger}" for agent, trigger in agents
    ), lines
    assert ("**" in reply) is markdown, reply


@pytest.mark.parametrize("intent", ["help", "none"])
def test_simulate_with_guidance_switched_off_has_no_reply(
    client: TestClient, superuser_token_headers: dict[str, str], intent: str
) -> None:
    user, _, _ = _user_with_two_agents(client, superuser_token_headers)

    with patch(_GUIDANCE_SETTING, False), patched_routing_externals(
        classify_result=classifier_answer(intent=intent)
    ):
        result = simulate_routing(
            client, superuser_token_headers, message="what can you do?", as_user_id=user["id"]
        )

    assert result["outcome"] == "no_match", result
    assert result["guidance_reply"] is None, result


def test_simulate_that_routes_or_has_nothing_to_list_has_no_reply(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    user, _, agents = _user_with_two_agents(client, superuser_token_headers)
    with patched_routing_externals(classify_result=classification(agents[0][0]["id"])):
        routed = simulate_routing(
            client, superuser_token_headers, message="tell me a joke", as_user_id=user["id"]
        )
    assert routed["outcome"] == "routed", routed
    assert routed["guidance_reply"] is None, routed

    # A user with nothing on any ballot: no model is asked, nothing to list.
    empty_user, _ = create_random_user_with_headers(client)
    with patched_routing_externals():
        nothing = simulate_routing(
            client,
            superuser_token_headers,
            message="what can you do?",
            as_user_id=empty_user["id"],
            include_catalog=False,
        )
    assert nothing["outcome"] == "no_match", nothing
    assert nothing["guidance_reply"] is None, nothing
