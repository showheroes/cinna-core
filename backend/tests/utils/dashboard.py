"""Helper functions for dashboard API tests."""
from fastapi.testclient import TestClient

from app.core.config import settings
from tests.utils.utils import random_lower_string


_BASE = f"{settings.API_V1_STR}/dashboards"


# ── Dashboard helpers ────────────────────────────────────────────────────────

def create_dashboard(
    client: TestClient,
    token_headers: dict[str, str],
    name: str | None = None,
    description: str | None = None,
) -> dict:
    """Create a dashboard via POST /dashboards/ and return response JSON."""
    payload = {"name": name or f"Dashboard {random_lower_string()[:8]}"}
    if description is not None:
        payload["description"] = description
    r = client.post(f"{_BASE}/", headers=token_headers, json=payload)
    assert r.status_code == 200, f"Create dashboard failed: {r.text}"
    return r.json()


def list_dashboards(client: TestClient, token_headers: dict[str, str]) -> list[dict]:
    """List dashboards via GET /dashboards/."""
    r = client.get(f"{_BASE}/", headers=token_headers)
    assert r.status_code == 200, f"List dashboards failed: {r.text}"
    return r.json()


def get_dashboard(
    client: TestClient, token_headers: dict[str, str], dashboard_id: str
) -> dict:
    """Get a single dashboard via GET /dashboards/{id}."""
    r = client.get(f"{_BASE}/{dashboard_id}", headers=token_headers)
    assert r.status_code == 200, f"Get dashboard failed: {r.text}"
    return r.json()


def update_dashboard(
    client: TestClient,
    token_headers: dict[str, str],
    dashboard_id: str,
    **fields,
) -> dict:
    """Update a dashboard via PUT /dashboards/{id}."""
    r = client.put(f"{_BASE}/{dashboard_id}", headers=token_headers, json=fields)
    assert r.status_code == 200, f"Update dashboard failed: {r.text}"
    return r.json()


def delete_dashboard(
    client: TestClient, token_headers: dict[str, str], dashboard_id: str
) -> None:
    """Delete a dashboard via DELETE /dashboards/{id}."""
    r = client.delete(f"{_BASE}/{dashboard_id}", headers=token_headers)
    assert r.status_code == 200, f"Delete dashboard failed: {r.text}"


# ── Block helpers ────────────────────────────────────────────────────────────

def add_block(
    client: TestClient,
    token_headers: dict[str, str],
    dashboard_id: str,
    agent_id: str,
    view_type: str = "latest_session",
    title: str | None = None,
    show_header: bool = False,
    grid_x: int = 0,
    grid_y: int = 0,
    grid_w: int = 2,
    grid_h: int = 2,
) -> dict:
    """Add a block to a dashboard via POST /dashboards/{id}/blocks."""
    payload = {
        "agent_id": agent_id,
        "view_type": view_type,
        "title": title,
        "show_border": True,
        "show_header": show_header,
        "grid_x": grid_x,
        "grid_y": grid_y,
        "grid_w": grid_w,
        "grid_h": grid_h,
    }
    r = client.post(
        f"{_BASE}/{dashboard_id}/blocks", headers=token_headers, json=payload
    )
    assert r.status_code == 200, f"Add block failed: {r.text}"
    return r.json()


def update_block(
    client: TestClient,
    token_headers: dict[str, str],
    dashboard_id: str,
    block_id: str,
    **fields,
) -> dict:
    """Update a block via PUT /dashboards/{id}/blocks/{block_id}."""
    r = client.put(
        f"{_BASE}/{dashboard_id}/blocks/{block_id}",
        headers=token_headers,
        json=fields,
    )
    assert r.status_code == 200, f"Update block failed: {r.text}"
    return r.json()


def delete_block(
    client: TestClient,
    token_headers: dict[str, str],
    dashboard_id: str,
    block_id: str,
) -> None:
    """Delete a block via DELETE /dashboards/{id}/blocks/{block_id}."""
    r = client.delete(
        f"{_BASE}/{dashboard_id}/blocks/{block_id}", headers=token_headers
    )
    assert r.status_code == 200, f"Delete block failed: {r.text}"


def update_block_layout(
    client: TestClient,
    token_headers: dict[str, str],
    dashboard_id: str,
    layouts: list[dict],
) -> list[dict]:
    """Bulk update block layout via PUT /dashboards/{id}/blocks/layout."""
    r = client.put(
        f"{_BASE}/{dashboard_id}/blocks/layout",
        headers=token_headers,
        json=layouts,
    )
    assert r.status_code == 200, f"Update block layout failed: {r.text}"
    return r.json()
