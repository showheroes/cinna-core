"""Guidance replies: what a sender is told when channel routing routes nowhere.

Channel routing guidance, Phase 2 (`docs/drafts/channel_routing_guidance_brief.md`,
"What the sender gets"). When the classifier answers `NONE` it now says *why* —
`help` ("what can you do?") or `none` (a real task nothing fits) — and the
router answers with a list of what the sender can already reach instead of
"contact your administrator". The classifier only picks the shape; every word
is composed by the platform from the sender's own post-policy ballot.

Scenarios, each driven through a real webhook (or poll) delivery:

  1. `help` lists the sender's own agents and the identities they may address
     — never another person's agent, an identity they cannot reach, or a
     catalog bundle — and routes nowhere (no session). Trace `guided`, debug
     feed `guided`.
  2. A single-agent sender with a catalog on offer is classified; `help` lists
     the agent only and records the unoffered bundle as `pass_1_guided`.
  3. An empty ballot lists the catalog bundles admitted for the sender, and
     never a bundle they may not install.
  4. `none` lists the sender's own ballot ahead of any catalog.
  5. Pass 1 `none` followed by an unusable Pass 2 reply is `REPLY_NO_MATCH`
     (unchanged by design).
  6. `CHANNEL_ROUTING_GUIDANCE_ENABLED=False` restores `REPLY_NO_MATCH` exactly.
  7. A classifier outage / unusable reply is `REPLY_NO_MATCH`, never guidance.
  8. `clarify` on Google Chat asks a question now (Phase 3) — that round-trip,
     and the kill switch routing the best pick instead, live in
     `server_channels_routing_clarification_test.py`.
  9. `only_one` is untouched: a meta question reaches the single agent with no
     classifier call.
  10. The trace's `guidance_kind` / `guidance_options[].ref_id` survive
      `ROUTING_TRACE_STORE_MESSAGE_TEXT=False` on both paths, and nothing the
      sender wrote does.
  11. Email receives `help` / `none` as plain mail (no markdown), and a
      `clarify` answer routes the best pick — email is never asked a question.

`REPLY_NO_MATCH` and `IDENTITY_DESCRIPTION` are imported from the service
modules that own them, as `server_channels_status_notice_test.py` already does
for the `REPLY_*` constants: the property is the exact text a sender reads.

The composer's pure half (each shape pinned whole, clamping, escaping, plain
mode) is `tests/unit/test_channel_routing_guidance.py`; `classify_answer`'s
intent on every unusable path is in `tests/unit/test_agent_classifier_parsing.py`;
simulate's `guidance_reply` is `tests/api/routing/routing_simulate_guidance_reply_test.py`.
"""
import json
from contextlib import ExitStack
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.services.server_channels.channel_inbound_service import REPLY_NO_MATCH
from app.services.server_channels.channel_routing_guidance import IDENTITY_DESCRIPTION
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.stubs.email_stubs import StubIMAPConnector
from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.bundle import (
    make_user_and_headers,
    publish_bundle,
    publish_bundle_and_make_public,
)
from tests.utils.email_channel import (
    IMAP_CONNECTOR_TARGET,
    build_raw_email,
    create_email_channel,
    poll_channel,
)
from tests.utils.identity import share_identity_agent
from tests.utils.mail_server import create_imap_server, create_smtp_server
from tests.utils.routing import (
    classification,
    classifier_answer,
    enter_classifier_patch,
    get_routing_trace,
    list_routing_traces,
    post_channel_message,
    unusable_classifier_reply,
)
from tests.utils.server_channel import (
    GoogleChatJWTSigner,
    add_auto_install_bundle,
    build_message_event,
    create_server_channel,
    get_routing_clarification,
    list_debug_events,
)
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.user_channel import update_my_channel
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR
_GUIDANCE_SETTING = "app.core.config.settings.CHANNEL_ROUTING_GUIDANCE_ENABLED"
_STORE_TEXT_SETTING = "app.core.config.settings.ROUTING_TRACE_STORE_MESSAGE_TEXT"
_PROVIDER_TARGET = "app.services.routing.agent_classifier.get_provider_manager"
_STREAM_TARGET = "app.services.sessions.message_service.agent_env_connector"
_EMAIL_SEND_TARGET = (
    "app.services.server_channels.adapters.email.EmailChannelAdapter.send_message"
)
_MAILBOX = "support@corp.example"

