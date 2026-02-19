"""
IMAP and SMTP test stubs matching the connector interfaces.

StubIMAPConnector returns preconfigured raw emails.
StubSMTPConnector captures sent emails for assertion.
"""


class _MockIMAPConnection:
    """Mimics imaplib.IMAP4 for a single INBOX with preconfigured messages."""

    def __init__(self, emails: list[bytes]):
        self._emails = emails

    def select(self, mailbox="INBOX", readonly=False):
        return ("OK", [b"1"])

    def search(self, charset, criteria):
        if not self._emails:
            return ("OK", [b""])
        ids = b" ".join(str(i + 1).encode() for i in range(len(self._emails)))
        return ("OK", [ids])

    def fetch(self, msg_id, parts):
        idx = int(msg_id) - 1
        if 0 <= idx < len(self._emails):
            return ("OK", [(b"1 (RFC822 {0})", self._emails[idx])])
        return ("NO", None)

    def store(self, msg_id, flags_op, flags):
        return ("OK", None)

    def close(self):
        pass

    def logout(self):
        pass


class StubIMAPConnector:
    """Returns preconfigured raw emails. Tracks connect calls."""

    def __init__(self, emails: list[bytes] | None = None):
        self.emails = emails or []
        self.connect_calls: list[tuple] = []

    def connect(self, server, password):
        self.connect_calls.append((server.host, server.username))
        return _MockIMAPConnection(self.emails)


class StubSMTPConnector:
    """Captures sent emails for assertion. Tracks all send() calls."""

    def __init__(self):
        self.sent_emails: list[dict] = []

    def send(self, server, password, from_address, to_address, msg):
        self.sent_emails.append({
            "from": from_address,
            "to": to_address,
            "msg": msg,
            "server_host": server.host,
        })
