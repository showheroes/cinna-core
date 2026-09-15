"""
`AgentClassifier`'s parse of the Phase 5 prompt contract.

The contract grew three advisory fields — `confidence`, `reason`, `runner_up` —
and the property that matters most about them is **negative**: a model that
ignores all three must still route. Local and small models routinely drop
fields added to a JSON schema, and this project's own default cascade ends at a
self-hosted `granite4`, so a strict parse would have turned a tuning feature
into a routing outage for exactly the deployments least able to diagnose it.

Everything here is a regression guard (it asserts behaviour the parse could
plausibly break), not a precondition assertion — each one is expected to survive
a mutation check.

No DB, no Docker, no LLM calls.
"""
import json
import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.routing import routing_trace
from app.services.routing.agent_classifier import (
    INTENT_CLARIFY,
    INTENT_HELP,
    INTENT_NONE,
    INTENT_ROUTE,
    MAX_CLARIFY_OPTIONS,
    MAX_EXAMPLE_CHARS,
    MAX_EXAMPLE_LINES,
    MAX_QUOTED_CONTEXT_CHARS,
    QUOTED_END_MARKER,
    AgentClassifier,
    Candidate,
    ClassifierAnswer,
    QuotedContext,
    _example_lines,
    _parse_confidence,
    _parse_intent_and_options,
    _parse_reason,
    _parse_runner_up,
    _parse_transformed_message,
)

_PROVIDER_TARGET = "app.services.routing.agent_classifier.get_provider_manager"

AGENT_ID = str(uuid.uuid4())
OTHER_ID = str(uuid.uuid4())
CANDIDATES = [
    Candidate(ref_id=AGENT_ID, name="Ops Runbook", trigger_prompt="Ops things"),
    Candidate(ref_id=OTHER_ID, name="People Ops", trigger_prompt="Policy things"),
]


def _classify(reply: str, message: str = "prod is down"):
    with patch(_PROVIDER_TARGET) as mock_pm:
        mock_pm.return_value.generate_content.return_value = MagicMock(text=reply)
        return AgentClassifier.classify(CANDIDATES, message)


# ---------------------------------------------------------------------------
# The one that keeps a tuning feature from becoming an outage
# ---------------------------------------------------------------------------


def test_a_reply_omitting_every_new_field_still_routes() -> None:
    """The pre-Phase-5 reply shape, which every deployed model still emits.

    If this ever fails, small-model deployments stop routing entirely — the
    field additions are advisory and must never be load-bearing.
    """
    result = _classify(json.dumps({"agent_id": AGENT_ID, "message": None}))

    assert result is not None
    assert result.agent_id == AGENT_ID
    assert result.confidence is None
    assert result.reason is None
    assert result.runner_up_id is None
    # ...and the guidance contract's two fields, which small models drop the
    # same way: no intent beside a pick is `route`, the pre-field reading.
    assert result.intent == INTENT_ROUTE
    assert result.options == ()


def test_a_reply_with_garbage_in_every_new_field_still_routes() -> None:
    """Wrong *types*, not just missing keys — the other half of the same risk."""
    result = _classify(
        json.dumps(
            {
                "agent_id": AGENT_ID,
                "message": None,
                "confidence": "very sure",
                "reason": {"nested": "object"},
                "runner_up": ["a", "list"],
            }
        )
    )

    assert result is not None
    assert result.agent_id == AGENT_ID
    assert result.confidence is None
    assert result.reason is None
    assert result.runner_up_id is None


def test_a_json_reply_that_is_not_an_object_is_a_no_match_not_a_crash() -> None:
    assert _classify("[1, 2, 3]") is None


# ---------------------------------------------------------------------------
# What the fields carry when the model does answer
# ---------------------------------------------------------------------------


def test_the_advisory_fields_are_carried_through_when_present() -> None:
    result = _classify(
        json.dumps(
            {
                "agent_id": AGENT_ID,
                "message": None,
                "confidence": 0.72,
                "reason": "it names a production outage",
                "runner_up": OTHER_ID,
            }
        )
    )

    assert result is not None
    assert result.confidence == 0.72
    assert result.reason == "it names a production outage"
    assert result.runner_up_id == OTHER_ID
    # A full Phase 5 reply with none of the guidance fields is still `route`.
    assert (result.intent, result.options) == (INTENT_ROUTE, ())


