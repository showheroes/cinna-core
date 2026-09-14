"""Simulate with a quoted message — quote-aware channel routing, Phase 5.

`POST /admin/routing/simulate` accepts three optional inputs so an admin can
reproduce a channel message that replied to another one:

- `quoted_message_text` (max 1000) and `quoted_message_author` (max 120): the
  quote, given to the classifier as context and nothing else;
- `quoted_agent_id`: the agent whose reply was quoted, preferred **only** when
  it is already on the target's ballot. It must name an existing agent — a
  404 *before* any LLM call, for the reason `channel_id` is checked: the trace
  INSERT's foreign key would otherwise fail after paid spend.

`CHANNEL_QUOTE_ROUTING_ENABLED` governs simulate exactly as it governs the
webhook: off, the quote and the quoted agent are dropped, and the audit row
says so (`quote_routing_enabled`).

The audit row carries `quoted_chars` and `quoted_agent_id`, never the body —
the same rule `message_chars` follows.

The prompt is captured at classifier depth (`agent_classifier.get_provider_manager`)
so the real render runs; a scenario that must not classify names no answer, so
`refuse_to_classify` fails it loudly. The no-side-effects property is re-pinned
on the quoted form against durable state, as
`routing_simulate_no_side_effects_test.py` does for the plain form.
"""
import json
import uuid
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.models import ChannelThreadBinding
from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.channel_quote import (
    PROVIDER_TARGET,
    QUOTED_SECTION_HEADING,
    QUOTED_START_MARKER,
    user_message_section,
)
from tests.utils.mfa import find_security_events
from tests.utils.routing import (
    classification,
    list_routing_traces,
    patched_routing_externals,
    simulate_routing,
)
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR


def _target_with_two_agents(client, superuser_headers) -> tuple[dict, dict, dict, dict]:
    """A target who owns two eligible agents, so an unpreferred run classifies."""
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    jokes = create_agent_via_api(client, headers, name=f"Jokes-{random_lower_string()[:6]}")
    weather = create_agent_via_api(client, headers, name=f"Weather-{random_lower_string()[:6]}")
    drain_tasks()
    set_router_trigger_prompt(client, headers, jokes["id"], "Tell jokes on request")
    set_router_trigger_prompt(client, headers, weather["id"], "Weather forecasts")
    return user, headers, jokes, weather


def _binding_count(db: Session) -> int:
    """EXEMPTION — bindings have no HTTP surface; the same read
    `routing_simulate_no_side_effects_test.py::_binding_count` takes."""
    return len(db.exec(select(ChannelThreadBinding)).all())


def _simulate_trace_ids(client, superuser_headers) -> set[str]:
    return {
        row["id"]
        for row in list_routing_traces(client, superuser_headers, origin="simulate")["data"]
    }


def _pass1(trace: dict) -> dict:
    return next(s for s in trace["stages"] if s["stage"] == "pass_1")


