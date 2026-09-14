"""Quote-aware channel routing, end to end through the webhook.

In a Google Chat space a person quotes an earlier message ("would be fun to
hear a dad joke") and writes "@DoBot can u?". The router used to classify only
"can u?" and decline. Now (``docs/plans/channel_quote_aware_routing_plan.md``):

- the quoted **snapshot** reaches every classifier call as a fenced,
  context-only section, while the stored user message, ``message_text`` and
  ``message_sha256`` stay the sender's own words;
- quoting a **platform agent's reply** routes to that agent — but only when it
  is already on the sender's own ballot, or is a reachable agent of an identity
  the sender consented to address. A quote never widens access;
- when the quoted message cannot be read, the agent's context shows the
  snapshot instead of "text unavailable", labelled as a platform agent's reply
  only when the delivery ledger says so;
- ``CHANNEL_QUOTE_ROUTING_ENABLED=False`` turns the routing half off and leaves
  the ingestion fallback on.

The scenarios are plan §12.2 items 1–10; item 11 (email unaffected) is
``server_channels_email_test.py::test_an_email_decision_renders_a_prompt_with_no_quote_section``.

**How each fact is observed.** The prompt is captured at classifier depth
(``agent_classifier.get_provider_manager``) so the real render runs. "Not
classified" is the refusal stub, a ``BaseException`` the router's catch-all
cannot swallow. Platform replies are real turns with all four Chat verbs mocked
(``tests/utils/channel_quote.py``), and the id a later sender quotes is read
off the delivery ledger through the documented ``list_turn_deliveries``
exemption. The read probe is always patched to "no access", the 403 case, so
the snapshot fallback is what the agent sees.

Unit coverage of the pieces: ``tests/unit/test_google_chat_quoted_snapshot.py``
(capture), ``test_router_quoted_context_prompt.py`` (render and fence),
``test_channel_conversation_context.py`` (fallback paths),
``test_agent_classifier_parsing.py`` (``message`` guard).
"""
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.bundle import make_user_and_headers, publish_bundle_and_make_public
from tests.utils.channel_quote import (
    CHANNEL_SECRETS,
    QUOTED_SECTION_HEADING,
    QUOTED_START_MARKER,
    ChatVerbs,
    deliver_channel_event,
    final_reply_message_id,
    patched_channel_transport,
    rendered_prompts,
    user_message_section,
)
from tests.utils.environment import set_environment_status
from tests.utils.identity import create_identity_binding, toggle_identity_contact
from tests.utils.message import list_messages
from tests.utils.routing import classification, get_routing_trace, list_routing_traces
from tests.utils.server_channel import (
    GoogleChatJWTSigner,
    add_auto_install_bundle,
    build_message_event,
    create_server_channel,
    flush_pending_bindings,
)
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.user_channel import update_my_channel
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR

_HUMAN_QUOTE = "would be fun to hear a dad joke"


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------


def _channel(client, superuser_headers) -> dict:
    return create_server_channel(
        client,
        superuser_headers,
        auto_register_users=False,
        email_whitelist="*",
        secrets=CHANNEL_SECRETS,
    )


def _developer(client, superuser_headers) -> tuple[dict, dict[str, str]]:
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    return user, headers


def _agents(client, headers, *specs: tuple[str, str]) -> list[dict]:
    """One eligible agent per ``(label, trigger prompt)``."""
    agents = [
        create_agent_via_api(client, headers, name=f"{label}-{random_lower_string()[:6]}")
        for label, _ in specs
    ]
    drain_tasks()
    for agent, (_, trigger) in zip(agents, specs, strict=True):
        set_router_trigger_prompt(client, headers, agent["id"], trigger)
    return agents


def _thread() -> str:
    return f"spaces/AAA/threads/{random_lower_string()}"


def _human_message_id() -> str:
    """A same-space message id no platform turn ever wrote."""
    return f"spaces/AAA/messages/{random_lower_string()}"


