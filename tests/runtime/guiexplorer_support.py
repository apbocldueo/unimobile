"""Independent pinned-source oracle and deterministic external I/O for online parity."""

import ast
from contextlib import asynccontextmanager, redirect_stdout
import copy
import dataclasses
from datetime import datetime
import hashlib
import io
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
from types import ModuleType, SimpleNamespace
from typing import Any, Dict, List, Tuple, Union, Optional

import cv2
import numpy as np
from PIL import Image

from zhixing.plugins.agent.guiexplorer.types import GUIExplorerReply


FIXTURES = Path(__file__).resolve().parents[1] / "fixtures/guiexplorer"
GOAL = "Open the target settings and inspect the result"


def original(filename, names=None, namespace=None):
    """Execute unchanged original definitions without running external imports.

    Args:
        filename: Pinned fixture filename.
        names: Optional selected original definitions.
        namespace: Explicit libraries and external I/O boundaries.
    Raises:
        Exception: A raw original definition cannot compile or initialize.
    Returns:
        dict: Independent original global namespace.
    """
    module = ModuleType("guiexplorer_oracle_" + filename.replace(".", "_"))
    sys.modules[module.__name__] = module
    ns = module.__dict__
    ns.update(namespace or {})
    raw = (FIXTURES / filename).read_text()
    if filename == "utils__utils.py.txt":
        lines = raw.splitlines(keepends=True)
        start = next(i for i, value in enumerate(lines) if value.startswith("def extract_json("))
        end = next(i for i in range(start + 1, len(lines)) if lines[i].startswith("def "))
        raw = "".join(lines[start:end])
    tree = ast.parse(raw)
    body = [node for node in tree.body if not isinstance(node, (ast.Import, ast.ImportFrom))
            and (names is None or getattr(node, "name", "") in names)]
    future = ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)
    exec(compile(ast.fix_missing_locations(ast.Module(body=[future, *body], type_ignores=[])),
                 "official/" + filename, "exec"), ns)
    return ns


def ui_namespace():
    """Load raw official UI dataclasses for both external device fixtures.

    Returns:
        dict: Original UI definitions without a device connection.
    """
    return original("utils__device.py.txt", {"BoundingBox", "UIElement"},
        {"dataclasses": dataclasses, "Image": Image})


class Device:
    """Simulate only source device I/O; real source dispatch and rendering still run."""

    def __init__(self, orientation=0, fail_click=False):
        """Create ordered source UI and an isolated observable operation log.

        Args:
            orientation: Source geometry fixture rotation.
            fail_click: Raise after recording an attempted click.
        Returns:
            None.
        """
        self.events, self.screen_count = [], 0
        self.orientation, self.fail_click = orientation, fail_click
        ui = ui_namespace()
        self.elements = [ui["UIElement"](text="First", is_visible=True, is_clickable=True,
            bbox_pixels=ui["BoundingBox"](10, 80, 40, 100)),
            ui["UIElement"](text="Hidden", is_visible=False, bbox_pixels=ui["BoundingBox"](90, 120, 40, 90)),
            ui["UIElement"](text="Second", is_visible=True, is_editable=True, is_scrollable=True,
                bbox_pixels=ui["BoundingBox"](130, 220, 140, 220))]

    def wait_to_stabilize(self):
        """Record and return the source stable-state observation."""
        self.events.append(("stable",))
        return self.elements

    def _get_ui_elements(self):
        """Record the additional source fresh post-action UI observation."""
        self.events.append(("ui",))
        return self.elements

    def get_orientation(self):
        """Return recorded fixture rotation."""
        self.events.append(("orientation",))
        return self.orientation

    def get_screen_size(self):
        """Return recorded source logical geometry."""
        self.events.append(("size",))
        return (240, 400)

    def get_physical_frame_boundary(self):
        """Return recorded source physical geometry."""
        self.events.append(("frame",))
        return (0, 0, 240, 400)

    def get_screenshot(self):
        """Return fresh distinctive RGB pixels to expose observation/copy mistakes."""
        self.events.append(("image", self.screen_count))
        self.screen_count += 1
        return Image.new("RGB", (240, 400), (40 + self.screen_count % 200, 80, 100))

    def get_top_package_name(self):
        """Return the recorded package used for knowledge-bank selection."""
        self.events.append(("package",))
        return "fixture.app"

    def sleep(self, seconds):
        """Record original timing without blocking or changing simulation state.

        Args:
            seconds: Original requested pause.
        Returns:
            None.
        """
        self.events.append(("sleep", seconds))

    def __getattr__(self, name):
        """Record only original source device methods needed by action dispatch.

        Args:
            name: Original device primitive.
        Returns:
            Callable: Deterministic original I/O boundary.
        """
        def call(*args, **kwargs):
            """Record safe source arguments and optionally fail a click.

            Args:
                args, kwargs: Unmodified original primitive arguments.
            Raises:
                OSError: The fixture requests an execution error.
            Returns:
                tuple | None: Source shell result, otherwise no value.
            """
            self.events.append((name, args, kwargs))
            if name == "click" and self.fail_click:
                raise OSError("fixture click failure")
            return ("ok", 0) if name == "run_shell_command" else None
        return call