def test_simulate_renders_the_quote_as_context_and_audits_only_its_length(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    1. Simulate "can u?" with a padded quoted text and an author label.
    2. The provider is handed a prompt with the quote section; the User Message
       is exactly "can u?".
    3. The returned trace carries the stripped quote and author (text gate on).
    4. The audit row carries `quoted_chars` (the stripped length),
       `quoted_agent_id=None` and `quote_routing_enabled=True` — never the
       body, never the author label.
    """
    user, _, jokes, _ = _target_with_two_agents(client, superuser_token_headers)
    quote = f"would be fun to hear a dad joke {random_lower_string()[:8]}"
    author = f"Bob-{random_lower_string()[:8]}"

    with patched_routing_externals(classify_via_provider=True), patch(PROVIDER_TARGET) as pm:
        pm.return_value.generate_content.return_value = MagicMock(
            text=json.dumps({"agent_id": jokes["id"]})
        )
        trace = simulate_routing(
            client,
            superuser_token_headers,
            message="can u?",
            as_user_id=user["id"],
            quoted_message_text=f"  {quote}\n",
            quoted_message_author=f" {author} ",
        )
        prompts = [c.args[0] for c in pm.return_value.generate_content.call_args_list]

    # ── The prompt ────────────────────────────────────────────────────────
    assert len(prompts) == 1, prompts
    prompt = prompts[0]
    assert QUOTED_SECTION_HEADING in prompt
    assert QUOTED_START_MARKER in prompt
    assert f"> {quote}" in prompt
    assert f"Author: {author}" in prompt
    assert user_message_section(prompt) == "can u?"

    # ── The trace ─────────────────────────────────────────────────────────
    assert trace["outcome"] == "routed", trace
    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["message_text"] == "can u?", trace
    assert trace["quoted_message_text"] == quote, trace
    assert trace["quoted_message_author"] == author, trace
    assert trace["quoted_agent_id"] is None, trace

    # ── The audit ─────────────────────────────────────────────────────────
    events = find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
    assert len(events) == 1, events
    details = events[0]["details"]
    assert details["message_chars"] == len("can u?")
    assert details["quoted_chars"] == len(quote)
    assert details["quoted_agent_id"] is None
    assert details["quote_routing_enabled"] is True
    assert quote not in json.dumps(details), details
    assert author not in json.dumps(details), details


def test_simulate_prefers_a_quoted_agent_only_when_it_is_on_the_ballot(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    1. **On the ballot.** `quoted_agent_id` names one of the target's two
       eligible agents: routed `quoted_reply` with NO classifier call (the
       refusal stub is installed), and both candidates still listed.
    2. **Off the ballot.** It names another user's agent: the preference cannot
       add a candidate, so the run classifies; the foreign agent is on no stage.
    3. The audit names the quoted agent id; neither run bound a thread, opened
       a session or sent anything.
    """
    user, headers, jokes, weather = _target_with_two_agents(client, superuser_token_headers)
    stranger, stranger_headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_token_headers, stranger["id"])
    create_random_ai_credential(client, stranger_headers, set_default=True)
    foreign = create_agent_via_api(client, stranger_headers, name=f"Foreign-{random_lower_string()[:6]}")
    drain_tasks()
    set_router_trigger_prompt(client, stranger_headers, foreign["id"], "Tell jokes on request")

    bindings_before = _binding_count(db)

    # ── Phase 1: on the ballot — no classifier ────────────────────────────
    with patched_routing_externals() as send_mock:
        preferred = simulate_routing(
            client,
            superuser_token_headers,
            message="another one please",
            as_user_id=user["id"],
            quoted_message_text="Why did the scarecrow win an award?",
            quoted_agent_id=weather["id"],
        )
    assert preferred["outcome"] == "routed", preferred
    assert preferred["match_method"] == "quoted_reply", preferred
    assert preferred["selected_agent_id"] == weather["id"], preferred
    assert preferred["quoted_agent_id"] == weather["id"], preferred
    pass1 = _pass1(preferred)
    assert {c["ref_id"] for c in pass1["candidates"]} == {jokes["id"], weather["id"]}
    assert pass1.get("prompt") is None, pass1
    assert send_mock.await_count == 0

    # ── Phase 2: off the ballot — classifies, never widens ────────────────
    with patched_routing_externals(classify_result=classification(jokes["id"])) as send_mock:
        classified = simulate_routing(
            client,
            superuser_token_headers,
            message="another one please",
            as_user_id=user["id"],
            quoted_message_text="Why did the scarecrow win an award?",
            quoted_agent_id=foreign["id"],
        )
    assert classified["match_method"] == "ai", classified
    assert classified["selected_agent_id"] == jokes["id"], classified
    assert classified["quoted_agent_id"] == foreign["id"], classified
    every_ref = {c["ref_id"] for s in classified["stages"] for c in s.get("candidates") or []}
    assert foreign["id"] not in every_ref, classified["stages"]
    assert not any(ref.startswith("identity:") for ref in every_ref), every_ref
    assert send_mock.await_count == 0

    # ── Phase 3: audit + no side effects ──────────────────────────────────
    events = find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
    assert sorted(e["details"]["quoted_agent_id"] for e in events) == sorted(
        [weather["id"], foreign["id"]]
    ), events
    assert _binding_count(db) == bindings_before
    assert list_sessions(client, headers) == []
    assert list_sessions(client, stranger_headers) == []