@pytest.mark.parametrize(
    "raw,expected",
    [
        (0.0, 0.0),
        (1.0, 1.0),
        (0.5, 0.5),
        ("0.5", 0.5),
        (1, 1.0),
        # Out of range is DROPPED, never rescaled: an `85` probably means 85%,
        # and "probably" is how a diagnostic starts reporting numbers the model
        # never gave it.
        (85, None),
        (-0.1, None),
        (1.01, None),
        (float("nan"), None),
        (float("inf"), None),
        # `True` is an `int` in Python and would otherwise arrive as 1.0.
        (True, None),
        (None, None),
        ("high", None),
        ([0.5], None),
    ],
)
def test_confidence_parsing(raw, expected) -> None:
    # Plain equality, not a disjunction: an `or`-ed fallback in an assertion is
    # a second way for the test to pass, which is one more than it should have.
    assert _parse_confidence(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("because it is an ops question", "because it is an ops question"),
        ("  padded  ", "padded"),
        ("", None),
        ("   ", None),
        (None, None),
        (42, None),
        ({"a": 1}, None),
    ],
)
def test_reason_parsing(raw, expected) -> None:
    assert _parse_reason(raw) == expected


def test_runner_up_must_name_a_candidate_on_the_ballot() -> None:
    """An allowlist, not a UUID format check.

    A runner-up naming something that was never a candidate is not a diagnosis;
    it is a dangling reference the tuning card would render as a real one.
    """
    known = {AGENT_ID, OTHER_ID}
    assert _parse_runner_up(OTHER_ID, known) == OTHER_ID
    assert _parse_runner_up(str(uuid.uuid4()), known) is None
    assert _parse_runner_up("NONE", known) is None
    assert _parse_runner_up("none", known) is None
    assert _parse_runner_up("", known) is None
    assert _parse_runner_up(None, known) is None
    assert _parse_runner_up(12345, known) is None


# ---------------------------------------------------------------------------
# `intent` / `options` — channel routing guidance, Phase 1
# ---------------------------------------------------------------------------
#
# `agent_id` decides; `intent` may refine it, never contradict it. Each case
# below is a way a careless or self-contradicting reply could otherwise change
# where a message goes, and Phase 1 promises no sender-visible change. The
# API-observable half — both stage fields surviving the message-text gate — is
# in `tests/api/routing/routing_message_text_gating_test.py`.

# Fixed, letter-bearing ids so the case-sensitivity case is deterministic.
THIRD_ID = "3c0ffee0-aaaa-4bbb-8ccc-00000000000c"
FOURTH_ID = "4d0ffee0-dddd-4eee-9fff-00000000000d"
BALLOT = {AGENT_ID, OTHER_ID, THIRD_ID, FOURTH_ID}


def _intent(intent, options=None, *, agent_id=AGENT_ID):
    result = _parse_intent_and_options(
        intent, options, agent_id=agent_id, known_ids=BALLOT
    )
    # The invariant every case rides on: `clarify` leads with the pick it
    # carries in `agent_id`, and nothing but `clarify` carries options.
    if result[0] == INTENT_CLARIFY:
        assert result[1][0] == agent_id, result
    else:
        assert result[1] == (), result
    return result


def test_the_intent_vocabulary_matches_the_prompt_contract_and_the_trace() -> None:
    assert (INTENT_ROUTE, INTENT_CLARIFY, INTENT_HELP, INTENT_NONE) == (
        "route",
        "clarify",
        "help",
        "none",
    )
    # One vocabulary: the recorder coerces to the set the parser produces.
    assert routing_trace.CLASSIFIER_INTENTS == {
        INTENT_ROUTE,
        INTENT_CLARIFY,
        INTENT_HELP,
        INTENT_NONE,
    }
    assert MAX_CLARIFY_OPTIONS == 3