def _event(sender: dict, thread_key: str, text: str, **quote) -> dict:
    return build_message_event(
        thread_key=thread_key, text=text, sender_email=sender["email"], **quote
    )


def _agent_replies(
    client,
    db: Session,
    channel: dict,
    signer,
    sender: dict,
    *,
    answer: str,
    route_to: str | None = None,
    thread_key: str | None = None,
) -> str:
    """One ordinary turn that ends in an agent reply; returns the reply's id.

    ``route_to`` names the classifier's answer when the sender's ballot needs
    one (two or more eligible agents, or a catalog on offer); omitted, the
    scenario must route without classifying.
    """
    thread_key = thread_key or _thread()
    resp, chat, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, thread_key, "tell me something"),
        stream_stub=StubAgentEnvConnector(response_text=answer),
        classify_result=classification(route_to) if route_to else None,
    )
    assert resp.status_code == 200
    assert any(answer in text for text in chat.delivered_to(thread_key)), (
        chat.send.await_args_list,
        chat.replace.await_args_list,
    )
    return final_reply_message_id(db, channel["id"], thread_key)


def _trace_ids(client, superuser_headers, channel) -> set[str]:
    page = list_routing_traces(client, superuser_headers, channel_id=channel["id"])
    return {row["id"] for row in page["data"]}


def _new_trace(client, superuser_headers, channel, before: set[str]) -> dict:
    """The one trace this delivery wrote — by diff, never by list position."""
    new = _trace_ids(client, superuser_headers, channel) - before
    assert len(new) == 1, new
    return get_routing_trace(client, superuser_headers, new.pop())


def _stage(trace: dict, name: str) -> dict | None:
    return next((s for s in trace["stages"] if s["stage"] == name), None)


def _all_refs(trace: dict) -> set[str]:
    return {c["ref_id"] for s in trace["stages"] for c in (s.get("candidates") or [])}


def _sessions(client, headers, agent_id: str) -> list[dict]:
    return [s for s in list_sessions(client, headers) if s["agent_id"] == agent_id]


def _context_notices(client, headers, session_id: str) -> list[dict]:
    return [
        m
        for m in list_messages(client, headers, session_id)
        if (m.get("message_metadata") or {}).get("channel_thread_context") is True
    ]


def _user_texts(client, headers, session_id: str) -> list[str]:
    return [
        m["content"]
        for m in list_messages(client, headers, session_id)
        if m["role"] == "user"
    ]


def _the_quoting_session(client, headers, agent_id: str) -> dict:
    """The one session on ``agent_id`` whose opening turn carried context."""
    matches = [
        s for s in _sessions(client, headers, agent_id) if _context_notices(client, headers, s["id"])
    ]
    assert len(matches) == 1, matches
    return matches[0]


def _publish_catalog_bundle(client, superuser_headers) -> str:
    """A public, listed bundle on the auto-install list. Returns its uuid."""
    publisher, publisher_headers = make_user_and_headers(client)
    promote_to_developer(client, superuser_headers, publisher["id"])
    agent = create_agent_via_api(
        client, publisher_headers, name=f"Catalog-{random_lower_string()[:6]}"
    )
    drain_tasks()
    set_router_trigger_prompt(client, publisher_headers, agent["id"], "Tell jokes from the catalog")
    publish_bundle_and_make_public(client, publisher_headers, agent["id"])
    bundle_uuid = client.get(f"{API}/agents/{agent['id']}", headers=publisher_headers).json()[
        "bundle_uuid"
    ]
    add_auto_install_bundle(client, superuser_headers, bundle_uuid)
    return bundle_uuid


# ---------------------------------------------------------------------------
# 1. The reported case
# ---------------------------------------------------------------------------