HELP_HEAD = "Here's who I can hand your message to:"
HELP_TAIL = "Just describe what you need and I'll pick the right one."
HELP_SETUP_HEAD = "I don't have an assistant set up for you here yet. I can set one up:"
NONE_HEAD = "I couldn't find an assistant for that. I can hand your message to:"
NONE_SETUP_HEAD = "I couldn't find an assistant for that. I can set one of these up for you:"
NONE_TAIL = "Rephrase your message, or name the one you mean."
_GUIDANCE_HEADS = (HELP_HEAD, HELP_SETUP_HEAD, NONE_HEAD, NONE_SETUP_HEAD)
_CLARIFY_QUESTION = "Reply with the number or the name"


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def _developer(client, superuser_headers) -> tuple[dict, dict]:
    user, headers = create_random_user_with_headers(client)
    promote_to_developer(client, superuser_headers, user["id"])
    create_random_ai_credential(client, headers, set_default=True)
    return user, headers


def _agent(client, headers, prefix: str, trigger: str) -> dict:
    agent = create_agent_via_api(client, headers, name=f"{prefix}-{random_lower_string()[:6]}")
    drain_tasks()
    set_router_trigger_prompt(client, headers, agent["id"], trigger)
    return agent


def _sender_with_two_agents(client, superuser_headers):
    """Two eligible agents: Pass 1 always classifies."""
    sender, headers = _developer(client, superuser_headers)
    joker = _agent(client, headers, "Joker", "Tells jokes and light banter")
    hr = _agent(client, headers, "HRHelper", "Leave, payroll and policy questions")
    return sender, headers, joker, hr


def _catalog_bundle(client, superuser_headers, *, public: bool = True) -> str:
    """A bundle on the auto-install list; `public=False` is one the sender may
    not install (`CatalogService.user_can_install` refuses it)."""
    publisher, publisher_headers = make_user_and_headers(client)
    promote_to_developer(client, superuser_headers, publisher["id"])
    agent = create_agent_via_api(
        client, publisher_headers, name=f"Bundle-{random_lower_string()[:6]}"
    )
    drain_tasks()
    r = client.patch(
        f"{API}/agents/{agent['id']}/router-trigger-prompt",
        headers=publisher_headers,
        json={"router_trigger_prompt": "Handle support desk tickets"},
    )
    assert r.status_code == 200, r.text
    if public:
        publish_bundle_and_make_public(client, publisher_headers, agent["id"])
        bundle_uuid = client.get(
            f"{API}/agents/{agent['id']}", headers=publisher_headers
        ).json()["bundle_uuid"]
    else:
        bundle_uuid = publish_bundle(client, publisher_headers, agent["id"])["bundle_uuid"]
    add_auto_install_bundle(client, superuser_headers, bundle_uuid)
    return bundle_uuid


def _channel(client, superuser_headers) -> dict:
    # No outbound secrets, so there is no status notice to settle: every
    # pipeline reply is a `send_message` call the helper's mock records.
    return create_server_channel(
        client, superuser_headers, auto_register_users=False, email_whitelist="*"
    )


def _deliver(client, channel, sender_email: str, text: str = "what can you do?", **classifier) -> list[str]:
    """One webhook delivery; returns every text the pipeline sent the thread."""
    event = build_message_event(
        thread_key=f"spaces/AAA/threads/{random_lower_string()}",
        text=text,
        sender_email=sender_email,
    )
    resp, send_mock = post_channel_message(
        client, channel, GoogleChatJWTSigner(), event, **classifier
    )
    assert resp.status_code == 200, resp.text
    return [c.args[-1] or "" for c in send_mock.await_args_list]


