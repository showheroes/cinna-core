"""
One job: bump ``input_task.updated_at`` when a task's *activity* changes.

Comments and attachments live in their own tables. Writing one leaves the task
row byte-for-byte identical, which is invisible until something reads
``updated_at`` as "when did this task last change" — and two things do:

  - ``GET /api/v1/tasks/?updated_since=`` — the incremental-sync cursor an
    external client polls. Without this touch, an agent posting a ``blocked``
    question as a comment produces no delta row at all, and a client driving
    its inbox from the cursor never surfaces it.
  - ``status_repair_tasks`` — uses ``updated_at`` as an optimistic lock
    ("has anyone touched this row since we looked?"). A task whose agent is
    actively posting comments is a task that is alive, so a comment counting
    as a touch is the answer that sweep already documents wanting.

Call it *before* the write path's own ``commit()``, never with its own. The
touch must land in the same transaction as the comment or attachment it
describes: a cursor that can observe the bump without the comment, or the
comment without the bump, is worse than no cursor.
"""
from datetime import UTC, datetime
from uuid import UUID

from sqlmodel import Session as DBSession

from app.models.tasks.input_task import InputTask


def touch_task(db_session: DBSession, task_id: UUID) -> None:
    """Mark a task as changed, without committing.

    A missing task is not an error — the caller is mid-write on a row that may
    have been deleted underneath it, and failing the activity write over a
    bookkeeping column would be the wrong trade.
    """
    task = db_session.get(InputTask, task_id)
    if task is None:
        return
    task.updated_at = datetime.now(UTC)
    db_session.add(task)
