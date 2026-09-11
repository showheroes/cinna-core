"""
Tests for the two affordances an external client needs to mirror cinna tasks
without hammering the API or duplicating rows. Both were added for the desktop
app (`drafts/desktop_tasks_integration_plan.md`, items B and C), and both are
generic: nothing here is desktop-specific.

  ``updated_since`` on GET /tasks/ — an incremental-sync cursor. Returns only
  tasks changed strictly after the given timestamp, ordered by ``updated_at``
  ascending, because a cursor needs a stable ascending order to page through.
  Without the param the list keeps its existing ``created_at desc`` order —
  that conditionality is the risk in the change and is pinned here.

  ``external_ref`` on POST /tasks/ — a caller-supplied idempotency key scoped
  to the owner. A create retried after a lost response returns the first task
  instead of making a second one. Two owners may independently use the same
  ref, so the uniqueness is per-owner, not global.

One known gap, pinned below so it is a decision on the record rather than an
oversight:

  - Deletes do not appear in an incremental pull. A client that needs them
    reconciles on a full list. (Tombstones were rejected as a table's worth of
    machinery for one client.)
  - Task *deletions* are the only remaining gap. Comment and attachment
    writes do bump ``input_task.updated_at`` (via
    ``app/services/tasks/task_touch.py``), so task activity is visible to the
    cursor; a removed task simply stops appearing.

Scenarios:
  1. updated_since returns only what changed after it, in ascending order
  2. updated_since does not disturb the default list order or its filters
  3. updated_since misses task deletions — reconcile with a full pull
  3b. updated_since DOES report comment and attachment changes
  4. external_ref round-trips and a retry returns the same task
  5. external_ref is scoped to the owner — two users may use the same value
  6. a create without external_ref is unconstrained (many are fine)
  7. a retry does not re-fire auto_execute — the row is deduplicated AND so is
     its side effect
  8. an empty or whitespace-only ref is "no ref", not a value the unique index
     can collide on
  9. the subtasks route does not honour external_ref
"""
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.input_task import (
    create_task,
    get_task,
    list_tasks,
    set_task_status,
)
from tests.utils.user import create_random_user, user_authentication_headers

_BASE = f"{settings.API_V1_STR}/tasks"
_AGENT_ENV_PATCH = "app.services.sessions.message_service.agent_env_connector"


def _headers_for_new_user(client: TestClient) -> dict[str, str]:
    user = create_random_user(client)
    return user_authentication_headers(
        client=client, email=user["email"], password=user["_password"]
    )


# ===========================================================================
# Item B — updated_since
# ===========================================================================


def test_updated_since_returns_only_changed_tasks_in_ascending_order(
    client: TestClient,
) -> None:
    """
    A client polls with the timestamp of its last pull and gets only the delta:

      1. Create three tasks — a full pull sees all three
      2. Take the newest updated_at from that pull as the cursor
      3. Touch two of them (a status write bumps updated_at)
      4. Pull with updated_since=<cursor> — only the two touched tasks come
         back, and in ascending updated_at order
      5. Pull with the cursor advanced past the last change — empty
    """
    headers = _headers_for_new_user(client)

    # ── Phase 1: three tasks, full pull ───────────────────────────────────
    a = create_task(client, headers, original_message="Cursor task A")
    b = create_task(client, headers, original_message="Cursor task B")
    c = create_task(client, headers, original_message="Cursor task C")

    full = list_tasks(client, headers, status="all")
    assert full["count"] == 3, f"Expected a clean 3-task account, got {full['count']}"

    # ── Phase 2: cursor = the newest updated_at currently on record ───────
    cursor = max(t["updated_at"] for t in full["data"])

    # ── Phase 3: touch two of them ────────────────────────────────────────
    set_task_status(client, headers, a["id"], "in_progress")
    set_task_status(client, headers, c["id"], "in_progress")

    # ── Phase 4: the delta, ascending ─────────────────────────────────────
    delta = list_tasks(client, headers, status="all", updated_since=cursor)
    returned_ids = [t["id"] for t in delta["data"]]
    assert set(returned_ids) == {a["id"], c["id"]}, (
        f"Only the touched tasks belong in the delta; B ({b['id']}) was not "
        f"touched. Got {returned_ids}"
    )
    assert delta["count"] == 2

    stamps = [t["updated_at"] for t in delta["data"]]
    assert stamps == sorted(stamps), (
        f"A cursor needs a stable ascending order to page through; got {stamps}"
    )
    assert returned_ids[0] == a["id"], (
        "A was touched before C, so it must come first under updated_at asc"
    )

    # ── Phase 5: cursor past the last change — nothing left ───────────────
    latest = max(stamps)
    empty = list_tasks(client, headers, status="all", updated_since=latest)
    assert empty["data"] == [] and empty["count"] == 0, (
        f"updated_since is strictly greater-than; got {empty}"
    )


