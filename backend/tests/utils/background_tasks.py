"""Shared background task collector for tests.

Allows test utilities (e.g. process_emails_with_stub) to drain
collected background tasks without the test explicitly managing them.
"""
import asyncio

_collector = None


def set_collector(collector):
    global _collector
    _collector = collector


def drain_tasks():
    """Drain all collected background tasks synchronously.

    Must be called from the test thread (not from inside the ASGI event loop).
    Handles cascading tasks (tasks spawned during execution).
    """
    if not _collector:
        return
    _collector.run_all()
