"""
Multi-image VLM evaluator.

Unified ``images`` param (see class docstring). Legacy keys (``all_steps``, ``steps``,
``last_n``, ``paths``, ``capture_final``) are still accepted and normalized automatically.
"""

import os
import copy
import re
from typing import Dict, Any, List, Optional, Tuple, Union

from zhixing.core.benchmark.protocol import EvalResult
from zhixing.core.benchmark.base_vision import BaseVLMAction
from zhixing.core.factory import PluginRegistry

from zhixing.core.benchmark.param_handler import ParamHandler
from zhixing.plugins.benchmark.evaluator.vision_mllm.single_image_qa import (
    _redact_api_keys,
    _split_pass_fail_verdict,
    _llm_inference_summary,
)

# Parsed image selection (internal).
_ImageSpec = Dict[str, Any]

_LAST_RE = re.compile(r"^last(?::(\d+))?$", re.IGNORECASE)


def _pick_screenshot_path(entry: Dict[str, Any], use_marked: bool) -> Optional[str]:
    if use_marked:
        marked = entry.get("action_marked_screenshot_path")
        if marked and os.path.isfile(marked):
            return marked
    path = entry.get("screenshot_path")
    if path and os.path.isfile(path):
        return path
    return None


def _resolve_trajectory_step(
    trajectory: List[Dict[str, Any]], step: int, use_marked: bool
) -> Tuple[Optional[str], str]:
    if not trajectory:
        return None, f"step {step}"

    if step < 0:
        idx = len(trajectory) + step
    else:
        idx = None
        for i, entry in enumerate(trajectory):
            if entry.get("step") == step:
                idx = i
                break
        if idx is None and 1 <= step <= len(trajectory):
            idx = step - 1

    if idx is None or idx < 0 or idx >= len(trajectory):
        return None, f"step {step}"

    entry = trajectory[idx]
    path = _pick_screenshot_path(entry, use_marked)
    actual_step = entry.get("step", idx + 1)
    return path, f"step {actual_step}"


def _append_trajectory_entries(
    trajectory: List[Dict[str, Any]],
    entries: List[Dict[str, Any]],
    use_marked: bool,
    paths: List[str],
    labels: List[str],
) -> Optional[str]:
    for entry in entries:
        path = _pick_screenshot_path(entry, use_marked)
        if not path:
            return f"no screenshot for trajectory step {entry.get('step', '?')}"
        paths.append(path)
        labels.append(f"step {entry.get('step', '?')}")
    return None


def _parse_trajectory_selector(
    selector: Union[str, int, List[int]],
) -> Tuple[Optional[str], Optional[int], Optional[List[int]], Optional[str]]:
    """
    Returns (mode, last_n, step_list, error).
    mode is one of: "all", "last", "steps".
    """
    if isinstance(selector, str):
        key = selector.strip().lower()
        if key == "all":
            return "all", None, None, None
        m = _LAST_RE.match(key)
        if m:
            n = int(m.group(1)) if m.group(1) else 1
            if n <= 0:
                return None, None, None, "trajectory 'last' count must be positive"
            return "last", n, None, None
        return None, None, None, f"unknown trajectory selector {selector!r} (use all, last, or last:N)"

    if isinstance(selector, int):
        return "steps", None, [selector], None

    if isinstance(selector, list):
        if not selector:
            return None, None, None, "trajectory step list must not be empty"
        steps: List[int] = []
        for item in selector:
            try:
                steps.append(int(item))
            except (TypeError, ValueError):
                return None, None, None, f"invalid trajectory step {item!r}"
        return "steps", None, steps, None

    return None, None, None, f"invalid trajectory selector type: {type(selector).__name__}"