def test_updated_since_absent_leaves_the_default_list_untouched(
    client: TestClient,
) -> None:
    """
    The ordering change is conditional on the param — the existing list UI must
    be unaffected.

      1. Create three tasks, then touch the *oldest* one
      2. A plain pull is still newest-created first — the touch did not
         reorder it
      3. updated_since combines with the other filters rather than replacing
         them (priority filter still applies inside the delta)
    """
    headers = _headers_for_new_user(client)

    first = create_task(client, headers, original_message="Order task 1", priority="high")
    second = create_task(client, headers, original_message="Order task 2")
    third = create_task(client, headers, original_message="Order task 3")

    # Touching the oldest would move it to the front under sync order
    set_task_status(client, headers, first["id"], "in_progress")

    plain = list_tasks(client, headers, status="all")
    assert [t["id"] for t in plain["data"]] == [third["id"], second["id"], first["id"]], (
        "Without updated_since the list keeps created_at desc — a status write "
        "must not reorder the list UI."
    )

    # ── Filters still compose with the cursor ─────────────────────────────
    delta = list_tasks(
        client, headers, status="all", updated_since="1970-01-01T00:00:00Z", priority="high"
    )
    assert [t["id"] for t in delta["data"]] == [first["id"]], (
        f"priority must still filter inside an incremental pull; got {delta['data']}"
    )


def test_updated_since_does_not_report_deletions(
    client: TestClient,
) -> None:
    """
    The documented gap: a delete disappears silently from an incremental pull.

      1. Two tasks; cursor taken
      2. Delete one
      3. The incremental pull is empty — the deletion is not announced
      4. A full pull shows it is gone

    This is the accepted trade (tombstones were rejected as a table's worth of
    machinery for one client). Pinned so the absence is on the record: a client
    that relies on the cursor alone will keep a phantom row until it reconciles.
    """
    headers = _headers_for_new_user(client)

    keep = create_task(client, headers, original_message="Kept task")
    doomed = create_task(client, headers, original_message="Doomed task")

    full = list_tasks(client, headers, status="all")
    cursor = max(t["updated_at"] for t in full["data"])

    r = client.delete(f"{_BASE}/{doomed['id']}", headers=headers)
    assert r.status_code == 200, f"Delete failed: {r.text}"

    delta = list_tasks(client, headers, status="all", updated_since=cursor)
    assert delta["data"] == [], (
        "A deletion produces no row in an incremental pull — this is the "
        "known gap, not a regression."
    )

    reconciled = list_tasks(client, headers, status="all")
    assert [t["id"] for t in reconciled["data"]] == [keep["id"]], (
        "A full pull is how a client learns about deletions."
    )


