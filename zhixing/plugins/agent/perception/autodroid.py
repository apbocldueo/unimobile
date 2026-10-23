"""AutoDroid-style hierarchy encoding without device or model side effects."""

from __future__ import annotations

import html
from pathlib import Path
import xml.etree.ElementTree as ET

from zhixing.components import BasePerception, DeviceObservation, PerceptionResult, RuntimeContext
from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.autodroid_types import Candidate, ScrollRegion, UIState, stable_id
from zhixing.plugins.agent.perception.ally import parse_bounds_string


def candidate_html(candidate: Candidate, hint: str = "") -> str:
    """Render an inert HTML-style UI statement with an optional memory hint.

    Args:
        candidate: The current prompt choice.
        hint: Downstream functionality from App Memory.
    Returns:
        str: Escaped text suitable for a model prompt.
    """
    attrs = f" id={candidate.choice_id}"
    if candidate.label:
        attrs += f" text='{html.escape(candidate.label, quote=True)}'"
    if candidate.tag == "checkbox":
        attrs += f" checked={candidate.checked}"
    if hint:
        attrs += f" onclick='{html.escape(hint, quote=True)}'"
    body = "<br>".join(html.escape(part) for part in candidate.text.split("<br>"))
    return f"<{candidate.tag}{attrs}>{body}</{candidate.tag}>"


