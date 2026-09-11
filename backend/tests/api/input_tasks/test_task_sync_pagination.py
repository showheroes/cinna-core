"""The desktop sync cursor must not lose rows at tied or moving page boundaries."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.input_task import create_task, list_tasks, update_task
from tests.utils.user import create_random_user_with_headers

_BASE = f"{settings.API_V1_STR}/tasks"


def test_sync_pages_preserve_timestamp_ties_and_rows_updated_during_pull(
    client: TestClient,
) -> None:
    """A paged pull survives ties, an already-read row moving, and ownership.

    1. Edit three tasks at one instant and another at a later instant.
    2. Read one row, then update that row again so it moves to the tail.
    3. Advance both cursor fields: every unread tie arrives, then later rows.
    4. The moved row arrives again, and the cursor terminates without repeats.
    5. Timestamp-only calls retain strict greater-than behavior; an id alone
       is refused instead of silently returning an unrelated ordinary list.

    Only the clock is controlled. All task setup, edits, and verification go
    through HTTP; the pagination service and database query run unchanged.
    """
    _, headers = create_random_user_with_headers(client)
    _, other_headers = create_random_user_with_headers(client)
    tasks = [create_task(client, headers) for _ in range(4)]
    foreign = create_task(client, other_headers)
    instant = datetime.now(UTC) + timedelta(seconds=10)

    # ── Phase 1: Real API edits with deliberately identical timestamps ────
    with patch("app.services.tasks.input_task_service.datetime", wraps=datetime) as clock:
        clock.now.return_value = instant
        tied = [update_task(client, headers, task["id"], title="Same instant") for task in tasks[:3]]
        update_task(client, other_headers, foreign["id"], title="Foreign tie")
        clock.now.return_value = instant + timedelta(seconds=1)
        later = update_task(client, headers, tasks[3]["id"], title="Later")

    assert len({task["updated_at"] for task in tied}) == 1, "Clock setup must actually produce a tie"
    tied_ids = sorted(task["id"] for task in tied)
    page = list_tasks(
        client, headers, status="all", limit=1,
        updated_since=(instant - timedelta(seconds=1)).isoformat(),
    )
    assert page["count"] == 4, "The foreign owner's tied row must stay excluded"
    assert [task["id"] for task in page["data"]] == tied_ids[:1]
    cursor = page["data"][0]

    # ── Phase 2: A consumed row moves beyond the unread page ──────────────
    with patch("app.services.tasks.input_task_service.datetime", wraps=datetime) as clock:
        clock.now.return_value = instant + timedelta(seconds=2)
        moved = update_task(client, headers, cursor["id"], title="Moved to tail")

    # ── Phase 3: Neither tied rows nor the moved row are skipped ──────────
    expected_ids = [*tied_ids[1:], later["id"], moved["id"]]
    for index, expected_id in enumerate(expected_ids):
        page = list_tasks(
            client, headers, status="all", limit=1,
            updated_since=cursor["updated_at"], updated_since_id=cursor["id"],
        )
        assert page["count"] == len(expected_ids) - index
        assert [task["id"] for task in page["data"]] == [expected_id]
        cursor = page["data"][0]
    empty = list_tasks(
        client, headers, status="all", limit=1,
        updated_since=cursor["updated_at"], updated_since_id=cursor["id"],
    )
    assert empty == {"data": [], "count": 0}

    # ── Phase 4: Compatibility and invalid cursor combinations ───────────
    strict = list_tasks(client, headers, status="all", updated_since=tied[0]["updated_at"])
    assert [task["id"] for task in strict["data"]] == [later["id"], moved["id"]]
    invalid = client.get(_BASE + "/", headers=headers, params={"updated_since_id": cursor["id"]})
    assert invalid.status_code == 400, invalid.text
    assert "updated_since" in invalid.json()["detail"]
