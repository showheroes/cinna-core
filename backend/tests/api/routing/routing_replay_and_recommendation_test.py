"""Replay and the recommendation draft — the other two Phase 3 routes.

Replay re-runs a stored decision's message against *current* state and diffs
the two; the recommendation draft turns a failed decision into wording its
agent's owner can apply. Both share simulate's conditions (superuser-only,
rate-limited, LLM-spending) and both are read-only with respect to agents.

Like the simulate suite next door, the absence assertions here are asserted
against durable state — the original trace still reading as it did, the
candidate's trigger prompt unchanged through the API — never against a log.
"""
import uuid

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.mfa import find_security_events
from tests.utils.routing import (
    STUB_TRIGGER_DRAFT,
    classification,
    draft_routing_recommendation,
    get_routing_trace,
    patched_routing_externals,
    patched_trigger_prompt_draft,
    post_channel_message,
    replay_routing_trace,
    simulate_routing,
)
from tests.utils.server_channel import (
    GoogleChatJWTSigner,
    build_message_event,
    create_server_channel,
)
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR


def _channel(client, superuser_headers) -> dict:
    return create_server_channel(
        client, superuser_headers, auto_register_users=True, email_whitelist="*"
    )


def _user_with_agent(client, superuser_headers) -> tuple[dict, dict, dict]:
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    agent = create_agent_via_api(client, headers, name=f"Rep-{random_lower_string()[:6]}")
    drain_tasks()
    return user, headers, agent


def _delivered_no_match_trace(client, superuser_headers, channel) -> dict:
    """One real webhook delivery from an unknown sender -> a `no_match` trace."""
    signer = GoogleChatJWTSigner()
    thread_key = f"spaces/AAA/threads/{random_lower_string()}"
    event = build_message_event(
        thread_key=thread_key,
        text="please compute the eigenvalues",
        sender_email=f"{random_lower_string()}@example.com",
    )
    resp, _ = post_channel_message(client, channel, signer, event)
    assert resp.status_code == 200
    from tests.utils.routing import list_routing_traces

    page = list_routing_traces(client, superuser_headers, channel_id=channel["id"])
    assert page["count"] == 1, page["data"]
    return page["data"][0]


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


def test_replay_reruns_the_stored_message_and_reports_no_change(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Replaying an unchanged system must say so *out loud*. "The change I made
    did not fix it" is a real answer, and an empty diff panel would read as
    though the replay had not run at all — §11a Rule 1 on a read surface.

    The original trace is also asserted unchanged: a replay writes a NEW row,
    it never edits the one it re-ran.
    """
    channel = _channel(client, superuser_token_headers)
    original_row = _delivered_no_match_trace(client, superuser_token_headers, channel)
    original_before = get_routing_trace(
        client, superuser_token_headers, original_row["id"]
    )

    with patched_routing_externals():
        result = replay_routing_trace(
            client, superuser_token_headers, original_row["id"]
        )

    assert result["replay"]["id"] != original_row["id"], "replay overwrote the original"
    assert result["replay"]["origin"] == "simulate"
    assert result["replay"]["actor_user_id"] is not None
    assert result["replay"]["outcome"] == original_row["outcome"]

    diff = result["diff"]
    assert diff["changed"] is False
    assert "Nothing changed" in diff["summary"]
    assert diff["original_outcome"] == diff["replay_outcome"] == "no_match"

    assert (
        get_routing_trace(client, superuser_token_headers, original_row["id"])
        == original_before
    ), "replay mutated the trace it re-ran"


def test_replay_reports_the_change_after_the_agent_becomes_routable(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    The tuning loop's payoff: a message that found nothing, replayed after the
    sender's own agent gains a trigger prompt, now routes — and the diff names
    the outcome flip and the candidate that appeared.
    """
    channel = _channel(client, superuser_token_headers)
    user, headers, agent = _user_with_agent(client, superuser_token_headers)

    signer = GoogleChatJWTSigner()
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text="please compute the eigenvalues",
        sender_email=user["email"],
    )
    resp, _ = post_channel_message(client, channel, signer, event)
    assert resp.status_code == 200

    from tests.utils.routing import list_routing_traces

    original = list_routing_traces(
        client, superuser_token_headers, channel_id=channel["id"]
    )["data"][0]
    assert original["outcome"] == "no_match", original

    # The fix an admin would ask the owner to make — on the agent itself, not
    # on an App MCP route, which channel routing does not read.
    set_router_trigger_prompt(client, headers, agent["id"], "Handle maths")

    with patched_routing_externals():
        result = replay_routing_trace(client, superuser_token_headers, original["id"])

    diff = result["diff"]
    assert diff["changed"] is True
    assert diff["outcome_changed"] is True
    assert diff["original_outcome"] == "no_match"
    assert diff["replay_outcome"] == "routed"
    assert diff["selection_changed"] is True
    assert diff["original_selection"] is None
    assert agent["name"] in (diff["replay_selection"] or "")
    # NOT `candidates_added`: the agent was on the original ballot too, as a
    # skipped candidate (`no_trigger_prompt`) — which is the whole point of
    # recording skips rather than dropping them. What changed is its
    # *eligibility*, which the set-difference fields cannot express, so it is
    # asserted where it is actually visible: the candidate rows themselves.
    def _agent_row(detail: dict) -> dict:
        return next(
            c
            for stage in detail["stages"]
            if stage["stage"] == "pass_1"
            for c in stage["candidates"]
            if c["ref_id"] == agent["id"]
        )

    original_detail = get_routing_trace(client, superuser_token_headers, original["id"])
    assert _agent_row(original_detail)["eligible"] is False
    assert _agent_row(original_detail)["skip_reason"] == "no_trigger_prompt"
    assert _agent_row(result["replay"])["eligible"] is True
    assert result["replay"]["selected_agent_id"] == agent["id"]


