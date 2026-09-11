"""ACP schema round trip on an isolated scratch database, never app_test.

API authorization and token secrecy scenarios live in
tests/api/acp_integration/test_acp_connectors.py. This test covers database
constraints, cascades and preservation of conversation history on rollback.
"""

import uuid
from collections.abc import Iterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError

from app.core.config import settings

BEFORE = "fc99da75645c"
AFTER = "6bdc1a2e709f"


@pytest.fixture(scope="session", autouse=True)
def setup_db() -> None:
    """Override root setup: this module neither migrates nor seeds app_test."""


def _config(url: str) -> Config:
    config = Config("alembic.ini")
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture
def scratch() -> Iterator[tuple[Engine, str]]:
    """Fresh revision-specific database for each test, dropped even on failure."""
    base = make_url(str(settings.TEST_SQLALCHEMY_DATABASE_URI))
    name = f"app_migration_acp_6bdc1a2e709f_{uuid.uuid4().hex[:10]}"
    admin = create_engine(base.set(database="postgres"), isolation_level="AUTOCOMMIT")
    scratch_url = base.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(scratch_url)
    created = False
    try:
        with admin.connect() as connection:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
            created = True
        command.upgrade(_config(scratch_url), BEFORE)
        yield engine, scratch_url
    finally:
        engine.dispose()
        if created:
            with admin.connect() as connection:
                connection.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def _execute(engine: Engine, sql: str, **params: object) -> None:
    with engine.begin() as connection:
        connection.execute(text(sql), params)


def _rows(engine: Engine, sql: str) -> list[tuple]:
    with engine.connect() as connection:
        return [tuple(row) for row in connection.execute(text(sql))]