@pytest.mark.parametrize(
    "intent,options,expected",
    [
        ("route", [], (INTENT_ROUTE, ())),
        ("clarify", [AGENT_ID, OTHER_ID], (INTENT_CLARIFY, (AGENT_ID, OTHER_ID))),
        ("  Clarify\n", [AGENT_ID, OTHER_ID], (INTENT_CLARIFY, (AGENT_ID, OTHER_ID))),
        # Missing or unknown beside a pick: `route`, as before the field existed.
        (None, None, (INTENT_ROUTE, ())),
        ("escalate", [AGENT_ID, OTHER_ID], (INTENT_ROUTE, ())),
        (42, [AGENT_ID, OTHER_ID], (INTENT_ROUTE, ())),
        (["clarify"], [AGENT_ID, OTHER_ID], (INTENT_ROUTE, ())),
        # help / none beside a real agent_id contradict it; the pick wins.
        ("help", [], (INTENT_ROUTE, ())),
        ("none", [], (INTENT_ROUTE, ())),
        ("help", [AGENT_ID, OTHER_ID], (INTENT_ROUTE, ())),
        # Options ride on `clarify` only.
        ("route", [AGENT_ID, OTHER_ID], (INTENT_ROUTE, ())),
    ],
    ids=[
        "route",
        "clarify",
        "clarify_padded_and_cased",
        "missing",
        "unknown",
        "non_string",
        "list",
        "help_beside_pick",
        "none_beside_pick",
        "help_beside_pick_with_options",
        "route_drops_options",
    ],
)
def test_intent_beside_a_pick_is_route_or_clarify(intent, options, expected) -> None:
    assert _intent(intent, options) == expected


@pytest.mark.parametrize("agent_id", [None, ""], ids=["none", "blank"])
@pytest.mark.parametrize(
    "intent,options,expected",
    [
        ("help", None, INTENT_HELP),
        (" HELP ", None, INTENT_HELP),
        ("none", None, INTENT_NONE),
        (None, None, INTENT_NONE),
        ("escalate", None, INTENT_NONE),
        ("route", None, INTENT_NONE),
        # An option is never promoted into a pick: nothing to route, nothing to ask.
        ("clarify", [AGENT_ID, OTHER_ID], INTENT_NONE),
        ("route", [AGENT_ID], INTENT_NONE),
        ("help", [AGENT_ID, OTHER_ID], INTENT_HELP),
    ],
    ids=[
        "help",
        "help_padded_and_cased",
        "none",
        "missing",
        "unknown",
        "route_without_pick",
        "clarify_without_pick",
        "route_with_option_without_pick",
        "help_with_options",
    ],
)
def test_intent_without_a_pick_is_help_or_none_and_never_carries_options(
    agent_id, intent, options, expected
) -> None:
    assert _intent(intent, options, agent_id=agent_id) == (expected, ())


@pytest.mark.parametrize(
    "options",
    [
        [],
        None,
        f"{AGENT_ID},{OTHER_ID}",
        {"first": AGENT_ID, "second": OTHER_ID},
        [AGENT_ID],
        [AGENT_ID, AGENT_ID, f"  {AGENT_ID}\n"],
        [str(uuid.uuid4()), "NONE", THIRD_ID.upper(), 7, None, {"ref_id": OTHER_ID}],
    ],
    ids=[
        "empty",
        "missing",
        "string_not_list",
        "dict_not_list",
        "only_the_pick",
        "the_pick_three_ways",
        "nothing_on_the_ballot",
    ],
)
def test_clarify_with_fewer_than_two_surviving_options_collapses_to_route(options) -> None:
    """A question with one answer is not a question."""
    assert _intent("clarify", options) == (INTENT_ROUTE, ())


def test_the_best_pick_leads_the_options_and_counts_towards_the_two() -> None:
    """`options` is led by `agent_id` when it is on the ballot, whether or not
    the model listed it — so a pick plus one tied id is a two-way question."""
    assert _intent("clarify", [OTHER_ID]) == (INTENT_CLARIFY, (AGENT_ID, OTHER_ID))
    assert _intent("clarify", [OTHER_ID, THIRD_ID, AGENT_ID]) == (
        INTENT_CLARIFY,
        (AGENT_ID, OTHER_ID, THIRD_ID),
    )
    # The rest keep the model's preference order.
    assert _intent("clarify", [THIRD_ID, OTHER_ID]) == (
        INTENT_CLARIFY,
        (AGENT_ID, THIRD_ID, OTHER_ID),
    )