@PluginRegistry.register(namespace="agent.perception", name="autodroid_perception")
class AutoDroidPerception(BasePerception):
    """Preserve clickable ancestry, semantic choices and scroll identities."""

    def __init__(self, max_xml_bytes: int = 4_194_304, max_candidates: int = 2048) -> None:
        """Configure bounded local XML parsing.

        Args:
            max_xml_bytes: Largest accepted observation XML.
            max_candidates: Largest accepted prompt choice set.
        Raises:
            ValueError: A bound is nonpositive.
        Returns:
            None.
        """
        if any(isinstance(value, bool) or not isinstance(value, int) or value < 1
               for value in (max_xml_bytes, max_candidates)):
            raise ValueError("perception limits must be positive")
        self.max_xml_bytes = max_xml_bytes
        self.max_candidates = max_candidates

    def invoke(self, input: DeviceObservation, runtime: RuntimeContext) -> PerceptionResult:
        """Encode only the supplied observation; never capture or scroll a device.

        Args:
            input: Screenshot dimensions and already captured UI XML.
            runtime: Unused run context.
        Raises:
            ValueError: XML is absent, oversized, malformed or has too many choices.
            OSError: The supplied XML cannot be read.
        Returns:
            PerceptionResult: Current UI plus identity-preserving choice data.
        """
        del runtime
        if not input.ui_path:
            raise ValueError("AutoDroid requires UI XML observations")
        path = Path(input.ui_path)
        if path.stat().st_size > self.max_xml_bytes:
            raise ValueError("AutoDroid XML exceeds configured limit")
        try:
            root = ET.fromstring(path.read_text(encoding="utf-8"))
        except ET.ParseError as error:
            raise ValueError("malformed AutoDroid UI XML") from error
        candidates: list[Candidate] = []
        regions: list[ScrollRegion] = []
        packages: set[str] = set()

        def actionable_node(node: ET.Element) -> bool:
            """Identify independent controls before merging descendant labels.

            Args:
                node: XML element under inspection.
            Returns:
                bool: Whether the element owns an independent action.
            """
            attrs = node.attrib
            return (attrs.get("editable") == "true" or "EditText" in attrs.get("class", "")
                    or attrs.get("checkable") == "true" or attrs.get("clickable") == "true")

        def owned_labels(node: ET.Element, depth: int = 0, attribute: str = "text") -> list[str]:
            """Collect labels without stealing text from nested controls.

            Args:
                node: Label-owning element.
                depth: Local descendant depth, bounded before recursion.
                attribute: Text or content-description field being merged.
            Raises:
                ValueError: The descendant hierarchy exceeds 100 levels.
            Returns:
                list[str]: Visible labels belonging to this control.
            """
            if depth > 100:
                raise ValueError("AutoDroid XML hierarchy exceeds depth limit")
            texts = [node.attrib.get(attribute, "").strip()]
            for child in node:
                if (not actionable_node(child) and child.attrib.get("enabled", "true") != "false"
                        and child.attrib.get("visible-to-user", "true") != "false"):
                    texts.extend(owned_labels(child, depth + 1, attribute))
            return texts

        def visit(node: ET.Element, ancestors: tuple[str, ...], region_key: str = "", owned: bool = False) -> None:
            """Walk the retained tree and collapse children of an actionable node.

            Args:
                node: Current XML element.
                ancestors: Stable ancestor class/resource identities.
                region_key: Innermost enclosing scroll container.
                owned: Ancestor already owns non-actionable labels.
            Raises:
                ValueError: The candidate count exceeds the configured bound.
            Returns:
                None: Appends immutable UI descriptors.
            """
            attr = node.attrib
            if len(ancestors) > 100:
                raise ValueError("AutoDroid XML hierarchy exceeds depth limit")
            if attr.get("visible-to-user", "true") == "false" or attr.get("enabled", "true") == "false":
                return
            package = attr.get("package", "")
            if package:
                packages.add(package)
            identity = attr.get("resource-id", "") + ":" + attr.get("class", node.tag)
            chain = (*ancestors, identity)
            bounds = parse_bounds_string(attr.get("bounds"))
            if bounds:
                left, top, right, bottom = bounds
                clipped = (max(0, left), max(0, top), min(input.width, right), min(input.height, bottom))
                bounds = clipped if clipped[0] < clipped[2] and clipped[1] < clipped[3] else None
            if bounds and attr.get("scrollable") == "true":
                region_key = stable_id(chain)
                regions.append(ScrollRegion(key=region_key, bounds=bounds))
            editable = attr.get("editable") == "true" or "EditText" in attr.get("class", "")
            checkable = attr.get("checkable") == "true"
            actionable = actionable_node(node)
            if bounds and (actionable or (not owned and not len(node) and (attr.get("text") or attr.get("content-desc")))):
                # Each clickable ancestor owns the text of its non-actionable children.
                texts = list(dict.fromkeys(owned_labels(node)))
                text = "<br>".join(item for item in texts if item)
                label = "<br>".join(item for item in dict.fromkeys(owned_labels(node, attribute="content-desc")) if item)
                tag = "input" if editable else "checkbox" if checkable else "button" if actionable else "p"
                key = stable_id((chain, tag, label, "" if editable else text))
                candidate = Candidate(
                    choice_id=len(candidates), key=key, tag=tag, text=text, label=label,
                    checked=attr.get("checked") == "true" or attr.get("selected") == "true",
                    bounds=bounds, region_key=region_key, interactive=actionable, description="",
                )
                candidate = candidate.model_copy(update={"description": candidate_html(candidate)})
                candidates.append(candidate)
                if len(candidates) > self.max_candidates:
                    raise ValueError("AutoDroid candidate limit exceeded")
            for child in node:
                visit(child, chain, region_key, owned or actionable)

        visit(root, ())
        # Upstream exposes BACK as a selectable synthetic control.
        back = Candidate(choice_id=len(candidates), key="__back__", tag="button", text="go back",
                         bounds=(0, 0, 0, 0), description="")
        candidates.append(back.model_copy(update={"description": candidate_html(back)}))
        signature = [(item.key, item.checked, item.text) for item in candidates]
        ui = UIState(state_id=stable_id(signature), app_id=next(iter(packages)) if len(packages) == 1 else "",
                     candidates=tuple(candidates), regions=tuple(regions))
        return PerceptionResult(
            mode="autodroid", original_screenshot_path=input.screenshot_path,
            elements=[item.model_dump(mode="json") for item in candidates],
            metadata={"width": input.width, "height": input.height},
            data={"autodroid": ui.model_dump(mode="json")},
            prompt_representation="\n".join(item.description for item in candidates),
        )