def test_updated_since_reports_comment_and_attachment_changes(
    client: TestClient,
) -> None:
    """
    A task's *activity* counts as a change to the task.

      1. A task; cursor taken once it has settled
      2. Post a comment — the task appears in the incremental pull
      3. Advance the cursor; upload an attachment — it appears again
      4. Advance the cursor; delete the comment — it appears again

    Comments and attachments live in their own tables, so writing one leaves
    the task row untouched unless something bumps it deliberately
    (``app/services/tasks/task_touch.py``). Without that bump the sharpest case
    is silent: an agent posting a ``blocked`` question as a comment, on a task
    whose status does not change, produces no delta row at all — and a client
    driving its inbox from this cursor never surfaces it.

    Deletions of the *task* are still not reported; that is a different gap and
    is pinned separately below.
    """
    import io

    headers = _headers_for_new_user(client)
    task = create_task(client, headers, original_message="Comment cursor task")
    task_id = task["id"]

    # ── Phase 1 + 2: a comment is a change ────────────────────────────────
    cursor = get_task(client, headers, task_id)["updated_at"]

    r = client.post(
        f"{_BASE}/{task_id}/comments/",
        headers=headers,
        json={"content": "A note the desktop must mirror"},
    )
    assert r.status_code == 200, f"Comment failed: {r.text}"
    comment_id = r.json()["id"]

    delta = list_tasks(client, headers, status="all", updated_since=cursor)
    assert [t["id"] for t in delta["data"]] == [task_id], (
        "A comment must put the task in the delta — otherwise an agent's "
        f"blocked question is invisible to a polling client. Got {delta['data']}"
    )

    # ── Phase 3: an attachment is a change ────────────────────────────────
    cursor = get_task(client, headers, task_id)["updated_at"]
    assert list_tasks(client, headers, status="all", updated_since=cursor)["data"] == [], (
        "Cursor must be caught up before the next phase, or it proves nothing"
    )

    r = client.post(
        f"{_BASE}/{task_id}/attachments/",
        headers=headers,
        files={"file": ("note.txt", io.BytesIO(b"deliverable"), "text/plain")},
    )
    assert r.status_code == 200, f"Attachment upload failed: {r.text}"

    delta = list_tasks(client, headers, status="all", updated_since=cursor)
    assert [t["id"] for t in delta["data"]] == [task_id], (
        f"An attachment must put the task in the delta; got {delta['data']}"
    )

    # ── Phase 4: removing activity is a change too ────────────────────────
    cursor = get_task(client, headers, task_id)["updated_at"]
    assert list_tasks(client, headers, status="all", updated_since=cursor)["data"] == []

    r = client.delete(f"{_BASE}/{task_id}/comments/{comment_id}", headers=headers)
    assert r.status_code == 200, f"Comment delete failed: {r.text}"

    delta = list_tasks(client, headers, status="all", updated_since=cursor)
    assert [t["id"] for t in delta["data"]] == [task_id], (
        "A client that mirrors comments needs to learn one was removed, not "
        f"just that one was added; got {delta['data']}"
    )


# ===========================================================================
# Item C — external_ref idempotency
# ===========================================================================


def test_external_ref_makes_a_retried_create_idempotent(
    client: TestClient,
) -> None:
    """
    A client whose create response was lost retries and gets its first task:

      1. Create with external_ref='desk_abc123' — ref round-trips in the
         response so the client can recognise its own rows later
      2. Retry the identical create — same task id, not a second task
      3. Retry with *different* content under the same ref — still the first
         task, unchanged. The ref identifies the task; it is not an upsert.
      4. The account holds exactly one task
    """
    headers = _headers_for_new_user(client)

    # ── Phase 1: first create ─────────────────────────────────────────────
    first = create_task(
        client, headers,
        original_message="Review the Q3 deck",
        external_ref="desk_abc123",
    )
    assert first["external_ref"] == "desk_abc123", (
        "The ref must come back so a client can re-bind local tasks to their "
        "cinna counterparts after a reinstall, instead of matching on title."
    )

    # ── Phase 2: the retry ────────────────────────────────────────────────
    retry = create_task(
        client, headers,
        original_message="Review the Q3 deck",
        external_ref="desk_abc123",
    )
    assert retry["id"] == first["id"], (
        "A retry after a lost response must be indistinguishable from the "
        "first call — that is the whole point of the key."
    )
    assert retry["short_code"] == first["short_code"], (
        "No second short code may be burned on a retry."
    )

    # ── Phase 3: same ref, different body — identify, do not upsert ───────
    third = create_task(
        client, headers,
        original_message="Something else entirely",
        external_ref="desk_abc123",
    )
    assert third["id"] == first["id"]
    assert third["original_message"] == "Review the Q3 deck", (
        "external_ref identifies an existing task; it is not an update channel."
    )

    # ── Phase 4: exactly one task exists ──────────────────────────────────
    listed = list_tasks(client, headers, status="all")
    assert listed["count"] == 1, (
        f"Three creates under one ref must leave one task; got {listed['count']}"
    )
    assert get_task(client, headers, first["id"])["external_ref"] == "desk_abc123"


