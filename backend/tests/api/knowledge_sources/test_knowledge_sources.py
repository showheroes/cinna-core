"""
Integration tests for the knowledge-sources admin API.

Knowledge sources are server-wide, admin-managed resources: every superuser
can view/edit/delete/enable/disable/check-access/refresh/preview/export EVERY
source regardless of who created it (``user_id`` is "created by" metadata
only). Non-superusers get 403 on every route. Consumer (query) access is a
separate concern governed by ``access_level`` (private/public/shared) and is
covered in ``test_knowledge_query.py``.

Scenario-based tests covering the full admin surface:
  1. Lifecycle    — CRUD, enable/disable, cross-admin management, non-admin 403
  2. Operational  — check-access (success + failure), refresh (success + disabled)
  3. SSH keys     — ownership validation on create/update; cross-admin refresh
                     uses the stored key regardless of the acting admin
  4. Shared users — add/remove/list, idempotency, 404s, non-admin 403
  5. Article/export — content preview + Markdown export, readable by any admin
"""

import uuid
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.knowledge_source import (
    add_shared_user,
    create_knowledge_source,
    delete_knowledge_source,
    disable_knowledge_source,
    enable_knowledge_source,
    export_knowledge_source,
    get_knowledge_article,
    get_knowledge_source,
    list_knowledge_articles,
    list_knowledge_sources,
    list_shared_users,
    remove_shared_user,
    update_knowledge_source,
)
from tests.utils.ssh_key import generate_random_ssh_key
from tests.utils.user import (
    create_random_user,
    create_random_user_with_headers,
    user_authentication_headers,
)
from tests.utils.utils import random_lower_string

_BASE = f"{settings.API_V1_STR}/knowledge-sources"


# ---------------------------------------------------------------------------
# Mock helpers
# ---------------------------------------------------------------------------

@contextmanager
def _fake_clone_context(*args, **kwargs):
    """Pretend to clone a repository — yields (repo_path, repo_handle)."""
    yield ("/tmp/fake-repo", MagicMock())


def _mock_parse_settings():
    mock_settings = MagicMock()
    mock_settings.static_articles = [MagicMock(path="articles/test.md")]
    return mock_settings


def _refresh_patches():
    """Stack of patches that prevent real git/embedding work in refresh tests."""
    return (
        patch(
            "app.services.knowledge.knowledge_source_service.clone_repository_context",
            side_effect=_fake_clone_context,
        ),
        patch(
            "app.services.knowledge.knowledge_source_service.parse_settings_json",
            return_value=_mock_parse_settings(),
        ),
        patch(
            "app.services.knowledge.knowledge_source_service.process_repository_articles",
            return_value={"total": 1, "created": 1, "updated": 0, "skipped": 0, "errors": []},
        ),
        patch(
            "app.services.knowledge.knowledge_source_service.delete_orphaned_articles",
            return_value=0,
        ),
        patch(
            "app.services.knowledge.knowledge_source_service.chunk_and_embed_all_articles",
            return_value={
                "articles_processed": 0,
                "articles_failed": 0,
                "total_chunks_created": 0,
                "total_chunks_updated": 0,
            },
        ),
        patch(
            "app.services.knowledge.knowledge_source_service.get_current_commit_hash",
            return_value="abc123",
        ),
    )


def _refresh_patches_with_article(article_holder: dict):
    """Like ``_refresh_patches`` but ``process_repository_articles`` inserts a
    real ``KnowledgeArticle`` row using the live request session, so the
    article-content/export endpoints have data to read.

    ``article_holder`` is mutated in place with the created article's ``id``
    and ``content`` so the test can assert against them.
    """
    from app.models.knowledge.knowledge import KnowledgeArticle

    content = article_holder.get("content", "# Heading\n\nBody text.")
    title = article_holder.get("title", "Test Article")
    file_path = article_holder.get("file_path", "articles/test.md")

    def _insert_article(*, session, git_repo_id, repo_path, commit_hash):
        article = KnowledgeArticle(
            git_repo_id=uuid.UUID(str(git_repo_id)),
            title=title,
            description="An article description that is fairly long for testing.",
            tags=["alpha", "beta"],
            features=["search"],
            file_path=file_path,
            content=content,
            content_hash="hash123",
            commit_hash=commit_hash,
        )
        session.add(article)
        session.flush()
        article_holder["id"] = str(article.id)
        return {"total": 1, "created": 1, "updated": 0, "skipped": 0, "errors": []}

    base = list(_refresh_patches())
    # Replace the process_repository_articles patch (index 2) with the inserter.
    base[2] = patch(
        "app.services.knowledge.knowledge_source_service.process_repository_articles",
        side_effect=_insert_article,
    )
    return tuple(base)


