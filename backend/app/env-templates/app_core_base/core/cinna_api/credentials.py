"""
Fresh-read credentials accessor for agent scripts and the agent REST API SDK.

The platform syncs every credential linked to the agent into
``/app/workspace/credentials/credentials.json``. This accessor centralises
reading it — for a producer's ``agent_api`` handlers and for any workspace or
skill script.

CRITICAL: the file is read **fresh on every access**. The serving child is a
long-running process; if we cached the parsed credentials at import time we would
serve stale secrets across an OAuth refresh or a credential resync (the old
subprocess-per-request webapp model got freshness for free — this one must not
regress it).

Slots
-----
A skill finds its credential by **slot**: the credential's non-secret
``service_uri``, carried top-level on every real entry together with
``is_placeholder``. :meth:`_Credentials.require_slot` raises
:class:`CredentialMissing` with a message that names the slot and the fix, so a
script can fail in a way the agent can relay to the user verbatim.

This module must stay importable with no network and without ``requests``:
:class:`AgentApiSession` is defined on first use.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

logger = logging.getLogger(__name__)

_CREDENTIALS_PATH = Path(
    os.getenv("CINNA_CREDENTIALS_PATH", "/app/workspace/credentials/credentials.json")
)

#: ``type`` markers of the synthetic entries the platform appends to
#: credentials.json. They are not credentials and never satisfy a slot.
#: Mirrors ``user_details_service.CURRENT_USER_TYPE`` and
#: ``agent_api_identity_service.OWNER_IDENTITY_TYPE`` (guarded by a unit test).
_CURRENT_USER_TYPE = "current_user"
_OWNER_IDENTITY_TYPE = "owner_identity_token"
_SYNTHETIC_TYPES = frozenset({_CURRENT_USER_TYPE, _OWNER_IDENTITY_TYPE})

_AGENT_API_TYPE = "agent_api"


class CredentialMissing(Exception):
    """A slot the script needs has no usable credential.

    ``reason`` is ``"not_linked"`` (no credential with this slot is linked to
    the agent) or ``"not_configured"`` (one is linked but not filled in yet).
    ``str(exc)`` is stable and written for a person: relay it verbatim.
    """

    def __init__(self, slot: str, reason: str):
        # ``args`` must be the constructor arguments so the exception
        # round-trips through pickle; ``__str__`` builds the message.
        super().__init__(slot, reason)
        self.slot = slot
        self.reason = reason

    def __str__(self) -> str:
        if self.reason == "not_configured":
            return (
                f"credential_missing: the credential for slot '{self.slot}' is "
                "linked but not filled in yet. Fix: open the agent's Credentials "
                "tab and complete it."
            )
        return (
            f"credential_missing: no credential for slot '{self.slot}' is linked "
            "to this agent. Fix: open the agent's Credentials tab and link a "
            f"credential whose service URI (slot) is '{self.slot}'."
        )


_DEFAULT_PORTS = {"http": 80, "https": 443}


def _origin(url: str) -> tuple[str, str, int | None] | None:
    """``(scheme, host, effective port)`` of an absolute URL, lowercased.

    ``None`` when the URL has no host or an unparseable port, which never
    equals any origin.
    """
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return None
    if not parts.hostname:
        return None
    scheme = parts.scheme.lower()
    if port is None:
        port = _DEFAULT_PORTS.get(scheme)
    return scheme, parts.hostname.lower(), port


_agent_api_session_class: type | None = None


def _get_agent_api_session_class() -> type:
    """Define :class:`AgentApiSession` on first use, so importing this module
    never imports ``requests``."""
    global _agent_api_session_class
    if _agent_api_session_class is not None:
        return _agent_api_session_class

    import requests
    from requests.structures import CaseInsensitiveDict

    class AgentApiSession(requests.Session):
        """A ``requests.Session`` pre-authorised for one ``agent_api`` connection.

        A relative ``url`` is joined onto :attr:`base_url` with exactly one
        ``/``; an absolute ``http(s)://`` URL is sent as given.

        Credentials only go to the producer. The ``Authorization`` and
        caller-identity headers are sent only when the request URL has the same
        origin as :attr:`base_url`: scheme, host and effective port, with scheme
        and host compared case-insensitively. A relative URL always gets them.
        An absolute URL to any other origin is sent without them. A header the
        caller passes explicitly for that one request is still sent. The
        session's own headers are never changed.

        Redirects follow the same rule: a redirect whose target origin is not
        :attr:`base_url`'s origin (a different host, scheme or port, so also a
        same-host http→https upgrade) loses both headers before it is sent.

        Only the verb methods (``get``, ``post``, ... and ``request``) are
        guarded. ``session.send(session.prepare_request(...))`` bypasses
        :meth:`request` and sends the session headers to any URL, so scripts
        should use the verb methods.
        """

        def __init__(self, base_url: str, spec_url: str | None):
            super().__init__()
            self.base_url = base_url
            self.spec_url = spec_url
            self._credential_header_names: list[str] = []

        def set_credential_header(self, name: str, value: str) -> None:
            """Set a session header sent only to :attr:`base_url`'s origin."""
            self.headers[name] = value
            self._credential_header_names.append(name)

        def request(self, method, url, *args, **kwargs):  # type: ignore[override]
            target = str(url)
            if not target.lower().startswith(("http://", "https://")):
                target = f"{self.base_url.rstrip('/')}/{target.lstrip('/')}"
            elif not self._is_producer_origin(target):
                # ``headers`` is the third positional after method and url.
                if len(args) > 2:
                    args = (*args[:2], self._without_credentials(args[2]), *args[3:])
                else:
                    kwargs["headers"] = self._without_credentials(
                        kwargs.get("headers")
                    )
            return super().request(method, target, *args, **kwargs)

        def _is_producer_origin(self, url: str) -> bool:
            origin = _origin(url)
            return origin is not None and origin == _origin(self.base_url)

        def _without_credentials(self, headers: Any) -> CaseInsensitiveDict:
            # requests drops a merged header whose per-request value is None.
            merged = CaseInsensitiveDict(headers or {})
            for name in self._credential_header_names:
                if name not in merged:
                    merged[name] = None
            return merged

        def rebuild_auth(self, prepared_request, response):  # type: ignore[override]
            # requests strips only ``Authorization``, and only on a host
            # change; the caller-identity header would otherwise follow a
            # redirect anywhere.
            super().rebuild_auth(prepared_request, response)
            if not self._is_producer_origin(str(prepared_request.url)):
                for name in self._credential_header_names:
                    if name in prepared_request.headers:
                        del prepared_request.headers[name]

    _agent_api_session_class = AgentApiSession
    return AgentApiSession


