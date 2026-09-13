"""Real HTTP contract tests for the local Studio application service."""

from __future__ import annotations

import http.client
import json
import threading
from collections.abc import Iterator

import pytest

from zhixing.studio import (
    SQLiteAgentDocumentRepository,
    StudioApplicationService,
    build_studio_component_catalog,
)
from zhixing.studio.httpd import create_http_server

from .test_documents_catalog_compiler import _planner_document


@pytest.fixture
def studio_http_server(tmp_path) -> Iterator[tuple[str, int]]:
    """Run a real ephemeral Studio HTTP server for one test.

    Args:
        tmp_path (Path): Pytest temporary directory.

    Raises:
        OSError: Server socket cannot bind.

    Yields:
        Iterator[tuple[str, int]]: Host and ephemeral port.
    """
    service = StudioApplicationService(
        catalog=build_studio_component_catalog(),
        repository=SQLiteAgentDocumentRepository(tmp_path / "studio.sqlite3"),
    )
    server = create_http_server(
        "127.0.0.1",
        0,
        application_service=service,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield "127.0.0.1", int(server.server_address[1])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)


def _request(
    server: tuple[str, int],
    method: str,
    path: str,
    payload: object | None = None,
    *,
    origin: str | None = None,
) -> tuple[int, dict]:
    """Send one JSON request to the ephemeral server.

    Args:
        server (tuple[str, int]): Host and port.
        method (str): HTTP method.
        path (str): Request path.
        payload (object | None): Optional JSON request.
        origin (str | None): Optional browser Origin.

    Raises:
        OSError: HTTP transport fails.
        json.JSONDecodeError: Response is not JSON.

    Returns:
        tuple[int, dict]: HTTP status and decoded object.
    """
    connection = http.client.HTTPConnection(*server, timeout=5)
    headers = {"Accept": "application/json"}
    body = None
    if payload is not None:
        body = json.dumps(payload)
        headers["Content-Type"] = "application/json"
    if origin is not None:
        headers["Origin"] = origin
    try:
        connection.request(method, path, body=body, headers=headers)
        response = connection.getresponse()
        return response.status, json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()


def test_catalog_compile_and_agent_revision_http_contract(studio_http_server) -> None:
    """Exercise create, compile, save, load, rename, and conflict routes."""
    status, catalog = _request(
        studio_http_server,
        "GET",
        "/studio/components/catalog",
    )
    assert status == 200
    assert catalog["schemaVersion"] == 1
    assert catalog["catalogVersion"].startswith("sha256:")

    document = _planner_document()
    status, compiled = _request(
        studio_http_server,
        "POST",
        "/studio/agent-graphs/compile",
        {
            "schemaVersion": 1,
            "catalogVersion": catalog["catalogVersion"],
            "document": document,
        },
    )
    assert status == 200
    assert compiled["isSuccess"] is True
    assert compiled["canonicalHash"].startswith("sha256:")

    status, created = _request(
        studio_http_server,
        "POST",
        "/studio/agents",
        {
            "schemaVersion": 1,
            "name": "HTTP Planner",
            "initialDocument": document,
        },
    )
    assert status == 201
    agent_id = created["agent"]["agentId"]
    first_revision_id = created["currentRevision"]["revisionId"]
    saved_document = created["currentRevision"]["document"]
    assert saved_document["agentId"] == agent_id

    status, loaded = _request(
        studio_http_server,
        "GET",
        f"/studio/agents/{agent_id}",
    )
    assert status == 200
    assert loaded["currentRevision"]["revisionId"] == first_revision_id

    saved_document["presentation"]["nodes"]["canvas-planner"]["x"] = 800
    status, saved = _request(
        studio_http_server,
        "POST",
        f"/studio/agents/{agent_id}/revisions",
        {
            "schemaVersion": 1,
            "baseRevisionId": first_revision_id,
            "document": saved_document,
        },
    )
    assert status == 201
    second_revision_id = saved["revision"]["revisionId"]
    assert second_revision_id != first_revision_id
    assert (
        saved["revision"]["compileSnapshot"]["canonicalHash"]
        == created["currentRevision"]["compileSnapshot"]["canonicalHash"]
    )

    status, conflict = _request(
        studio_http_server,
        "POST",
        f"/studio/agents/{agent_id}/revisions",
        {
            "schemaVersion": 1,
            "baseRevisionId": first_revision_id,
            "document": saved_document,
        },
    )
    assert status == 409
    assert conflict["error"]["code"] == "studio.revision.conflict"
    assert conflict["error"]["currentRevisionId"] == second_revision_id

    status, renamed = _request(
        studio_http_server,
        "PATCH",
        f"/studio/agents/{agent_id}",
        {"schemaVersion": 1, "name": "Renamed"},
    )
    assert status == 200
    assert renamed["agent"]["name"] == "Renamed"


