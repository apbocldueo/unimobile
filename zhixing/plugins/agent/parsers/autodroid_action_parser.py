"""Strict AutoDroid choice parsing; malformed responses never become DONE."""

from __future__ import annotations

import ast
import json
import re

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.autodroid_types import Choice
from zhixing.plugins.agent.parsers.json_action_parser import ActionParseError


@PluginRegistry.register(namespace="agent.parser", name="autodroid_action_parser")
class AutoDroidActionParser:
    """Parse the upstream JSON protocol and its paper-style id/action format."""

    def parse(self, response: str) -> Choice:
        """Return a choice without guessing coordinates or task completion.

        Args:
            response: Model response, optionally wrapped in a code fence.
        Raises:
            ActionParseError: The response is malformed, contradictory or unsupported.
        Returns:
            Choice: A validated id, operation, text and decision explanation.
        """
        if not isinstance(response, str) or len(response) > 131072:
            raise ActionParseError("invalid AutoDroid response")
        value = response.strip()
        if value.startswith("```"):
            value = re.sub(r"^```(?:json|python)?\s*|\s*```$", "", value).strip()
        try:
            if value.startswith("{"):
                try:
                    data = json.loads(value)
                except json.JSONDecodeError:
                    data = ast.literal_eval(value)
                if not isinstance(data, dict):
                    raise ValueError("expected a decision object")
                raw_id = data.get("id")
                if isinstance(raw_id, bool) or not re.fullmatch(r"-?\d+", str(raw_id)):
                    raise ValueError("id must be an integer")
                finished = str(data.get("Finished", data.get("finished", ""))).lower()
                if finished and finished not in {"yes", "no", "true", "false", "y", "n"}:
                    raise ValueError("invalid finished flag")
                raw_action = str(data.get("action", "tap")).lower()
                text = data.get("input_text", "")
                thought = str(data.get("Analyses", data.get("thought", "")))
                if finished in {"yes", "true", "y"}:
                    if raw_id not in (-1, "-1"):
                        raise ValueError("finished decision must have id=-1")
                    return Choice(choice_id=-1, thought=thought)
                if finished in {"no", "false", "n"} and raw_id in (-1, "-1"):
                    raise ValueError("unfinished decision cannot have id=-1")
            else:
                matches = re.findall(r"\bid\s*=\s*(-?\d+)", value)
                actions = re.findall(r"\baction\s*=\s*(tap|click|input)\b", value, re.I)
                if len(matches) != 1:
                    raise ValueError("expected one selected id")
                raw_id = matches[0]
                raw_action = actions[0].lower() if len(actions) == 1 else ""
                text_match = re.search(r"input\s+text\s*=\s*(.*)$", value, re.I)
                text = text_match.group(1).strip().strip("\"'") if text_match else ""
                thought = ""
            if isinstance(raw_id, bool) or not re.fullmatch(r"-?\d+", str(raw_id)):
                raise ValueError("id must be an integer")
            choice_id = int(raw_id)
            if choice_id == -1:
                return Choice(choice_id=-1, thought=thought)
            if raw_action not in {"tap", "click", "input"} or not isinstance(text, str):
                raise ValueError("unsupported AutoDroid operation")
            if raw_action == "input" and text in {"", "N/A"}:
                raise ValueError("input requires text")
            return Choice(choice_id=choice_id, operation="tap" if raw_action == "click" else raw_action,
                          text="" if text == "N/A" else text, thought=thought)
        except (ValueError, TypeError, SyntaxError, RecursionError) as error:
            raise ActionParseError("malformed AutoDroid decision") from error
