"""
Domain exceptions for the External Agent Access API surface.

Hierarchy:
  ExternalAccessError (base)
    TargetNotAccessibleError    — agent/route/identity not found or caller lacks access
    NoActiveEnvironmentError    — agent exists but has no active environment
    TaskScopeViolationError     — task_id belongs to a different caller
    IdentityBindingRevokedError — mid-conversation binding/assignment was disabled
  InvalidExternalParamsError   — invalid JSON-RPC params (jsonrpc_code -32602)

  ExternalSessionError (base, HTTP surface)
    SessionNotVisibleError      — session not found / not visible to caller (HTTP 404)

Usage
-----
Routes catch ExternalAccessError subclasses (and InvalidExternalParamsError) and
convert them to JSON-RPC error envelopes using ``exception.jsonrpc_code``.

Routes catch ExternalSessionError subclasses and convert them to HTTPException
using ``exception.http_status``.
"""
from http import HTTPStatus


class ExternalAccessError(Exception):
    """Base domain exception for external A2A access violations.

    All subclasses carry a ``jsonrpc_code`` attribute so the route layer can
    translate them to JSON-RPC error envelopes without substring matching.
    """

    jsonrpc_code: int = -32004

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class TargetNotAccessibleError(ExternalAccessError):
    """Target (agent/route/identity) not found or caller lacks access.

    Maps to JSON-RPC code -32004.
    """

    jsonrpc_code: int = -32004

    def __init__(self, message: str = "Target not found or access denied") -> None:
        super().__init__(message)


class NoActiveEnvironmentError(ExternalAccessError):
    """Agent exists but has no active environment.

    Maps to JSON-RPC code -32004.
    """

    jsonrpc_code: int = -32004

    def __init__(self, message: str = "Agent has no active environment") -> None:
        super().__init__(message)


class TaskScopeViolationError(ExternalAccessError):
    """task_id supplied by the caller belongs to a different caller.

    Maps to JSON-RPC code -32004.
    """

    jsonrpc_code: int = -32004

    def __init__(self, message: str = "Task does not belong to this caller") -> None:
        super().__init__(message)


class IdentityBindingRevokedError(ExternalAccessError):
    """The identity binding or assignment was disabled mid-conversation.

    Maps to JSON-RPC code -32004.
    """

    jsonrpc_code: int = -32004

    def __init__(
        self, message: str = "This identity connection is no longer active."
    ) -> None:
        super().__init__(message)


class InvalidExternalParamsError(Exception):
    """Invalid JSON-RPC params (e.g. unknown protocol version, bad method).

    Maps to JSON-RPC code -32602 (InvalidParams).
    """

    jsonrpc_code: int = -32602

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


# ---------------------------------------------------------------------------
# HTTP-surface exceptions (session metadata endpoints)
# ---------------------------------------------------------------------------


class ExternalSessionError(Exception):
    """Base exception for the HTTP session metadata surface.

    Subclasses carry an ``http_status`` attribute so routes can translate them
    to ``HTTPException`` without substring matching.
    """

    http_status: int = HTTPStatus.BAD_REQUEST.value

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class SessionNotVisibleError(ExternalSessionError):
    """Session not found or not visible to the current caller.

    Maps to HTTP 404.
    """

    http_status: int = HTTPStatus.NOT_FOUND.value

    def __init__(self, message: str = "Session not found") -> None:
        super().__init__(message)