def _normalize_images_spec(
    params: Dict[str, Any], task_params: Dict[str, Any]
) -> Tuple[Optional[_ImageSpec], Optional[str]]:
    """
    Build internal spec: {trajectory_mode, last_n, steps, files, capture_final}.
    Prefer ``params.images``; fall back to legacy keys.
    """
    raw = params.get("images")
    if raw is None:
        # --- Legacy compatibility ---
        spec: _ImageSpec = {
            "trajectory_mode": None,
            "last_n": None,
            "steps": None,
            "files": [],
            "capture_final": bool(params.get("capture_final", False)),
        }
        if params.get("all_steps"):
            if params.get("steps") is not None or params.get("last_n") is not None:
                return None, "use only one of: all_steps, steps, last_n (or switch to params.images)"
            spec["trajectory_mode"] = "all"
        elif params.get("steps") is not None:
            spec["steps"] = params.get("steps")
            spec["trajectory_mode"] = "steps"
        elif params.get("last_n") is not None:
            spec["last_n"] = int(params["last_n"])
            spec["trajectory_mode"] = "last"
        elif params.get("paths") or spec["capture_final"]:
            pass  # files / final only
        else:
            # Nothing legacy → default: last frame
            spec["trajectory_mode"] = "last"
            spec["last_n"] = 1

        if "paths" in params:
            rendered = ParamHandler.render_placeholders(params["paths"], task_params)
            if not isinstance(rendered, list):
                return None, "params.paths must be a list of strings"
            spec["files"] = [str(p).strip() for p in rendered]
        return spec, None

    # Render placeholders on images when it is a string/list/dict
    images = ParamHandler.render_placeholders(raw, task_params)

    spec = {
        "trajectory_mode": None,
        "last_n": None,
        "steps": None,
        "files": [],
        "capture_final": False,
    }

    # --- Shorthand string ---
    if isinstance(images, str):
        mode, last_n, steps, err = _parse_trajectory_selector(images)
        if err:
            return None, err
        spec["trajectory_mode"] = mode
        spec["last_n"] = last_n
        spec["steps"] = steps
        return spec, None

    # --- Shorthand list: all int → steps; all str → files ---
    if isinstance(images, list):
        if not images:
            return None, "params.images list must not be empty"
        if all(isinstance(x, (int, float)) and not isinstance(x, bool) for x in images):
            spec["trajectory_mode"] = "steps"
            spec["steps"] = [int(x) for x in images]
            return spec, None
        if all(isinstance(x, str) for x in images):
            spec["files"] = [x.strip() for x in images]
            return spec, None
        return None, "params.images list must be all step numbers (int) or all file paths (str)"

    # --- Object form ---
    if isinstance(images, dict):
        if "trajectory" in images:
            sel = images["trajectory"]
            mode, last_n, steps, err = _parse_trajectory_selector(sel)
            if err:
                return None, err
            spec["trajectory_mode"] = mode
            spec["last_n"] = last_n
            spec["steps"] = steps

        files = images.get("files", [])
        if files:
            if not isinstance(files, list):
                return None, "images.files must be a list of paths"
            spec["files"] = [str(p).strip() for p in files]

        spec["capture_final"] = bool(
            images.get("final", images.get("capture_final", False))
        )
        return spec, None

    return None, f"params.images must be string, list, or object (got {type(images).__name__})"


def _resolve_image_paths(
    context: Dict[str, Any],
    params: Dict[str, Any],
    device: Any = None,
) -> Tuple[List[str], List[str], Optional[str]]:
    trajectory = context.get("trajectory") or []
    task_params = context.get("task_params") or {}
    use_marked = bool(params.get("use_marked", False))

    max_images_raw = params.get("max_images", 10)
    max_images: Optional[int] = int(max_images_raw) if max_images_raw is not None else 10
    if max_images <= 0:
        max_images = None

    spec, err = _normalize_images_spec(params, task_params)
    if err:
        return [], [], err

    paths: List[str] = []
    labels: List[str] = []

    mode = spec.get("trajectory_mode")
    if mode == "all":
        if not trajectory:
            return [], [], "trajectory is empty"
        err = _append_trajectory_entries(trajectory, trajectory, use_marked, paths, labels)
        if err:
            return [], [], err
    elif mode == "last":
        n = spec.get("last_n") or 1
        if not trajectory:
            return [], [], "trajectory is empty"
        err = _append_trajectory_entries(
            trajectory, trajectory[-n:], use_marked, paths, labels
        )
        if err:
            return [], [], err
    elif mode == "steps":
        for step_num in spec["steps"]:
            path, label = _resolve_trajectory_step(trajectory, step_num, use_marked)
            if not path:
                return [], [], f"no screenshot for trajectory {label}"
            paths.append(path)
            labels.append(label)

    for path in spec.get("files") or []:
        if not os.path.isfile(path):
            return [], [], f"image file not found: {path}"
        paths.append(path)
        labels.append(f"file {os.path.basename(path)}")

    if spec.get("capture_final"):
        screenshot_dir = os.path.join(os.getcwd(), "temp", "eval_screenshots")
        os.makedirs(screenshot_dir, exist_ok=True)
        final_path = os.path.join(screenshot_dir, "vlm_multi_final.png")
        if device is None:
            return [], [], "images.final requires device on evaluator"
        try:
            device.screenshot(path=final_path)
        except Exception as e:
            return [], [], f"final screenshot failed: {e}"
        paths.append(final_path)
        labels.append("live screen")

    if not paths:
        return [], [], "no images resolved: set params.images (see multi_image_qa docs)"

    if max_images is not None and len(paths) > max_images:
        paths = paths[-max_images:]
        labels = labels[-max_images:]

    custom_labels = params.get("labels")
    if custom_labels:
        if not isinstance(custom_labels, list) or len(custom_labels) != len(paths):
            return [], [], "params.labels length must match number of images"
        labels = [str(x) for x in custom_labels]

    return paths, labels, None