class _Credentials:
    """Typed accessor over credentials.json. Reads the file fresh on each call."""

    def _load(self) -> list[dict]:
        """Read + parse credentials.json. Returns [] when missing/unreadable."""
        try:
            if not _CREDENTIALS_PATH.is_file():
                return []
            with open(_CREDENTIALS_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            # Tolerate a {"credentials": [...]} envelope just in case.
            if isinstance(data, dict) and isinstance(data.get("credentials"), list):
                return data["credentials"]
            logger.warning("credentials.json has unexpected shape: %s", type(data).__name__)
            return []
        except (OSError, json.JSONDecodeError) as e:
            logger.warning("Failed to read credentials.json: %s", e)
            return []

    def all(self) -> list[dict]:
        """Return every credential dict (read fresh)."""
        return self._load()

    def get(self, credential_id: str) -> dict | None:
        """
        Return the credential whose ``id`` (or ``name``) matches, or None.

        Reads the file fresh so a just-refreshed token is picked up.
        """
        for cred in self._load():
            if str(cred.get("id")) == str(credential_id) or cred.get("name") == credential_id:
                return cred
        return None

    def by_type(self, credential_type: str) -> dict | None:
        """
        Return the first credential of the given ``type`` (e.g. "odoo",
        "email_imap"), or None. Reads the file fresh.
        """
        for cred in self._load():
            if cred.get("type") == credential_type:
                return cred
        return None

    def all_by_type(self, credential_type: str) -> list[dict]:
        """Return every credential of the given ``type`` (read fresh)."""
        return [c for c in self._load() if c.get("type") == credential_type]

    def by_slot(self, slot: str) -> dict | None:
        """
        Return the first real credential whose ``service_uri`` equals ``slot``,
        or None. Synthetic entries never match. Reads the file fresh.
        """
        return self._find_slot(self._load(), slot)

    def require_slot(self, slot: str) -> dict:
        """
        Return the credential for ``slot``, or raise :class:`CredentialMissing`:
        ``not_linked`` when none is linked, ``not_configured`` when the linked
        one is still a placeholder. Reads the file fresh.
        """
        return self._require_slot_in(self._load(), slot)

    def agent_api_session(self, slot: str) -> Any:
        """
        Return an ``AgentApiSession`` (a ``requests.Session``) for the
        ``agent_api`` connection in ``slot``: ``Authorization: Bearer <token>``
        plus the caller-identity header when the platform provided one, and
        ``.base_url`` / ``.spec_url`` from the connection.

        Raises :class:`CredentialMissing` like :meth:`require_slot`, and
        ``ValueError`` when the slot holds a credential of another type.
        """
        entries = self._load()
        entry = self._require_slot_in(entries, slot)
        if entry.get("type") != _AGENT_API_TYPE:
            raise ValueError(
                f"The credential for slot '{slot}' is of type "
                f"'{entry.get('type')}', not '{_AGENT_API_TYPE}'."
            )

        data = entry.get("credential_data") or {}
        session = _get_agent_api_session_class()(
            base_url=str(data.get("base_url") or ""),
            spec_url=data.get("spec_url"),
        )
        session.set_credential_header(
            "Authorization", f"Bearer {data.get('token') or ''}"
        )

        identity = next(
            (e for e in entries if e.get("type") == _OWNER_IDENTITY_TYPE), None
        )
        if identity is not None:
            identity_data = identity.get("credential_data") or {}
            header, token = identity_data.get("header"), identity_data.get("token")
            if header and token:
                session.set_credential_header(header, token)
        return session

    @staticmethod
    def _find_slot(entries: list[dict], slot: str) -> dict | None:
        for cred in entries:
            if cred.get("type") in _SYNTHETIC_TYPES:
                continue
            if cred.get("service_uri") == slot:
                return cred
        return None

    @classmethod
    def _require_slot_in(cls, entries: list[dict], slot: str) -> dict:
        entry = cls._find_slot(entries, slot)
        if entry is None:
            raise CredentialMissing(slot, "not_linked")
        if entry.get("is_placeholder") is True:
            raise CredentialMissing(slot, "not_configured")
        return entry


# Singleton accessor — stateless (no caching), safe to import once.
credentials = _Credentials()