class Model:
    """Script external action/summary and pairwise-comparison responses only."""

    def __init__(self, replies, comparison="2"):
        """Bind deterministic response scripts and independent request logs.

        Args:
            replies: Ordered source action/summary replies.
            comparison: Source ranking comparison output, including malformed strings.
        Returns:
            None.
        """
        self.replies, self.comparison = iter(replies), comparison
        self.calls, self.rank_calls = [], []

    def ask_original(self, prompt, images):
        """Return an original response tuple and capture actual source input pixels.

        Args:
            prompt: Original source prompt.
            images: Original ndarray images.
        Returns:
            tuple: Source text and truthy private HTTP-response sentinel or None.
        """
        self.calls.append((prompt, [np.array(image).copy() for image in images]))
        reply = next(self.replies)
        return reply.text, {"private-response-sentinel": True} if reply.has_response else None

    def generate_guiexplorer(self, prompt, images):
        """Expose the production dependency protocol without implementing Agent policy.

        Args:
            prompt: Actual production source prompt.
            images: Ordered PNG image paths.
        Returns:
            GUIExplorerReply: Scripted external reply.
        """
        pixels = []
        for path in images:
            with Image.open(path) as image:
                pixels.append(np.array(image))
        text, response = self.ask_original(prompt, pixels)
        return GUIExplorerReply(text, bool(response))

    @asynccontextmanager
    async def ranking_session(self):
        """Yield the scripted model without opening a network session.

        Yields:
            Model: Async external comparison boundary.
        """
        yield self

    async def ask(self, prompt, usage):
        """Record one source comparison and accumulate deterministic token counts.

        Args:
            prompt: Original pairwise ranking prompt.
            usage: Source accumulator, shared across recursive comparisons.
        Returns:
            str: Scripted source comparison output.
        """
        self.rank_calls.append(prompt)
        usage["prompt_tokens"] += 2
        usage["completion_tokens"] += 1
        return self.comparison


class Retrieval:
    """Script only the external knowledge-service results; retain source image inputs."""

    def __init__(self, results=None):
        """Keep a private source result fixture and query log.

        Args:
            results: Optional explicit batch result, including empty/short batches.
        Returns:
            None.
        """
        self.results = results if results is not None else [[{"knowledge": "hint-A"}, {"knowledge": "hint-A2"}], [{"knowledge": "hint-B"}]]
        self.calls = []

    def original(self, queries, *, top_k, threshold, package_name):
        """Return scripted external results without replacing source mapping/sorting.

        Args:
            queries: Original ordered PIL element crops.
            top_k, threshold, package_name: Original retrieval settings.
        Returns:
            list: Independent source-shaped knowledge results.
        """
        self.calls.append(([np.array(image).copy() for image in queries], top_k, threshold, package_name))
        return copy.deepcopy(self.results)

    def retrieve_batch(self, paths, **kwargs):
        """Expose the production image-path protocol with identical external results.

        Args:
            paths: Original-equivalent lossless crop paths.
            kwargs: Original query settings.
        Returns:
            list: Scripted original response.
        """
        queries = []
        for path in paths:
            with Image.open(path) as image:
                queries.append(image.copy())
        return self.original(queries, **kwargs)


