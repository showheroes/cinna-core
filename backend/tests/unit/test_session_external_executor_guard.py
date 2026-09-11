"""Defend task execution at the final session-creation boundary.

The API lifecycle is covered by
``tests/api/input_tasks/test_task_external_executor.py``. Its Execute call
normally rejects at the earlier task-service gate, so it cannot prove this
second gate survives. Here a mocked database supplies the task as observed at
session creation, after an external client could have claimed it.

These are pure defensive-branch tests: no real database or TestClient. They
prove the late refusal and permitted insert, not PostgreSQL lock scheduling.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlmodel import Session as DBSession

from app.models import Agent, Session, SessionCreate
from app.services.sessions.session_service import SessionService
from app.services.tasks.input_task_service import ValidationError


def _session_creation_db(external_executor: str | None):
    agent = SimpleNamespace(
        id=uuid4(), active_environment_id=uuid4(), user_workspace_id=uuid4(),
    )
    task = SimpleNamespace(id=uuid4(), external_executor=external_executor)
    db = MagicMock(spec=DBSession)

    def get_agent(model, identity):
        assert model is Agent
        assert identity == agent.id
        return agent

    db.get.side_effect = get_agent
    task_result = MagicMock()
    task_result.one_or_none.return_value = task
    # Only the task lookup receives this result; unexpected later queries fail.
    db.exec.side_effect = [task_result]
    return db, agent, task, task_result


def test_session_creation_refuses_task_claimed_by_external_executor() -> None:
    """A late claim refuses session creation before any insert or commit."""
    db, agent, task, task_result = _session_creation_db("Desktop")

    with pytest.raises(ValidationError, match="Desktop"):
        SessionService.create_session(
            db_session=db,
            user_id=uuid4(),
            data=SessionCreate(agent_id=agent.id),
            source_task_id=task.id,
        )

    task_result.one_or_none.assert_called_once_with()
    db.add.assert_not_called()
    db.commit.assert_not_called()
    db.refresh.assert_not_called()


def test_session_creation_allows_task_without_external_executor() -> None:
    """The same late check permits a real Session model with its task link."""
    db, agent, task, task_result = _session_creation_db(None)
    owner_id = uuid4()

    created = SessionService.create_session(
        db_session=db,
        user_id=owner_id,
        data=SessionCreate(agent_id=agent.id, title="Cinna execution"),
        source_task_id=task.id,
        integration_type="task",
    )

    task_result.one_or_none.assert_called_once_with()
    assert isinstance(created, Session)
    assert created.source_task_id == task.id
    assert created.user_id == owner_id
    assert created.agent_id == agent.id
    assert created.environment_id == agent.active_environment_id
    assert created.integration_type == "task"
    db.add.assert_called_once_with(created)
    db.commit.assert_called_once_with()
    db.refresh.assert_called_once_with(created)