def test_replay_is_refused_when_the_message_text_gate_is_off(
    client: TestClient, superuser_token_headers: dict[str, str], monkeypatch
) -> None:
    """
    Replay needs the original message. With ``ROUTING_TRACE_STORE_MESSAGE_TEXT``
    off it is refused rather than run — the flag means "stop showing me this
    text", and re-running it to make a fresh trace is not honouring that. The
    refusal names the flag and points at simulate, so an admin is not left
    guessing.
    """
    channel = _channel(client, superuser_token_headers)
    original = _delivered_no_match_trace(client, superuser_token_headers, channel)

    monkeypatch.setattr(settings, "ROUTING_TRACE_STORE_MESSAGE_TEXT", False)
    r = client.post(
        f"{API}/admin/routing/traces/{original['id']}/replay",
        headers=superuser_token_headers,
        json={"include_catalog": True},
    )
    assert r.status_code == 409, r.text
    assert "ROUTING_TRACE_STORE_MESSAGE_TEXT" in r.json()["detail"]
    assert "simulate" in r.json()["detail"]


def _quote_cast(client, superuser_headers, db, *, agents: int):
    """A channel, a sender with `agents` eligible agents, and one real reply.

    The reply is the LAST agent's, on its own thread, so a later message can
    quote a platform-authored message the delivery ledger knows. Returns
    `(channel, signer, sender, headers, agent_list, reply_id, answer)`.
    """
    from tests.utils.channel_quote import (
        CHANNEL_SECRETS,
        deliver_channel_event,
        final_reply_message_id,
    )
    from tests.stubs.agent_env_stub import StubAgentEnvConnector

    channel = create_server_channel(
        client,
        superuser_headers,
        auto_register_users=False,
        email_whitelist="*",
        secrets=CHANNEL_SECRETS,
    )
    signer = GoogleChatJWTSigner()
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    made = [
        create_agent_via_api(client, headers, name=f"Quote{i}-{random_lower_string()[:6]}")
        for i in range(agents)
    ]
    drain_tasks()
    for i, agent in enumerate(made):
        set_router_trigger_prompt(client, headers, agent["id"], f"Handle topic {i}")

    answer = f"Sunny tomorrow. {random_lower_string()[:6]}"
    thread_key = f"spaces/AAA/threads/{random_lower_string()}"
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        build_message_event(thread_key=thread_key, text="weather?", sender_email=user["email"]),
        stream_stub=StubAgentEnvConnector(response_text=answer),
        classify_result=classification(made[-1]["id"]),
    )
    assert resp.status_code == 200
    reply_id = final_reply_message_id(db, channel["id"], thread_key)
    return channel, signer, user, headers, made, reply_id, answer


