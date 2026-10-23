"""Real protocol adapters with deterministic HTTP doubles and no external services."""

import asyncio
import base64
import io
import json
from types import SimpleNamespace

from PIL import Image
import pytest

from zhixing.core.llm.usage import get_task_usage_dict, record_usage, reset_task_usage
from zhixing.knowledge.guiexplorer import GUIExplorerRetrieval
from zhixing.plugins.agent.guiexplorer.protocol import rank_entries
from zhixing.plugins.llm.guiexplorer_llm import GUIExplorerLLM, _RankingSession

from tests.runtime.guiexplorer_support import Model


def image_file(tmp_path):
    """Create one local deterministic input for actual WEBP serialization.

    Args:
        tmp_path: Isolated local directory.
    Returns:
        str: Input PNG path.
    """
    path = tmp_path / "input.png"
    Image.new("RGB", (240, 400), (80, 90, 100)).save(path)
    return str(path)


@pytest.mark.parametrize("text", ["", "model response"])
def test_model_original_webp_payload_and_response_presence(tmp_path, monkeypatch, text):
    """Check actual image encoding, request settings, usage and successful empty content.

    Args:
        tmp_path: Local image directory.
        monkeypatch: HTTP boundary replacement.
        text: Successful source response content.
    Returns:
        None.
    """
    import requests

    calls = []
    reset_task_usage()

    def post(url, **kwargs):
        """Capture one actual source-model request and return a successful response.

        Args:
            url: Actual model endpoint.
            kwargs: Actual transport arguments.
        Returns:
            SimpleNamespace: Deterministic HTTP response boundary.
        """
        calls.append((url, kwargs))
        return SimpleNamespace(ok=True, json=lambda: {"choices": [{"message": {"content": text}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2}})

    monkeypatch.setattr(requests, "post", post)
    model = GUIExplorerLLM(model="fixture-model", base_url="http://fixture/v1", api_key="dummy-private-key", low_resolution=False)
    path = image_file(tmp_path)
    reply = model.generate_guiexplorer("source prompt", (path, path))
    assert reply.has_response and reply.text == text
    url, request = calls[0]
    assert url == "http://fixture/v1/chat/completions" and request["timeout"] == 60
    payload = request["json"]
    assert payload["model"] == "fixture-model" and payload["temperature"] == 0.0 and payload["max_tokens"] == 1000
    content = payload["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "source prompt"} and len(content) == 3
    for item in content[1:]:
        assert "detail" not in item["image_url"]
        mime, data = item["image_url"]["url"].split(",")
        assert mime == "data:image/webp;base64"
        with Image.open(io.BytesIO(base64.b64decode(data))) as image:
            assert image.format == "WEBP" and image.size == (240, 400)
    assert get_task_usage_dict()["total_tokens"] == 7
    assert "dummy-private-key" not in repr(reply)


def test_low_resolution_pillow_compatibility(tmp_path, monkeypatch):
    """Exercise the original resize rule with the supported Pillow constant spelling.

    Args:
        tmp_path: Local fixture image directory.
        monkeypatch: HTTP replacement.
    Returns:
        None.
    """
    import requests

    content = []

    def post(url, **kwargs):
        """Capture encoded image dimensions without making a network request.

        Args:
            url, kwargs: Actual transport input.
        Returns:
            SimpleNamespace: Successful external boundary.
        """
        encoded = kwargs["json"]["messages"][0]["content"][1]["image_url"]["url"].split(",")[1]
        with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
            content.append(image.size)
        return SimpleNamespace(ok=True, json=lambda: {"choices": [{"message": {"content": "ok"}}]})

    monkeypatch.setattr(requests, "post", post)
    GUIExplorerLLM(low_resolution=True).generate_guiexplorer("prompt", (image_file(tmp_path),))
    assert content == [(600, 1000)]


def test_non_ok_model_responses_are_bounded_and_private(tmp_path, monkeypatch):
    """Verify the explicitly recorded repair of the official infinite HTTP-error loop.

    Args:
        tmp_path: Local image directory.
        monkeypatch: HTTP/timing boundary replacements.
    Returns:
        None.
    """
    import requests
    from zhixing.plugins.llm import guiexplorer_llm

    calls, sleeps = [], []
    monkeypatch.setattr(guiexplorer_llm.time, "sleep", sleeps.append)

    def post(*args, **kwargs):
        """Return repeated source-shaped HTTP errors without emitting private content.

        Args:
            args, kwargs: Actual model request.
        Returns:
            SimpleNamespace: Failing external response.
        """
        calls.append(True)
        return SimpleNamespace(ok=False, json=lambda: {"error": {"message": "dummy-private-error"}})

    monkeypatch.setattr(requests, "post", post)
    reply = GUIExplorerLLM().generate_guiexplorer("prompt", (image_file(tmp_path),))
    assert len(calls) == 5 and sleeps == [1, 2, 4, 8, 16]
    assert not reply.has_response and "dummy-private-error" not in repr(reply)


def test_retrieval_payload_and_original_retry_budget(tmp_path, monkeypatch):
    """Validate actual image queries, package/top-k/threshold, and three source tries.

    Args:
        tmp_path: Local crop directory.
        monkeypatch: HTTP/timing boundary replacements.
    Returns:
        None.
    """
    import requests
    from zhixing.knowledge import guiexplorer

    calls, sleeps = [], []
    monkeypatch.setattr(guiexplorer.time, "sleep", sleeps.append)

    def post(url, **kwargs):
        """Fail two real adapter attempts, then return original-shaped empty knowledge.

        Args:
            url, kwargs: Actual request arguments.
        Raises:
            OSError: First two simulated network failures.
        Returns:
            SimpleNamespace: Third source response.
        """
        calls.append((url, kwargs))
        if len(calls) < 3:
            raise OSError("fixture offline")
        return SimpleNamespace(json=lambda: {"results": [[]]})

    monkeypatch.setattr(requests, "post", post)
    result = GUIExplorerRetrieval("http://fixture-rag").retrieve_batch((image_file(tmp_path),),
        top_k=3, threshold=0.75, package_name="fixture.app")
    assert result == [[]] and len(calls) == 3 and sleeps == [1, 1]
    url, kwargs = calls[0]
    assert url == "http://fixture-rag/retrieval_batch" and kwargs["timeout"] == 300
    body = kwargs["json"]
    assert set(body) == {"package_name", "queries", "top_k", "threshold"}
    assert body["package_name"] == "fixture.app" and body["top_k"] == 3 and body["threshold"] == 0.75
    with Image.open(io.BytesIO(base64.b64decode(body["queries"][0]))) as image:
        assert image.format == "WEBP"


@pytest.mark.parametrize("failing", [False, True])
def test_original_async_ranking_transport(monkeypatch, failing):
    """Preserve source model ID, usage counts and permissive fallback after three errors.

    Args:
        monkeypatch: Async timing boundary replacement.
        failing: Select source error fallback or successful comparison.
    Returns:
        None.
    """
    calls, sleeps = [], []

    async def sleep(seconds):
        """Record original async pauses without blocking.

        Args:
            seconds: Source retry delay.
        Returns:
            None.
        """
        sleeps.append(seconds)

    class Response:
        """Script one aiohttp response context."""

        async def __aenter__(self):
            """Return the fake response context."""
            return self

        async def __aexit__(self, *args):
            """Propagate exceptions without closing external resources."""
            return False

        async def json(self):
            """Return a source comparison or fail the external response decoder.

            Raises:
                ValueError: Controlled external response failure.
            Returns:
                dict: Source choices and usage.
            """
            if failing:
                raise ValueError("fixture error")
            return {"choices": [{"message": {"content": "prefer 2"}}], "usage": {"prompt_tokens": 7, "completion_tokens": 1}}

    def post(url, **kwargs):
        """Record one actual ranking request.

        Args:
            url, kwargs: Actual external request.
        Returns:
            Response: Fake aiohttp context manager.
        """
        calls.append((url, kwargs))
        return Response()

    monkeypatch.setattr(asyncio, "sleep", sleep)
    usage = {"prompt_tokens": 0, "completion_tokens": 0}
    session = _RankingSession(GUIExplorerLLM(base_url="http://fixture/v1"), SimpleNamespace(post=post))
    result = asyncio.run(session.ask("rank prompt", usage))
    assert result == ("1" if failing else "prefer 2")
    assert len(calls) == (3 if failing else 1) and sleeps == ([1, 1, 1] if failing else [])
    assert calls[0][1]["json"] == {"model": "gpt-4o-mini", "messages": [{"role": "user", "content": "rank prompt"}], "temperature": 0.0}
    assert usage == ({"prompt_tokens": 0, "completion_tokens": 0} if failing else {"prompt_tokens": 7, "completion_tokens": 1})


def test_rank_bridge_inside_existing_event_loop_preserves_usage_context():
    """Verify the synchronous component works in an async host without global loop patches.

    Returns:
        None.
    """
    class AccountingModel(Model):
        """A source comparison double using the existing token usage collector."""

        async def ask(self, prompt, usage):
            """Return source response and record usage in the current task context.

            Args:
                prompt: Original pairwise prompt.
                usage: Original per-step accumulator.
            Returns:
                str: Scripted comparison result.
            """
            response = await super().ask(prompt, usage)
            record_usage(prompt_tokens=2, completion_tokens=1)
            return response

    model = AccountingModel([])
    entries = [{"index": i, "hints": {"hint_1": str(i)}} for i in (0, 2)]
    reset_task_usage()

    async def host():
        """Invoke the synchronous component while this host owns its event loop.

        Returns:
            list: Full original knowledge ordering.
        """
        return rank_entries(model, "task", entries, {"prompt_tokens": 0, "completion_tokens": 0})

    result = asyncio.run(host())
    assert [entry["index"] for entry in result] == [2, 0]
    assert get_task_usage_dict()["total_tokens"] == 3
