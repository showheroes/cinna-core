"""
JSON-RPC utility helpers for the A2A / External A2A surfaces.

These are pure data helpers — they return plain dicts, not HTTPResponse objects.
The route layer is responsible for wrapping them in JSONResponse / StreamingResponse.
"""
from typing import Any, Literal

from app.services.external.errors import InvalidExternalParamsError


def resolve_protocol(protocol_param: str | None) -> Literal["v1.0", "v0.3"]:
    """Resolve the ``?protocol=`` query param to a canonical version string.

    Accepted values:
      ``v1.0`` / ``v1``   → ``"v1.0"``
      ``v0.3`` / ``v0.3.0`` → ``"v0.3"``
      ``None``             → ``"v1.0"``  (default)

    Raises:
        InvalidExternalParamsError: For any other value.
    """
    if protocol_param is None or protocol_param in ("v1.0", "v1"):
        return "v1.0"
    if protocol_param in ("v0.3", "v0.3.0"):
        return "v0.3"
    raise InvalidExternalParamsError(
        f"Unknown protocol: {protocol_param!r}. Use 'v1.0' (default) or 'v0.3'."
    )


def jsonrpc_success(request_id: Any, result: Any) -> dict:
    """Build a standard JSON-RPC 2.0 success envelope dict.

    Returns a plain dict — callers are responsible for wrapping in JSONResponse.
    """
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def jsonrpc_error(request_id: Any, code: int, message: str) -> dict:
    """Build a standard JSON-RPC 2.0 error envelope dict.

    Returns a plain dict — callers are responsible for wrapping in JSONResponse.
    """
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