def _build_multi_image_prompt(user_prompt: str, labels: List[str]) -> str:
    system_prompt = (
        "Please act as a strict automated testing judge. "
        "You will receive multiple screenshots in order. "
        "Your response MUST start with 'PASS:' or 'FAIL:', followed by a short comment."
    )
    lines = [system_prompt, "", "[Images in order]"]
    for i, label in enumerate(labels, start=1):
        lines.append(f"  Image {i}: {label}")
    lines.extend(["", "[Verification Rule]:", user_prompt])
    return "\n".join(lines)


@PluginRegistry.register(namespace="evaluator.vision_mllm", name="multi_image_qa")
class MultiImageEvaluatorAction(BaseVLMAction):
    """
    Multi-image VLM judge — one request, all images together.

    ------------------------------------------------------------
    Required
    ------------------------------------------------------------

    * ``prompt`` (str): What to verify.

  * ``images`` — **only param you need for picking screenshots**:

    | Value | Meaning |
    |-------|---------|
    | ``"all"`` | Every step in the agent trajectory |
    | ``"last"`` or ``"last:1"`` | Last screenshot only |
    | ``"last:4"`` | Last 4 (if run has 3 steps → sends 3, no error) |
    | ``[1, -1]`` | Trajectory step numbers (1-based, negative from end) |
    | ``["ref/a.png"]`` | Host file paths (supports ``${var}``) |
    | object | Combine trajectory + files + live screen (below) |

    **Object form** (advanced):

    .. code-block:: json

        "images": {
            "trajectory": "all",
            "files": ["benchmarks/ref.png"],
            "final": true
        }

    If ``images`` is omitted, legacy keys ``all_steps`` / ``steps`` / ``last_n`` / ``paths``
    still work; default is ``"last"`` (final trajectory frame).

    ------------------------------------------------------------
    Optional
    ------------------------------------------------------------

    * ``max_images`` (int): Cap count sent to VLM (default ``10``). Use ``0`` for no cap.
    * ``labels`` (list[str]): Custom label per image (same length as resolved images).
    * ``use_marked`` (bool): Prefer action-annotated screenshots.

    ------------------------------------------------------------
    Examples
    ------------------------------------------------------------

    All frames::

        "images": "all", "max_images": 0

    First and last::

        "images": [1, -1]

    Reference + device now::

        "images": { "files": ["ref.png"], "final": true }
    """

    def evaluate(self, context: Dict[str, Any]) -> EvalResult:
        llm = self.get_llm(context)
        user_prompt = self.get_param("prompt", context, expected_type=str)

        paths, labels, err = _resolve_image_paths(
            context, self.params, device=self.device
        )
        if err:
            return EvalResult(is_pass=False, reason=err)

        self.logger.info(
            "multi_image_qa resolved %d image(s) (trajectory len=%d, images=%r)",
            len(paths),
            len(context.get("trajectory") or []),
            self.params.get("images", "<legacy/default>"),
        )
        final_prompt = _build_multi_image_prompt(user_prompt, labels)

        try:
            params_for_log = _redact_api_keys(copy.deepcopy(self.params))
            self.logger.info("multi_image_qa params (api_key redacted): %s", params_for_log)
            self.logger.info("multi_image_qa VLM prompt:\n%s", final_prompt)
            self.logger.info(
                "multi_image_qa VLM request %s",
                _llm_inference_summary(llm, paths),
            )
            response = llm.generate(prompt=final_prompt, images=paths)
        except Exception as e:
            return EvalResult(is_pass=False, reason=f"LLM request crashed: {e}")

        self.logger.info("multi_image_qa VLM raw response: %r", response)
        result_text = (response or "").strip()
        verdict, reason = _split_pass_fail_verdict(result_text)
        if verdict is True:
            return EvalResult(is_pass=True, reason=reason)
        if verdict is False:
            return EvalResult(is_pass=False, reason=reason)
        self.logger.warning("Unexpected LLM response format: %s", result_text)
        return EvalResult(
            is_pass=False,
            reason=f"Invalid VLM response format: {result_text[:100]}",
        )
