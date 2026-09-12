"""Inspect transport-only lifecycle state that has no public management endpoint."""

from collections import Counter


def acp_runtime_counts() -> dict[str, int]:
    from app.acp.agent import _active_prompts
    from app.acp.server import acp_runtime

    return {
        "connections": len(acp_runtime.connections),
        "tasks": len(acp_runtime.tasks),
        "admitted": sum(acp_runtime.counts.values()),
        "prompts": len(_active_prompts),
    }


def acp_prompt_slots() -> dict[str, int]:
    """Admitted prompt slots per connector id, for sub-quota assertions.

    ``_active_prompts`` is keyed by an opaque ticket, so the connector counts
    have to be derived rather than read off a key.
    """
    from app.acp.agent import _active_prompts

    return Counter(str(connector_id) for connector_id in _active_prompts.values())
