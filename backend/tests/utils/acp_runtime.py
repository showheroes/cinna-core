"""Inspect transport-only lifecycle state that has no public management endpoint."""


def acp_runtime_counts() -> dict[str, int]:
    from app.acp.agent import _active_prompts
    from app.acp.server import acp_runtime

    return {
        "connections": len(acp_runtime.connections),
        "tasks": len(acp_runtime.tasks),
        "admitted": sum(acp_runtime.counts.values()),
        "sessions": len(_active_prompts),
    }