def test_simulate_naming_an_unknown_quoted_agent_is_404_before_it_spends(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """The target owns two eligible agents, so a run past the guard would
    classify — and no answer is named, so `refuse_to_classify` (a
    `BaseException`) fails this test if the refusal stops happening first.
    Nothing is stored and nothing is audited."""
    user, _, _, _ = _target_with_two_agents(client, superuser_token_headers)
    before = _simulate_trace_ids(client, superuser_token_headers)

    with patched_routing_externals():
        r = client.post(
            f"{API}/admin/routing/simulate",
            headers=superuser_token_headers,
            json={
                "message": "another one please",
                "as_user_id": user["id"],
                "quoted_message_text": "a joke",
                "quoted_agent_id": str(uuid.uuid4()),
            },
        )
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "Quoted agent not found", r.text
    assert _simulate_trace_ids(client, superuser_token_headers) == before
    assert find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN") == []


def test_simulate_rejects_over_length_quoted_fields(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """1000 / 120 are the bounds the classifier renders to; one past is a 422
    (before any run), and exactly at the bound is accepted."""
    user, _, jokes, _ = _target_with_two_agents(client, superuser_token_headers)

    for body in (
        {"quoted_message_text": "q" * 1001},
        {"quoted_message_text": "a joke", "quoted_message_author": "a" * 121},
    ):
        with patched_routing_externals():
            r = client.post(
                f"{API}/admin/routing/simulate",
                headers=superuser_token_headers,
                json={"message": "can u?", "as_user_id": user["id"], **body},
            )
        assert r.status_code == 422, (body.keys(), r.text)

    with patched_routing_externals(classify_result=classification(jokes["id"])):
        at_bound = simulate_routing(
            client,
            superuser_token_headers,
            message="can u?",
            as_user_id=user["id"],
            quoted_message_text="q" * 1000,
            quoted_message_author="a" * 120,
        )
    assert at_bound["outcome"] == "routed", at_bound
    assert at_bound["quoted_message_author"] == "a" * 120, at_bound
    # Stored under ROUTING_TRACE_TEXT_MAX_CHARS, which 1000 fits inside.
    assert at_bound["quoted_message_text"] == "q" * 1000, at_bound


def test_simulate_with_the_kill_switch_off_drops_the_quote_and_the_preference(
    client: TestClient, superuser_token_headers: dict[str, str], monkeypatch
) -> None:
    """
    `CHANNEL_QUOTE_ROUTING_ENABLED=False` must make simulate answer the way the
    webhook would with the switch off:

    1. A quoted agent that is on the ballot is NOT preferred — the provider is
       called, so the run classified.
    2. The prompt has no quote section.
    3. The trace carries no quote and no quoted agent.
    4. The audit still describes the *request* (`quoted_chars`,
       `quoted_agent_id`) and says the switch was off, so the two cannot be
       mistaken for what the run used.
    """
    monkeypatch.setattr(settings, "CHANNEL_QUOTE_ROUTING_ENABLED", False)
    user, _, jokes, weather = _target_with_two_agents(client, superuser_token_headers)
    quote = "Why did the scarecrow win an award?"

    with patched_routing_externals(classify_via_provider=True), patch(PROVIDER_TARGET) as pm:
        pm.return_value.generate_content.return_value = MagicMock(
            text=json.dumps({"agent_id": jokes["id"]})
        )
        trace = simulate_routing(
            client,
            superuser_token_headers,
            message="another one please",
            as_user_id=user["id"],
            quoted_message_text=quote,
            quoted_message_author="Bob",
            quoted_agent_id=weather["id"],
        )
        prompts = [c.args[0] for c in pm.return_value.generate_content.call_args_list]

    assert len(prompts) == 1, "the preference applied although the switch is off"
    assert QUOTED_SECTION_HEADING not in prompts[0]
    assert QUOTED_START_MARKER not in prompts[0]
    assert quote not in prompts[0]

    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["quoted_message_text"] is None, trace
    assert trace["quoted_message_author"] is None, trace
    assert trace["quoted_agent_id"] is None, trace

    events = find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
    assert len(events) == 1, events
    details = events[0]["details"]
    assert details["quote_routing_enabled"] is False
    assert details["quoted_chars"] == len(quote)
    assert details["quoted_agent_id"] == weather["id"]
    assert quote not in json.dumps(details), details


def test_a_quoted_agent_deleted_mid_decision_still_writes_the_trace(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """`routing_decision.quoted_agent_id` is a foreign key. An agent deleted
    after the 404 check but before the trace INSERT must cost that one id —
    the row is written with `quoted_agent_id` NULL — never the whole row.

    The delete happens inside the classifier call: the quoted agent is a
    stranger's, so it is off the ballot, the run classifies, and nothing in the
    decision holds the deleted row. It is written straight to the row rather
    than through `DELETE /agents/{id}` for the reason
    `server_channels_identity_revocation_test.py` gives for its mid-decision
    revoke: a nested `TestClient` request cannot run inside the in-flight
    request. A setup input on a row whose own API is covered elsewhere.
    """
    from app.models import Agent

    user, _, jokes, _ = _target_with_two_agents(client, superuser_token_headers)
    stranger, stranger_headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_token_headers, stranger["id"])
    create_random_ai_credential(client, stranger_headers, set_default=True)
    doomed = create_agent_via_api(client, stranger_headers, name=f"Doomed-{random_lower_string()[:6]}")
    drain_tasks()

    deleted: list[bool] = []

    def _classify_then_delete(*_args, **_kwargs):
        row = db.get(Agent, uuid.UUID(doomed["id"]))
        assert row is not None
        db.delete(row)
        db.commit()
        deleted.append(True)
        return classification(jokes["id"])

    before = _simulate_trace_ids(client, superuser_token_headers)
    with patched_routing_externals(classify_side_effect=_classify_then_delete):
        trace = simulate_routing(
            client,
            superuser_token_headers,
            message="another one please",
            as_user_id=user["id"],
            quoted_message_text="Why did the scarecrow win an award?",
            quoted_agent_id=doomed["id"],
        )

    assert deleted == [True], deleted
    assert trace["outcome"] == "routed", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["quoted_agent_id"] is None, trace
    # The quote itself was kept: only the dangling id was dropped.
    assert trace["quoted_message_text"] == "Why did the scarecrow win an award?", trace
    after = _simulate_trace_ids(client, superuser_token_headers)
    assert after - before == {trace["id"]}, after - before


def test_simulate_treats_blank_quoted_text_as_no_quote_and_ignores_an_author_alone(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    user, _, jokes, _ = _target_with_two_agents(client, superuser_token_headers)
    author = f"Bob-{random_lower_string()[:8]}"

    with patched_routing_externals(classify_via_provider=True), patch(PROVIDER_TARGET) as pm:
        pm.return_value.generate_content.return_value = MagicMock(
            text=json.dumps({"agent_id": jokes["id"]})
        )
        trace = simulate_routing(
            client,
            superuser_token_headers,
            message="can u?",
            as_user_id=user["id"],
            quoted_message_text="   \n  ",
            quoted_message_author=author,
        )
        prompts = [c.args[0] for c in pm.return_value.generate_content.call_args_list]

    assert len(prompts) == 1, prompts
    assert QUOTED_SECTION_HEADING not in prompts[0]
    assert author not in prompts[0]
    assert trace["quoted_message_text"] is None, trace
    assert trace["quoted_message_author"] is None, trace

    events = find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
    assert events[0]["details"]["quoted_chars"] == 0, events