def run_original(replies, *, max_rounds=3, device=None, retrieval=None, comparison="2", top_k=1, threshold=0.9):
    """Run the unchanged official GUI_explorer.run/step against explicit fake I/O.

    Args:
        replies: Scripted external action/summary model replies.
        max_rounds: Original step-call budget.
        device, retrieval: Optional isolated controlled external services.
        comparison: Original ranking-model response.
        top_k, threshold: Original retrieval parameters.
    Returns:
        tuple: Source result/exception, Agent, model, device and retrieval service.
    """
    device, rag, model = device or Device(), retrieval or Retrieval(), Model(replies, comparison)
    common = {"dataclasses": dataclasses, "asdict": dataclasses.asdict, "np": np, "cv2": cv2,
        "Image": Image, "ast": ast, "re": re, "json": json, "copy": copy, "logging": logging,
        "os": os, "datetime": datetime, "hashlib": hashlib,
        "time": SimpleNamespace(sleep=device.sleep), "Device": lambda **_: device}
    ui = original("utils__device.py.txt", namespace=dict(common))
    action_ns = original("MLLM_Agent__json_action.py.txt", namespace=dict(common))
    prompts = original("utils__prompt_templates.py.txt")
    utils = original("utils__utils.py.txt", namespace=dict(common))
    import asyncio

    class Session:
        """Original aiohttp context boundary replaced by the same fake comparison model."""

        async def __aenter__(self):
            """Return the external comparison service."""
            return model

        async def __aexit__(self, *args):
            """Close no external resources and propagate source exceptions."""
            return False

    ns = original("MLLM_Agent__GUI_explorer.py.txt", namespace={**common,
        **{name: ui[name] for name in ("_generate_ui_elements_description_list", "validate_ui_element", "add_ui_element_mark", "_ui_element_logical_corner", "_logical_to_physical", "add_screenshot_label")},
        "extract_json": utils["extract_json"], "json_action": SimpleNamespace(**action_ns),
        "REASONING": prompts["REASONING"], "SUMMARY": prompts["SUMMARY"], "RANKER": prompts["RANKER"],
        "asyncio": asyncio, "nest_asyncio": SimpleNamespace(apply=lambda: None),
        "aiohttp": SimpleNamespace(ClientSession=Session)})
    # Replace only external transport/presentation/persistence, after loading
    # original definitions. No task-loop, parser, drawing or sorting is replaced.
    ns.update(ask_mllm=model.ask_original, retrieval_batch_api=rag.original,
        ranking_ask=lambda prompt, session, usage: model.ask(prompt, usage),
        is_need_stop=lambda: False, send_message=lambda *a, **k: None, send_message2=lambda *a, **k: None,
        save_object_to_disk=lambda *a, **k: None, str_to_md5=lambda text: hashlib.md5(text.encode()).hexdigest())
    agent = ns["GUI_explorer"](rag_top_k=top_k, rag_threshold=threshold)
    agent.demo_on = False
    # The raw loop's only filesystem assembly creates its output directory.
    ns["os"] = SimpleNamespace(makedirs=lambda *a, **k: None, path=os.path, getenv=os.getenv)
    try:
        with redirect_stdout(io.StringIO()):
            result = agent.run(GOAL, max_rounds=max_rounds, step_data_output_dir="unused-oracle-output")
    except Exception as error:
        result = error
    return result, agent, model, device, rag