def test_an_off_ballot_pick_never_leads_a_clarify_question() -> None:
    """A UUID-shaped `agent_id` the ballot never held cannot be the first
    option, and two genuine ballot options do not rescue it into `clarify`."""
    off_ballot = str(uuid.uuid4())

    assert _intent("clarify", [AGENT_ID, OTHER_ID], agent_id=off_ballot) == (
        INTENT_ROUTE,
        (),
    )
    assert _intent("clarify", [off_ballot, AGENT_ID, OTHER_ID], agent_id=off_ballot) == (
        INTENT_ROUTE,
        (),
    )


def test_clarify_options_drop_off_ballot_and_duplicate_ids() -> None:
    """Exact match after stripping — the `runner_up` rule — then deduplicated."""
    options = [
        THIRD_ID,
        str(uuid.uuid4()),
        "NONE",
        THIRD_ID.upper(),
        7,
        None,
        {"ref_id": FOURTH_ID},
        f"  {THIRD_ID}\n",
        AGENT_ID,
    ]
    assert _intent("clarify", options) == (INTENT_CLARIFY, (AGENT_ID, THIRD_ID))


def test_clarify_options_are_capped_after_the_best_pick_is_placed_first() -> None:
    intent, options = _intent("clarify", [OTHER_ID, THIRD_ID, FOURTH_ID, AGENT_ID])

    assert intent == INTENT_CLARIFY
    assert options == (AGENT_ID, OTHER_ID, THIRD_ID)
    assert len(options) == MAX_CLARIFY_OPTIONS


def test_classify_carries_a_clarify_answer_and_still_names_the_best_pick() -> None:
    """A consumer that ignores `intent` routes `agent_id` — the additive half."""
    with routing_trace.RoutingTrace.capture(
        origin=routing_trace.ORIGIN_SIMULATE,
        stage=routing_trace.STAGE_PASS_1,
        message="prod is down",
    ) as trace:
        result = _classify(
            json.dumps(
                {
                    "agent_id": AGENT_ID,
                    "intent": "clarify",
                    "options": [OTHER_ID, str(uuid.uuid4()), AGENT_ID],
                    "runner_up": OTHER_ID,
                }
            )
        )
        stages = trace.stages_payload()

    assert result is not None
    assert result.agent_id == AGENT_ID
    assert result.intent == INTENT_CLARIFY
    assert result.options == (AGENT_ID, OTHER_ID)
    assert stages[0]["intent"] == INTENT_CLARIFY
    assert stages[0]["options"] == [{"ref_id": AGENT_ID}, {"ref_id": OTHER_ID}]


@pytest.mark.parametrize(
    "extra",
    [
        {"intent": "help"},
        {"intent": "none", "options": [OTHER_ID]},
        {"intent": {"nested": "object"}, "options": "not a list"},
        {"intent": "clarify", "options": OTHER_ID},
        {"intent": "clarify", "options": [str(uuid.uuid4())]},
    ],
    ids=["help", "none_with_options", "garbage", "options_string", "options_off_ballot"],
)
def test_classify_routes_the_pick_whatever_intent_sits_beside_it(extra) -> None:
    result = _classify(json.dumps({"agent_id": AGENT_ID, "message": None, **extra}))

    assert result is not None
    assert result.agent_id == AGENT_ID
    assert (result.intent, result.options) == (INTENT_ROUTE, ())


@pytest.mark.parametrize(
    "reply,expected_intent",
    [
        ({"agent_id": "NONE"}, INTENT_NONE),
        ({"agent_id": "NONE", "intent": "none"}, INTENT_NONE),
        ({"agent_id": "NONE", "intent": "help"}, INTENT_HELP),
        ({"agent_id": "", "intent": "help"}, INTENT_HELP),
        ({"agent_id": "NONE", "intent": "route"}, INTENT_NONE),
        (
            {"agent_id": "NONE", "intent": "clarify", "options": [AGENT_ID, OTHER_ID]},
            INTENT_NONE,
        ),
    ],
    ids=["bare", "none", "help", "blank_help", "route", "clarify_with_options"],
)
def test_classify_without_a_pick_is_no_match_and_traces_its_intent(
    reply, expected_intent
) -> None:
    with routing_trace.RoutingTrace.capture(
        origin=routing_trace.ORIGIN_SIMULATE,
        stage=routing_trace.STAGE_PASS_1,
        message="what can you do?",
    ) as trace:
        result = _classify(json.dumps(reply), message="what can you do?")
        stages = trace.stages_payload()

    assert result is None
    assert stages[0]["intent"] == expected_intent
    assert stages[0]["options"] == []


