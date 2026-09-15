"""Clarification round-trip: the router asks, the sender answers, the ORIGINAL routes.

Channel routing guidance, Phase 3 (`docs/drafts/channel_routing_guidance_brief.md`,
"The clarification round-trip"). When the classifier answers `clarify` where
the question can be followed up — guidance on, a transport with a status notice
(Google Chat) and outbound credentials to rewrite it with — the router settles
its notice into a numbered question and stores the options with the original
message in `channel_routing_clarification`. The sender's next unbound message in
that scope is read as the answer: `resolve_choice` first; a short unread reply
gets one classifier call over the options; anything longer is a new request. A
pick routes the ORIGINAL message (text and files) under
`match_method="clarified"`.

Scenarios, each driven through real webhook deliveries:

  1–2. The question (notice settled into it, trace `guided`, no session, row
       written), then "2" ingests the original text and file into the second
       option's agent and never "2" itself; the follow-up trace is `clarified`;
       the row is gone.
  3. A name reply resolves without a model and is not ingested. A short
     free-text reply is read by the classifier over the options with the
     original as quoted context, and is then delivered after the original.
  4. A short reply the classifier matches to no option routes as a new request;
     a long reply routes fresh with no classifier call over the options;
     "No, thanks!" answers `REPLY_CLARIFY_CANCELLED` and ingests nothing; a
     classifier-read reply that loses to a plain choice is `already_answered`
     and dropped, whether the read named an option or none.
  5. An expired question is dropped lazily; the flush tick purges expired rows
     and only those.
  6. A second asker in the same thread is unaffected.
  7. An identity option goes through Stage 2 into the owner's workspace; a
     bundle option parks an install of that bundle.
  8. An option policy no longer admits is never routed to — the original
     classifies over the current ballot, and a `clarify` answer routes its
     best pick instead of asking a second question.
  9. A redelivered answer is not ingested again; a redelivered original while
     the question is open is acknowledged and ignored.
  10. `CHANNEL_ROUTING_GUIDANCE_ENABLED=False` asks nothing and ignores a
      question already open; a Google Chat channel with no outbound credentials
      is never asked. Email's half is
      `server_channels_routing_guidance_test.py::test_email_is_never_asked_a_question_clarify_routes_the_best_pick`.
  11. With `ROUTING_TRACE_STORE_MESSAGE_TEXT=False` neither the question's
      trace nor the follow-up's carries the sender's words.

The open question has no read API (pipeline state, like a binding), so it is
read through `tests/utils/server_channel.py::get_routing_clarification` and aged
through `expire_routing_clarification` — both documented Rule-1 exemptions.
`REPLY_*` constants are imported from the service that owns them, as the other
files in this domain do: the property is the exact text a sender reads.

`resolve_choice` and `is_selector_like` are unit-tested in
`tests/unit/test_channel_routing_resolve_choice.py`.
"""
import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from app.services.server_channels.channel_inbound_service import (
    REPLY_CLARIFY_CANCELLED,
    REPLY_STILL_SETTING_UP,
)
from app.services.server_channels.channel_routing_guidance import IDENTITY_DESCRIPTION
from tests.stubs.agent_env_stub import StubAgentEnvConnector
from tests.utils.agent import create_agent_via_api, set_router_trigger_prompt
from tests.utils.ai_credential import create_random_ai_credential
from tests.utils.background_tasks import drain_tasks
from tests.utils.bundle import make_user_and_headers, publish_bundle_and_make_public
from tests.utils.channel_quote import (
    CHANNEL_SECRETS,
    ChatVerbs,
    deliver_channel_event,
    patched_channel_transport,
)
from tests.utils.environment import set_environment_status
from tests.utils.identity import share_identity_agent
from tests.utils.message import list_messages
from tests.utils.routing import (
    classification,
    classifier_answer,
    enter_classifier_patch,
    get_routing_trace,
    list_routing_traces,
)
from tests.utils.server_channel import (
    GoogleChatJWTSigner,
    add_auto_install_bundle,
    build_message_attachment,
    build_message_event,
    create_server_channel,
    expire_routing_clarification,
    flush_pending_bindings,
    get_routing_clarification,
    list_debug_events,
    post_webhook,
)
from tests.utils.session import list_sessions
from tests.utils.user import create_random_user_with_headers, promote_to_developer
from tests.utils.user_channel import update_my_channel
from tests.utils.utils import random_lower_string

API = settings.API_V1_STR
_FETCH_TARGET = (
    "app.services.server_channels.adapters.google_chat.GoogleChatAdapter.fetch_attachment"
)
_PDF = b"%PDF-1.4 contract draft"
_SIGNER = GoogleChatJWTSigner()
_GUIDANCE_OFF = {"CHANNEL_ROUTING_GUIDANCE_ENABLED": False}

QUESTION_HEAD = "That could go to two different assistants:"
QUESTION_TAIL = (
    "Reply with the number or the name. Anything else and I'll treat it as a new request."
)
JOKER_TRIGGER = "Tells jokes and light banter"
HR_TRIGGER = "Leave, payroll and policy questions"
NONE_HEAD = "I couldn't find an assistant for that. I can hand your message to:"


@pytest.fixture(autouse=True)
def _upload_root(tmp_path):
    """Attachment bytes are materialised to disk; give them a tmp root."""
    with patch.object(settings, "UPLOAD_BASE_PATH", str(tmp_path / "uploads")):
        yield


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
    joker = _agent(client, headers, "Joker", JOKER_TRIGGER)
    hr = _agent(client, headers, "HRHelper", HR_TRIGGER)
    return sender, headers, joker, hr


