"""Agent Skills routes — the three owner-scoped endpoints on the agent page.

    GET  /agents/{id}/skills                  — cached index, never wakes the env
    POST /agents/{id}/skills/refresh          — re-read, same shape
    GET  /agents/{id}/skills/{name}/content   — one skill's SKILL.md

Scenarios:
  1. Index → content → refresh lifecycle, plus the ownership / 404 guards.
  2. ``can_publish`` as a capability reply: the agent-level flag and the
     per-entry one, including a developer looking at a foreign install.
  3. Refresh on an unreachable environment: cached rows kept, reason recorded
     (``adapter_error`` for a running container that cannot answer — which is
     what a pre-feature ``/app/core`` looks like — and ``env_not_running`` for a
     stopped one).
  4. A watcher signal naming ``skills/`` refreshes the cache inside the 30 s
     rate-limit window; one naming a different file does not.
  5. An agent with no environment answers an empty list, not an error.
  6. Opening a skill wakes a suspended environment; a stopped one is a 503.
  7. A skill folder's files are listed host-side, without waking the env.

Test seam:
  The skills cache is populated by the env-start sweep
  (``_sync_dynamic_data`` → ``AgentSkillsService.refresh_after_action``), so a
  scenario seeds the stub adapter's ``skills_index`` BEFORE creating the agent
  and drains. Unit coverage of the cache service itself (normalisation, the
  write short-circuit, the ``AGENT_UPDATED`` rule) lives in
  ``tests/unit/test_agent_skills_service.py``.
"""
import uuid
from typing import Any

from fastapi.testclient import TestClient
from sqlmodel import Session

from app.core.config import settings
from tests.stubs.environment_adapter_stub import EnvironmentTestAdapter
from tests.utils.agent import create_agent_via_api, get_agent
from tests.utils.background_tasks import drain_tasks
from tests.utils.bundle import (
    install_bundle,
    make_user_and_headers,
    publish_bundle_and_make_public,
)
from tests.utils.environment import (
    delete_environment,
    get_environment,
    set_environment_auth_token,
    set_environment_status,
    stop_environment,
)
from tests.utils.skill_catalog import workspace_root, write_skill
from tests.utils.user import (
    create_random_user_with_headers,
    promote_to_developer,
)

API = settings.API_V1_STR


# ── Payload helpers ────────────────────────────────────────────────────────


def _row(name: str, **overrides: Any) -> dict:
    """One entry in the shape env-core's ``GET /config/skills`` reports."""
    entry = {
        "name": name,
        "description": f"Does {name} things.",
        "source": "local",
        "plugin_ref": None,
        "path": f"skills/{name}",
        "has_scripts": False,
        "user_invocable": True,
        "model_invocable": True,
        "size_bytes": 512,
        "error": None,
        "warning": None,
        "secret_paths": [],
    }
    entry.update(overrides)
    return entry


def _index(rows: list[dict], tree_hash: str = "hash-1") -> dict:
    return {"hash": tree_hash, "skills": rows, "errors": []}


def _skill_md(name: str) -> bytes:
    return (
        f"---\nname: {name}\ndescription: Does {name} things.\n---\n\n"
        f"# {name}\n\nStep one.\n"
    ).encode()


def _install_adapter(
    lifecycle_manager,
    *,
    index: dict | None = None,
    files: dict[str, bytes] | None = None,
) -> EnvironmentTestAdapter:
    """Route every ``get_adapter`` call at one adapter the test controls.

    ``workspace_files`` is set as an INSTANCE attribute: the stub declares it at
    class level, so mutating it in place would leak seeded files into every
    later test in the session.
    """
    adapter = EnvironmentTestAdapter()
    adapter.skills_index = index or _index([])
    adapter.workspace_files = dict(files or {})
    lifecycle_manager.get_adapter = lambda env: adapter
    return adapter