def test_the_reported_case_classifies_can_u_with_the_quote_as_context(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    "would be fun to hear a dad joke" → "can u?", from a sender who owns two
    eligible agents and quotes a HUMAN message that came with a snapshot.

      1. The Pass-1 prompt carries the fenced quote section, and its User
         Message is exactly "can u?".
      2. The decision routes to the classifier's pick; the trace stores the
         sender's words as `message_text` and the quote beside them.
      3. The session's stored user message is "can u?" — never the quote.
      4. The agent's context shows the attributed snapshot, not "text
         unavailable", ahead of the question.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, weather = _agents(
        client, headers, ("Jokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )
    thread_key = _thread()
    stub = StubAgentEnvConnector(response_text="Why did the scarecrow win an award?")

    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, provider = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            sender,
            thread_key,
            "can u?",
            quoted_message_name=_human_message_id(),
            quoted_text=_HUMAN_QUOTE,
            quoted_sender="Bob Human",
            quote_type="REPLY",
        ),
        stream_stub=stub,
        provider_reply={"agent_id": jokes["id"]},
    )
    assert resp.status_code == 200

    # ── Phase 1: the prompt ───────────────────────────────────────────────
    prompts = rendered_prompts(provider)
    assert len(prompts) == 1, "exactly one classifier call (Pass 1)"
    prompt = prompts[0]
    assert QUOTED_SECTION_HEADING in prompt
    assert QUOTED_START_MARKER in prompt
    assert f"Author: Bob Human\n> {_HUMAN_QUOTE}" in prompt
    assert user_message_section(prompt) == "can u?"

    # ── Phase 2: the decision and its trace ───────────────────────────────
    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["outcome"] == "routed", trace
    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["message_text"] == "can u?", trace
    assert trace["quoted_message_text"] == _HUMAN_QUOTE, trace
    assert trace["quoted_message_author"] == "Bob Human", trace
    # A human's message: the ledger names no agent, so there is no preference.
    assert trace["quoted_agent_id"] is None, trace

    # ── Phase 3: the stored user message is the sender's own ──────────────
    assert _sessions(client, headers, weather["id"]) == []
    sessions = _sessions(client, headers, jokes["id"])
    assert len(sessions) == 1, sessions
    session_id = sessions[0]["id"]
    assert _user_texts(client, headers, session_id) == ["can u?"]

    # ── Phase 4: the agent's context shows the snapshot ───────────────────
    notices = _context_notices(client, headers, session_id)
    assert len(notices) == 1, notices
    content = notices[0]["content"]
    assert f"Bob Human [time unknown]:\n{_HUMAN_QUOTE}" in content
    assert "text unavailable" not in content
    assert len(stub.stream_calls) == 1
    sent = stub.stream_calls[0]["payload"]["message"]
    assert sent.endswith("can u?"), sent
    assert sent.count(_HUMAN_QUOTE) == 1, sent


# ---------------------------------------------------------------------------
# 2. No snapshot
# ---------------------------------------------------------------------------


def test_a_quote_without_a_snapshot_leaves_the_prompt_and_the_unavailable_note_as_they_were(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
    Google may send the quoted id without a snapshot. Then nothing about the
    classifier changes — the prompt is byte-identical to the same sender's
    unquoted message — and ingestion keeps today's metadata-only note.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, _ = _agents(
        client, headers, ("Jokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )
    quote_id = _human_message_id()

    # ── Phase 1: an unquoted "can u?" — the reference prompt ──────────────
    resp, _, plain_provider = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "can u?"),
        provider_reply={"agent_id": jokes["id"]},
    )
    assert resp.status_code == 200

    # ── Phase 2: the same words quoting an id with no snapshot ────────────
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, quoted_provider = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "can u?", quoted_message_name=quote_id),
        provider_reply={"agent_id": jokes["id"]},
    )
    assert resp.status_code == 200

    [plain_prompt] = rendered_prompts(plain_provider)
    [quoted_prompt] = rendered_prompts(quoted_provider)
    assert QUOTED_SECTION_HEADING not in quoted_prompt
    assert quoted_prompt == plain_prompt

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["quoted_message_text"] is None, trace
    assert trace["quoted_message_author"] is None, trace
    assert trace["quoted_agent_id"] is None, trace

    # ── Phase 3: ingestion says what it always said ───────────────────────
    session = _the_quoting_session(client, headers, jokes["id"])
    [notice] = _context_notices(client, headers, session["id"])
    assert quote_id in notice["content"]
    assert "text unavailable" in notice["content"]
    assert _user_texts(client, headers, session["id"]) == ["can u?"]