def _make_second_superuser(
    client: TestClient, superuser_token_headers: dict[str, str]
) -> tuple[dict, dict[str, str]]:
    """Create a fresh user and promote them to superuser via the admin API.

    Returns ``(user_data, auth_headers)`` for the new superuser.
    """
    user, _ = create_random_user_with_headers(client)
    r = client.patch(
        f"{settings.API_V1_STR}/users/{user['id']}",
        headers=superuser_token_headers,
        json={"is_superuser": True},
    )
    assert r.status_code == 200, r.text
    headers = user_authentication_headers(
        client=client, email=user["email"], password=user["_password"]
    )
    return user, headers


def _connect_source(
    client: TestClient, headers: dict[str, str], source_id: str
) -> None:
    """Drive a source to ``connected`` status via check-access."""
    with patch(
        "app.services.knowledge.knowledge_source_service.verify_repository_access",
        return_value=(True, "Repository accessible"),
    ):
        client.post(f"{_BASE}/{source_id}/check-access", headers=headers)


# ---------------------------------------------------------------------------
# Scenario 1: Source lifecycle — server-wide, cross-admin management
# ---------------------------------------------------------------------------

def test_knowledge_source_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Full source management lifecycle:
      1.  Unauthenticated request is rejected
      2.  Create source — verify initial state (pending, is_enabled, article_count,
          access_level=private default, created_by_email/name, shared_user_count)
      3.  Source appears in list
      4.  GET by ID — fields match
      5.  Update name and description — changes persist
      6.  Non-admin user gets 403 on all endpoints
      7.  Requests for a non-existent ID return 404
      8.  Changing branch resets status to 'pending'
      9.  A second, unrelated superuser can edit/enable/disable/delete the
          FIRST admin's source (server-wide management, no ownership guard)
      10. Delete source — gone (404)
    """
    name = f"ks-{random_lower_string()[:12]}"

    # ── Phase 1: No auth ───────────────────────────────────────────────────
    r = client.get(f"{_BASE}/")
    assert r.status_code in (401, 403)

    # ── Phase 2: Create ───────────────────────────────────────────────────
    source = create_knowledge_source(client, superuser_token_headers, name=name)
    source_id = source["id"]

    assert source["name"] == name
    assert source["status"] == "pending"
    assert source["is_enabled"] is True
    assert source["article_count"] == 0
    assert source["access_level"] == "private"
    assert source["shared_user_count"] == 0
    assert "created_by_email" in source
    assert "created_by_name" in source
    assert "git_url" in source and "branch" in source
    assert "created_at" in source and "updated_at" in source

    # ── Phase 3: List → source is present ────────────────────────────────
    sources = list_knowledge_sources(client, superuser_token_headers)
    assert any(s["id"] == source_id for s in sources)

    # ── Phase 4: GET by ID ───────────────────────────────────────────────
    fetched = get_knowledge_source(client, superuser_token_headers, source_id)
    assert fetched["id"] == source_id
    assert fetched["name"] == name

    # ── Phase 5: Update name and description ─────────────────────────────
    new_name = f"renamed-{random_lower_string()[:8]}"
    updated = update_knowledge_source(
        client, superuser_token_headers, source_id,
        name=new_name, description="updated desc",
    )
    assert updated["name"] == new_name
    assert updated["description"] == "updated desc"
    assert updated["status"] == "pending"  # non-git change must not affect status

    re_fetched = get_knowledge_source(client, superuser_token_headers, source_id)
    assert re_fetched["name"] == new_name

    # ── Phase 6: Non-admin user gets 403 on all endpoints ────────────────
    other_user = create_random_user(client)
    other_headers = user_authentication_headers(
        client=client, email=other_user["email"], password=other_user["_password"]
    )

    assert client.get(f"{_BASE}/", headers=other_headers).status_code == 403
    assert client.get(f"{_BASE}/{source_id}", headers=other_headers).status_code == 403
    assert client.put(
        f"{_BASE}/{source_id}", headers=other_headers, json={"name": "hacked"}
    ).status_code == 403
    assert client.delete(f"{_BASE}/{source_id}", headers=other_headers).status_code == 403
    assert client.post(
        f"{_BASE}/{source_id}/enable", headers=other_headers
    ).status_code == 403
    assert client.post(
        f"{_BASE}/{source_id}/check-access", headers=other_headers
    ).status_code == 403
    assert client.get(
        f"{_BASE}/{source_id}/shared-users", headers=other_headers
    ).status_code == 403
    assert client.post(
        f"{_BASE}/{source_id}/shared-users",
        headers=other_headers,
        json={"user_id": str(uuid.uuid4())},
    ).status_code == 403

    # Original source is still intact
    get_knowledge_source(client, superuser_token_headers, source_id)

    # ── Phase 7: Non-existent ID returns 404 ─────────────────────────────
    ghost = str(uuid.uuid4())
    assert client.get(f"{_BASE}/{ghost}", headers=superuser_token_headers).status_code == 404
    assert client.put(
        f"{_BASE}/{ghost}", headers=superuser_token_headers, json={"name": "x"}
    ).status_code == 404
    assert client.delete(f"{_BASE}/{ghost}", headers=superuser_token_headers).status_code == 404
    assert client.post(
        f"{_BASE}/{ghost}/enable", headers=superuser_token_headers
    ).status_code == 404
    assert client.post(
        f"{_BASE}/{ghost}/check-access", headers=superuser_token_headers
    ).status_code == 404
    assert client.post(
        f"{_BASE}/{ghost}/refresh", headers=superuser_token_headers
    ).status_code == 404

    # ── Phase 8: Changing branch resets status to pending ────────────────
    with patch(
        "app.services.knowledge.knowledge_source_service.verify_repository_access",
        return_value=(True, "Repository accessible"),
    ):
        client.post(f"{_BASE}/{source_id}/check-access", headers=superuser_token_headers)

    assert get_knowledge_source(client, superuser_token_headers, source_id)["status"] == "connected"

    branch_updated = update_knowledge_source(
        client, superuser_token_headers, source_id, branch="develop"
    )
    assert branch_updated["branch"] == "develop"
    assert branch_updated["status"] == "pending"

    # ── Phase 9: A second, unrelated superuser manages the SAME source ────
    _, second_su_headers = _make_second_superuser(client, superuser_token_headers)

    cross_updated = update_knowledge_source(
        client, second_su_headers, source_id, description="edited by another admin",
    )
    assert cross_updated["description"] == "edited by another admin"

    cross_disabled = disable_knowledge_source(client, second_su_headers, source_id)
    assert cross_disabled["is_enabled"] is False
    assert get_knowledge_source(client, superuser_token_headers, source_id)["is_enabled"] is False

    cross_enabled = enable_knowledge_source(client, second_su_headers, source_id)
    assert cross_enabled["is_enabled"] is True

    # ── Phase 10: Cross-admin delete → gone ───────────────────────────────
    delete_knowledge_source(client, second_su_headers, source_id)
    assert client.get(f"{_BASE}/{source_id}", headers=superuser_token_headers).status_code == 404


# ---------------------------------------------------------------------------
# Scenario 2: Check access and refresh
# ---------------------------------------------------------------------------

def test_check_access_and_refresh(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Operational actions on a source:
      1. Create source
      2. Check access → success → status=connected
      3. Check access → failure → status=error
      4. Check access → success again → status=connected
      5. Articles endpoint returns empty list
      6. Refresh (all internals mocked) → status=success, last_sync_at set
      7. Disable source, then refresh → status=error (disabled guard)
      8. A second superuser can refresh the SAME source too
    """
    # ── Phase 1: Create ───────────────────────────────────────────────────
    source = create_knowledge_source(client, superuser_token_headers)
    source_id = source["id"]
    assert source["status"] == "pending"

    # ── Phase 2: Check access success ─────────────────────────────────────
    with patch(
        "app.services.knowledge.knowledge_source_service.verify_repository_access",
        return_value=(True, "Repository accessible"),
    ):
        r = client.post(f"{_BASE}/{source_id}/check-access", headers=superuser_token_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["accessible"] is True
        assert "message" in body

    assert get_knowledge_source(client, superuser_token_headers, source_id)["status"] == "connected"

    # ── Phase 3: Check access failure ─────────────────────────────────────
    with patch(
        "app.services.knowledge.knowledge_source_service.verify_repository_access",
        return_value=(False, "Connection refused"),
    ):
        r = client.post(f"{_BASE}/{source_id}/check-access", headers=superuser_token_headers)
        assert r.status_code == 200
        assert r.json()["accessible"] is False

    assert get_knowledge_source(client, superuser_token_headers, source_id)["status"] == "error"

    # ── Phase 4: Restore to connected ─────────────────────────────────────
    with patch(
        "app.services.knowledge.knowledge_source_service.verify_repository_access",
        return_value=(True, "Repository accessible"),
    ):
        client.post(f"{_BASE}/{source_id}/check-access", headers=superuser_token_headers)

    assert get_knowledge_source(client, superuser_token_headers, source_id)["status"] == "connected"

    # ── Phase 5: Articles → empty ─────────────────────────────────────────
    r = client.get(f"{_BASE}/{source_id}/articles", headers=superuser_token_headers)
    assert r.status_code == 200
    assert r.json() == []

    # ── Phase 6: Refresh → success ────────────────────────────────────────
    p1, p2, p3, p4, p5, p6 = _refresh_patches()
    with p1, p2, p3, p4, p5, p6:
        r = client.post(f"{_BASE}/{source_id}/refresh", headers=superuser_token_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "success"
        assert "message" in body

    after_refresh = get_knowledge_source(client, superuser_token_headers, source_id)
    assert after_refresh["status"] == "connected"
    assert after_refresh["last_sync_at"] is not None

    # ── Phase 7: Disabled source → refresh returns error ──────────────────
    disable_knowledge_source(client, superuser_token_headers, source_id)

    r = client.post(f"{_BASE}/{source_id}/refresh", headers=superuser_token_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "error"
    assert "disabled" in body["message"].lower() or "enable" in body["message"].lower()

    # ── Phase 8: A second superuser can refresh the same source too ───────
    enable_knowledge_source(client, superuser_token_headers, source_id)
    _, second_su_headers = _make_second_superuser(client, superuser_token_headers)

    p1, p2, p3, p4, p5, p6 = _refresh_patches()
    with p1, p2, p3, p4, p5, p6:
        r = client.post(f"{_BASE}/{source_id}/refresh", headers=second_su_headers)
        assert r.status_code == 200
        assert r.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Scenario 3: SSH key ownership rules
# ---------------------------------------------------------------------------

def test_ssh_key_ownership_rules(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    SSH key attachment must belong to the acting admin, but a stored key is
    usable by any admin for git operations:
      1. Admin A creates a source with their own SSH key → 200
      2. Admin B (second superuser) tries to create a source with Admin A's
         key → 400
      3. Admin B tries to update their OWN source to attach Admin A's key → 400
      4. Admin B updates their own source with their OWN key → 200
      5. Admin A can refresh Admin B's source (uses the stored key, resolved
         by the key's own owner — not the acting admin) → success
    """
    _, admin_a_headers = _make_second_superuser(client, superuser_token_headers)
    _, admin_b_headers = _make_second_superuser(client, superuser_token_headers)

    key_a = generate_random_ssh_key(client, admin_a_headers)
    key_b = generate_random_ssh_key(client, admin_b_headers)

    # ── Phase 1: Admin A creates a source with their own key ──────────────
    source_a = create_knowledge_source(
        client, admin_a_headers, ssh_key_id=key_a["id"]
    )
    assert source_a["ssh_key_id"] == key_a["id"]

    # ── Phase 2: Admin B cannot create a source with Admin A's key ────────
    r = client.post(
        f"{_BASE}/",
        headers=admin_b_headers,
        json={
            "name": f"ks-{random_lower_string()[:12]}",
            "git_url": f"https://github.com/test/{random_lower_string()[:12]}.git",
            "branch": "main",
            "ssh_key_id": key_a["id"],
        },
    )
    assert r.status_code == 400, r.text

    # ── Phase 3: Admin B creates their own source, then tries to attach
    #             Admin A's key via update → 400 ──────────────────────────
    source_b = create_knowledge_source(client, admin_b_headers)
    r = client.put(
        f"{_BASE}/{source_b['id']}",
        headers=admin_b_headers,
        json={"ssh_key_id": key_a["id"]},
    )
    assert r.status_code == 400, r.text

    # ── Phase 4: Admin B attaches their OWN key → 200 ──────────────────────
    updated_b = update_knowledge_source(
        client, admin_b_headers, source_b["id"], ssh_key_id=key_b["id"]
    )
    assert updated_b["ssh_key_id"] == key_b["id"]

    # ── Phase 5: Admin A (a different admin) refreshes Admin B's source —
    #             the stored key (owned by Admin B) is used regardless ─────
    p1, p2, p3, p4, p5, p6 = _refresh_patches()
    with p1, p2, p3, p4, p5, p6:
        r = client.post(
            f"{_BASE}/{source_b['id']}/refresh", headers=admin_a_headers
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "success"


# ---------------------------------------------------------------------------
# Scenario 4: Shared-users list management
# ---------------------------------------------------------------------------

def test_shared_users_management(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Shared-users list CRUD (effective when access_level == shared):
      1. Create source with access_level=shared → shared_user_count=0
      2. List shared users → empty
      3. Add a user → appears in list, shared_user_count increments
      4. Adding the SAME user again is idempotent (still one entry)
      5. Add a second user → both present
      6. Remove first user → only second remains
      7. Removing a user NOT on the list → 404
      8. Add on a non-existent source → 404
      9. Add a non-existent user → 404
      10. Non-admin is rejected (403) on list/add/remove
    """
    # ── Phase 1: Create shared source ──────────────────────────────────────
    source = create_knowledge_source(
        client, superuser_token_headers, access_level="shared"
    )
    source_id = source["id"]
    assert source["access_level"] == "shared"
    assert source["shared_user_count"] == 0

    # ── Phase 2: Empty list ─────────────────────────────────────────────────
    assert list_shared_users(client, superuser_token_headers, source_id) == []

    # ── Phase 3: Add a user ──────────────────────────────────────────────────
    user_1 = create_random_user(client)
    entry_1 = add_shared_user(client, superuser_token_headers, source_id, user_1["id"])
    assert entry_1["user_id"] == user_1["id"]
    assert entry_1["email"] == user_1["email"]

    shared = list_shared_users(client, superuser_token_headers, source_id)
    assert [s["user_id"] for s in shared] == [user_1["id"]]
    assert get_knowledge_source(client, superuser_token_headers, source_id)["shared_user_count"] == 1

    # ── Phase 4: Idempotent add ──────────────────────────────────────────────
    add_shared_user(client, superuser_token_headers, source_id, user_1["id"])
    shared = list_shared_users(client, superuser_token_headers, source_id)
    assert len(shared) == 1

    # ── Phase 5: Add a second user ───────────────────────────────────────────
    user_2 = create_random_user(client)
    add_shared_user(client, superuser_token_headers, source_id, user_2["id"])
    shared = list_shared_users(client, superuser_token_headers, source_id)
    assert {s["user_id"] for s in shared} == {user_1["id"], user_2["id"]}
    assert get_knowledge_source(client, superuser_token_headers, source_id)["shared_user_count"] == 2

    # ── Phase 6: Remove first user ───────────────────────────────────────────
    r = remove_shared_user(client, superuser_token_headers, source_id, user_1["id"])
    assert r.status_code == 200, r.text
    shared = list_shared_users(client, superuser_token_headers, source_id)
    assert [s["user_id"] for s in shared] == [user_2["id"]]

    # ── Phase 7: Removing a user not on the list → 404 ──────────────────────
    r = remove_shared_user(client, superuser_token_headers, source_id, user_1["id"])
    assert r.status_code == 404

    # ── Phase 8: Add on a non-existent source → 404 ─────────────────────────
    ghost_source = str(uuid.uuid4())
    r = client.post(
        f"{_BASE}/{ghost_source}/shared-users",
        headers=superuser_token_headers,
        json={"user_id": user_1["id"]},
    )
    assert r.status_code == 404
    r = client.get(f"{_BASE}/{ghost_source}/shared-users", headers=superuser_token_headers)
    assert r.status_code == 404
    r = remove_shared_user(client, superuser_token_headers, ghost_source, user_1["id"])
    assert r.status_code == 404

    # ── Phase 9: Add a non-existent user → 404 ──────────────────────────────
    ghost_user = str(uuid.uuid4())
    r = client.post(
        f"{_BASE}/{source_id}/shared-users",
        headers=superuser_token_headers,
        json={"user_id": ghost_user},
    )
    assert r.status_code == 404

    # ── Phase 10: Non-admin rejected on list/add/remove ─────────────────────
    other_user, other_headers = create_random_user_with_headers(client)
    assert client.get(
        f"{_BASE}/{source_id}/shared-users", headers=other_headers
    ).status_code == 403
    assert client.post(
        f"{_BASE}/{source_id}/shared-users",
        headers=other_headers,
        json={"user_id": user_2["id"]},
    ).status_code == 403
    assert remove_shared_user(
        client, other_headers, source_id, user_2["id"]
    ).status_code == 403


# ---------------------------------------------------------------------------
# Scenario 5: Article content preview + Markdown export (any admin, any level)
# ---------------------------------------------------------------------------

def test_article_content_and_export(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Article preview content + source export — readable by ANY superuser
    regardless of who created the source or its access_level:
      1.  Creator connects the source and refreshes → one article persisted
      2.  Creator GET article content → 200, body has content + commit_hash
      3.  GET with random article id → 404
      4.  GET with article id from a *different* source → 404
      5.  Creator GET export → 200, text/markdown, attachment, body has content
      6.  Export of an empty source → 200, header-only doc (no crash)
      7.  A different (unrelated) superuser can ALSO read article + export,
          even though the source is left at its default access_level=private
      8.  Non-superuser is rejected (403) on both endpoints
    """
    article_holder: dict = {
        "content": "# Title\n\nLong markdown body for preview.",
        "title": "Preview Article",
        "file_path": "articles/preview.md",
    }

    # ── Phase 1: Create + connect + refresh (inserts one real article) ─────
    source = create_knowledge_source(client, superuser_token_headers)
    source_id = source["id"]
    assert source["access_level"] == "private"
    _connect_source(client, superuser_token_headers, source_id)

    patches = _refresh_patches_with_article(article_holder)
    with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
        r = client.post(f"{_BASE}/{source_id}/refresh", headers=superuser_token_headers)
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "success"

    articles = list_knowledge_articles(client, superuser_token_headers, source_id)
    assert len(articles) == 1
    article_id = articles[0]["id"]
    # listing endpoint must NOT leak content
    assert "content" not in articles[0]

    # ── Phase 2: Creator reads article content ─────────────────────────────
    r = get_knowledge_article(client, superuser_token_headers, source_id, article_id)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"] == article_holder["content"]
    assert body["commit_hash"] == "abc123"
    assert body["title"] == "Preview Article"

    # ── Phase 3: Random article id → 404 ──────────────────────────────────
    r = get_knowledge_article(
        client, superuser_token_headers, source_id, str(uuid.uuid4())
    )
    assert r.status_code == 404

    # ── Phase 4: Article from a different source → 404 ────────────────────
    other_source = create_knowledge_source(client, superuser_token_headers)
    r = get_knowledge_article(
        client, superuser_token_headers, other_source["id"], article_id
    )
    assert r.status_code == 404

    # ── Phase 5: Creator export ─────────────────────────────────────────────
    r = export_knowledge_source(client, superuser_token_headers, source_id)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/markdown")
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".md" in r.headers.get("content-disposition", "")
    assert source["name"] in r.text
    assert "Preview Article" in r.text
    assert "Long markdown body for preview." in r.text

    # ── Phase 6: Export of an empty source → header-only doc ──────────────
    empty_source = create_knowledge_source(client, superuser_token_headers)
    r = export_knowledge_source(client, superuser_token_headers, empty_source["id"])
    assert r.status_code == 200
    assert empty_source["name"] in r.text

    # ── Phase 7: A different, unrelated superuser reads it too — no
    #             ownership/access-level gate on admin read routes ─────────
    _, second_su_headers = _make_second_superuser(client, superuser_token_headers)

    r = get_knowledge_article(client, second_su_headers, source_id, article_id)
    assert r.status_code == 200, r.text
    assert r.json()["content"] == article_holder["content"]

    r = export_knowledge_source(client, second_su_headers, source_id)
    assert r.status_code == 200
    assert "Preview Article" in r.text

    # ── Phase 8: Non-superuser rejected on both endpoints ──────────────────
    normal_user = create_random_user(client)
    normal_headers = user_authentication_headers(
        client=client, email=normal_user["email"], password=normal_user["_password"]
    )
    assert (
        get_knowledge_article(client, normal_headers, source_id, article_id).status_code
        == 403
    )
    assert (
        export_knowledge_source(client, normal_headers, source_id).status_code == 403
    )


# ---------------------------------------------------------------------------
# Scenario 6: SSH key deletion guard + creator/key deletion cascades
# ---------------------------------------------------------------------------

def test_ssh_key_delete_guard_and_deletion_cascades(
    client: TestClient,
    superuser_token_headers: dict[str, str],
) -> None:
    """
    Deletion side effects that must not corrupt a still-existing source:
      1. Admin B creates a source with their own SSH key
      2. Admin B tries to delete that SSH key directly → 409 (still in use)
      3. Admin A (another superuser) deletes Admin B's account entirely
      4. Admin B's SSH key cascade-deletes with the account; the source
         SET NULLs both `ssh_key_id` and the creator fields, and survives
      5. Admin A can still manage the orphaned source (get/update)
    """
    _, admin_b_headers = _make_second_superuser(client, superuser_token_headers)
    admin_b_id = client.get(
        f"{settings.API_V1_STR}/users/me", headers=admin_b_headers
    ).json()["id"]

    key_b = generate_random_ssh_key(client, admin_b_headers)
    source = create_knowledge_source(client, admin_b_headers, ssh_key_id=key_b["id"])
    source_id = source["id"]
    assert source["ssh_key_id"] == key_b["id"]
    assert source["created_by_email"] is not None

    # ── Phase 2: Direct key deletion is blocked while in use ───────────────
    r = client.delete(
        f"{settings.API_V1_STR}/ssh-keys/{key_b['id']}", headers=admin_b_headers
    )
    assert r.status_code == 409, r.text
    assert source["name"] in r.json()["detail"]

    # ── Phase 3: Delete the creating admin's account entirely ─────────────
    r = client.delete(
        f"{settings.API_V1_STR}/users/{admin_b_id}", headers=superuser_token_headers
    )
    assert r.status_code == 200, r.text

    # ── Phase 4: Source survives; ssh_key_id + creator fields are nulled ──
    fetched = get_knowledge_source(client, superuser_token_headers, source_id)
    assert fetched["ssh_key_id"] is None
    assert fetched["user_id"] is None
    assert fetched["created_by_email"] is None
    assert fetched["created_by_name"] is None

    # ── Phase 5: Still manageable by any admin ─────────────────────────────
    updated = update_knowledge_source(
        client, superuser_token_headers, source_id, description="orphan source"
    )
    assert updated["description"] == "orphan source"

