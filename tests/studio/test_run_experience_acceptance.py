"""Current-policy acceptance of the actual ordinary Run HTTP composition."""

import threading

import pytest

from tests.studio.run_experience_fixtures import RunControl, build_run_experience_harness, forbid_real_effects
from tests.studio.test_run_replay_http import _http_json, _wait_terminal
from zhixing.studio.httpd import create_http_server


@pytest.fixture(autouse=True)
def effect_canaries():
    """Install effect tripwires for every new acceptance test and assert zero.

    Raises:
        AssertionError: A forbidden attempt occurred even if runtime caught it.
    Yields:
        Instrumented counters; literal loopback HTTP/SSE remains permitted.
    """
    with forbid_real_effects() as counts:
        yield counts
    assert all(value == 0 for value in counts.values())


@pytest.mark.parametrize("fail_at", [None, 1, 2])
def test_current_policy_http_run_preserves_same_source_and_retry(tmp_path, fail_at):
    """Exercise current template/readiness and retain success or failure evidence.

    Args:
        tmp_path: Empty pytest-owned directory.
        fail_at: Optional first or second reasoning failure.
    Raises:
        AssertionError: Actual HTTP identity, invocation counts, or Replay diverge.
    """
    harness = build_run_experience_harness(tmp_path, control=RunControl(fail_at=fail_at))
    server = create_http_server(
        "127.0.0.1", 0, application_service=harness.authoring,
        run_composition=harness.composition,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    address = ("127.0.0.1", server.server_address[1])
    try:
        request = {
            "schemaVersion": 1, "clientRequestId": "acceptance-intent",
            "agentId": harness.agent_id, "revisionId": harness.revision_id,
            "task": {"text": "FAKE: tap the synthetic target once, then finish"},
            "deviceProfileId": "acceptance-fake",
        }
        status, created = _http_json(address, "POST", "/api/studio/runs", request)
        assert status == 202, created
        status, retry = _http_json(address, "POST", "/api/studio/runs", request)
        assert status == 202 and not retry["created"]
        assert retry["runId"] == created["runId"]
        terminal = _wait_terminal(address, created["runId"])
        assert terminal["result"]["status"] == ("success" if fail_at is None else "failure")
        assert harness.control.executions == 1
        assert harness.control.secret_attempts == 0
        assert harness.control.model_calls == (fail_at or 2)
        assert sum(call[0] == "tap" for call in harness.device.calls) == (0 if fail_at == 1 else 1)
        before = (harness.control.model_calls, len(harness.device.calls))
        status, replay = _http_json(address, "GET", f"/api/studio/replays/{created['runId']}")
        assert status == 200, replay
        assert len(replay["observations"]) == (1 if fail_at == 1 else 2)
        assert before == (harness.control.model_calls, len(harness.device.calls))
    finally:
        harness.control.release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        harness.close()


def test_acceptance_rejects_nonempty_workspace(tmp_path):
    """Refuse to reuse or mutate existing workspace data.

    Args:
        tmp_path: Pytest-owned directory containing a sentinel.
    Raises:
        AssertionError: Fixture accepts existing data or changes the sentinel.
    """
    sentinel = tmp_path / "existing.txt"
    sentinel.write_text("preserve", encoding="utf-8")
    with pytest.raises(ValueError, match="empty isolated"):
        build_run_experience_harness(tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "preserve"