# ---------------------------------------------------------------------------
# 3. Quoting the sender's own agent's reply
# ---------------------------------------------------------------------------


def test_quoting_the_senders_own_agents_reply_routes_to_it_without_classifying(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. A real turn: the sender's Jokes agent answers, and the ledger records
         the reply's message id.
      2. A NEW thread by the same sender quotes that reply. The sender owns two
         eligible agents and no classifier answer is named — so routing to
         Jokes proves the preference, and the trace says `quoted_reply` with
         both candidates still listed and no prompt.
      3. The context labels the quoted text as the platform agent's reply,
         from the ledger — not with the snapshot's own author label.
      4. The id alone is enough (plan D5): the same quote with no snapshot is
         still preferred.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, weather = _agents(
        client, headers, ("Jokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )
    answer = f"Why did the scarecrow win an award? {random_lower_string()[:6]}"

    # ── Phase 1: the reply being quoted ───────────────────────────────────
    reply_id = _agent_replies(
        client, db, channel, signer, sender, answer=answer, route_to=jokes["id"]
    )

    # ── Phase 2: a new thread quotes it — no classifier ───────────────────
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            sender,
            _thread(),
            "another one please",
            quoted_message_name=reply_id,
            quoted_text=answer,
            quoted_sender="DoBot",
        ),
    )
    assert resp.status_code == 200

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["outcome"] == "routed", trace
    assert trace["match_method"] == "quoted_reply", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["quoted_agent_id"] == jokes["id"], trace
    pass_1 = _stage(trace, "pass_1")
    assert {c["ref_id"] for c in pass_1["candidates"]} == {jokes["id"], weather["id"]}
    assert all(c["eligible"] for c in pass_1["candidates"]), pass_1["candidates"]
    assert pass_1.get("prompt") is None, pass_1
    assert pass_1.get("raw_response") is None, pass_1
    assert _stage(trace, "pass_2") is None, trace["stages"]
    assert "quoted one of its earlier replies" in trace["diagnosis"]["verdict"], trace["diagnosis"]

    assert len(_sessions(client, headers, jokes["id"])) == 2
    assert _sessions(client, headers, weather["id"]) == []

    # ── Phase 3: the ledger, not the snapshot, names the author ───────────
    session = _the_quoting_session(client, headers, jokes["id"])
    [notice] = _context_notices(client, headers, session["id"])
    assert f"Agent {jokes['name']} on this platform [time unknown]:\n{answer}" in notice["content"]
    assert "DoBot" not in notice["content"]
    assert _user_texts(client, headers, session["id"]) == ["another one please"]

    # ── Phase 4: the id alone still prefers the agent ─────────────────────
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "and one more", quoted_message_name=reply_id),
    )
    assert resp.status_code == 200
    id_only = _new_trace(client, superuser_token_headers, channel, before)
    assert id_only["match_method"] == "quoted_reply", id_only
    assert id_only["selected_agent_id"] == jokes["id"], id_only
    assert id_only["quoted_message_text"] is None, id_only


# ---------------------------------------------------------------------------
# 4. A single-agent sender with a catalog on offer
# ---------------------------------------------------------------------------