def _seed_owner_agent(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    owner_id, agent_id = uuid.uuid4(), uuid.uuid4()
    _execute(
        engine,
        """INSERT INTO "user" (
            id, email, is_active, is_superuser, role, workspaces_enabled,
            task_sequence_counter, two_factor_enabled, email_confirmed, conversation_style
        ) VALUES (:id, :email, true, false, 'agent-developer', false, 0, false, true, 'ai_default')""",
        id=owner_id,
        email=f"{owner_id}@migration.example",
    )
    _execute(
        engine,
        """INSERT INTO agent (
            id, owner_id, name, bundle_id, is_publisher_install, is_active,
            show_on_dashboard, conversation_mode_ui, webapp_enabled,
            agent_api_enabled, agent_api_identity_enabled, agent_api_external_access_enabled,
            created_at, updated_at, update_mode, pending_update
        ) VALUES (:id, :owner, 'Migration agent', :bundle, false, true, true,
            'detailed', false, false, false, false, NOW(), NOW(), 'manual', false)""",
        id=agent_id,
        owner=owner_id,
        bundle=f"migration.{agent_id.hex}",
    )
    return owner_id, agent_id


def _seed_session(
    engine: Engine, owner_id: uuid.UUID, agent_id: uuid.UUID, integration: str | None
) -> uuid.UUID:
    session_id = uuid.uuid4()
    _execute(
        engine,
        """INSERT INTO session (id, user_id, agent_id, mode, status, interaction_status,
            pending_messages_count, created_at, updated_at, integration_type, session_metadata)
        VALUES (:id, :owner, :agent, 'conversation', 'active', '', 0, NOW(), NOW(),
            :integration, '{"preserve":"history"}')""",
        id=session_id,
        owner=owner_id,
        agent=agent_id,
        integration=integration,
    )
    _execute(
        engine,
        """INSERT INTO message (id, session_id, role, content, sequence_number,
            timestamp, status, sent_to_agent_status, message_metadata)
        VALUES (:id, :session, 'user', 'Keep this conversation', 1, NOW(), '', 'sent', '{}')""",
        id=uuid.uuid4(),
        session=session_id,
    )
    return session_id


def _seed_connector_token(
    engine: Engine, owner_id: uuid.UUID, agent_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    connector_id, token_id = uuid.uuid4(), uuid.uuid4()
    _execute(
        engine,
        """INSERT INTO acp_connector (id, agent_id, owner_id, name, mode, is_active,
            max_connections, created_at, updated_at)
        VALUES (:id, :agent, :owner, 'Remote client', 'conversation', true, 10, NOW(), NOW())""",
        id=connector_id,
        agent=agent_id,
        owner=owner_id,
    )
    _execute(
        engine,
        """INSERT INTO acp_token (id, connector_id, token_hash, prefix, label, revoked,
            expires_at, created_at)
        VALUES (:id, :connector, :digest, 'acp_prefix', 'Editor', false,
            '2030-01-02T03:04:05+02:00', NOW())""",
        id=token_id,
        connector=connector_id,
        digest=token_id.hex * 2,
    )
    return connector_id, token_id


def test_acp_schema_constraints_cascades_and_history_survive_roundtrip(
    scratch: tuple[Engine, str],
) -> None:
    engine, url = scratch
    owner, agent = _seed_owner_agent(engine)
    _seed_session(engine, owner, agent, None)
    before = _rows(engine, "SELECT id, content FROM message ORDER BY id")
    command.upgrade(_config(url), AFTER)
    inspector = inspect(engine)
    assert {"acp_connector", "acp_token"} <= set(inspector.get_table_names())
    assert {index["name"] for index in inspector.get_indexes("acp_connector")} == {
        "ix_acp_connector_agent_id",
        "ix_acp_connector_owner_id",
    }
    token_indexes = {
        index["name"]: index for index in inspector.get_indexes("acp_token")
    }
    assert token_indexes["ix_acp_token_token_hash"]["unique"] is True
    assert token_indexes["ix_acp_token_connector_id"]["column_names"] == [
        "connector_id"
    ]
    columns = {column["name"]: column for column in inspector.get_columns("acp_token")}
    assert "token" not in columns
    assert columns["expires_at"]["type"].timezone is True
    assert columns["created_at"]["type"].timezone is True
    assert columns["last_used_at"]["type"].timezone is True
    connector, token = _seed_connector_token(engine, owner, agent)
    for change in ("mode = 'shell'", "max_connections = 0", "max_connections = 101"):
        with pytest.raises(IntegrityError):
            _execute(
                engine,
                f"UPDATE acp_connector SET {change} WHERE id = :id",
                id=connector,
            )
    with pytest.raises(IntegrityError):
        _execute(
            engine,
            "UPDATE acp_token SET connector_id = :ghost WHERE id = :id",
            ghost=uuid.uuid4(),
            id=token,
        )
    other_connector, other_token = _seed_connector_token(engine, owner, agent)
    with pytest.raises(IntegrityError):
        _execute(
            engine,
            "UPDATE acp_token SET token_hash = :duplicate WHERE id = :id",
            duplicate=token.hex * 2,
            id=other_token,
        )

    # Connector deletion kills only its tokens; conversations remain durable.
    _seed_session(engine, owner, agent, "acp")
    _execute(engine, "DELETE FROM acp_connector WHERE id = :id", id=connector)
    assert _rows(engine, "SELECT id FROM acp_token") == [(other_token,)]
    assert len(_rows(engine, "SELECT id FROM session")) == 2

    # Agent and user removal both propagate through the new foreign keys.
    extra_owner, extra_agent = _seed_owner_agent(engine)
    _seed_connector_token(engine, extra_owner, extra_agent)
    _execute(engine, "DELETE FROM agent WHERE id = :id", id=extra_agent)
    assert _rows(engine, "SELECT id FROM acp_connector") == [(other_connector,)]
    extra_owner, extra_agent = _seed_owner_agent(engine)
    _seed_connector_token(engine, extra_owner, extra_agent)
    _execute(engine, 'DELETE FROM "user" WHERE id = :id', id=extra_owner)
    assert _rows(engine, "SELECT id FROM acp_token") == [(other_token,)]

    sessions = _rows(
        engine, "SELECT id, integration_type, session_metadata FROM session ORDER BY id"
    )
    messages = _rows(engine, "SELECT id, content FROM message ORDER BY id")
    assert set(before) <= set(messages)
    command.downgrade(_config(url), BEFORE)
    assert not {"acp_connector", "acp_token"} & set(inspect(engine).get_table_names())
    assert (
        _rows(
            engine,
            "SELECT id, integration_type, session_metadata FROM session ORDER BY id",
        )
        == sessions
    )
    assert _rows(engine, "SELECT id, content FROM message ORDER BY id") == messages
    command.upgrade(_config(url), AFTER)
    assert _rows(engine, "SELECT id FROM acp_connector") == []
    assert _rows(engine, "SELECT id FROM acp_token") == []
    assert _rows(engine, "SELECT id, content FROM message ORDER BY id") == messages