def test_external_ref_is_scoped_to_the_owner(
    client: TestClient,
) -> None:
    """
    Two users may independently use the same ref — the key is per-owner.

      1. User A creates with ref 'task-1'
      2. User B creates with the same ref — a *different* task, not A's
      3. Neither can see the other's task
    """
    headers_a = _headers_for_new_user(client)
    headers_b = _headers_for_new_user(client)

    a_task = create_task(
        client, headers_a, original_message="A's local task", external_ref="task-1"
    )
    b_task = create_task(
        client, headers_b, original_message="B's local task", external_ref="task-1"
    )

    assert b_task["id"] != a_task["id"], (
        "Two clients both numbering their tasks from 1 must not collide — "
        "the unique index is on (owner_id, external_ref)."
    )
    assert b_task["original_message"] == "B's local task"

    assert list_tasks(client, headers_a, status="all")["count"] == 1
    assert list_tasks(client, headers_b, status="all")["count"] == 1

    r = client.get(f"{_BASE}/{a_task['id']}", headers=headers_b)
    assert r.status_code in (400, 404)


def test_creates_without_external_ref_are_unconstrained(
    client: TestClient,
) -> None:
    """
    The partial index must not constrain the overwhelming majority of tasks —
    everything created on the web carries no ref.

      1. Three creates with no external_ref, identical text
      2. Three distinct tasks, all with external_ref null
    """
    headers = _headers_for_new_user(client)

    ids = {
        create_task(client, headers, original_message="Same text every time")["id"]
        for _ in range(3)
    }
    assert len(ids) == 3, (
        "NULL refs must not collide with each other — that is why the unique "
        "index is partial."
    )

    listed = list_tasks(client, headers, status="all")
    assert listed["count"] == 3
    assert all(t["external_ref"] is None for t in listed["data"])


