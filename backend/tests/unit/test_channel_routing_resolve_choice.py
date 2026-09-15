"""`resolve_choice` / `is_selector_like` — reading a reply to the router's question.

Channel routing guidance, Phase 3. Both pure. `resolve_choice` maps a reply and
the options the question offered to a ``ref_id``, ``CHOICE_CANCEL`` or ``None``.
``None`` is not a failure: the inbound path then asks `is_selector_like`
whether the reply is short enough (``CLARIFY_SELECTOR_MAX_WORDS`` words after
filler) to be worth one classifier call over the options, and routes anything
longer as a new request. So the properties worth pinning are that a NEW request
which merely contains a digit, starts with a filler word or mentions a name in
passing is never read as a choice, and that an ambiguous reply never guesses.

The API-observable round-trip (the question, "2" routing the original message,
the classifier fallback for a short reply, a long reply routing fresh, cancel,
expiry) is `tests/api/server_channels/server_channels_routing_clarification_test.py`.

No DB, no Docker, no LLM calls.
"""
import pytest

from app.services.server_channels.channel_routing_guidance import (
    CHOICE_CANCEL,
    CLARIFY_SELECTOR_MAX_WORDS,
    ENTRY_AGENT,
    ENTRY_BUNDLE,
    ENTRY_IDENTITY,
    ClarificationOption,
    is_selector_like,
    resolve_choice,
)

JOKER = ClarificationOption(ref_id="ref-joker", name="Joker", kind=ENTRY_AGENT)
HR = ClarificationOption(ref_id="ref-hr", name="HR Helper", kind=ENTRY_AGENT)
WRITER = ClarificationOption(ref_id="ref-writer", name="Writer", kind=ENTRY_AGENT)
TWO = (JOKER, HR)
THREE = (JOKER, HR, WRITER)


def _option(ref_id: str, name: str, kind: str = ENTRY_AGENT) -> ClarificationOption:
    return ClarificationOption(ref_id=ref_id, name=name, kind=kind)


# ---------------------------------------------------------------------------
# 1. Ordinals
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("1", "ref-joker"),
        ("2", "ref-hr"),
        ("3", "ref-writer"),
        (" 2 ", "ref-hr"),
        ("#2", "ref-hr"),
        ("2.", "ref-hr"),
        ("option 2", "ref-hr"),
        ("Option #2", "ref-hr"),
        ("number 3", "ref-writer"),
        ("no 2", "ref-hr"),
        ("no. 2", "ref-hr"),
        ("first", "ref-joker"),
        ("Second", "ref-hr"),
        ("THIRD", "ref-writer"),
        ("1st", "ref-joker"),
        ("2nd", "ref-hr"),
        ("3rd", "ref-writer"),
        ("one", "ref-joker"),
        ("two", "ref-hr"),
        ("three", "ref-writer"),
        ("the second one", "ref-hr"),
        ("I choose 1", "ref-joker"),
        ("go with the first one please", "ref-joker"),
        ("pick 3 thanks", "ref-writer"),
    ],
)
def test_an_ordinal_names_the_option_the_question_numbered(reply: str, expected: str) -> None:
    assert resolve_choice(reply, THREE) == expected


@pytest.mark.parametrize("reply", ["3", "#3", "option 3", "third", "3rd", "0", "4"])
def test_an_ordinal_past_the_offered_options_names_nothing(reply: str) -> None:
    assert resolve_choice(reply, TWO) is None


def test_the_number_still_picks_between_two_options_with_the_same_name() -> None:
    twins = (_option("a", "Joker"), _option("b", "joker", ENTRY_BUNDLE))
    assert resolve_choice("joker", twins) is None
    assert resolve_choice("2", twins) == "b"


