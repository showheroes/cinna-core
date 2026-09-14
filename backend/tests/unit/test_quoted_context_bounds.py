"""The quote bounds agree across every layer that re-applies them.

Quote-aware channel routing bounds a quoted message's text to 1,000 characters
and its author label to 120, and layering prevents one shared constant: the
adapter (``adapters/base``), the classifier renderer (``agent_classifier``),
the trace recorder (``routing_trace``, which may import nothing from
``app.*``) and the model (``routing_decision``: the column width and the
simulate request's ``max_length``) each define their own.

A drift between them is silent in every other test. An adapter bound above the
render bound just clamps twice; a column narrower than the recorder's cut drops
the author at persist; a simulate request wider than the render bound accepts
text that never reaches the provider. So the numbers are pinned equal here, by
reading the real definitions — including the column type and the request's
validation behaviour, not only the named constants beside them.
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.models.routing import routing_decision
from app.models.routing.routing_decision import RoutingDecision, RoutingSimulateRequest
from app.services.routing import agent_classifier, routing_trace
from app.services.server_channels.adapters import base


def test_the_quoted_text_bound_is_one_number_everywhere() -> None:
    assert base.QUOTED_SNAPSHOT_MAX_CHARS == 1_000
    assert agent_classifier.MAX_QUOTED_CONTEXT_CHARS == base.QUOTED_SNAPSHOT_MAX_CHARS
    assert (
        routing_decision.MAX_SIMULATE_QUOTED_TEXT_CHARS
        == agent_classifier.MAX_QUOTED_CONTEXT_CHARS
    )
    # The trace stores a quote under its own text clamp. It must hold a whole
    # rendered quote, or a replay would re-render a shorter one than the
    # original decision was given.
    assert routing_trace.TRACE_TEXT_MAX_CHARS >= agent_classifier.MAX_QUOTED_CONTEXT_CHARS


def test_the_quoted_author_bound_is_one_number_everywhere() -> None:
    assert base.QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS == 120
    assert agent_classifier.MAX_QUOTED_AUTHOR_CHARS == base.QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS
    assert routing_trace.QUOTED_AUTHOR_MAX_CHARS == base.QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS
    assert routing_decision.MAX_QUOTED_AUTHOR_CHARS == base.QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS
    # The column the recorder hard-cuts to, read off the table itself.
    column = RoutingDecision.__table__.c.quoted_message_author
    assert column.type.length == base.QUOTED_SNAPSHOT_AUTHOR_MAX_CHARS


@pytest.mark.parametrize(
    "field,limit",
    [
        ("quoted_message_text", agent_classifier.MAX_QUOTED_CONTEXT_CHARS),
        ("quoted_message_author", agent_classifier.MAX_QUOTED_AUTHOR_CHARS),
    ],
)
def test_the_simulate_request_enforces_the_same_bounds(field: str, limit: int) -> None:
    """Behaviour, not the ``max_length`` metadata: the request validates."""
    base_body = {"message": "can u?", "as_user_id": str(uuid.uuid4())}

    accepted = RoutingSimulateRequest.model_validate({**base_body, field: "q" * limit})
    assert getattr(accepted, field) == "q" * limit

    with pytest.raises(ValidationError):
        RoutingSimulateRequest.model_validate({**base_body, field: "q" * (limit + 1)})