def test_invalid_compile_is_normal_result_and_malformed_json_is_400(
    studio_http_server,
) -> None:
    """Distinguish business diagnostics from malformed transport input."""
    status, invalid = _request(
        studio_http_server,
        "POST",
        "/studio/agent-graphs/compile",
        {
            "schemaVersion": 1,
            "document": {
                "schemaVersion": 2,
                "contractVersion": "1.1",
                "documentId": "d",
                "agentId": "a",
                "name": "Invalid",
                "semantic": {"nodes": [], "edges": []},
            },
        },
    )
    assert status == 200
    assert invalid["isSuccess"] is False
    assert invalid["canonicalHash"] is None

    connection = http.client.HTTPConnection(*studio_http_server, timeout=5)
    try:
        connection.request(
            "POST",
            "/studio/agents",
            body="{broken",
            headers={
                "Content-Type": "application/json",
                "Content-Length": "7",
            },
        )
        response = connection.getresponse()
        payload = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    assert response.status == 400
    assert payload["error"]["code"] == "studio.http.json_invalid"


def test_request_size_and_origin_boundaries(studio_http_server) -> None:
    """Reject oversized writes and untrusted browser origins."""
    connection = http.client.HTTPConnection(*studio_http_server, timeout=5)
    try:
        connection.putrequest("POST", "/studio/agents")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("Content-Length", str(2 * 1024 * 1024 + 1))
        connection.endheaders()
        response = connection.getresponse()
        oversized = json.loads(response.read().decode("utf-8"))
    finally:
        connection.close()
    assert response.status == 413
    assert oversized["error"]["code"] == "studio.http.body_too_large"

    status, forbidden = _request(
        studio_http_server,
        "GET",
        "/studio/components/catalog",
        origin="https://attacker.invalid",
    )
    assert status == 403
    assert forbidden["error"]["code"] == "studio.http.forbidden"


def test_legacy_metadata_routes_remain_available(studio_http_server) -> None:
    """Keep the existing Builder metadata/template paths reachable."""
    status, navigation = _request(
        studio_http_server,
        "GET",
        "/studio/nav-modules",
    )
    assert status == 200
    assert any(item["path"] == "/builder" for item in navigation["modules"])

    status, templates = _request(
        studio_http_server,
        "GET",
        "/studio/flow-templates",
    )
    assert status == 200
    assert isinstance(templates["templates"], list)


def test_legacy_document_migration_http_contract(studio_http_server) -> None:
    """Migrate schema 1 as a pure API operation with explicit diagnostics."""
    legacy = {
        "schemaVersion": 1,
        "contractVersion": "1.0",
        "flowId": "legacy-empty",
        "flowName": "Legacy",
        "nodes": [],
        "edges": [],
    }
    status, migrated = _request(
        studio_http_server,
        "POST",
        "/studio/flow-documents/migrate",
        {
            "schemaVersion": 1,
            "agentId": "agent-migrated",
            "document": legacy,
        },
    )
    assert status == 200
    assert migrated["schemaVersion"] == 1
    assert migrated["isSuccess"] is True
    assert migrated["document"]["schemaVersion"] == 2
    assert migrated["document"]["agentId"] == "agent-migrated"
    assert legacy["schemaVersion"] == 1