def _deliver_and_get_trace(client, superuser_headers, channel, signer, event, **kwargs) -> dict:
    from tests.utils.channel_quote import deliver_channel_event
    from tests.utils.routing import list_routing_traces

    before = {
        r["id"] for r in list_routing_traces(client, superuser_headers, channel_id=channel["id"])["data"]
    }
    resp, _, _ = deliver_channel_event(client, channel, signer, event, **kwargs)
    assert resp.status_code == 200
    new = {
        r["id"] for r in list_routing_traces(client, superuser_headers, channel_id=channel["id"])["data"]
    } - before
    assert len(new) == 1, new
    return get_routing_trace(client, superuser_headers, new.pop())


def test_replay_of_a_quoted_decision_re_renders_the_quote_and_re_applies_the_preference(
    client: TestClient, superuser_token_headers: dict[str, str], db, monkeypatch
) -> None:
    """
    Replay needs the quote the original decision was given — the stored
    `stages[].prompt` is clamped inside the template and can never supply it —
    so the trace stores it (plan D6) and replay carries it back in.

      1. **Preference re-applied.** A decision routed by `quoted_reply` replays
         to the same agent with NO classifier call (the refusal stub is
         installed), carrying the quote and the quoted agent, and says
         nothing changed.
      2. **Quote re-rendered.** A decision that classified with a human quote
         replays through the real renderer: the captured prompt holds the quote
         section with the stored text and author, and the User Message is the
         original words. The audit row carries the quote's length, not its body.
      3. With `ROUTING_TRACE_STORE_MESSAGE_TEXT` off, a quoted trace is still a
         409 — the quote is never re-run from a withheld row.
    """
    import json
    from unittest.mock import MagicMock, patch

    from tests.utils.channel_quote import (
        PROVIDER_TARGET,
        QUOTED_SECTION_HEADING,
        user_message_section,
    )

    channel, signer, user, headers, (jokes, weather), reply_id, answer = _quote_cast(
        client, superuser_token_headers, db, agents=2
    )

    # ── Phase 1: a quoted_reply decision replays as one ───────────────────
    preferred = _deliver_and_get_trace(
        client,
        superuser_token_headers,
        channel,
        signer,
        build_message_event(
            thread_key=f"spaces/AAA/threads/{random_lower_string()}",
            text="and the day after?",
            sender_email=user["email"],
            quoted_message_name=reply_id,
            quoted_text=answer,
            quoted_sender="DoBot",
        ),
    )
    assert preferred["match_method"] == "quoted_reply", preferred

    with patched_routing_externals():
        result = replay_routing_trace(client, superuser_token_headers, preferred["id"])
    replay = result["replay"]
    assert replay["match_method"] == "quoted_reply", replay
    assert replay["selected_agent_id"] == weather["id"], replay
    assert replay["quoted_agent_id"] == weather["id"], replay
    assert replay["quoted_message_text"] == answer, replay
    assert replay["quoted_message_author"] == "DoBot", replay
    assert result["diff"]["changed"] is False, result["diff"]

    # ── Phase 2: a classified decision replays with the quote rendered ────
    human_quote = f"would be fun to hear a dad joke {random_lower_string()[:6]}"
    classified = _deliver_and_get_trace(
        client,
        superuser_token_headers,
        channel,
        signer,
        build_message_event(
            thread_key=f"spaces/AAA/threads/{random_lower_string()}",
            text="can u?",
            sender_email=user["email"],
            quoted_message_name=f"spaces/AAA/messages/{random_lower_string()}",
            quoted_text=human_quote,
            quoted_sender="Bob Human",
        ),
        classify_result=classification(jokes["id"]),
    )
    assert classified["match_method"] == "ai", classified

    with patched_routing_externals(classify_via_provider=True), patch(PROVIDER_TARGET) as pm:
        pm.return_value.generate_content.return_value = MagicMock(
            text=json.dumps({"agent_id": jokes["id"]})
        )
        result = replay_routing_trace(client, superuser_token_headers, classified["id"])
        prompts = [c.args[0] for c in pm.return_value.generate_content.call_args_list]

    assert len(prompts) == 1, prompts
    assert QUOTED_SECTION_HEADING in prompts[0]
    assert f"Author: Bob Human\n> {human_quote}" in prompts[0]
    assert user_message_section(prompts[0]) == "can u?"
    assert result["replay"]["quoted_message_text"] == human_quote, result["replay"]
    assert result["replay"]["selected_agent_id"] == jokes["id"], result["replay"]
    assert result["diff"]["changed"] is False, result["diff"]

    events = [
        e
        for e in find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
        if e["details"].get("source_trace_id") == classified["id"]
    ]
    assert len(events) == 1, events
    assert events[0]["details"]["quoted_chars"] == len(human_quote)
    assert human_quote not in json.dumps(events[0]["details"])

    # ── Phase 3: the text gate still refuses ──────────────────────────────
    monkeypatch.setattr(settings, "ROUTING_TRACE_STORE_MESSAGE_TEXT", False)
    r = client.post(
        f"{API}/admin/routing/traces/{preferred['id']}/replay",
        headers=superuser_token_headers,
        json={"include_catalog": True},
    )
    assert r.status_code == 409, r.text