# ---------------------------------------------------------------------------
# What reaches the trace
# ---------------------------------------------------------------------------


def test_confidence_reaches_both_the_stage_and_the_decision() -> None:
    """The `confidence` column exists to be filled by exactly this path.

    Without the decision-level lift the column would be permanently NULL while
    reading, to an operator, as "the model gave no confidence" — a hazardous
    state wearing an ordinary one's clothes (plan §11a, Rule 1).
    """
    with routing_trace.RoutingTrace.capture(
        origin=routing_trace.ORIGIN_SIMULATE,
        stage=routing_trace.STAGE_PASS_1,
        message="prod is down",
    ) as trace:
        _classify(
            json.dumps({"agent_id": AGENT_ID, "confidence": 0.64, "reason": "ops"})
        )
        routing_trace.record_outcome(
            routing_trace.OUTCOME_ROUTED, selected_agent_id=AGENT_ID
        )
        stages = trace.stages_payload()
        decision_confidence = trace.confidence

    assert stages[0]["confidence"] == 0.64
    assert stages[0]["reason"] == "ops"
    assert decision_confidence == 0.64


def test_a_non_routed_outcome_clears_the_lifted_confidence() -> None:
    """A `no_match` row must not carry a score for an agent it does not name.

    The classifier picked something and a downstream filter threw it out; the
    settler clears the selection, and the confidence has to go with it or the
    row reports a decision that was not taken.
    """
    with routing_trace.RoutingTrace.capture(
        origin=routing_trace.ORIGIN_SIMULATE,
        stage=routing_trace.STAGE_PASS_1,
        message="prod is down",
    ) as trace:
        _classify(json.dumps({"agent_id": AGENT_ID, "confidence": 0.64}))
        routing_trace.record_outcome(routing_trace.OUTCOME_NO_MATCH)
        decision_confidence = trace.confidence

    assert decision_confidence is None


def test_reason_is_not_on_the_message_text_allowlist() -> None:
    """Pinned here as well as end-to-end, because this is the *rule*.

    The API test proves the withholding happens; this one pins why it can, and
    fails the moment somebody puts the field back to make a stage read nicer.
    """
    assert "reason" not in routing_trace.SAFE_STAGE_FIELDS
    # ...while the two neighbours that are genuinely not sender-derived stay.
    assert "confidence" in routing_trace.SAFE_STAGE_FIELDS
    assert "runner_up_id" in routing_trace.SAFE_STAGE_FIELDS


# ---------------------------------------------------------------------------
# Example rendering is bounded on BOTH axes
# ---------------------------------------------------------------------------
#
# The line cap was enforced from the start; the character cap was only ever
# documented by the comment on the constants, and held by accident because
# every write path into a candidate was bounded by a route-layer validator.
# `ChannelCandidateProvider` opened the first unbounded one — `Agent
# .example_prompts` is a user-editable JSON column with no validator anywhere —
# so a prose promise became a real limit and gets a real test.


def test_examples_are_capped_by_characters_not_only_by_lines():
    """One pasted 500KB line is ten lines' worth of nothing — it is one line.

    The line cap cannot see it, which is the whole point: without the
    character cap this string reaches the model verbatim on every inbound
    channel message.
    """
    lines = _example_lines("x" * 500_000)

    assert len(lines) == 1
    assert len(lines[0]) == MAX_EXAMPLE_CHARS


def test_the_character_cap_is_applied_before_the_split():
    """A megabyte of newlines must not build a million-element list first.

    Order is the property, not just the result: clamping after the split would
    still materialise every line before taking ten of them. Asserted through
    behaviour — 300k blank lines followed by real content renders NOTHING,
    because the real content lies beyond the character budget.
    """
    raw = "\n" * 300_000 + "book a meeting"

    assert _example_lines(raw) == []


def test_the_line_cap_still_applies_within_the_character_budget():
    """Both caps, not one replacing the other."""
    raw = "\n".join(f"example {i}" for i in range(50))

    lines = _example_lines(raw)

    assert len(lines) == MAX_EXAMPLE_LINES
    assert lines[0] == "example 0"


