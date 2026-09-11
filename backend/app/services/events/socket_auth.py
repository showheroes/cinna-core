"""Authentication and room authorization for the Socket.IO surface.

The Socket.IO app is mounted **publicly** at ``/ws`` (``main.py``) with
``cors_allowed_origins="*"``, so the ``connect`` handler is the only thing
standing between the open internet and a user's live event stream. Before this
module existed, ``connect`` read ``user_id`` straight out of the client-supplied
``auth`` dict and joined that client to ``user_{user_id}`` — membership of a
user's event room was self-asserted, and anyone who could reach the socket and
guess a user id received that user's session streams, task status changes and
activities.

Two rules follow from that, and both are load-bearing:

1. **Identity comes from a signed token, never from the client's claim.** A
   caller-supplied ``user_id`` is ignored outright. The token is resolved
   through the *same* functions the REST API uses (``deps.get_current_user`` /
   ``deps.get_webapp_chat_user``) rather than a second decode written here, so
   the socket cannot drift away from the HTTP surface's rules — including the
   ``aud``-at-decode gate that keeps an agent-environment token from resolving
   to the full owner, and the desktop-client revocation check.
2. **A room is joined only if it belongs to the connection's principal.**
   ``subscribe`` used to enter any room by name, which is the same hole one
   level down: ``session_{uuid}_stream`` rooms are guessable in principle and
   were never checked.

Two principal kinds can hold a socket, matching the two front ends that open
one: an ordinary logged-in user, and a public webapp viewer whose JWT's ``sub``
is an ``AgentWebappShare`` id rather than a user id. Every other token type —
guest-share, CLI, agent-environment, agent-API identity — is refused. Nothing
opens a socket with those today, and a refusal is the right default for a
surface whose failure mode is silent disclosure; the place to widen it is
``resolve_principal`` below.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

from sqlmodel import Session as DBSession

from app.models import Session

logger = logging.getLogger(__name__)


PrincipalKind = Literal["user", "webapp_share"]

# The only room shape a client is allowed to ask for by name. Session ids are
# UUIDs; the pattern is deliberately loose about the UUID's internals because
# ``UUID()`` below is the real parser — this only has to isolate the id.
_SESSION_STREAM_ROOM = re.compile(r"^session_([0-9a-fA-F-]{36})_stream$")


@dataclass(frozen=True)
class SocketPrincipal:
    """The authenticated identity behind one socket connection."""

    kind: PrincipalKind
    id: UUID

    @property
    def room(self) -> str:
        """The principal's own broadcast room.

        Note this is ``user_{id}`` for a webapp viewer too: ``emit_event`` maps
        ``user_id`` to ``user_{user_id}``, and webapp chat emits to the share
        id through that same path. The prefix is a room-naming convention, not
        a claim that the id is a user id.
        """
        return f"user_{self.id}"


def resolve_principal(db_session: DBSession, auth: Any) -> SocketPrincipal | None:
    """Resolve the signed token in ``auth`` to a principal, or ``None``.

    Returning ``None`` means "reject this connection". Any client-supplied
    identity hint (the old ``auth["user_id"]``) is ignored.
    """
    # Imported here rather than at module scope: ``app.api.deps`` pulls in
    # services, and services importing it back at import time risks a cycle.
    from fastapi import HTTPException

    from app.api import deps
    from app.core.security import decode_token_claims

    token = auth.get("token") if isinstance(auth, dict) else None
    if not token or not isinstance(token, str):
        return None

    claims = decode_token_claims(token)
    if claims is None:
        # Malformed, expired, wrongly signed, or carrying an ``aud`` (env and
        # agent-API identity tokens do) — ``decode_token_claims`` passes no
        # ``audience=``, so PyJWT rejects those at decode, exactly as
        # ``get_current_user`` does.
        return None

    # Anything the resolvers raise means "no principal". They signal refusal
    # with ``HTTPException``, but a well-signed token with a nonsense ``sub``
    # reaches ``session.get(User, sub)`` and fails in the driver instead — and
    # an authentication gate that *raises* is harder to reason about than one
    # that returns ``None``, so both land in the same place.
    if claims.get("token_type") == "webapp_share":
        try:
            context = deps.get_webapp_chat_user(session=db_session, token=token)
        except HTTPException:
            return None
        except Exception:
            logger.exception("Socket webapp-token resolution failed; refusing")
            return None
        return SocketPrincipal(kind="webapp_share", id=context.webapp_share_id)

    try:
        user = deps.get_current_user(session=db_session, token=token)
    except HTTPException:
        return None
    except Exception:
        logger.exception("Socket user-token resolution failed; refusing")
        return None
    return SocketPrincipal(kind="user", id=user.id)


def can_join_room(
    db_session: DBSession, principal: SocketPrincipal, room: str
) -> bool:
    """Whether ``principal`` may join ``room``.

    Allowed: the principal's own broadcast room, and the stream room of a
    session the principal can already read over HTTP. Everything else — an
    unknown room shape, another principal's room, a session that does not
    exist — is refused.
    """
    if not room or not isinstance(room, str):
        return False

    if room == principal.room:
        return True

    match = _SESSION_STREAM_ROOM.match(room)
    if not match:
        return False

    try:
        session_id = UUID(match.group(1))
    except ValueError:
        return False

    chat_session = db_session.get(Session, session_id)
    if chat_session is None:
        return False

    if principal.kind == "webapp_share":
        # A webapp viewer sees exactly the sessions its own share created —
        # the rule ``WebappChatService.verify_session_access`` enforces on the
        # HTTP side.
        return chat_session.webapp_share_id == principal.id

    from app.services.sessions.session_access import user_can_access_session

    return user_can_access_session(db_session, principal.id, chat_session)