def test_replay_after_the_quoted_agent_is_deleted_runs_without_the_preference(
    client: TestClient, superuser_token_headers: dict[str, str], db
) -> None:
    """
    `routing_decision.quoted_agent_id` is SET NULL when that agent is deleted.
    A replay then has no agent to prefer: it classifies among what is left,
    still carrying the quote, and the diff reports what changed — the match
    method, the selection, and the candidate that is gone.
    """
    channel, signer, user, headers, (jokes, news, weather), reply_id, answer = _quote_cast(
        client, superuser_token_headers, db, agents=3
    )
    original = _deliver_and_get_trace(
        client,
        superuser_token_headers,
        channel,
        signer,
        build_message_event(
            thread_key=f"spaces/AAA/threads/{random_lower_string()}",
            text="and the day after?",
            sender_email=user["email"],
            quoted_message_name=reply_id,
            quoted_text=answer,
        ),
    )
    assert original["match_method"] == "quoted_reply", original
    assert original["quoted_agent_id"] == weather["id"], original

    r = client.delete(f"{API}/agents/{weather['id']}", headers=headers)
    assert r.status_code == 200, r.text
    after_delete = get_routing_trace(client, superuser_token_headers, original["id"])
    assert after_delete["quoted_agent_id"] is None, after_delete
    assert after_delete["quoted_message_text"] == answer, after_delete

    with patched_routing_externals(classify_result=classification(jokes["id"])):
        result = replay_routing_trace(client, superuser_token_headers, original["id"])

    replay = result["replay"]
    assert replay["match_method"] == "ai", replay
    assert replay["selected_agent_id"] == jokes["id"], replay
    assert replay["quoted_agent_id"] is None, replay
    assert replay["quoted_message_text"] == answer, replay

    diff = result["diff"]
    assert diff["changed"] is True, diff
    assert diff["match_method_changed"] is True, diff
    assert diff["original_match_method"] == "quoted_reply", diff
    assert diff["replay_match_method"] == "ai", diff
    assert diff["selection_changed"] is True, diff
    assert weather["name"] in diff["candidates_removed"], diff