def _answers(calls: list, *answers):
    """A classifier side effect that records each ballot and answers in turn."""
    remaining = list(answers)

    def _classify(candidates, message, **kwargs):
        calls.append([c.ref_id for c in candidates])
        return remaining.pop(0) if len(remaining) > 1 else remaining[0]

    return _classify


def _guidance(texts: list[str]) -> list[str]:
    return [t for t in texts if t.startswith(_GUIDANCE_HEADS)]


def _only_trace(client, superuser_headers, channel) -> dict:
    page = list_routing_traces(client, superuser_headers, channel_id=channel["id"])
    assert page["count"] == 1, page["data"]
    return get_routing_trace(client, superuser_headers, page["data"][0]["id"])


def _stage(detail: dict, name: str) -> dict:
    stage = next((s for s in detail["stages"] if s["stage"] == name), None)
    assert stage is not None, [s["stage"] for s in detail["stages"]]
    return stage


def _option_ids(stage: dict) -> set[str]:
    return {o["ref_id"] for o in stage.get("guidance_options") or []}


# ---------------------------------------------------------------------------
# 1–2. `help` lists what the sender can already reach, and nothing else
# ---------------------------------------------------------------------------


def test_help_lists_the_senders_own_agents_and_reachable_identities_only(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """
      1. The sender owns two agents and may address one identity owner (Anna,
         no full name, so her display name is an email address).
      2. Around them: Bob assigned the sender a binding but it was never
         enabled (unreachable), Carol owns an agent she never shared, and a
         public catalog bundle is on the auto-install list.
      3. "what can you do?" is classified `help` over the sender's ballot.
      4. The reply lists exactly the two agents and Anna — by local part, with
         the fixed identity description — and routes nowhere.
      5. Trace `guided` with the listed ids; debug feed `guided`, not `no_match`.
    """
    sender, sender_headers, joker, hr = _sender_with_two_agents(client, superuser_token_headers)

    anna, anna_headers = _developer(client, superuser_token_headers)
    anna_agent = _agent(client, anna_headers, "AnnaAgent", "Anna's own work")
    share_identity_agent(
        client, anna_headers, sender_headers,
        agent_id=anna_agent["id"], target_user_id=sender["id"], owner_id=anna["id"],
    )
    bob, bob_headers = _developer(client, superuser_token_headers)
    bob_agent = _agent(client, bob_headers, "BobAgent", "Bob's own work")
    share_identity_agent(
        client, bob_headers, sender_headers,
        agent_id=bob_agent["id"], target_user_id=sender["id"], owner_id=bob["id"],
        enable=False,
    )
    carol, carol_headers = _developer(client, superuser_token_headers)
    carol_agent = _agent(client, carol_headers, "CarolAgent", "Carol's private work")
    bundle_uuid = _catalog_bundle(client, superuser_token_headers)

    channel = _channel(client, superuser_token_headers)
    update_my_channel(client, sender_headers, channel["id"], allow_identity_routing=True)
    anna_ref = f"identity:{anna['id']}"
    expected_ids = {joker["id"], hr["id"], anna_ref}

    # ── Phase 1: one classification, over the sender's own ballot ─────────
    calls: list = []
    texts = _deliver(
        client, channel, sender["email"],
        classify_side_effect=_answers(calls, classifier_answer(intent="help")),
    )
    assert len(calls) == 1, calls  # `help` ends at Pass 1: the catalog is never asked
    assert set(calls[0]) == expected_ids, calls

    # ── Phase 2: the reply ────────────────────────────────────────────────
    replies = _guidance(texts)
    assert len(replies) == 1, texts
    lines = replies[0].splitlines()
    assert lines[0] == HELP_HEAD
    assert lines[-1] == HELP_TAIL
    assert sorted(lines[1:-1]) == sorted(
        [
            f"- **{joker['name']}** — Tells jokes and light banter",
            f"- **{hr['name']}** — Leave, payroll and policy questions",
            f"- **{anna['email'].split('@')[0]}** — {IDENTITY_DESCRIPTION}",
        ]
    ), lines
    for absent in (
        anna["email"],
        bob["email"].split("@")[0],
        bob_agent["name"],
        anna_agent["name"],
        carol_agent["name"],
    ):
        assert absent not in replies[0], (absent, replies[0])
    assert REPLY_NO_MATCH not in texts, texts
    # Routed nowhere.
    assert list_sessions(client, sender_headers) == []

    # ── Phase 3: the trace ───────────────────────────────────────────────
    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "guided", detail
    assert detail["selected_agent_id"] is None, detail
    pass1 = _stage(detail, "pass_1")
    assert pass1["guidance_kind"] == "help", pass1
    assert _option_ids(pass1) == expected_ids, pass1
    assert bundle_uuid not in json.dumps(detail["stages"])

    # ── Phase 4: the debug feed ──────────────────────────────────────────
    events = list_debug_events(client, superuser_token_headers, channel["id"])["events"]
    guided = [e for e in events if e["kind"] == "guided"]
    assert len(guided) == 1, [e["kind"] for e in events]
    assert guided[0]["detail"]["guidance"] == "help", guided[0]
    assert guided[0]["detail"]["pass"] == "1", guided[0]
    assert not any(e["kind"] == "no_match" for e in events), [e["kind"] for e in events]


def test_a_single_agent_sender_with_a_catalog_on_offer_gets_help_about_their_agent(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """One eligible agent plus an installable bundle is not `only_one`: the
    classifier runs. Its `help` lists the agent, not the bundle, and the bundle
    it was never offered is recorded as `pass_1_guided` — not as "Pass 1
    matched first", which would claim a match that did not happen."""
    sender, headers = _developer(client, superuser_token_headers)
    agent = _agent(client, headers, "Solo", "Handles anything I send")
    bundle_uuid = _catalog_bundle(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)

    calls: list = []
    texts = _deliver(
        client, channel, sender["email"],
        classify_side_effect=_answers(calls, classifier_answer(intent="help")),
    )

    assert calls == [[agent["id"]]], calls
    replies = _guidance(texts)
    assert len(replies) == 1, texts
    assert replies[0].splitlines() == [
        HELP_HEAD,
        f"- **{agent['name']}** — Handles anything I send",
        HELP_TAIL,
    ]
    assert list_sessions(client, headers) == []

    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "guided", detail
    assert _option_ids(_stage(detail, "pass_1")) == {agent["id"]}
    bundle_rows = [
        c for c in _stage(detail, "pass_2")["candidates"] if c["ref_id"] == bundle_uuid
    ]
    assert len(bundle_rows) == 1, _stage(detail, "pass_2")
    assert bundle_rows[0]["skip_reason"] == "pass_1_guided", bundle_rows[0]


# ---------------------------------------------------------------------------
# 3–4. Which list: the sender's own ballot first, else the admitted catalog
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "intent,head,tail",
    [
        ("help", HELP_SETUP_HEAD, "Describe what you need and I'll set it up."),
        ("none", NONE_SETUP_HEAD, NONE_TAIL),
    ],
)
def test_an_empty_ballot_lists_only_the_catalog_bundles_admitted_for_the_sender(
    client: TestClient, superuser_token_headers: dict[str, str], intent, head, tail
) -> None:
    sender, headers = create_random_user_with_headers(client)
    public_uuid = _catalog_bundle(client, superuser_token_headers)
    private_uuid = _catalog_bundle(client, superuser_token_headers, public=False)
    channel = _channel(client, superuser_token_headers)

    calls: list = []
    texts = _deliver(
        client, channel, sender["email"], text="please help",
        classify_side_effect=_answers(calls, classifier_answer(intent=intent)),
    )

    # Pass 1's ballot is empty (no model); Pass 2 classifies the admitted bundle.
    assert calls == [[public_uuid]], calls

    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "guided", detail  # not parked: nothing installed
    assert detail["selected_bundle_uuid"] is None, detail
    names = {c["ref_id"]: c["name"] for c in _stage(detail, "pass_2")["candidates"]}
    assert _option_ids(_stage(detail, "pass_2")) == {public_uuid}

    replies = _guidance(texts)
    assert len(replies) == 1, texts
    assert replies[0].splitlines() == [
        head,
        f"- **{names[public_uuid]}** — Handle support desk tickets",
        tail,
    ]
    assert names[private_uuid] not in replies[0]
    assert list_sessions(client, headers) == []


@pytest.mark.parametrize("with_catalog", [False, True], ids=["no_catalog", "catalog"])
def test_none_lists_the_senders_own_ballot_ahead_of_any_catalog(
    client: TestClient, superuser_token_headers: dict[str, str], with_catalog: bool
) -> None:
    """`none` at Pass 1 lets Pass 2 run; when Pass 2 finds nothing either, the
    sender's own agents are listed, never the catalog in their place."""
    sender, headers, joker, hr = _sender_with_two_agents(client, superuser_token_headers)
    bundle_uuid = _catalog_bundle(client, superuser_token_headers) if with_catalog else None
    channel = _channel(client, superuser_token_headers)

    calls: list = []
    texts = _deliver(
        client, channel, sender["email"], text="book me a flight",
        classify_side_effect=_answers(calls, classifier_answer(intent="none")),
    )

    assert len(calls) == (2 if with_catalog else 1), calls
    replies = _guidance(texts)
    assert len(replies) == 1, texts
    lines = replies[0].splitlines()
    assert (lines[0], lines[-1]) == (NONE_HEAD, NONE_TAIL)
    assert sorted(lines[1:-1]) == sorted(
        [
            f"- **{joker['name']}** — Tells jokes and light banter",
            f"- **{hr['name']}** — Leave, payroll and policy questions",
        ]
    )
    assert REPLY_NO_MATCH not in texts

    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "guided", detail
    pass1 = _stage(detail, "pass_1")
    assert pass1["guidance_kind"] == "none", pass1
    assert _option_ids(pass1) == {joker["id"], hr["id"]}
    if bundle_uuid is not None:
        assert bundle_uuid not in _option_ids(_stage(detail, "pass_2"))
    assert list_sessions(client, headers) == []


def test_pass1_none_then_an_unusable_pass2_reply_is_the_no_match_reply(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Unchanged by design: both passes must have answered for guidance."""
    sender, _, _, _ = _sender_with_two_agents(client, superuser_token_headers)
    _catalog_bundle(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)

    calls: list = []
    texts = _deliver(
        client, channel, sender["email"], text="book me a flight",
        classify_side_effect=_answers(
            calls, classifier_answer(intent="none"), unusable_classifier_reply()
        ),
    )

    assert len(calls) == 2, calls
    assert REPLY_NO_MATCH in texts, texts
    assert _guidance(texts) == [], texts
    assert _only_trace(client, superuser_token_headers, channel)["outcome"] == "no_match"


# ---------------------------------------------------------------------------
# 5–6. The kill switch, and an unusable reply
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("intent", ["help", "none"])
def test_guidance_switched_off_restores_the_no_match_reply_exactly(
    client: TestClient, superuser_token_headers: dict[str, str], intent: str
) -> None:
    sender, _, _, _ = _sender_with_two_agents(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)

    with patch(_GUIDANCE_SETTING, False):
        texts = _deliver(
            client, channel, sender["email"], classify_result=classifier_answer(intent=intent)
        )

    # The routing notice is posted first (no status notice to rewrite on this
    # channel); the answer is the no-match sentence, once, and nothing else.
    assert texts[-1] == REPLY_NO_MATCH, texts
    assert texts.count(REPLY_NO_MATCH) == 1, texts
    assert _guidance(texts) == [], texts
    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "no_match", detail
    pass1 = _stage(detail, "pass_1")
    assert pass1.get("guidance_kind") is None, pass1
    assert _option_ids(pass1) == set()
    kinds = [e["kind"] for e in list_debug_events(client, superuser_token_headers, channel["id"])["events"]]
    assert "no_match" in kinds and "guided" not in kinds, kinds


def test_an_unusable_classifier_reply_is_the_no_match_reply_not_guidance(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """An outage, non-JSON or malformed reply carries no intent: it must never
    be read as the model saying "nothing fits"."""
    sender, _, _, _ = _sender_with_two_agents(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)

    texts = _deliver(client, channel, sender["email"], classify_unusable=True)

    assert REPLY_NO_MATCH in texts, texts
    assert _guidance(texts) == [], texts
    detail = _only_trace(client, superuser_token_headers, channel)
    assert detail["outcome"] == "no_match", detail
    assert _stage(detail, "pass_1").get("guidance_kind") is None


# ---------------------------------------------------------------------------
# 7–8. What stays routed
# ---------------------------------------------------------------------------


# A `clarify` answer on Google Chat asks a question since Phase 3: the
# round-trip, the kill switch and the no-outbound-credentials channel that
# still route the best pick are in `server_channels_routing_clarification_test.py`.


def test_only_one_still_hands_a_meta_question_to_the_single_agent_without_a_model(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """No classifier answer is named, so reaching one fails at the call."""
    sender, headers = _developer(client, superuser_token_headers)
    agent = _agent(client, headers, "Solo", "Handles anything I send")
    channel = _channel(client, superuser_token_headers)

    texts = _deliver(client, channel, sender["email"], text="what can you do?")

    assert _guidance(texts) == [], texts
    assert [s["agent_id"] for s in list_sessions(client, headers)] == [agent["id"]]
    detail = _only_trace(client, superuser_token_headers, channel)
    assert (detail["outcome"], detail["match_method"]) == ("routed", "only_one"), detail


# ---------------------------------------------------------------------------
# 9. The trace fields ride the message-text allowlist
# ---------------------------------------------------------------------------


def test_guidance_trace_fields_survive_the_message_text_gate_and_sender_text_does_not(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> None:
    """Real parse (provider mocked at classifier depth), so the stage genuinely
    holds the sender's words in `raw_response` before the gate acts.

      0. Captured and read with text storage ON: the words are there.
      1. Read path — the same row read OFF: `guidance_kind` and the option ids
         served, the words not.
      2. Write path — captured OFF, read ON: both fields stored, the words not.
    """
    sender, _, joker, hr = _sender_with_two_agents(client, superuser_token_headers)
    channel = _channel(client, superuser_token_headers)
    expected = {joker["id"], hr["id"]}

    def _post(store_text: bool) -> tuple[str, str]:
        words = f"what can you actually do {random_lower_string()}"
        before = {
            r["id"]
            for r in list_routing_traces(
                client, superuser_token_headers, channel_id=channel["id"]
            )["data"]
        }
        reply = MagicMock(
            text=json.dumps(
                {"agent_id": "NONE", "intent": "help", "reason": f"the sender asked {words}"}
            )
        )
        with patch(_STORE_TEXT_SETTING, store_text), patch(_PROVIDER_TARGET) as pm:
            pm.return_value.generate_content.return_value = reply
            texts = _deliver(client, channel, sender["email"], text=words, classify_via_provider=True)
            assert pm.return_value.generate_content.call_count == 1
        assert len(_guidance(texts)) == 1, texts
        new = [
            r["id"]
            for r in list_routing_traces(
                client, superuser_token_headers, channel_id=channel["id"]
            )["data"]
            if r["id"] not in before
        ]
        assert len(new) == 1, new
        return new[0], words

    def _read(trace_id: str, store_text: bool) -> dict:
        with patch(_STORE_TEXT_SETTING, store_text):
            return get_routing_trace(client, superuser_token_headers, trace_id)

    # ── 0. Baseline ──────────────────────────────────────────────────────
    on_id, on_words = _post(store_text=True)
    stage_on = _stage(_read(on_id, True), "pass_1")
    assert stage_on["guidance_kind"] == "help", stage_on
    assert _option_ids(stage_on) == expected
    assert stage_on["intent"] == "help", stage_on
    assert on_words in (stage_on["raw_response"] or ""), stage_on

    # ── 1. Read path ─────────────────────────────────────────────────────
    detail_off = _read(on_id, False)
    stage_off = _stage(detail_off, "pass_1")
    assert stage_off.get("guidance_kind") == "help", stage_off
    assert _option_ids(stage_off) == expected
    assert on_words not in json.dumps(detail_off["stages"])
    assert detail_off["message_text"] is None

    # ── 2. Write path ────────────────────────────────────────────────────
    off_id, off_words = _post(store_text=False)
    detail_written_off = _read(off_id, True)
    stage_written_off = _stage(detail_written_off, "pass_1")
    assert stage_written_off.get("guidance_kind") == "help", stage_written_off
    assert _option_ids(stage_written_off) == expected
    assert off_words not in json.dumps(detail_written_off["stages"])


# ---------------------------------------------------------------------------
# 10. Email: plain mail for help / none, and never a question
# ---------------------------------------------------------------------------


def _email_channel(client, superuser_headers) -> dict:
    imap = create_imap_server(client, superuser_headers)
    smtp = create_smtp_server(client, superuser_headers)
    return create_email_channel(
        client,
        superuser_headers,
        incoming_server_id=imap["id"],
        outgoing_server_id=smtp["id"],
        incoming_mailbox=_MAILBOX,
        email_whitelist="*",
    )


def _poll(db: Session, sender_email: str, answer) -> list[str]:
    """One poll tick carrying one mail; returns every text queued as a reply."""
    raw = build_raw_email(
        message_id=f"<{random_lower_string()}@sender.example>",
        sender=sender_email,
        to=_MAILBOX,
        subject="Hello",
        body="what can you do?",
    )
    send = AsyncMock(return_value=None)
    with ExitStack() as stack:
        stack.enter_context(patch(IMAP_CONNECTOR_TARGET, StubIMAPConnector(emails=[raw])))
        stack.enter_context(patch(_STREAM_TARGET, StubAgentEnvConnector(response_text="Happy to help.")))
        stack.enter_context(patch(_EMAIL_SEND_TARGET, send))
        enter_classifier_patch(stack, classify_result=answer)
        assert poll_channel(db) == 1
        drain_tasks()
    return [c.args[-1] or "" for c in send.await_args_list]


@pytest.mark.parametrize(
    "intent,head,tail",
    [("help", HELP_HEAD, HELP_TAIL), ("none", NONE_HEAD, NONE_TAIL)],
)
def test_email_receives_help_and_none_as_plain_mail(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session, intent, head, tail
) -> None:
    channel = _email_channel(client, superuser_token_headers)
    sender, headers, joker, hr = _sender_with_two_agents(client, superuser_token_headers)

    texts = _poll(db, sender["email"], classifier_answer(intent=intent))

    replies = _guidance(texts)
    assert len(replies) == 1, texts
    lines = replies[0].splitlines()
    assert (lines[0], lines[-1]) == (head, tail)
    assert sorted(lines[1:-1]) == sorted(
        [
            f"- {joker['name']} — Tells jokes and light banter",
            f"- {hr['name']} — Leave, payroll and policy questions",
        ]
    ), lines
    assert "**" not in replies[0]
    assert REPLY_NO_MATCH not in texts
    assert list_sessions(client, headers) == []
    detail = _only_trace(client, superuser_token_headers, channel)
    assert (detail["origin"], detail["outcome"]) == ("email", "guided"), detail


def test_email_is_never_asked_a_question_clarify_routes_the_best_pick(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    channel = _email_channel(client, superuser_token_headers)
    sender, headers, joker, hr = _sender_with_two_agents(client, superuser_token_headers)
    answer = classifier_answer(
        intent="clarify",
        result=classification(joker["id"], intent="clarify", options=(joker["id"], hr["id"])),
    )

    texts = _poll(db, sender["email"], answer)

    assert not any(_CLARIFY_QUESTION in t for t in texts), texts
    assert _guidance(texts) == [], texts
    assert [s["agent_id"] for s in list_sessions(client, headers)] == [joker["id"]]
    detail = _only_trace(client, superuser_token_headers, channel)
    assert (detail["outcome"], detail["selected_agent_id"]) == ("routed", joker["id"]), detail
    # No question state either: nothing could ever answer it.
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None