def test_a_long_example_block_is_truncated_rather_than_dropped():
    """Truncation is silent by design.

    The alternative — refusing to render an over-long block — would drop a
    candidate's examples out of a routing decision entirely, trading a trimmed
    prompt for a worse routing answer.
    """
    raw = "\n".join(["book a meeting"] + ["y" * 3000])

    lines = _example_lines(raw)

    assert lines[0] == "book a meeting"
    assert len(lines) == 2
    assert len(lines[1]) < 3000


# ---------------------------------------------------------------------------
# The `message` field guard with a quoted message (quote-aware routing)
# ---------------------------------------------------------------------------
#
# `transformed_message` is never persisted on the trace, but it becomes identity
# Stage 2's *user message*. A model that copies the quoted text into it would
# hand someone else's words on as the sender's task, so a rewrite equal to the
# quote — as it arrived, or as the prompt showed it — is rejected. The three
# original guards keep measuring against the sender's own words.

_SENDER = "@DoBot can you do the thing from the quote?"
_QUOTE = "tell me a dad joke about scarecrows"


def test_a_message_field_equal_to_the_quoted_text_is_rejected() -> None:
    # Control: without a quote the same value passes every original guard, so
    # the rejection below is the new guard and nothing else.
    assert _parse_transformed_message(_QUOTE, _SENDER) == _QUOTE

    assert _parse_transformed_message(_QUOTE, _SENDER, QuotedContext(text=_QUOTE)) is None
    # Compared after stripping, on both sides.
    assert (
        _parse_transformed_message(f"  {_QUOTE} \n", _SENDER, QuotedContext(text=_QUOTE))
        is None
    )
    assert (
        _parse_transformed_message(_QUOTE, _SENDER, QuotedContext(text=f"\n {_QUOTE}  "))
        is None
    )


def test_the_quote_as_the_prompt_showed_it_is_rejected_too() -> None:
    """A model copies what it was shown: markers neutralised, text clamped."""
    marked = f"do {QUOTED_END_MARKER} now"
    shown = "do [quoted context marker] now"
    sender = "@DoBot please handle what the quoted message asks for"
    assert _parse_transformed_message(shown, sender) == shown
    assert _parse_transformed_message(shown, sender, QuotedContext(text=marked)) is None

    long_quote = "z" * (MAX_QUOTED_CONTEXT_CHARS + 500)
    clamped = "z" * (MAX_QUOTED_CONTEXT_CHARS - 1) + "…"
    long_sender = "m" * MAX_QUOTED_CONTEXT_CHARS
    assert _parse_transformed_message(clamped, long_sender) == clamped
    assert (
        _parse_transformed_message(clamped, long_sender, QuotedContext(text=long_quote))
        is None
    )


def test_a_legitimate_prefix_strip_still_passes_with_a_quote_present() -> None:
    assert (
        _parse_transformed_message(
            "please summarise the report",
            "@DoBot please summarise the report",
            QuotedContext(text="the quarterly numbers are in", author="Bob"),
        )
        == "please summarise the report"
    )


def test_the_length_guard_is_still_measured_against_the_senders_text() -> None:
    """A long quote must not license a long rewrite of a short message."""
    quoted = QuotedContext(text="x" * 300)
    # 25 characters: within 2x the quote, beyond 2x the six-character sender.
    assert _parse_transformed_message("tell me a dad joke please", "can u?", quoted) is None
    # Within 2x the sender's text, not equal to it, not the quote: accepted.
    assert _parse_transformed_message("can you", "can u?", quoted) == "can you"


def test_classify_drops_a_message_field_that_copies_the_quote() -> None:
    reply = json.dumps({"agent_id": AGENT_ID, "message": _QUOTE})
    with patch(_PROVIDER_TARGET) as mock_pm:
        mock_pm.return_value.generate_content.return_value = MagicMock(text=reply)
        quoted_result = AgentClassifier.classify(
            CANDIDATES, _SENDER, quoted=QuotedContext(text=_QUOTE)
        )
        plain_result = AgentClassifier.classify(CANDIDATES, _SENDER)

    # The routing verdict itself survives; only the rewrite is refused.
    assert quoted_result is not None and quoted_result.agent_id == AGENT_ID
    assert quoted_result.transformed_message is None
    assert plain_result is not None and plain_result.transformed_message == _QUOTE