def test_replay_is_superuser_only_and_audited(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Same conditions as simulate: it decides against another account's live
    state and spends an LLM call, so it is superuser-only and leaves an audit
    row naming the acting admin, the target, and which mode it was."""
    channel = _channel(client, superuser_token_headers)
    user, headers, _ = _user_with_agent(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text="hello",
        sender_email=user["email"],
    )
    resp, _ = post_channel_message(
        client, channel, signer, event, classify_no_match=True
    )
    assert resp.status_code == 200
    from tests.utils.routing import list_routing_traces

    original = list_routing_traces(
        client, superuser_token_headers, channel_id=channel["id"]
    )["data"][0]

    replay_routing_trace(client, headers, original["id"], expected_status=403)

    with patched_routing_externals():
        replay_routing_trace(client, superuser_token_headers, original["id"])

    events = find_security_events(
        client, superuser_token_headers, "ROUTING_SIMULATE_RUN"
    )
    assert len(events) == 1, events
    details = events[0]["details"]
    assert details["mode"] == "replay"
    assert details["source_trace_id"] == original["id"]
    assert details["target_user_id"] == user["id"]
    assert "hello" not in str(details), details


def test_replay_of_an_unknown_trace_is_404(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    replay_routing_trace(
        client, superuser_token_headers, str(uuid.uuid4()), expected_status=404
    )


# ---------------------------------------------------------------------------
# Recommendation draft
# ---------------------------------------------------------------------------


def test_recommendation_drafts_for_a_candidate_and_changes_nothing(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    The advisory boundary: a draft comes back, and the agent's actual trigger
    prompt is untouched. Asserted by reading the agent back through its own
    API — the durable state, not a log line saying we did not write.
    """
    channel = _channel(client, superuser_token_headers)
    user, headers, agent = _user_with_agent(client, superuser_token_headers)
    set_router_trigger_prompt(client, headers, agent["id"], "Handle invoices")

    signer = GoogleChatJWTSigner()
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text="please compute the eigenvalues",
        sender_email=user["email"],
    )
    # The agent IS a candidate (it has a trigger prompt) and the classifier
    # runs and rejects it — which is what puts it in the trace as an eligible
    # candidate that lost, the state a recommendation is drafted from.
    resp, _ = post_channel_message(
        client, channel, signer, event, classify_no_match=True
    )
    assert resp.status_code == 200
    from tests.utils.routing import list_routing_traces

    trace = list_routing_traces(
        client, superuser_token_headers, channel_id=channel["id"]
    )["data"][0]

    before = client.get(f"{API}/agents/{agent['id']}", headers=headers).json()

    with patched_trigger_prompt_draft() as generator:
        draft = draft_routing_recommendation(
            client, superuser_token_headers, trace["id"], ref_id=agent["id"]
        )
    assert draft["trace_id"] == trace["id"]
    assert draft["success"] is True
    assert draft["suggested_trigger_prompt"] == STUB_TRIGGER_DRAFT
    # The brief handed to the generator carries the message that failed to
    # route AND the candidate's current configuration — that pairing is the
    # whole reason this beats re-running the generator on the description.
    brief = generator.call_args.kwargs["description"]
    assert "please compute the eigenvalues" in brief
    assert "Handle invoices" in brief
    assert draft["ref_id"] == agent["id"]
    assert draft["kind"] == "agent"
    assert draft["current_trigger_prompt"] == "Handle invoices"
    # The advisory notice is server-authored and always present, whether or not
    # the generator succeeded — it is what stops the draft reading as a change.
    assert "never edits" in draft["notice"]

    after = client.get(f"{API}/agents/{agent['id']}", headers=headers).json()
    assert after == before, "the recommendation draft modified the agent"


