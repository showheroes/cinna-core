"""Trailing per-turn placement directives; never match a phrase before the end."""

import re
from dataclasses import dataclass

#: Joiners between the question and a trailing phrase ("joke, reply here",
#: "joke - reply here"). Stripped with the phrase; sentence terminators stay.
_TRAILING_JOINERS = re.compile(r"[\s,;:\-–—]+\Z")


@dataclass(frozen=True)
class ReplyDirective:
    text: str
    reply_here: bool = True


def match_reply_directive(
    text: str, phrase: str = "reply here"
) -> ReplyDirective | None:
    if not phrase.strip():
        return None
    # Whatever precedes the phrase counts as a separator, as long as the phrase
    # is not the tail of a longer word.
    match = re.search(
        r"(?<!\w)" + re.escape(phrase.strip()) + r"[.!?]*\s*\Z",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return ReplyDirective(text=_TRAILING_JOINERS.sub("", text[: match.start()]))


def strip_reply_here(text: str, phrase: str = "reply here") -> tuple[str, bool]:
    directive = match_reply_directive(text, phrase)
    return (directive.text, True) if directive else (text, False)