def test_a_single_agent_sender_with_a_catalog_quotes_their_agent_and_nothing_probes(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    One eligible agent plus a bundle still on offer normally classifies (so
    auto-install stays reachable) and records the catalog scan. A quote of that
    agent's reply routes by `quoted_reply` before the probe: no catalog scan
    on the trace, no Pass 2, nothing installed.
    """
    _publish_catalog_bundle(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    [jokes] = _agents(client, headers, ("Jokes", "Tell jokes on request"))
    answer = "Knock knock."

    # ── Phase 1: the ordinary turn classifies and scans the catalog ───────
    before = _trace_ids(client, superuser_token_headers, channel)
    thread_key = _thread()
    reply_id = _agent_replies(
        client,
        db,
        channel,
        signer,
        sender,
        answer=answer,
        route_to=jokes["id"],
        thread_key=thread_key,
    )
    first = _new_trace(client, superuser_token_headers, channel, before)
    assert first["match_method"] == "ai", first
    # The control that makes the absence below mean something.
    assert _stage(first, "pass_2") is not None, first["stages"]

    owned_before = {a["id"] for a in client.get(f"{API}/agents/", headers=headers).json()["data"]}

    # ── Phase 2: quoting the reply skips the probe entirely ───────────────
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "who's there?", quoted_message_name=reply_id, quoted_text=answer),
    )
    assert resp.status_code == 200
    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["match_method"] == "quoted_reply", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert _stage(trace, "pass_2") is None, trace["stages"]

    owned_after = {a["id"] for a in client.get(f"{API}/agents/", headers=headers).json()["data"]}
    assert owned_after == owned_before


# ---------------------------------------------------------------------------
# 5. Quoting someone else's agent — access never widens
# ---------------------------------------------------------------------------


def test_quoting_another_askers_agent_classifies_and_never_widens_the_ballot(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    The quoted reply was written by an agent the sender does not own, and the
    sender has identity routing off. The ledger still names that agent, and it
    must change nothing about what the sender may reach: the classifier runs
    (with the quote as context) over the sender's own two agents, the foreign
    agent is on no stage, and no `identity:` candidate appears.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    owner, owner_headers = _developer(client, superuser_token_headers)
    [foreign] = _agents(client, owner_headers, ("OwnerJokes", "Tell jokes on request"))
    answer = "I only tell jokes to my owner."
    reply_id = _agent_replies(client, db, channel, signer, owner, answer=answer)

    sender, headers = _developer(client, superuser_token_headers)
    mine, weather = _agents(
        client, headers, ("MyJokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )

    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, provider = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            sender,
            _thread(),
            "can u do that for me?",
            quoted_message_name=reply_id,
            quoted_text=answer,
            quoted_sender="DoBot",
        ),
        provider_reply={"agent_id": mine["id"]},
    )
    assert resp.status_code == 200

    [prompt] = rendered_prompts(provider)
    assert QUOTED_SECTION_HEADING in prompt
    assert f"> {answer}" in prompt
    assert foreign["id"] not in prompt

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == mine["id"], trace
    refs = _all_refs(trace)
    assert refs == {mine["id"], weather["id"]}, refs
    assert not any(ref.startswith("identity:") for ref in refs), refs
    assert _stage(trace, "identity_stage2") is None, trace["stages"]
    # What the quote pointed at is recorded — an id, not a candidate.
    assert trace["quoted_agent_id"] == foreign["id"], trace

    assert {s["agent_id"] for s in list_sessions(client, headers)} == {mine["id"]}
    assert len(_sessions(client, owner_headers, foreign["id"])) == 1


# ---------------------------------------------------------------------------
# 6. An own agent excluded by scope
# ---------------------------------------------------------------------------


def test_a_scope_excluded_own_agent_is_not_preferred(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    The quoted reply is the sender's own Weather agent's, but the sender has
    since narrowed this channel to `agent_scope="list"` without it. The quote
    does not resurrect it: the skip stays on the trace, and classification
    runs over the in-scope agents with the quote as context.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, weather, news = _agents(
        client,
        headers,
        ("Jokes", "Tell jokes on request"),
        ("Weather", "Weather forecasts"),
        ("News", "Summarise the news"),
    )
    answer = "Sunny tomorrow."
    reply_id = _agent_replies(
        client, db, channel, signer, sender, answer=answer, route_to=weather["id"]
    )
    update_my_channel(
        client, headers, channel["id"], agent_scope="list", agent_ids=[jokes["id"], news["id"]]
    )

    seen: list[tuple[list[str], object]] = []

    def _classify(candidates, _message, **kwargs):
        seen.append((sorted(c.ref_id for c in candidates), kwargs.get("quoted")))
        return classification(jokes["id"])

    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "and the day after?", quoted_message_name=reply_id, quoted_text=answer),
        classify_side_effect=_classify,
    )
    assert resp.status_code == 200

    assert len(seen) == 1, seen
    ballot, quoted = seen[0]
    assert ballot == sorted([jokes["id"], news["id"]])
    assert quoted is not None and quoted.text == answer

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["quoted_agent_id"] == weather["id"], trace
    weather_row = next(c for c in _stage(trace, "pass_1")["candidates"] if c["ref_id"] == weather["id"])
    assert weather_row["eligible"] is False, weather_row
    assert weather_row["skip_reason"] == "not_in_channel_scope", weather_row
    assert len(_sessions(client, headers, weather["id"])) == 1


# ---------------------------------------------------------------------------
# 7. The pin outranks the quote
# ---------------------------------------------------------------------------


def test_a_pin_outranks_a_quoted_reply(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, weather = _agents(
        client, headers, ("Jokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )
    answer = "Sunny tomorrow."
    reply_id = _agent_replies(
        client, db, channel, signer, sender, answer=answer, route_to=weather["id"]
    )
    saved = update_my_channel(client, headers, channel["id"], pinned_agent_id=jokes["id"])
    assert saved["pinned_agent_id"] == jokes["id"], saved

    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(sender, _thread(), "and the day after?", quoted_message_name=reply_id, quoted_text=answer),
    )
    assert resp.status_code == 200

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["match_method"] == "pinned", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert len(_sessions(client, headers, jokes["id"])) == 1
    assert len(_sessions(client, headers, weather["id"])) == 1


# ---------------------------------------------------------------------------
# 8. The identity arm, and its consent-off control
# ---------------------------------------------------------------------------


def test_quoting_an_identity_agents_reply_prefers_it_only_with_consent(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. HR shares two agents (Payroll, TimeOff) with three people and each
         turns the contact on. Two of them switch identity routing on.
      2. The first asker's question classifies in Stage 2 and Payroll answers
         on their thread.
      3. The sender (owns nothing, consent on) quotes Payroll's reply in a new
         thread. No classifier answer is named — Stage 2 would otherwise have
         to classify between two bindings — so reaching Payroll proves the
         preference. The session is in HR's workspace with the sender as the
         identity caller, the grant was re-verified (the reply is delivered to
         the sender's thread), and both stages say `quoted_reply`.
      4. Control: a third person with the same shares but consent OFF quotes
         the same reply. No preference, no `identity:` candidate, no Stage 2.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    owner, owner_headers = _developer(client, superuser_token_headers)
    payroll, timeoff = _agents(
        client,
        owner_headers,
        ("Payroll", "Answer payroll questions"),
        ("TimeOff", "Answer time-off questions"),
    )
    asker, asker_headers = create_random_user_with_headers(client)
    sender, sender_headers = create_random_user_with_headers(client)
    control, control_headers = _developer(client, superuser_token_headers)
    control_a, control_b = _agents(
        client, control_headers, ("CtlJokes", "Tell jokes on request"), ("CtlWeather", "Weather forecasts")
    )

    # ── Phase 1: the shares and the consents ──────────────────────────────
    people = [asker, sender, control]
    for agent, trigger in ((payroll, "Answer payroll questions"), (timeoff, "Answer time-off questions")):
        create_identity_binding(
            client,
            owner_headers,
            agent["id"],
            trigger_prompt=trigger,
            assigned_user_ids=[p["id"] for p in people],
        )
    for headers in (asker_headers, sender_headers, control_headers):
        toggle_identity_contact(client, headers, owner["id"], True)
    for headers in (asker_headers, sender_headers):
        row = update_my_channel(client, headers, channel["id"], allow_identity_routing=True)
        assert row["allow_identity_routing"] is True, row
    control_row = update_my_channel(client, control_headers, channel["id"])
    assert control_row["allow_identity_routing"] is False, control_row

    # ── Phase 2: Payroll answers the first asker ──────────────────────────
    asker_thread = _thread()
    answer = f"Payday is the 25th. {random_lower_string()[:6]}"
    resp, asker_chat, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(asker, asker_thread, "when is payday?"),
        stream_stub=StubAgentEnvConnector(response_text=answer),
        classify_result=classification(payroll["id"]),
    )
    assert resp.status_code == 200
    assert any(answer in t for t in asker_chat.delivered_to(asker_thread))
    reply_id = final_reply_message_id(db, channel["id"], asker_thread)
    assert len(_sessions(client, owner_headers, payroll["id"])) == 1

    # ── Phase 3: the sender quotes it — preferred, no classifier ──────────
    sender_thread = _thread()
    second_answer = "Same for you: the 25th."
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, sender_chat, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            sender,
            sender_thread,
            "is that the same for me?",
            quoted_message_name=reply_id,
            quoted_text=answer,
            quoted_sender="DoBot",
        ),
        stream_stub=StubAgentEnvConnector(response_text=second_answer),
    )
    assert resp.status_code == 200

    payroll_sessions = _sessions(client, owner_headers, payroll["id"])
    assert len(payroll_sessions) == 2, payroll_sessions
    assert _sessions(client, owner_headers, timeoff["id"]) == []
    r = client.get(f"{API}/external/sessions", headers=sender_headers)
    assert r.status_code == 200, r.text
    mine = [s for s in r.json() if s["agent_id"] == payroll["id"]]
    assert len(mine) == 1, r.json()
    assert mine[0]["identity_caller_id"] == sender["id"], mine[0]
    assert any(second_answer in t for t in sender_chat.delivered_to(sender_thread)), (
        sender_chat.send.await_args_list,
        sender_chat.replace.await_args_list,
    )

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["outcome"] == "routed", trace
    assert trace["match_method"] == "quoted_reply", trace
    assert trace["selected_agent_id"] == payroll["id"], trace
    assert trace["quoted_agent_id"] == payroll["id"], trace
    assert f"identity:{owner['id']}" in {c["ref_id"] for c in _stage(trace, "pass_1")["candidates"]}
    stage_2 = _stage(trace, "identity_stage2")
    assert stage_2 is not None, trace["stages"]
    assert stage_2["match_method"] == "quoted_reply", stage_2
    assert {c["ref_id"] for c in stage_2["candidates"]} == {payroll["id"], timeoff["id"]}
    assert stage_2.get("prompt") is None, stage_2

    # ── Phase 4: control — consent off, same shares, same quote ───────────
    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            control,
            _thread(),
            "is that the same for me?",
            quoted_message_name=reply_id,
            quoted_text=answer,
        ),
        classify_result=classification(control_a["id"]),
    )
    assert resp.status_code == 200
    control_trace = _new_trace(client, superuser_token_headers, channel, before)
    assert control_trace["match_method"] == "ai", control_trace
    assert control_trace["selected_agent_id"] == control_a["id"], control_trace
    refs = _all_refs(control_trace)
    assert refs == {control_a["id"], control_b["id"]}, refs
    assert not any(ref.startswith("identity:") for ref in refs), refs
    assert _stage(control_trace, "identity_stage2") is None, control_trace["stages"]
    assert len(_sessions(client, owner_headers, payroll["id"])) == 2


# ---------------------------------------------------------------------------
# 9. A parked message keeps its snapshot through the flush
# ---------------------------------------------------------------------------


def test_a_parked_quoted_message_keeps_its_snapshot_through_the_flush(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. A sender who owns nothing quotes a message (with a snapshot); Pass 2
         auto-installs a bundle and the message is parked behind the install.
      2. The environment comes up and the scheduler's flush (documented
         exemption) drains the parked message.
      3. The agent's context holds the snapshot, and the stored user message is
         still the sender's own words.
    """
    bundle_uuid = _publish_catalog_bundle(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    consumer, consumer_headers = make_user_and_headers(client)
    stub = StubAgentEnvConnector(response_text="Here is one.")

    # ── Phase 1: route → install → park ───────────────────────────────────
    resp, _, _ = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            consumer,
            _thread(),
            "tell me one please",
            quoted_message_name=_human_message_id(),
            quoted_text=_HUMAN_QUOTE,
            quoted_sender="Bob Human",
        ),
        stream_stub=stub,
        classify_result=classification(bundle_uuid),
    )
    assert resp.status_code == 200
    installed = next(
        a
        for a in client.get(f"{API}/agents/", headers=consumer_headers).json()["data"]
        if a["bundle_uuid"] == bundle_uuid
    )
    assert list_sessions(client, consumer_headers) == [], "parked, not delivered yet"

    # ── Phase 2: the environment is ready; the scheduler flushes ──────────
    set_environment_status(db, installed["active_environment_id"], "running")
    db.commit()
    with patched_channel_transport(chat=ChatVerbs(), stream_stub=stub):
        advanced = flush_pending_bindings(db)
        drain_tasks()
    assert advanced == 1

    # ── Phase 3: the snapshot survived the queue ──────────────────────────
    sessions = _sessions(client, consumer_headers, installed["id"])
    assert len(sessions) == 1, sessions
    session_id = sessions[0]["id"]
    assert _user_texts(client, consumer_headers, session_id) == ["tell me one please"]
    [notice] = _context_notices(client, consumer_headers, session_id)
    assert f"Bob Human [time unknown]:\n{_HUMAN_QUOTE}" in notice["content"]
    assert "text unavailable" not in notice["content"]
    sent = stub.stream_calls[-1]["payload"]["message"]
    assert _HUMAN_QUOTE in sent and sent.endswith("tell me one please"), sent