def test_recommendation_refuses_a_candidate_that_is_not_in_the_trace(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Scoped to this trace's candidates on purpose. Unrestricted, the route
    would be a general 'draft a trigger prompt for any agent id' oracle that
    happens to hang off a diagnostics endpoint."""
    channel = _channel(client, superuser_token_headers)
    user, headers, agent = _user_with_agent(client, superuser_token_headers)
    set_router_trigger_prompt(client, headers, agent["id"], "Handle invoices")

    signer = GoogleChatJWTSigner()
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text="hello",
        sender_email=user["email"],
    )
    resp, _ = post_channel_message(
        client, channel, signer, event, classify_no_match=True
    )
    assert resp.status_code == 200
    from tests.utils.routing import list_routing_traces

    trace = list_routing_traces(
        client, superuser_token_headers, channel_id=channel["id"]
    )["data"][0]

    draft_routing_recommendation(
        client,
        superuser_token_headers,
        trace["id"],
        ref_id=str(uuid.uuid4()),
        expected_status=404,
    )


def test_recommendation_refuses_a_trace_with_no_candidates(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """A trace that considered nothing has no subject to draft for, and saying
    so names the real problem: the expected agent was never a candidate."""
    channel = _channel(client, superuser_token_headers)
    trace = _delivered_no_match_trace(client, superuser_token_headers, channel)
    r = client.post(
        f"{API}/admin/routing/traces/{trace['id']}/recommendation",
        headers=superuser_token_headers,
        json={"ref_id": None},
    )
    assert r.status_code == 409, r.text
    assert "never a routing candidate" in r.json()["detail"]


def test_recommendation_is_superuser_only(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    channel = _channel(client, superuser_token_headers)
    trace = _delivered_no_match_trace(client, superuser_token_headers, channel)
    _, headers = create_random_user_with_headers(client)
    draft_routing_recommendation(
        client, headers, trace["id"], expected_status=403
    )


def test_recommendation_writes_no_security_event(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """"Writes nothing" is meant literally. The draft exposes nothing the
    caller did not already have from GET /traces/{id}, so unlike simulate and
    replay it leaves no audit row — and that is easier to keep true when the
    route genuinely writes nothing at all."""
    channel = _channel(client, superuser_token_headers)
    user, headers, agent = _user_with_agent(client, superuser_token_headers)
    set_router_trigger_prompt(client, headers, agent["id"], "Handle invoices")
    signer = GoogleChatJWTSigner()
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text="hello",
        sender_email=user["email"],
    )
    resp, _ = post_channel_message(
        client, channel, signer, event, classify_no_match=True
    )
    assert resp.status_code == 200
    from tests.utils.routing import list_routing_traces

    trace = list_routing_traces(
        client, superuser_token_headers, channel_id=channel["id"]
    )["data"][0]

    traces_before = list_routing_traces(client, superuser_token_headers)["count"]
    with patched_trigger_prompt_draft():
        draft_routing_recommendation(
            client, superuser_token_headers, trace["id"], ref_id=agent["id"]
        )

    assert (
        find_security_events(client, superuser_token_headers, "ROUTING_SIMULATE_RUN")
        == []
    )
    assert list_routing_traces(client, superuser_token_headers)["count"] == traces_before


def test_simulate_replay_and_recommendation_share_one_rate_limit_bucket(
    client: TestClient, superuser_token_headers: dict[str, str], monkeypatch
) -> None:
    """One per-admin budget across all three LLM-spending routes. Separate
    buckets would let one admin spend three times the configured limit by
    rotating between them."""
    from app.api.routes import admin_routing
    from app.services.common.rate_limiter import RateLimiter

    monkeypatch.setattr(settings, "ROUTING_SIMULATE_RATE_LIMIT_PER_MIN", 2)
    monkeypatch.setattr(admin_routing, "_simulate_rate_limiter", RateLimiter())

    channel = _channel(client, superuser_token_headers)
    trace = _delivered_no_match_trace(client, superuser_token_headers, channel)
    user, _, _ = _user_with_agent(client, superuser_token_headers)

    with patched_routing_externals():
        # One simulate + one replay exhausts a budget of two...
        simulate_routing(
            client, superuser_token_headers, message="hi", as_user_id=user["id"]
        )
        replay_routing_trace(client, superuser_token_headers, trace["id"])
        # ...so the third call, on the third route, is throttled.
        stack = patched_trigger_prompt_draft()
        stack.__enter__()
        r = client.post(
            f"{API}/admin/routing/traces/{trace['id']}/recommendation",
            headers=superuser_token_headers,
            json={"ref_id": None},
        )
        stack.__exit__(None, None, None)
    assert r.status_code == 429, r.text