def test_a_retried_create_does_not_re_fire_auto_execute(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deduplicating the row is only half the job — the side effect must be
    deduplicated too.

      1. Create with auto_execute=True, an agent, and external_ref — one
         session is started
      2. Retry the identical create — same task, and STILL one session

    Without the `created` gate this is strictly worse than the duplicate task
    the key exists to prevent: two agent sessions on one task means duplicate
    work, duplicate token spend and duplicate result comments, all on the row
    the client thinks it deduplicated. A flaky-network retry — the exact
    scenario the key is for — is what triggers it.

    Also pinned: the flag is read from the *stored* task, so a retry that sends
    auto_execute=false must not re-fire either.
    """
    from unittest.mock import patch

    from tests.stubs.agent_env_stub import StubAgentEnvConnector
    from tests.utils.agent import create_agent_via_api
    from tests.utils.background_tasks import drain_tasks
    from tests.utils.input_task import get_task_sessions

    # The superuser, not a fresh user: creating an agent needs the
    # agent-developer role, which a plain signup does not carry.
    headers = superuser_token_headers

    agent = create_agent_via_api(client, headers, name="Retry Auto Execute Agent")
    drain_tasks()

    stub = StubAgentEnvConnector(response_text="Ran once.")
    with patch(_AGENT_ENV_PATCH, stub):
        # ── Phase 1: the create that really executes ──────────────────────
        first = create_task(
            client, headers,
            original_message="Run me exactly once",
            selected_agent_id=agent["id"],
            auto_execute=True,
            external_ref="desk_retry_1",
        )
        drain_tasks()

    task_id = first["id"]
    sessions_after_first = get_task_sessions(client, headers, task_id)
    assert len(sessions_after_first) == 1, (
        f"Setup expects exactly one session from the first create, got "
        f"{len(sessions_after_first)}"
    )

    # ── Phase 2: the retry ────────────────────────────────────────────────
    with patch(_AGENT_ENV_PATCH, stub):
        retry = create_task(
            client, headers,
            original_message="Run me exactly once",
            selected_agent_id=agent["id"],
            auto_execute=True,
            external_ref="desk_retry_1",
        )
        drain_tasks()

    assert retry["id"] == task_id
    assert len(get_task_sessions(client, headers, task_id)) == 1, (
        "A retried create must not start a second agent session. The row was "
        "deduplicated; the side effect must be too."
    )

    # ── Phase 3: auto_execute=false on the retry is equally inert ─────────
    with patch(_AGENT_ENV_PATCH, stub):
        again = create_task(
            client, headers,
            original_message="Run me exactly once",
            selected_agent_id=agent["id"],
            auto_execute=False,
            external_ref="desk_retry_1",
        )
        drain_tasks()

    assert again["id"] == task_id
    assert len(get_task_sessions(client, headers, task_id)) == 1

    # Exactly one task carries the ref (the account is not otherwise clean here)
    all_tasks = list_tasks(client, headers, status="all", limit=200)["data"]
    matching = [t for t in all_tasks if t["external_ref"] == "desk_retry_1"]
    assert len(matching) == 1, f"Three creates under one ref left {len(matching)} tasks"


def test_blank_external_ref_is_treated_as_absent(
    client: TestClient,
) -> None:
    """
    An empty or whitespace-only ref means "no ref" and must never reach the DB.

      1. Two creates with external_ref="" — two distinct tasks, no error
      2. Two more with a whitespace-only ref — likewise
      3. All four come back with external_ref null

    ``''`` IS NOT NULL, so the partial unique index *does* cover it. If a blank
    ref were stored, the second such create would violate the constraint and
    surface as a 500 — the one outcome idempotency exists to prevent, reached
    by a client that merely left the field empty. Normalising to None at the
    top of create_task is what keeps these in the unconstrained majority.
    """
    headers = _headers_for_new_user(client)

    ids = []
    for blank in ("", "", "   ", "\t"):
        r = client.post(
            f"{_BASE}/",
            headers=headers,
            json={"original_message": "Blank ref task", "external_ref": blank},
        )
        assert r.status_code == 200, (
            f"A blank external_ref must behave as no ref, not as a collidable "
            f"value; got {r.status_code}: {r.text}"
        )
        body = r.json()
        assert body["external_ref"] is None, (
            f"A blank ref must be normalised away before storage, got {body['external_ref']!r}"
        )
        ids.append(body["id"])

    assert len(set(ids)) == 4, "Blank refs must not deduplicate against each other"
    assert list_tasks(client, headers, status="all")["count"] == 4


def test_subtasks_route_does_not_honour_external_ref(
    client: TestClient,
) -> None:
    """
    ``external_ref`` is an idempotency key for POST /tasks/ only.

      1. A root task carrying ref 'shared-ref'
      2. A second root task, to be the parent
      3. POST /tasks/{parent}/subtasks/ with the SAME ref
      4. The result is a real subtask of the requested parent — not the first
         root task handed back with the wrong parent

    Honouring the key here would return 200 with a task whose parent is not the
    one the caller named, and the client would believe a subtask exists where
    none does. Silently wrong beats loudly wrong only when the answer is right.
    """
    headers = _headers_for_new_user(client)

    root = create_task(
        client, headers, original_message="Unrelated root", external_ref="shared-ref"
    )
    parent = create_task(client, headers, original_message="The real parent")

    r = client.post(
        f"{_BASE}/{parent['id']}/subtasks/",
        headers=headers,
        json={"original_message": "A genuine subtask", "external_ref": "shared-ref"},
    )
    assert r.status_code == 200, f"Subtask creation failed: {r.text}"
    subtask = r.json()

    assert subtask["id"] != root["id"], (
        "The subtasks route must not match an unrelated root task by ref."
    )
    assert subtask["parent_task_id"] == parent["id"], (
        f"The subtask must hang off the parent the caller named; got "
        f"{subtask['parent_task_id']}"
    )
    assert subtask["external_ref"] is None, (
        "The ref is ignored on this route, so it must not be stored either — "
        "storing it would let a later POST /tasks/ retry match a subtask."
    )

    # The root task is untouched and still owns the ref
    assert get_task(client, headers, root["id"])["external_ref"] == "shared-ref"