# ---------------------------------------------------------------------------
# 10. The kill switch
# ---------------------------------------------------------------------------


def test_the_kill_switch_stops_quote_routing_but_not_the_ingestion_fallback(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
    `CHANNEL_QUOTE_ROUTING_ENABLED=False`, with a quote that would otherwise
    prefer the sender's own Weather agent: the provider is called (no
    preference), the prompt has no quote section, the classifier's pick wins,
    and the trace carries no quote. The ingestion snapshot fallback is not
    governed by the switch, so the agent still sees the quoted reply —
    labelled from the ledger.
    """
    channel = _channel(client, superuser_token_headers)
    signer = GoogleChatJWTSigner()
    sender, headers = _developer(client, superuser_token_headers)
    jokes, weather = _agents(
        client, headers, ("Jokes", "Tell jokes on request"), ("Weather", "Weather forecasts")
    )
    answer = f"Sunny tomorrow. {random_lower_string()[:6]}"
    reply_id = _agent_replies(
        client, db, channel, signer, sender, answer=answer, route_to=weather["id"]
    )

    before = _trace_ids(client, superuser_token_headers, channel)
    resp, _, provider = deliver_channel_event(
        client,
        channel,
        signer,
        _event(
            sender,
            _thread(),
            "and the day after?",
            quoted_message_name=reply_id,
            quoted_text=answer,
            quoted_sender="DoBot",
        ),
        provider_reply={"agent_id": jokes["id"]},
        settings_overrides={"CHANNEL_QUOTE_ROUTING_ENABLED": False},
    )
    assert resp.status_code == 200

    prompts = rendered_prompts(provider)
    assert len(prompts) == 1, "the quoted-reply preference ran with the switch off"
    assert QUOTED_SECTION_HEADING not in prompts[0]
    assert answer not in prompts[0]

    trace = _new_trace(client, superuser_token_headers, channel, before)
    assert trace["match_method"] == "ai", trace
    assert trace["selected_agent_id"] == jokes["id"], trace
    assert trace["quoted_message_text"] is None, trace
    assert trace["quoted_message_author"] is None, trace
    assert trace["quoted_agent_id"] is None, trace

    session = _the_quoting_session(client, headers, jokes["id"])
    [notice] = _context_notices(client, headers, session["id"])
    assert f"Agent {weather['name']} on this platform [time unknown]:\n{answer}" in notice["content"]