def _catalog_bundle(client, superuser_headers, trigger: str) -> str:
    """A public bundle on the auto-install list. Returns its ballot ref."""
    publisher, publisher_headers = make_user_and_headers(client)
    promote_to_developer(client, superuser_headers, publisher["id"])
    agent = create_agent_via_api(
        client, publisher_headers, name=f"Bundle-{random_lower_string()[:6]}"
    )
    drain_tasks()
    r = client.patch(
        f"{API}/agents/{agent['id']}/router-trigger-prompt",
        headers=publisher_headers,
        json={"router_trigger_prompt": trigger},
    )
    assert r.status_code == 200, r.text
    publish_bundle_and_make_public(client, publisher_headers, agent["id"])
    bundle_uuid = client.get(
        f"{API}/agents/{agent['id']}", headers=publisher_headers
    ).json()["bundle_uuid"]
    add_auto_install_bundle(client, superuser_headers, bundle_uuid)
    return bundle_uuid


def _channel(client, superuser_headers, *, outbound: bool = True) -> dict:
    """A Google Chat channel; with outbound credentials a question can be asked."""
    return create_server_channel(
        client,
        superuser_headers,
        auto_register_users=False,
        email_whitelist="*",
        secrets=CHANNEL_SECRETS if outbound else None,
    )


def _thread() -> str:
    return f"spaces/AAA/threads/{random_lower_string()}"


def _message_name() -> str:
    return f"spaces/AAA/messages/{random_lower_string()}"


def _clarify(best: str, *tied: str):
    return classifier_answer(
        intent="clarify",
        result=classification(best, intent="clarify", options=(best, *tied)),
    )


def _route(ref_id: str):
    return classifier_answer(intent="route", result=classification(ref_id))


class _Script:
    """A classifier side effect: records each call, answers in order.

    An unexpected extra call gets an unusable reply rather than raising (the
    router swallows exceptions), and the caller's `len(calls)` assertion is
    what fails.
    """

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []

    def __call__(self, candidates, message, **kwargs):
        quoted = kwargs.get("quoted")
        self.calls.append(
            {
                "refs": [c.ref_id for c in candidates],
                "message": message,
                "quoted": getattr(quoted, "text", None),
            }
        )
        return self.answers.pop(0) if self.answers else classifier_answer()


def _send(
    client,
    channel,
    sender_email: str,
    text: str,
    *,
    thread_key: str,
    message_name: str | None = None,
    attachments: list[dict] | None = None,
    answer=None,
    script: _Script | None = None,
    provider_reply: dict | None = None,
    settings_overrides: dict | None = None,
):
    """One verified delivery, drained. Returns ``(resp, chat)``.

    Naming no ``answer`` / ``script`` / ``provider_reply`` installs the
    refusal stub: the delivery must not classify.
    """
    event = build_message_event(
        thread_key=thread_key,
        text=text,
        sender_email=sender_email,
        message_name=message_name,
        attachments=attachments,
    )
    with patch(_FETCH_TARGET, AsyncMock(return_value=_PDF)):
        resp, chat, _ = deliver_channel_event(
            client,
            channel,
            _SIGNER,
            event,
            stream_stub=StubAgentEnvConnector(response_text="ok"),
            classify_result=answer,
            classify_side_effect=script,
            provider_reply=provider_reply,
            settings_overrides=settings_overrides,
        )
    assert resp.status_code == 200, resp.text
    return resp, chat


def _shown(chat: ChatVerbs) -> list[str]:
    """Every text the thread was shown: posted, patched or replaced."""
    return [
        call.args[-1] or ""
        for mock in (chat.send, chat.update, chat.replace)
        for call in mock.await_args_list
    ]


def _questions(texts: list[str]) -> list[str]:
    return [t for t in texts if t.startswith(QUESTION_HEAD)]


def _ask(client, channel, sender, *options: str, thread_key: str, text: str, **kwargs) -> str:
    """Deliver ``text`` answered `clarify(*options)`; returns the one question."""
    _, chat = _send(
        client, channel, sender["email"], text, thread_key=thread_key,
        answer=_clarify(*options), **kwargs,
    )
    questions = _questions(_shown(chat))
    assert len(questions) == 1, _shown(chat)
    return questions[0]


def _ingested(client, headers, agent_id: str) -> list[str]:
    """The user messages on ``agent_id``'s one session, in order ([] if none)."""
    sessions = [s for s in list_sessions(client, headers) if s["agent_id"] == agent_id]
    assert len(sessions) <= 1, sessions
    if not sessions:
        return []
    return [
        m["content"]
        for m in list_messages(client, headers, sessions[0]["id"])
        if m["role"] == "user"
    ]


def _all_ingested(client, headers) -> list[str]:
    return [
        m["content"]
        for s in list_sessions(client, headers)
        for m in list_messages(client, headers, s["id"])
        if m["role"] == "user"
    ]


def _trace_ids(client, superuser_headers, channel) -> set[str]:
    page = list_routing_traces(client, superuser_headers, channel_id=channel["id"])
    return {r["id"] for r in page["data"]}


def _new_trace(client, superuser_headers, channel, before: set[str]) -> dict:
    new = _trace_ids(client, superuser_headers, channel) - before
    assert len(new) == 1, new
    return get_routing_trace(client, superuser_headers, new.pop())


def _stage(detail: dict, name: str) -> dict:
    stage = next((s for s in detail["stages"] if s["stage"] == name), None)
    assert stage is not None, [s["stage"] for s in detail["stages"]]
    return stage


def _option_ids(stage: dict) -> set[str]:
    return {o["ref_id"] for o in stage.get("guidance_options") or []}


def _answer_events(client, superuser_headers, channel) -> list[tuple]:
    events = list_debug_events(client, superuser_headers, channel["id"])["events"]
    return [
        (e["kind"], e["detail"].get("resolution"), e["detail"].get("option"))
        for e in events
        if (e.get("detail") or {}).get("stage") == "clarification_answer"
    ]


