"""Anchored per-turn placement directives; never match a mid-sentence phrase."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ReplyDirective:
    text: str
    reply_here: bool = True


def match_reply_directive(
    text: str, phrase: str = "reply here"
) -> ReplyDirective | None:
    if not phrase.strip():
        return None
    match = re.search(
        r"(?:^|\n|(?<=[.!?])[ \t]+)[ \t]*" + re.escape(phrase.strip()) + r"[.!?]*\s*\Z",
        text,
        re.IGNORECASE,
    )
    if match is None:
        return None
    return ReplyDirective(text=text[: match.start()].rstrip())


def strip_reply_here(text: str, phrase: str = "reply here") -> tuple[str, bool]:
    directive = match_reply_directive(text, phrase)
    return (directive.text, True) if directive else (text, False)