# ---------------------------------------------------------------------------
# 2. Names: exact, prefix, unique substring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("Joker", "ref-joker"),
        ("joker", "ref-joker"),
        ("JOKER!", "ref-joker"),
        ("hr helper", "ref-hr"),
        ("HR-Helper", "ref-hr"),
        ("  HR   Helper. ", "ref-hr"),
        ("writer?", "ref-writer"),
    ],
)
def test_an_exact_name_matches_regardless_of_case_spacing_and_punctuation(
    reply: str, expected: str
) -> None:
    assert resolve_choice(reply, THREE) == expected


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("jok", "ref-joker"),
        ("wri", "ref-writer"),
        ("hr h", "ref-hr"),
        ("joker please", "ref-joker"),
        ("the writer one", "ref-writer"),
        ("helper", "ref-hr"),
        ("oker", "ref-joker"),
    ],
)
def test_a_prefix_or_a_unique_substring_of_one_name_matches_it(reply: str, expected: str) -> None:
    assert resolve_choice(reply, THREE) == expected


@pytest.mark.parametrize("reply", ["j", "jo", "hr", "ok"])
def test_a_prefix_or_substring_shorter_than_three_characters_matches_nothing(
    reply: str,
) -> None:
    # "jo" / "hr" start a name and "ok" is inside "joker": all too weak to read.
    assert resolve_choice(reply, THREE) is None


def test_hi_never_selects_hiring_helper() -> None:
    options = (_option("ref-hiring", "Hiring Helper"), JOKER)
    assert resolve_choice("hi", options) is None
    assert resolve_choice("hi!", options) is None
    # Control: three characters of the same name do select it.
    assert resolve_choice("hir", options) == "ref-hiring"


def test_an_ambiguous_prefix_or_substring_names_nothing_rather_than_guessing() -> None:
    options = (
        _option("ref-sales-desk", "Sales Desk"),
        _option("ref-sales-ops", "Sales Ops"),
        _option("ref-support-desk", "Support Desk", ENTRY_BUNDLE),
    )
    assert resolve_choice("sales", options) is None  # a prefix of two
    assert resolve_choice("desk", options) is None  # a substring of two
    # Controls: the same levels with exactly one match do resolve.
    assert resolve_choice("sup", options) == "ref-support-desk"
    assert resolve_choice("ops", options) == "ref-sales-ops"


def test_an_identity_option_is_matched_by_the_name_the_question_showed() -> None:
    """An identity owner with no full name is named by email; the question
    shows the local part only, so that is what an answer can name."""
    anna = _option("identity:anna", "anna.smith@corp.example", ENTRY_IDENTITY)
    options = (JOKER, anna)
    assert resolve_choice("anna.smith", options) == "identity:anna"
    assert resolve_choice("Anna", options) == "identity:anna"
    # The domain was never shown and is not a name.
    assert resolve_choice("corp.example", options) is None


# ---------------------------------------------------------------------------
# 3. A name inside a short answer — at most two extra words
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("tell joker hi", "ref-joker"),  # one-word name + 2
        ("tell joker hi there", None),  # one-word name + 3
        ("ask hr helper now", "ref-hr"),  # two-word name + 2
        ("please ask hr helper now", None),  # two-word name + 3
        ("write a joke about the writer", None),
    ],
)
def test_a_name_inside_an_answer_counts_only_within_two_extra_words(
    reply: str, expected: str | None
) -> None:
    assert resolve_choice(reply, THREE) == expected


# ---------------------------------------------------------------------------
# 4. Declines — read on the whole reply, before filler is stripped
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "neither",
        "None",
        "cancel",
        "Cancel.",
        "no",
        "No!",
        "no thanks",
        "No, thanks!",
        "no thank you",
        "No thank you.",
        "nope",
        "Nope!",
        "neither of them",
        "Neither of those",
        "None of these",
        "none of those",
        "never mind",
        "Nevermind!",
    ],
)
def test_a_decline_cancels_the_question(reply: str) -> None:
    assert resolve_choice(reply, TWO) == CHOICE_CANCEL


def test_a_decline_wins_over_a_name_it_would_otherwise_prefix() -> None:
    """"no" is checked before any other level, so an option whose name starts
    with it cannot turn a refusal into a pick."""
    options = (_option("ref-notes", "Notes Bot"), JOKER)
    assert resolve_choice("no", options) == CHOICE_CANCEL
    # Control: a prefix that is neither a decline nor a negation ("not") does.
    assert resolve_choice("note", options) == "ref-notes"