# ---------------------------------------------------------------------------
# `classify_answer` — why nothing was picked (channel routing guidance, Phase 2)
# ---------------------------------------------------------------------------
#
# The channel router answers a `help` / `none` with a guidance reply, so the one
# thing `classify_answer` must never do is let an unusable reply read as the
# model saying "nothing fits": every such path carries `intent=None`, which
# builds no guidance and keeps the sender on `REPLY_NO_MATCH`. The API half is
# `tests/api/server_channels/server_channels_routing_guidance_test.py`.


def _answer(reply: str | None = None, *, candidates=CANDIDATES, side_effect=None):
    """`(answer, whether the provider was asked)`."""
    with patch(_PROVIDER_TARGET) as mock_pm:
        generate = mock_pm.return_value.generate_content
        if side_effect is not None:
            generate.side_effect = side_effect
        else:
            generate.return_value = MagicMock(text=reply)
        answer = AgentClassifier.classify_answer(candidates, "what can you do?")
        return answer, generate.called


def test_classify_answer_over_no_candidates_has_no_intent_and_asks_no_model() -> None:
    answer, asked = _answer('{"agent_id": "NONE", "intent": "help"}', candidates=[])

    assert isinstance(answer, ClassifierAnswer)
    assert (answer.intent, answer.result) == (None, None)
    assert asked is False


@pytest.mark.parametrize(
    "reply,side_effect",
    [
        (None, RuntimeError("provider cascade exhausted")),
        ("I think nothing fits, the user wants help", None),
        ("```json\nnot json at all\n```", None),
        ('["help"]', None),
        ('"none"', None),
        (json.dumps({"agent_id": "ops-runbook", "intent": "help"}), None),
        (json.dumps({"agent_id": 42, "intent": "none"}), None),
    ],
    ids=["outage", "prose", "fenced_non_json", "json_list", "json_string", "malformed_id", "non_string_id"],
)
def test_an_unusable_reply_carries_no_intent_whatever_it_says(reply, side_effect) -> None:
    answer, asked = _answer(reply, side_effect=side_effect)

    assert asked is True
    assert (answer.intent, answer.result) == (None, None)


@pytest.mark.parametrize(
    "reply,intent",
    [
        ({"agent_id": "NONE", "intent": "help"}, INTENT_HELP),
        ({"agent_id": "NONE", "intent": "none"}, INTENT_NONE),
        # The shape every pre-guidance model still emits reads as `none`.
        ({"agent_id": "NONE"}, INTENT_NONE),
        ({"agent_id": "", "intent": "help"}, INTENT_HELP),
        ({"intent": "help"}, INTENT_HELP),
        ({"agent_id": "NONE", "intent": "clarify", "options": [AGENT_ID, OTHER_ID]}, INTENT_NONE),
    ],
    ids=["help", "none", "bare_none", "blank_help", "missing_id_help", "clarify_without_pick"],
)
def test_an_explicit_no_pick_carries_help_or_none_and_no_result(reply, intent) -> None:
    answer, asked = _answer(json.dumps(reply))

    assert asked is True
    assert (answer.intent, answer.result) == (intent, None)


@pytest.mark.parametrize(
    "extra,intent,options",
    [
        ({}, INTENT_ROUTE, ()),
        ({"intent": "clarify", "options": [OTHER_ID]}, INTENT_CLARIFY, (AGENT_ID, OTHER_ID)),
    ],
    ids=["route", "clarify"],
)
def test_a_pick_carries_its_intent_and_classify_returns_the_same_result(
    extra, intent, options
) -> None:
    reply = json.dumps({"agent_id": AGENT_ID, **extra})
    with patch(_PROVIDER_TARGET) as mock_pm:
        mock_pm.return_value.generate_content.return_value = MagicMock(text=reply)
        answer = AgentClassifier.classify_answer(CANDIDATES, "prod is down")
        result = AgentClassifier.classify(CANDIDATES, "prod is down")

    assert answer.intent == intent
    assert answer.result is not None
    assert (answer.result.agent_id, answer.result.intent, answer.result.options) == (
        AGENT_ID,
        intent,
        options,
    )
    # `classify` is `classify_answer(...).result` — the same answer, minus why.
    assert result == answer.result