def _get_skills(client: TestClient, headers: dict[str, str], agent_id: str) -> dict:
    r = client.get(f"{API}/agents/{agent_id}/skills", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _refresh_skills(
    client: TestClient, headers: dict[str, str], agent_id: str
) -> dict:
    r = client.post(f"{API}/agents/{agent_id}/skills/refresh", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _by_name(payload: dict) -> dict[str, dict]:
    return {entry["name"]: entry for entry in payload["skills"]}


# ── Scenario 1: index → content → refresh ──────────────────────────────────


def test_agent_skills_index_content_and_refresh_lifecycle(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    The card's whole read path:
      1. Create an agent whose environment reports three skills.
      2. GET /skills → all three, with hash / fetched_at / no error.
      3. GET /skills/{name}/content → the SKILL.md text, at the cached path.
      4. Content for a name that is not in the index → 404 "Skill not found".
      5. Content for an indexed skill whose file is gone → 404 that says the
         list is stale (a different next step for the user).
      6. The environment's index changes → GET /skills still serves the cache
         (a poll must never wake a container).
      7. POST /skills/refresh → the new list, and the cache now holds it.
      8. Auth + ownership guards; unknown agent id is a 404.
    """
    # ── Phase 1: env reports three skills ────────────────────────────────
    adapter = _install_adapter(
        patch_environment_adapter,
        index=_index(
            [
                _row("pdf-report", has_scripts=True),
                _row(
                    "from-plugin",
                    source="plugin",
                    plugin_ref="mkt/reporting",
                    path="plugins/mkt/reporting/skills/from-plugin",
                ),
                _row(
                    "broken",
                    error={
                        "code": "name_mismatch",
                        "message": "The name in SKILL.md does not match the folder name.",
                        "paths": [],
                    },
                ),
            ]
        ),
        files={"skills/pdf-report/SKILL.md": _skill_md("pdf-report")},
    )
    agent = create_agent_via_api(client, superuser_token_headers, name="Skilled")
    agent_id = agent["id"]
    drain_tasks()  # env-start sweep populates the cache

    # ── Phase 2: the index reaches the card ──────────────────────────────
    payload = _get_skills(client, superuser_token_headers, agent_id)
    assert payload["agent_id"] == agent_id
    assert payload["environment_id"] is not None
    assert [s["name"] for s in payload["skills"]] == [
        "pdf-report",
        "from-plugin",
        "broken",
    ]
    assert payload["hash"] == "hash-1"
    assert payload["fetched_at"] is not None
    assert payload["error"] is None

    entries = _by_name(payload)
    assert entries["pdf-report"]["has_scripts"] is True
    assert entries["from-plugin"]["source"] == "plugin"
    assert entries["from-plugin"]["plugin_ref"] == "mkt/reporting"
    assert entries["broken"]["error"]["code"] == "name_mismatch"
    assert entries["broken"]["error"]["message"], "the code travels with its copy"

    # ── Phase 3: SKILL.md text ───────────────────────────────────────────
    r = client.get(
        f"{API}/agents/{agent_id}/skills/pdf-report/content",
        headers=superuser_token_headers,
    )
    assert r.status_code == 200, r.text
    content = r.json()
    assert content["name"] == "pdf-report"
    # The path is derived from the CACHED entry, not from the name in the URL.
    assert content["path"] == "skills/pdf-report/SKILL.md"
    assert "Step one." in content["content"]
    assert content["truncated"] is False

    # ── Phase 4: a name that is not a skill ──────────────────────────────
    r = client.get(
        f"{API}/agents/{agent_id}/skills/ghost/content",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert "Skill not found" in r.json()["detail"]

    # ── Phase 5: indexed, but the file is gone → "refresh" ───────────────
    r = client.get(
        f"{API}/agents/{agent_id}/skills/from-plugin/content",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert "refresh" in r.json()["detail"].lower(), (
        "a stale-cache 404 must tell the user their list is out of date"
    )

    # ── Phase 6: GET is cache-only ───────────────────────────────────────
    adapter.skills_index = _index(
        [_row("pdf-report", has_scripts=True), _row("new-skill")],
        tree_hash="hash-2",
    )
    unchanged = _get_skills(client, superuser_token_headers, agent_id)
    assert [s["name"] for s in unchanged["skills"]] == [
        "pdf-report",
        "from-plugin",
        "broken",
    ], "GET must serve the cache, never re-read the environment"

    # ── Phase 7: refresh picks the new index up ──────────────────────────
    refreshed = _refresh_skills(client, superuser_token_headers, agent_id)
    assert [s["name"] for s in refreshed["skills"]] == ["pdf-report", "new-skill"]
    assert refreshed["hash"] == "hash-2"
    assert refreshed["error"] is None
    # …and the cache now holds it, so the next poll agrees.
    assert [s["name"] for s in _get_skills(
        client, superuser_token_headers, agent_id
    )["skills"]] == ["pdf-report", "new-skill"]

    # ── Phase 8: auth and ownership guards ───────────────────────────────
    assert client.get(f"{API}/agents/{agent_id}/skills").status_code in (401, 403)

    _, other_headers = create_random_user_with_headers(client)
    for method, url in (
        ("get", f"{API}/agents/{agent_id}/skills"),
        ("post", f"{API}/agents/{agent_id}/skills/refresh"),
        ("get", f"{API}/agents/{agent_id}/skills/pdf-report/content"),
    ):
        r = getattr(client, method)(url, headers=other_headers)
        assert r.status_code in (403, 404), f"{method} {url} → {r.status_code}"

    ghost_agent = uuid.uuid4()
    assert client.get(
        f"{API}/agents/{ghost_agent}/skills", headers=superuser_token_headers
    ).status_code == 404


# ── Scenario 2: can_publish is a capability reply ──────────────────────────


def test_can_publish_covers_the_agent_and_each_entry(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    ``can_publish`` answers two different questions, and both are server-side:
      1. Agent level — developer role AND not a consumer install.
      2. Entry level — that, AND the skill is locally owned and clean.

    Phases:
      1. Publisher agent with a clean local skill, a plugin skill, a
         secret-bearing local skill and a broken one.
      2. Owner (developer) → can_publish True; only the clean local skill
         carries an entry-level True.
      3. Publish + install as a second developer → the consumer's install is a
         foreign install, so can_publish is False for the agent AND for every
         entry, even for the very same clean local skill.
    """
    # ── Phase 1: an agent whose env reports one of each kind ─────────────
    _install_adapter(
        patch_environment_adapter,
        index=_index(
            [
                _row("clean-local"),
                _row("plugin-skill", source="plugin", plugin_ref="mkt/p"),
                _row("leaky-local", secret_paths=["scripts/.env"]),
                _row(
                    "broken-local",
                    error={"code": "missing_description", "message": "no description", "paths": []},
                ),
            ]
        ),
    )
    publisher_agent = create_agent_via_api(
        client, superuser_token_headers, name="Publisher-Skills"
    )
    publisher_id = publisher_agent["id"]
    drain_tasks()

    # ── Phase 2: the owning developer ────────────────────────────────────
    payload = _get_skills(client, superuser_token_headers, publisher_id)
    assert payload["can_publish"] is True, "a developer owns this standalone agent"

    entries = _by_name(payload)
    assert entries["clean-local"]["can_publish"] is True
    assert entries["plugin-skill"]["can_publish"] is False, (
        "a plugin's skill belongs to the plugin's publisher"
    )
    assert entries["leaky-local"]["can_publish"] is False, (
        "the publish gate would reject it, so the verb must not be offered"
    )
    assert entries["broken-local"]["can_publish"] is False

    # ── Phase 3: the same skills on a foreign install ────────────────────
    publish_bundle_and_make_public(
        client, superuser_token_headers, publisher_id, notes="v1 with skills"
    )
    consumer, consumer_headers = make_user_and_headers(client)
    # Promote the consumer so the ONLY thing standing between them and
    # can_publish is the foreign-install half of the predicate.
    promote_to_developer(client, superuser_token_headers, consumer["id"])

    fresh_publisher = get_agent(client, superuser_token_headers, publisher_id)
    installed = install_bundle(
        client, consumer_headers, fresh_publisher["bundle_id"]
    )
    installed_agent_id = installed["id"]

    consumer_payload = _get_skills(client, consumer_headers, installed_agent_id)
    assert consumer_payload["can_publish"] is False, (
        "a consumer install is use-only for every role — the developer role "
        "must not unlock publishing somebody else's bundle"
    )
    assert consumer_payload["skills"], (
        "the install's env reports the same index — an empty list here would "
        "make the per-entry assertion below vacuous"
    )
    assert "clean-local" in {e["name"] for e in consumer_payload["skills"]}
    for entry in consumer_payload["skills"]:
        assert entry["can_publish"] is False, entry["name"]


# ── Scenario 3: unreachable environments ───────────────────────────────────


def test_refresh_keeps_cached_rows_and_records_why_it_failed(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    A refresh never fails on an unreachable environment — it answers with the
    cached rows plus the reason, which is what the card renders as a banner.

    Phases:
      1. Agent with one cached skill.
      2. The environment stops answering ``/config/skills`` (what a container
         built before agent skills existed looks like: the endpoint 404s) →
         refresh is still 200, rows survive, error is ``adapter_error``.
      3. Stop the environment → the reason becomes ``env_not_running``, which
         is a different message and a different fix.
      4. The environment answers again → the error clears.
    """
    # ── Phase 1: a populated cache ───────────────────────────────────────
    adapter = _install_adapter(
        patch_environment_adapter, index=_index([_row("pdf-report")])
    )
    agent = create_agent_via_api(client, superuser_token_headers, name="Flaky-Env")
    agent_id = agent["id"]
    drain_tasks()
    assert [s["name"] for s in _get_skills(
        client, superuser_token_headers, agent_id
    )["skills"]] == ["pdf-report"]

    # ── Phase 2: pre-feature container — no such endpoint ────────────────
    async def _no_endpoint():
        raise RuntimeError("404 Not Found: /config/skills")

    adapter.get_skills_index = _no_endpoint

    payload = _refresh_skills(client, superuser_token_headers, agent_id)
    assert payload["error"] == "adapter_error"
    assert [s["name"] for s in payload["skills"]] == ["pdf-report"], (
        "cached rows must survive a failed read — blanking the card would be "
        "a worse answer than showing what we know"
    )

    # ── Phase 3: a stopped environment is a different story ──────────────
    env_id = get_agent(client, superuser_token_headers, agent_id)[
        "active_environment_id"
    ]
    stop_environment(client, superuser_token_headers, env_id)

    payload = _refresh_skills(client, superuser_token_headers, agent_id)
    assert payload["error"] == "env_not_running"
    assert [s["name"] for s in payload["skills"]] == ["pdf-report"]

    # ── Phase 4: a good read clears the banner ───────────────────────────
    async def _answers():
        return _index([_row("pdf-report"), _row("second")], tree_hash="hash-9")

    adapter.get_skills_index = _answers

    payload = _refresh_skills(client, superuser_token_headers, agent_id)
    assert payload["error"] is None
    assert [s["name"] for s in payload["skills"]] == ["pdf-report", "second"]


# ── Scenario 4: the watcher signal ─────────────────────────────────────────


def test_a_watcher_signal_naming_skills_refreshes_inside_the_rate_limit(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
    db: Session,
) -> None:
    """
    ``WORKSPACE_FILES_CHANGED`` from the env-core watcher is direct evidence the
    cache is stale, so it bypasses the 30 s per-environment window. A signal
    about some other watched file is a guess, and does not.

    Phases:
      1. Agent + cache populated by the start sweep (which also opens the
         rate-limit window, so everything below happens inside it).
      2. The environment's index changes.
      3. Watcher signal naming ``docs/CLI_COMMANDS.yaml`` → skills cache
         unchanged (rate-limited).
      4. Watcher signal naming ``skills/`` → cache updated.
    """
    # ── Phase 1: populate ────────────────────────────────────────────────
    adapter = _install_adapter(
        patch_environment_adapter, index=_index([_row("pdf-report")])
    )
    agent = create_agent_via_api(client, superuser_token_headers, name="Watched")
    agent_id = agent["id"]
    drain_tasks()
    env_id = get_agent(client, superuser_token_headers, agent_id)[
        "active_environment_id"
    ]
    assert [s["name"] for s in _get_skills(
        client, superuser_token_headers, agent_id
    )["skills"]] == ["pdf-report"]

    # ── Phase 2: the folder changes behind our back ──────────────────────
    adapter.skills_index = _index(
        [_row("pdf-report"), _row("just-added")], tree_hash="hash-2"
    )

    # The watcher callback authenticates as the environment, not as the user.
    env_token = set_environment_auth_token(db, env_id)
    callback_headers = {
        "Authorization": f"Bearer {env_token}",
        "X-Agent-Env-Id": str(env_id),
    }
    callback_url = f"{API}/environments/{env_id}/workspace-files-changed"

    # ── Phase 3: an unrelated watched file does not force ────────────────
    r = client.post(
        callback_url,
        headers=callback_headers,
        json={"changed_files": ["docs/CLI_COMMANDS.yaml"]},
    )
    assert r.status_code == 200, r.text
    drain_tasks()
    assert [s["name"] for s in _get_skills(
        client, superuser_token_headers, agent_id
    )["skills"]] == ["pdf-report"], (
        "a signal about another file is speculative and stays rate-limited"
    )

    # ── Phase 4: naming skills/ forces the read ──────────────────────────
    r = client.post(
        callback_url,
        headers=callback_headers,
        json={"changed_files": ["skills/"]},
    )
    assert r.status_code == 200, r.text
    drain_tasks()
    payload = _get_skills(client, superuser_token_headers, agent_id)
    assert [s["name"] for s in payload["skills"]] == ["pdf-report", "just-added"]
    assert payload["hash"] == "hash-2"


# ── Scenario 5: an agent with no environment ───────────────────────────────


def test_an_agent_without_an_environment_answers_empty_not_broken(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    No environment is an empty state, not an error: the list is empty, the
    capability flag is still answered (so the card can render its copy), and
    only the content route — which genuinely needs a container — 404s.

    ``get_primary_environment`` falls back to the agent's newest env row when
    the active pointer is clear, so the environment is deleted outright (the
    route clears the pointer for us) rather than just detached.
    """
    _install_adapter(patch_environment_adapter, index=_index([_row("pdf-report")]))
    agent = create_agent_via_api(client, superuser_token_headers, name="No-Env")
    agent_id = agent["id"]
    drain_tasks()

    env_id = get_agent(client, superuser_token_headers, agent_id)[
        "active_environment_id"
    ]
    delete_environment(client, superuser_token_headers, env_id)

    payload = _get_skills(client, superuser_token_headers, agent_id)
    assert payload["skills"] == []
    assert payload["environment_id"] is None
    assert payload["error"] is None
    assert payload["can_publish"] is True, (
        "the capability does not depend on a container being there"
    )

    r = client.get(
        f"{API}/agents/{agent_id}/skills/pdf-report/content",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert "environment" in r.json()["detail"].lower()


# ── Scenario 6: opening a skill wakes a suspended environment ──────────────


def test_reading_a_skill_wakes_a_suspended_environment(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
    db: Session,
) -> None:
    """
    ``SKILL.md`` lives in the container, so opening one takes Refresh's posture:
    a suspended environment is woken, not reported as unavailable.

    Phases:
      1. Agent with one cached skill and its SKILL.md.
      2. Suspend the environment; the stub stops serving files while its
         container is down, as the Docker adapter does.
      3. A name that is not a skill → 404, and the container stays down.
      4. GET content → 200 with the text; the container was started once and
         the environment is running again.
      5. Stop the environment → 503: a stopped env needs a full start that
         opening a dialog does not trigger.
      6. An environment already activating → 503 that says it is waking up.
    """
    # ── Phase 1: a cached skill ──────────────────────────────────────────
    adapter = _install_adapter(
        patch_environment_adapter,
        index=_index([_row("pdf-report")]),
        files={"skills/pdf-report/SKILL.md": _skill_md("pdf-report")},
    )
    agent = create_agent_via_api(client, superuser_token_headers, name="Sleepy")
    agent_id = agent["id"]
    drain_tasks()
    env_id = get_agent(client, superuser_token_headers, agent_id)[
        "active_environment_id"
    ]
    content_url = f"{API}/agents/{agent_id}/skills/pdf-report/content"

    # ── Phase 2: suspend; a stopped container serves nothing ─────────────
    serve_file = adapter.fetch_workspace_item_with_meta

    async def _only_while_running(path: str):
        if await adapter.get_status() != "running":
            raise RuntimeError("container is not running")
        return await serve_file(path)

    adapter.fetch_workspace_item_with_meta = _only_while_running

    r = client.post(
        f"{API}/environments/{env_id}/suspend", headers=superuser_token_headers
    )
    assert r.status_code == 200, r.text
    assert get_environment(client, superuser_token_headers, env_id)[
        "status"
    ] == "suspended"
    starts = adapter.start_calls

    # ── Phase 3: an unknown name never starts a container ────────────────
    r = client.get(
        f"{API}/agents/{agent_id}/skills/ghost/content",
        headers=superuser_token_headers,
    )
    assert r.status_code == 404
    assert adapter.start_calls == starts, (
        "a name that is not a skill must not wake the environment"
    )

    # ── Phase 4: opening the skill wakes it ──────────────────────────────
    r = client.get(content_url, headers=superuser_token_headers)
    assert r.status_code == 200, r.text
    assert "Step one." in r.json()["content"]
    assert adapter.start_calls == starts + 1
    assert get_environment(client, superuser_token_headers, env_id)[
        "status"
    ] == "running"

    # ── Phase 5: a stopped environment is not started from a dialog ──────
    stop_environment(client, superuser_token_headers, env_id)

    r = client.get(content_url, headers=superuser_token_headers)
    assert r.status_code == 503
    assert "unavailable" in r.json()["detail"].lower()
    assert adapter.start_calls == starts + 1

    # ── Phase 6: a wake already under way asks for a retry, not a start ──
    set_environment_status(db, env_id, "activating")

    r = client.get(content_url, headers=superuser_token_headers)
    assert r.status_code == 503
    assert "waking up" in r.json()["detail"].lower()
    assert adapter.start_calls == starts + 1


# ── Scenario 7: what a skill folder carries ────────────────────────────────


def test_skill_files_are_listed_host_side_without_waking_the_environment(
    client: TestClient,
    superuser_token_headers: dict[str, str],
    patch_environment_adapter,
) -> None:
    """
    The Content fact's list: every file of one skill folder with its size and
    run bit, read off the workspace mount rather than through the container.

    Phases:
      1. Agent whose index holds a local skill, a plugin skill, and rows the
         container could write to point elsewhere: a ``..`` climb, the whole
         workspace (``.``), a top-level folder, a symlinked skill folder, and a
         folder that is gone. The files are written on the host workspace,
         including a symlinked file and directory inside the real skill.
      2. Suspend the environment.
      3. Local skill → every regular file, junk and symlinks skipped, the run
         bit kept; the environment is still suspended and was never started.
      4. Plugin skill → resolves inside the plugin folder.
      5. Every row that is not a real skill folder → 404 without a listing;
         unknown name → "Skill not found".
      6. Another user → 403/404.
    """
    # ── Phase 1: an index and the folders behind it ──────────────────────
    stray_rows = {
        "escapee": "skills/../../escapee",
        "whole-workspace": ".",
        "top-level": "scripts",
        "linked": "skills/linked",
        "gone": "skills/gone",
    }
    adapter = _install_adapter(
        patch_environment_adapter,
        index=_index(
            [
                _row("pdf-report", has_scripts=True),
                _row(
                    "from-plugin",
                    source="plugin",
                    plugin_ref="mkt/reporting",
                    path="plugins/mkt/reporting/skills/from-plugin",
                ),
                *(_row(name, path=path) for name, path in stray_rows.items()),
            ]
        ),
    )
    agent = create_agent_via_api(client, superuser_token_headers, name="Folders")
    agent_id = agent["id"]
    drain_tasks()
    env_id = get_agent(client, superuser_token_headers, agent_id)[
        "active_environment_id"
    ]

    skill_dir = write_skill(
        env_id,
        "pdf-report",
        extra={
            "scripts/run.sh": "#!/bin/sh\necho hi\n",
            "references/guide.md": "# Guide\n",
            "__pycache__/cached.pyc": "junk",
        },
    )
    (skill_dir / "scripts" / "run.sh").chmod(0o755)

    plugin_dir = workspace_root(env_id) / "plugins/mkt/reporting/skills/from-plugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "SKILL.md").write_bytes(_skill_md("from-plugin"))

    outside = workspace_root(env_id).parent / "escapee"
    outside.mkdir()
    (outside / "SKILL.md").write_text("not part of the workspace")

    # Symlinks the container could plant: inside the real skill, and as a
    # whole skill folder.
    (skill_dir / "leak.md").symlink_to(outside / "SKILL.md")
    (skill_dir / "outside").symlink_to(outside, target_is_directory=True)
    (workspace_root(env_id) / "skills" / "linked").symlink_to(
        outside, target_is_directory=True
    )
    scripts_dir = workspace_root(env_id) / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "deploy.sh").write_text("echo deploy\n")

    cached = _by_name(_get_skills(client, superuser_token_headers, agent_id))
    assert set(stray_rows) <= set(cached), (
        "every stray row must really be in the index, or its 404 proves nothing"
    )

    def _files(name: str, headers: dict[str, str] = superuser_token_headers):
        return client.get(
            f"{API}/agents/{agent_id}/skills/{name}/files", headers=headers
        )

    # ── Phase 2: asleep ──────────────────────────────────────────────────
    r = client.post(
        f"{API}/environments/{env_id}/suspend", headers=superuser_token_headers
    )
    assert r.status_code == 200, r.text
    starts = adapter.start_calls

    # ── Phase 3: the local skill's folder ────────────────────────────────
    r = _files("pdf-report")
    assert r.status_code == 200, r.text
    listing = r.json()
    assert listing["name"] == "pdf-report"
    assert listing["path"] == "skills/pdf-report"
    assert [f["path"] for f in listing["data"]] == [
        "SKILL.md",
        "references/guide.md",
        "scripts/run.sh",
    ], "junk directories and symlinks are not part of what the skill carries"
    assert listing["count"] == 3
    assert listing["total_size_bytes"] == sum(
        f["size_bytes"] for f in listing["data"]
    )
    assert listing["truncated"] is False
    run_bits = {f["path"]: f["is_executable"] for f in listing["data"]}
    assert run_bits["scripts/run.sh"] is True
    assert run_bits["SKILL.md"] is False

    assert adapter.start_calls == starts, "listing files must not start a container"
    assert get_environment(client, superuser_token_headers, env_id)[
        "status"
    ] == "suspended"

    # ── Phase 4: a plugin's skill ────────────────────────────────────────
    r = _files("from-plugin")
    assert r.status_code == 200, r.text
    assert [f["path"] for f in r.json()["data"]] == ["SKILL.md"]

    # ── Phase 5: nothing to list ─────────────────────────────────────────
    for name in stray_rows:
        r = _files(name)
        assert r.status_code == 404, f"{name}: {r.text}"
        assert r.json()["detail"].startswith("Skill folder not found"), (
            f"{name} is in the index, so its 404 is the stale-folder one"
        )

    r = _files("ghost")
    assert r.status_code == 404
    assert "Skill not found" in r.json()["detail"]

    # ── Phase 6: ownership ───────────────────────────────────────────────
    _, other_headers = create_random_user_with_headers(client)
    assert _files("pdf-report", other_headers).status_code in (403, 404)