# ---------------------------------------------------------------------------
# 1–2. The question, then "2"
# ---------------------------------------------------------------------------


def test_the_question_then_2_routes_the_original_text_and_file_to_the_second_option(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. The sender owns Joker and HRHelper; "please check this contract" with a
         PDF is answered `clarify` (Joker best, HRHelper tied).
      2. The status notice is posted once and settled into the numbered
         question; nothing routes: no session, trace `guided` /
         `guidance_kind="clarify"`, debug feed `guided`.
      3. The question is stored: both options in order, the original text, its
         one file, the notice id.
      4. "2" arrives in the same thread and no model runs. The ORIGINAL text and
         PDF are ingested into HRHelper's session; "2" is ingested nowhere.
      5. The follow-up trace routes HRHelper with `match_method="clarified"`,
         the debug feed records option 2, and the question is gone.
    """
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"please check this contract {random_lower_string()[:8]}"

    # ── Phase 1: the question ────────────────────────────────────────────
    before = _trace_ids(client, su, channel)
    resp, chat = _send(
        client, channel, sender["email"], original, thread_key=thread_key,
        attachments=[
            build_message_attachment(content_name="contract.pdf", content_type="application/pdf")
        ],
        answer=_clarify(joker["id"], hr["id"]),
    )
    assert resp.json() == {}, resp.json()
    questions = _questions(_shown(chat))
    assert len(questions) == 1, _shown(chat)
    assert questions[0].splitlines() == [
        QUESTION_HEAD,
        f"1. **{joker['name']}** — {JOKER_TRIGGER}",
        f"2. **{hr['name']}** — {HR_TRIGGER}",
        QUESTION_TAIL,
    ]
    # One notice, rewritten into the question — not a second message under it.
    assert chat.send.await_count == 1, chat.send.await_args_list
    assert chat.send.await_args_list[0].args[-1] != questions[0]
    assert list_sessions(client, headers) == []

    asked = _new_trace(client, su, channel, before)
    assert (asked["outcome"], asked["selected_agent_id"]) == ("guided", None), asked
    pass1 = _stage(asked, "pass_1")
    assert pass1["guidance_kind"] == "clarify", pass1
    assert _option_ids(pass1) == {joker["id"], hr["id"]}
    guided = [
        e for e in list_debug_events(client, su, channel["id"])["events"]
        if e["kind"] == "guided"
    ]
    assert [e["detail"].get("guidance") for e in guided] == ["clarify"], guided

    # ── Phase 2: the stored question ─────────────────────────────────────
    row = get_routing_clarification(db, channel["id"], sender["id"])
    assert row is not None
    assert [(o["ref_id"], o["kind"]) for o in row["options"]] == [
        (joker["id"], "agent"),
        (hr["id"], "agent"),
    ], row["options"]
    assert row["message"]["text"] == original, row["message"]
    assert len(row["message"]["file_ids"]) == 1, row["message"]
    assert (row["status_message_id"] or "").startswith("spaces/AAA/messages/"), row

    # ── Phase 3: "2" routes the original ─────────────────────────────────
    before = _trace_ids(client, su, channel)
    resp, chat = _send(client, channel, sender["email"], "2", thread_key=thread_key)
    assert resp.json() == {}, resp.json()
    assert _questions(_shown(chat)) == []
    assert _ingested(client, headers, joker["id"]) == []
    assert _ingested(client, headers, hr["id"]) == [original]
    hr_session = next(s for s in list_sessions(client, headers) if s["agent_id"] == hr["id"])
    user_messages = [
        m for m in list_messages(client, headers, hr_session["id"]) if m["role"] == "user"
    ]
    assert [f["filename"] for f in user_messages[0]["files"]] == ["contract.pdf"]

    # ── Phase 4: trace, feed, row ────────────────────────────────────────
    routed = _new_trace(client, su, channel, before)
    assert (routed["outcome"], routed["selected_agent_id"], routed["match_method"]) == (
        "routed", hr["id"], "clarified",
    ), routed
    assert _answer_events(client, su, channel) == [("guided", "matched", "2")]
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


# ---------------------------------------------------------------------------
# 3. A name reply; a short free-text reply read by the classifier
# ---------------------------------------------------------------------------


def test_a_name_reply_routes_the_original_without_a_model_and_is_not_ingested(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"who can sort this out {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    before = _trace_ids(client, su, channel)
    _send(client, channel, sender["email"], "HRHelper please", thread_key=thread_key)

    assert _ingested(client, headers, hr["id"]) == [original]
    assert _ingested(client, headers, joker["id"]) == []
    routed = _new_trace(client, su, channel, before)
    assert (routed["selected_agent_id"], routed["match_method"]) == (hr["id"], "clarified")
    assert _answer_events(client, su, channel) == [("guided", "matched", "2")]
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_a_short_free_text_reply_is_read_over_the_options_and_delivered_after_the_original(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. A question over Joker / HRHelper.
      2. "the payroll person" names neither option plainly, and is short, so
         the classifier is called once — over the two options, with the reply
         as the message and the original as quoted context — and picks HRHelper.
      3. The original is routed to HRHelper under `clarified`, and the reply,
         which may carry words of its own, is ingested after it on the same
         session. Nothing reaches Joker; the question is gone.
    """
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"I have a question about my leave {random_lower_string()[:8]}"
    reply = "the payroll person"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    before = _trace_ids(client, su, channel)
    script = _Script(_route(hr["id"]))
    _send(client, channel, sender["email"], reply, thread_key=thread_key, script=script)

    assert script.calls == [
        {"refs": [joker["id"], hr["id"]], "message": reply, "quoted": original}
    ], script.calls
    assert _ingested(client, headers, hr["id"]) == [original, reply]
    assert _ingested(client, headers, joker["id"]) == []
    routed = _new_trace(client, su, channel, before)
    assert (routed["selected_agent_id"], routed["match_method"]) == (hr["id"], "clarified")
    assert ("guided", "classifier_matched", "2") in _answer_events(client, su, channel)
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_a_short_reply_is_dropped_as_superseded_when_its_original_binds_nothing(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. A question over Joker / HRHelper; the sender then narrows the channel
         to Joker and Writer.
      2. "the payroll person" is short and unread: the classifier reads it over
         the options still admitted (Joker only — HRHelper is not offered to
         the model) and names HRHelper, which was on the question.
      3. HRHelper is off the current ballot, so the ORIGINAL classifies over
         {Joker, Writer} and is answered `none`: a guidance reply listing the
         two, which binds nothing (the `list` scope keeps Pass 2 from running).
      4. The reply is dropped as `superseded`, not routed: one guidance reply
         and no question reach the sender, nothing is ingested, and no question
         is left open.
    """
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    writer = _agent(client, headers, "Writer", "Drafts letters and announcements")
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"I need a hand with a letter {random_lower_string()[:8]}"
    reply = "the payroll person"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)
    update_my_channel(
        client, headers, channel["id"], agent_scope="list", agent_ids=[joker["id"], writer["id"]]
    )

    script = _Script(_route(hr["id"]), classifier_answer(intent="none"))
    _, chat = _send(client, channel, sender["email"], reply, thread_key=thread_key, script=script)

    assert script.calls == [
        {"refs": [joker["id"]], "message": reply, "quoted": original},
        {"refs": script.calls[1]["refs"], "message": original, "quoted": None},
    ], script.calls
    assert set(script.calls[1]["refs"]) == {joker["id"], writer["id"]}
    shown = _shown(chat)
    guidance = [t for t in shown if t.startswith(NONE_HEAD)]
    assert len(guidance) == 1, shown
    assert writer["name"] in guidance[0] and hr["name"] not in guidance[0], guidance[0]
    assert _questions(shown) == [], shown
    assert list_sessions(client, headers) == []
    assert ("guided", "superseded", None) in _answer_events(client, su, channel)
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


# ---------------------------------------------------------------------------
# 4. Moved on: no option, a long reply, a decline, a lost answer
# ---------------------------------------------------------------------------


def test_a_short_reply_the_classifier_matches_to_no_option_routes_as_a_new_request(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"can someone help {random_lower_string()[:8]}"
    reply = "what about lunch"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    before = _trace_ids(client, su, channel)
    script = _Script(classifier_answer(intent="none"), _route(joker["id"]))
    _send(client, channel, sender["email"], reply, thread_key=thread_key, script=script)

    # Once over the options (with the original quoted), then as a fresh message.
    assert [(c["message"], c["quoted"]) for c in script.calls] == [
        (reply, original),
        (reply, None),
    ], script.calls
    assert _ingested(client, headers, joker["id"]) == [reply]
    assert original not in _all_ingested(client, headers)
    routed = _new_trace(client, su, channel, before)
    assert (routed["selected_agent_id"], routed["match_method"]) == (joker["id"], "ai")
    assert ("guided", "new_request", None) in _answer_events(client, su, channel)
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_a_long_reply_drops_the_question_and_routes_fresh_without_reading_it_over_the_options(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Longer than `CLARIFY_SELECTOR_MAX_WORDS` after filler: a new request, as
    the question promised. The classifier runs once, as an ordinary decision
    over the ballot (no quoted original) — never over the options."""
    su = superuser_token_headers
    sender, headers = _developer(client, su)
    joker = _agent(client, headers, "Joker", JOKER_TRIGGER)
    writer = _agent(client, headers, "Writer", "Drafts letters and announcements")
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"I need something written {random_lower_string()[:8]}"
    reply = "tell me a long joke about cats please"
    _ask(client, channel, sender, joker["id"], writer["id"], thread_key=thread_key, text=original)

    script = _Script(_route(joker["id"]))
    _send(client, channel, sender["email"], reply, thread_key=thread_key, script=script)

    assert len(script.calls) == 1, script.calls
    assert (script.calls[0]["message"], script.calls[0]["quoted"]) == (reply, None)
    assert _ingested(client, headers, joker["id"]) == [reply]
    assert _ingested(client, headers, writer["id"]) == []
    assert original not in _all_ingested(client, headers)
    assert _answer_events(client, su, channel) == []
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_no_thanks_cancels_the_question_and_the_next_message_is_a_new_request(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"help me with something {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    # ── Phase 1: the decline ─────────────────────────────────────────────
    before = _trace_ids(client, su, channel)
    resp, chat = _send(client, channel, sender["email"], "No, thanks!", thread_key=thread_key)
    assert resp.json().get("text") == REPLY_CLARIFY_CANCELLED, resp.json()
    assert list_sessions(client, headers) == []
    assert _trace_ids(client, su, channel) == before  # nothing was decided
    assert _answer_events(client, su, channel) == [("guided", "cancelled", None)]
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None

    # ── Phase 2: the next message routes as itself ───────────────────────
    _send(
        client, channel, sender["email"], "tell me a joke", thread_key=thread_key,
        answer=_route(joker["id"]),
    )
    assert _ingested(client, headers, joker["id"]) == ["tell me a joke"]
    assert original not in _all_ingested(client, headers)


def test_a_classifier_read_reply_that_loses_to_a_plain_choice_is_dropped_as_already_answered(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Two answers race for one question without threads: both webhooks are
    posted before anything drains. "the payroll person" is short and unread,
    so it only schedules a classifier read; "1" claims the question on the
    webhook path. When the drain runs the read first, its claim misses:
    `already_answered`, the reply is dropped, and the original routes to Joker
    — the choice that won. (The *synchronous* claim's loser needs two webhook
    requests inside one find→claim window, which a sequential client cannot
    produce, so it is not driven here.)"""
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"route this somewhere {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    script = _Script(_route(hr["id"]))
    token = _SIGNER.token(audience=channel["config"]["project_number"])
    with patched_channel_transport(chat=ChatVerbs()) as stack:
        stack.enter_context(_SIGNER.patched())
        enter_classifier_patch(stack, classify_side_effect=script)
        for text in ("the payroll person", "1"):
            event = build_message_event(
                thread_key=thread_key, text=text, sender_email=sender["email"]
            )
            resp = post_webhook(client, channel["webhook_token"], event, bearer_token=token)
            assert resp.status_code == 200, resp.text
        drain_tasks()

    assert len(script.calls) == 1, script.calls  # the read ran, and lost
    assert _ingested(client, headers, joker["id"]) == [original]
    assert _ingested(client, headers, hr["id"]) == []
    events = _answer_events(client, su, channel)
    assert ("guided", "matched", "1") in events, events
    assert ("guided", "already_answered", None) in events, events
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_a_reply_read_as_no_option_that_loses_to_a_plain_choice_is_dropped_not_routed(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """The same race, with a read that matches nothing. "let me think" only
    schedules a classifier read; "2" claims the question on the webhook path
    and routes the original to HRHelper. The read then names no option and its
    claim misses: `already_answered`, and the reply is dropped rather than
    routed as a new request beside the original on the same scope key, where
    it could send a second reply or win the binding race. The one classifier
    call is the read; a fresh route would have made a second."""
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"route this somewhere {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)

    # The second answer is what a fresh route of the reply would be given.
    script = _Script(classifier_answer(intent="none"), _route(joker["id"]))
    token = _SIGNER.token(audience=channel["config"]["project_number"])
    with patched_channel_transport(chat=ChatVerbs()) as stack:
        stack.enter_context(_SIGNER.patched())
        enter_classifier_patch(stack, classify_side_effect=script)
        for text in ("let me think", "2"):
            event = build_message_event(
                thread_key=thread_key, text=text, sender_email=sender["email"]
            )
            resp = post_webhook(client, channel["webhook_token"], event, bearer_token=token)
            assert resp.status_code == 200, resp.text
        drain_tasks()

    assert [c["message"] for c in script.calls] == ["let me think"], script.calls
    assert _ingested(client, headers, hr["id"]) == [original]
    assert _all_ingested(client, headers) == [original]
    events = _answer_events(client, su, channel)
    assert ("guided", "matched", "2") in events, events
    assert ("guided", "already_answered", None) in events, events
    assert ("guided", "new_request", None) not in events, events
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


# ---------------------------------------------------------------------------
# 5. Expiry: lazily on the next message, and on the flush tick
# ---------------------------------------------------------------------------


def test_an_expired_question_is_dropped_and_the_reply_routes_as_a_new_request(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"something for someone {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)
    expire_routing_clarification(db, channel["id"], sender["id"])

    before = _trace_ids(client, su, channel)
    script = _Script(_route(joker["id"]))
    _send(client, channel, sender["email"], "2", thread_key=thread_key, script=script)

    # "2" was classified as a message in its own right, not read as option 2.
    assert len(script.calls) == 1, script.calls
    assert (script.calls[0]["message"], script.calls[0]["quoted"]) == ("2", None)
    assert set(script.calls[0]["refs"]) == {joker["id"], hr["id"]}
    assert _ingested(client, headers, joker["id"]) == ["2"]
    assert _ingested(client, headers, hr["id"]) == []
    routed = _new_trace(client, su, channel, before)
    assert routed["match_method"] == "ai", routed
    assert _answer_events(client, su, channel) == []
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_the_flush_tick_purges_expired_questions_and_leaves_live_ones_answerable(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    stale_channel = _channel(client, su)
    live_channel = _channel(client, su)
    live_thread = _thread()
    live_text = f"live question {random_lower_string()[:8]}"
    _ask(client, stale_channel, sender, joker["id"], hr["id"], thread_key=_thread(), text="stale")
    _ask(client, live_channel, sender, joker["id"], hr["id"], thread_key=live_thread, text=live_text)
    expire_routing_clarification(db, stale_channel["id"], sender["id"])
    # Control: expiry alone deletes nothing.
    assert get_routing_clarification(db, stale_channel["id"], sender["id"]) is not None
    live_row = get_routing_clarification(db, live_channel["id"], sender["id"])
    assert live_row is not None

    flush_pending_bindings(db)

    assert get_routing_clarification(db, stale_channel["id"], sender["id"]) is None
    after = get_routing_clarification(db, live_channel["id"], sender["id"])
    assert after is not None and after["id"] == live_row["id"], after
    _send(client, live_channel, sender["email"], "1", thread_key=live_thread)
    assert _ingested(client, headers, joker["id"]) == [live_text]


# ---------------------------------------------------------------------------
# 6. A second asker in the same thread
# ---------------------------------------------------------------------------


def test_a_second_asker_in_the_same_thread_is_unaffected_by_the_first_askers_question(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. Anna is asked to choose between her Joker and HRHelper.
      2. Bob writes "2" in the same thread. He has no question, so "2" is his
         own message: classified over HIS ballot and ingested into his agent.
      3. Anna's question is untouched and she has no session.
      4. Anna answers "1": her original reaches her Joker.
    """
    su = superuser_token_headers
    anna, anna_headers, anna_joker, anna_hr = _sender_with_two_agents(client, su)
    bob, bob_headers, bob_joker, bob_hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"anna needs a hand {random_lower_string()[:8]}"
    _ask(client, channel, anna, anna_joker["id"], anna_hr["id"], thread_key=thread_key, text=original)
    anna_row = get_routing_clarification(db, channel["id"], anna["id"])
    assert anna_row is not None

    # ── Phase 1: Bob's "2" ───────────────────────────────────────────────
    script = _Script(_route(bob_hr["id"]))
    _send(client, channel, bob["email"], "2", thread_key=thread_key, script=script)
    assert len(script.calls) == 1, script.calls
    assert set(script.calls[0]["refs"]) == {bob_joker["id"], bob_hr["id"]}
    assert _ingested(client, bob_headers, bob_hr["id"]) == ["2"]
    assert get_routing_clarification(db, channel["id"], bob["id"]) is None

    # ── Phase 2: Anna's question is intact ───────────────────────────────
    assert list_sessions(client, anna_headers) == []
    still = get_routing_clarification(db, channel["id"], anna["id"])
    assert still is not None and still["id"] == anna_row["id"], still

    # ── Phase 3: Anna answers ────────────────────────────────────────────
    _send(client, channel, anna["email"], "1", thread_key=thread_key)
    assert _ingested(client, anna_headers, anna_joker["id"]) == [original]
    assert _ingested(client, anna_headers, anna_hr["id"]) == []
    assert _ingested(client, bob_headers, bob_hr["id"]) == ["2"]


# ---------------------------------------------------------------------------
# 7. Identity and bundle options
# ---------------------------------------------------------------------------


def test_an_identity_option_goes_through_stage_2_into_the_owners_workspace(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """The sender owns Joker and may address Anna (one reachable binding, so
    Stage 2 takes its own single-candidate path and no model runs after the
    question). Choosing Anna lands the original in HER session on HER agent."""
    su = superuser_token_headers
    sender, headers = _developer(client, su)
    joker = _agent(client, headers, "Joker", JOKER_TRIGGER)
    anna, anna_headers = _developer(client, su)
    anna_agent = _agent(client, anna_headers, "AnnaAgent", "Anna's own work")
    share_identity_agent(
        client, anna_headers, headers,
        agent_id=anna_agent["id"], target_user_id=sender["id"], owner_id=anna["id"],
    )
    channel = _channel(client, su)
    update_my_channel(client, headers, channel["id"], allow_identity_routing=True)
    anna_ref = f"identity:{anna['id']}"
    thread_key = _thread()
    original = f"can anna look at this {random_lower_string()[:8]}"

    question = _ask(client, channel, sender, joker["id"], anna_ref, thread_key=thread_key, text=original)
    assert question.splitlines() == [
        QUESTION_HEAD,
        f"1. **{joker['name']}** — {JOKER_TRIGGER}",
        f"2. **{anna['email'].split('@')[0]}** — {IDENTITY_DESCRIPTION}",
        QUESTION_TAIL,
    ]
    assert anna["email"] not in question
    row = get_routing_clarification(db, channel["id"], sender["id"])
    assert [o["kind"] for o in row["options"]] == ["agent", "identity"], row

    before = _trace_ids(client, su, channel)
    _send(client, channel, sender["email"], "2", thread_key=thread_key)

    assert _ingested(client, anna_headers, anna_agent["id"]) == [original]
    assert list_sessions(client, headers) == []
    routed = _new_trace(client, su, channel, before)
    assert (routed["outcome"], routed["selected_agent_id"]) == ("routed", anna_agent["id"]), routed
    assert "identity_stage2" in [s["stage"] for s in routed["stages"]], routed["stages"]
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


def test_a_bundle_option_parks_an_install_of_the_chosen_bundle(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. The sender owns nothing; two catalog bundles tie at Pass 2 and the
         question lists both by name.
      2. "2" parks an install of the second bundle, `clarified`, with no model.
      3. The same "2" redelivered while that install is pending is already
         handled: acknowledged silently, never parked for the new agent.
    """
    su = superuser_token_headers
    sender, headers = _developer(client, su)
    desk = _catalog_bundle(client, su, "Handle support desk tickets")
    travel = _catalog_bundle(client, su, "Handle travel bookings")
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"I need help with a trip {random_lower_string()[:8]}"

    # ── Phase 1: the question ────────────────────────────────────────────
    before = _trace_ids(client, su, channel)
    question = _ask(client, channel, sender, desk, travel, thread_key=thread_key, text=original)
    asked = _new_trace(client, su, channel, before)
    assert asked["outcome"] == "guided", asked
    pass2 = _stage(asked, "pass_2")
    assert (pass2["guidance_kind"], _option_ids(pass2)) == ("clarify", {desk, travel}), pass2
    names = {c["ref_id"]: c["name"] for c in pass2["candidates"]}
    assert question.splitlines() == [
        QUESTION_HEAD,
        f"1. **{names[desk]}** — Handle support desk tickets",
        f"2. **{names[travel]}** — Handle travel bookings",
        QUESTION_TAIL,
    ]
    row = get_routing_clarification(db, channel["id"], sender["id"])
    assert [(o["ref_id"], o["kind"]) for o in row["options"]] == [
        (desk, "bundle"), (travel, "bundle"),
    ], row

    # ── Phase 2: "2" parks the install ───────────────────────────────────
    answer_name = _message_name()
    before = _trace_ids(client, su, channel)
    _send(client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name)
    parked = _new_trace(client, su, channel, before)
    assert (parked["outcome"], parked["selected_bundle_uuid"], parked["match_method"]) == (
        "parked_install", travel, "clarified",
    ), parked
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None

    # ── Phase 3: the answer redelivered onto the pending binding ─────────
    before = _trace_ids(client, su, channel)
    resp, _ = _send(client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name)
    assert resp.json() == {}, resp.json()
    assert resp.json().get("text") != REPLY_STILL_SETTING_UP
    assert _trace_ids(client, su, channel) == before


def test_a_redelivered_answer_is_not_ingested_after_its_parked_install_is_flushed(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """
      1. The sender owns nothing; a question over two catalog bundles; "2" parks
         an install of the second.
      2. The environment comes up and the flush drains the parked original,
         opening the session — which resets the binding's context receipts.
      3. "2" redelivered now reaches an ACTIVE binding: its receipt survived that
         reset, so it is acknowledged, never ingested, and decides nothing.
    """
    su = superuser_token_headers
    sender, headers = _developer(client, su)
    desk = _catalog_bundle(client, su, "Handle support desk tickets")
    travel = _catalog_bundle(client, su, "Handle travel bookings")
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"book my conference trip {random_lower_string()[:8]}"
    _ask(client, channel, sender, desk, travel, thread_key=thread_key, text=original)

    # ── Phase 1: "2" parks the install ───────────────────────────────────
    answer_name = _message_name()
    _send(client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name)
    installed = next(
        a for a in client.get(f"{API}/agents/", headers=headers).json()["data"]
        if a["bundle_uuid"] == travel
    )
    assert list_sessions(client, headers) == []

    # ── Phase 2: the flush drains the original into a new session ────────
    set_environment_status(db, installed["active_environment_id"], "running")
    db.commit()
    with patched_channel_transport(chat=ChatVerbs()):
        assert flush_pending_bindings(db) == 1
        drain_tasks()
    assert _ingested(client, headers, installed["id"]) == [original]

    # ── Phase 3: the answer redelivered onto the now-active binding ──────
    before = _trace_ids(client, su, channel)
    resp, _ = _send(
        client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name
    )
    assert resp.json() == {}, resp.json()
    assert _ingested(client, headers, installed["id"]) == [original]
    assert _trace_ids(client, su, channel) == before


# ---------------------------------------------------------------------------
# 8. The chosen option is no longer on the ballot
# ---------------------------------------------------------------------------


def test_an_option_the_senders_policy_no_longer_admits_is_never_routed_to(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Asked between Joker and HRHelper; the sender then narrows the channel to
    Joker and Writer. "2" still names HRHelper, but a choice can only narrow
    what policy admits now: the ORIGINAL is classified over {Joker, Writer} and
    routes where the classifier says, under `ai` — never to HRHelper. The
    sender already chose, so a `clarify` answer is not met with a second
    question: it routes its best pick, as on a transport that cannot ask."""
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    writer = _agent(client, headers, "Writer", "Drafts letters and announcements")
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"please draft a note {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=original)
    update_my_channel(
        client, headers, channel["id"], agent_scope="list", agent_ids=[joker["id"], writer["id"]]
    )

    before = _trace_ids(client, su, channel)
    script = _Script(_clarify(writer["id"], joker["id"]))
    _, chat = _send(client, channel, sender["email"], "2", thread_key=thread_key, script=script)

    assert len(script.calls) == 1, script.calls
    assert set(script.calls[0]["refs"]) == {joker["id"], writer["id"]}, script.calls
    assert script.calls[0]["message"] == original
    assert _questions(_shown(chat)) == [], _shown(chat)
    assert _ingested(client, headers, hr["id"]) == []
    assert _ingested(client, headers, writer["id"]) == [original]
    routed = _new_trace(client, su, channel, before)
    assert (routed["selected_agent_id"], routed["match_method"]) == (writer["id"], "ai"), routed
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


# ---------------------------------------------------------------------------
# 9. Redelivery
# ---------------------------------------------------------------------------


def test_redelivered_original_and_redelivered_answer_are_acknowledged_and_ignored(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su)
    thread_key = _thread()
    original = f"forward this please {random_lower_string()[:8]}"
    original_name = _message_name()
    _ask(
        client, channel, sender, joker["id"], hr["id"],
        thread_key=thread_key, text=original, message_name=original_name,
    )
    row = get_routing_clarification(db, channel["id"], sender["id"])

    # ── Phase 1: the original again, while the question is open ──────────
    before = _trace_ids(client, su, channel)
    resp, chat = _send(
        client, channel, sender["email"], original, thread_key=thread_key,
        message_name=original_name,
    )
    assert resp.json() == {}, resp.json()
    assert _shown(chat) == []  # not asked twice, nothing said
    assert _trace_ids(client, su, channel) == before
    assert list_sessions(client, headers) == []
    still = get_routing_clarification(db, channel["id"], sender["id"])
    assert still is not None and still["id"] == row["id"], still

    # ── Phase 2: the answer ──────────────────────────────────────────────
    answer_name = _message_name()
    _send(client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name)
    assert _ingested(client, headers, hr["id"]) == [original]

    # ── Phase 3: the answer again, now that the thread is bound ──────────
    before = _trace_ids(client, su, channel)
    resp, _ = _send(
        client, channel, sender["email"], "2", thread_key=thread_key, message_name=answer_name
    )
    assert resp.json() == {}, resp.json()
    assert _ingested(client, headers, hr["id"]) == [original]
    assert _ingested(client, headers, joker["id"]) == []
    assert _trace_ids(client, su, channel) == before


# ---------------------------------------------------------------------------
# 10. Where no question is asked
# ---------------------------------------------------------------------------


def test_guidance_switched_off_asks_nothing_and_ignores_a_question_already_open(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)

    # ── Phase 1: a clarify answer with guidance off routes the best pick ─
    quiet = _channel(client, su)
    first = f"first request {random_lower_string()[:8]}"
    _, chat = _send(
        client, quiet, sender["email"], first, thread_key=_thread(),
        answer=_clarify(joker["id"], hr["id"]), settings_overrides=_GUIDANCE_OFF,
    )
    assert _questions(_shown(chat)) == []
    assert _ingested(client, headers, joker["id"]) == [first]
    assert get_routing_clarification(db, quiet["id"], sender["id"]) is None

    # ── Phase 2: a question asked while on, then guidance switched off ───
    channel = _channel(client, su)
    thread_key = _thread()
    asked = f"second request {random_lower_string()[:8]}"
    _ask(client, channel, sender, joker["id"], hr["id"], thread_key=thread_key, text=asked)
    row = get_routing_clarification(db, channel["id"], sender["id"])
    assert row is not None

    script = _Script(_route(hr["id"]))
    _send(
        client, channel, sender["email"], "2", thread_key=thread_key, script=script,
        settings_overrides=_GUIDANCE_OFF,
    )
    # "2" is an ordinary message: classified over the ballot, ingested as itself.
    assert [(c["message"], c["quoted"]) for c in script.calls] == [("2", None)], script.calls
    assert _ingested(client, headers, hr["id"]) == ["2"]
    assert asked not in _all_ingested(client, headers)
    ignored = get_routing_clarification(db, channel["id"], sender["id"])
    assert ignored is not None and ignored["id"] == row["id"], ignored


def test_a_google_chat_channel_without_outbound_credentials_is_never_asked(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """With nothing to rewrite the notice with, a question could not be followed
    up: `clarify` routes the best pick, exactly as on email."""
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    channel = _channel(client, su, outbound=False)
    original = f"no credentials here {random_lower_string()[:8]}"

    before = _trace_ids(client, su, channel)
    _, chat = _send(
        client, channel, sender["email"], original, thread_key=_thread(),
        answer=_clarify(joker["id"], hr["id"]),
    )

    assert _questions(_shown(chat)) == []
    assert _ingested(client, headers, joker["id"]) == [original]
    assert _ingested(client, headers, hr["id"]) == []
    routed = _new_trace(client, su, channel, before)
    assert (routed["outcome"], routed["selected_agent_id"]) == ("routed", joker["id"]), routed
    assert _stage(routed, "pass_1").get("guidance_kind") is None
    assert get_routing_clarification(db, channel["id"], sender["id"]) is None


# ---------------------------------------------------------------------------
# 11. The message-text gate
# ---------------------------------------------------------------------------


def test_neither_the_question_trace_nor_the_follow_up_carries_sender_text_with_storage_off(
    client: TestClient, superuser_token_headers: dict[str, str], db: Session
) -> None:
    """Real parse (provider mocked at classifier depth), so the question's stage
    genuinely holds the sender's words in `raw_response` before the gate acts.

      0. Control — captured and read ON: the words are in the question's
         `raw_response` and are the follow-up's `message_text`.
      1. Read path — those rows read OFF: `guidance_kind` / `guidance_options`
         and `match_method="clarified"` served, the words nowhere.
      2. Write path — captured OFF, read ON: the same fields stored, the words
         nowhere.
    """
    su = superuser_token_headers
    sender, headers, joker, hr = _sender_with_two_agents(client, su)
    expected = {joker["id"], hr["id"]}

    def _round_trip(store_text: bool) -> tuple[str, str, str]:
        channel = _channel(client, su)
        thread_key = _thread()
        needle = random_lower_string()
        words = f"sort out my thing {needle}"
        overrides = {"ROUTING_TRACE_STORE_MESSAGE_TEXT": store_text}
        before = _trace_ids(client, su, channel)
        _, chat = _send(
            client, channel, sender["email"], words, thread_key=thread_key,
            provider_reply={
                "agent_id": joker["id"],
                "intent": "clarify",
                "options": [joker["id"], hr["id"]],
                "message": None,
                "confidence": 0.5,
                "reason": f"the sender wrote {words}",
            },
            settings_overrides=overrides,
        )
        assert len(_questions(_shown(chat))) == 1, _shown(chat)
        asked_id = _new_trace(client, su, channel, before)["id"]
        before = _trace_ids(client, su, channel)
        _send(client, channel, sender["email"], "2", thread_key=thread_key, settings_overrides=overrides)
        followed_id = _new_trace(client, su, channel, before)["id"]
        return asked_id, followed_id, needle

    def _read(trace_id: str, store_text: bool) -> dict:
        with patch.object(settings, "ROUTING_TRACE_STORE_MESSAGE_TEXT", store_text):
            return get_routing_trace(client, su, trace_id)

    def _assert_safe_fields(asked: dict, followed: dict) -> None:
        pass1 = _stage(asked, "pass_1")
        assert (pass1.get("guidance_kind"), _option_ids(pass1)) == ("clarify", expected), pass1
        assert (followed["match_method"], followed["selected_agent_id"]) == (
            "clarified", hr["id"],
        ), followed

    # ── 0. Control ───────────────────────────────────────────────────────
    on_asked, on_followed, on_needle = _round_trip(store_text=True)
    assert on_needle in (_stage(_read(on_asked, True), "pass_1")["raw_response"] or "")
    assert on_needle in (_read(on_followed, True)["message_text"] or "")

    # ── 1. Read path ─────────────────────────────────────────────────────
    asked_off, followed_off = _read(on_asked, False), _read(on_followed, False)
    for detail in (asked_off, followed_off):
        assert on_needle not in json.dumps(detail), detail["id"]
        assert detail["message_text"] is None
        assert detail["message_sha256"]
    _assert_safe_fields(asked_off, followed_off)

    # ── 2. Write path ────────────────────────────────────────────────────
    off_asked, off_followed, off_needle = _round_trip(store_text=False)
    asked_written, followed_written = _read(off_asked, True), _read(off_followed, True)
    for detail in (asked_written, followed_written):
        assert off_needle not in json.dumps(detail), detail["id"]
    _assert_safe_fields(asked_written, followed_written)
