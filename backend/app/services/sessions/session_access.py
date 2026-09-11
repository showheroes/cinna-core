"""Who may read a chat session.

Extracted from ``api/routes/sessions.py::_verify_session_access`` so the
Socket.IO stream-room check and the HTTP routes decide the same question with
the same code. The route keeps its own raising wrapper (its two different
status codes are part of its contract); only the *decision* lives here.
"""

import logging
from uuid import UUID

from sqlmodel import Session as DBSession

from app.models import Session
from app.models.users.user import User

logger = logging.getLogger(__name__)


def user_can_access_session(
    db_session: DBSession, user: User | UUID, chat_session: Session
) -> bool:
    """Whether an authenticated user may read ``chat_session``.

    True when the user is a superuser, owns the session, or holds a grant for
    the guest share the session was created through.

    ``user`` accepts a ``User`` or a bare id. The id form cannot short-circuit
    on ``is_superuser`` without a lookup, so it does one — callers that already
    hold the row should pass it.
    """
    if isinstance(user, UUID):
        loaded = db_session.get(User, user)
        if loaded is None:
            return False
        user = loaded

    if user.is_superuser:
        return True

    if chat_session.user_id == user.id:
        return True

    if chat_session.guest_share_id:
        # Imported lazily: the sharing service imports session models, and a
        # module-level import here would close the loop.
        from app.services.sharing.agent_guest_share_service import (
            AgentGuestShareService,
        )

        return bool(
            AgentGuestShareService.check_grant(
                db_session, user.id, chat_session.guest_share_id
            )
        )

    return False


def guest_can_access_session(
    guest_share_id: UUID, chat_session: Session
) -> bool:
    """Whether an anonymous guest-share caller may read ``chat_session``."""
    return chat_session.guest_share_id == guest_share_id