# ---------------------------------------------------------------------------
# 5. What is NOT a choice
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply",
    [
        "not joker",
        "Not the writer",
        "no joker",
        "No, the writer",
        "joker? no",
        "don't pick joker",
        "dont pick joker",
        "don’t pick joker",
        "the writer isn't it",
        "never hr helper",
        "anyone except joker",
    ],
)
def test_a_negation_never_reads_as_choosing_the_option_it_names(reply: str) -> None:
    """"no" is leading filler and a name may carry two extra words, so without
    the negation rule "no joker" and "not the writer" each picked the option
    they refuse. `None` instead, and still short enough for the classifier."""
    assert resolve_choice(reply, THREE) is None
    assert is_selector_like(reply)


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("no", CHOICE_CANCEL),
        ("no thanks", CHOICE_CANCEL),
        ("No, thanks!", CHOICE_CANCEL),
        ("no 2", "ref-hr"),
        ("No. 3", "ref-writer"),
        ("no second", "ref-hr"),
    ],
)
def test_no_alone_still_cancels_and_no_before_a_number_still_chooses(
    reply: str, expected: str
) -> None:
    assert resolve_choice(reply, THREE) == expected


@pytest.mark.parametrize(
    "reply",
    [
        "book 2 tickets to Paris",
        "2 more days of leave please",
        "I need 3 days off next week",
        "the printer on floor 2 is broken",
        "take the day off tomorrow",
        "no thanks, I need a new laptop",
        "none of these work, I need payroll",
        "cancel my meeting with the joker team tomorrow",
    ],
)
def test_a_new_request_with_a_digit_a_filler_or_a_decline_word_inside_is_not_a_choice(
    reply: str,
) -> None:
    assert resolve_choice(reply, THREE) is None


@pytest.mark.parametrize("reply", ["the", "go", "option", "please", "with"])
def test_a_lone_filler_word_never_prefix_matches_a_name(reply: str) -> None:
    options = (
        _option("ref-theo", "Theo"),
        _option("ref-gopher", "Gopher"),
        _option("ref-optional", "Optional Tasks"),
        _option("ref-pleasant", "Pleasant Replies"),
        _option("ref-withholding", "Withholding Tax"),
    )
    assert resolve_choice(reply, options) is None
    # Control: a prefix that is not a filler word does match the same list.
    assert resolve_choice("pleas", options) == "ref-pleasant"


@pytest.mark.parametrize("reply", [None, "", "   ", "?!", 42])
def test_an_unreadable_reply_names_nothing(reply) -> None:
    assert resolve_choice(reply, TWO) is None


def test_no_options_means_nothing_can_be_named() -> None:
    assert resolve_choice("1", ()) is None
    assert resolve_choice("joker", []) is None
    assert resolve_choice("neither", ()) is None


# ---------------------------------------------------------------------------
# 6. is_selector_like — which unread replies are worth classifying as a pick
# ---------------------------------------------------------------------------


def test_the_selector_limit_is_four_words() -> None:
    # Pinned: the API test's "long reply" is written against this number.
    assert CLARIFY_SELECTOR_MAX_WORDS == 4


@pytest.mark.parametrize(
    "reply,expected",
    [
        ("the payroll person", True),
        ("sort out payroll today", True),  # exactly 4
        ("sort out my payroll today", False),  # 5
        ("the payroll person thanks", True),  # filler at both ends is not counted
        ("i pick the hr one please", True),  # -> "hr"
        ("option number 2 please", True),
        ("tell me a long joke about cats please", False),
        ("please sort out my payroll today", False),  # "please" leads: not filler there
    ],
)
def test_a_reply_is_selector_like_only_within_four_words_after_filler(
    reply: str, expected: bool
) -> None:
    assert is_selector_like(reply) is expected


@pytest.mark.parametrize("reply", [None, "", "   ", "?!", 42])
def test_an_unreadable_reply_is_not_selector_like(reply) -> None:
    assert is_selector_like(reply) is False
