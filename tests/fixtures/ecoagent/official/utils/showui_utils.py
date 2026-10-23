import json
import re
import subprocess
from typing import Optional

# Screen resolution (same as other utils)
SCREEN_W, SCREEN_H = 1080, 2400


# ============== Extract JSON action from model response ==============
def extract_action_block(response: str) -> dict:
    """
    Extract and parse the JSON action dict from ShowUI model output.

    Expected format (Python-style dict):
        {'action': 'TAP', 'value': None, 'position': [0.5, 0.3]}
    """
    # Try to find a dict-like block in the response
    text = response.strip()

    # Find the JSON/dict portion
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or start >= end:
        raise ValueError("No JSON action found in model output")

    raw = text[start:end + 1]
    # Convert Python-style dict to valid JSON
    raw = raw.replace("'", '"').replace("None", "null")
    return json.loads(raw)


# ============== Parse action dict to ADB command ==============
def parse_action_to_adb(data: dict) -> Optional[str]:
    """
    Parse ShowUI action dict to ADB command.

    Supported actions:
        TAP:   position [x, y] in 0-1 range
        INPUT: value is text to type
        SWIPE: position [[x1,y1], [x2,y2]] in 0-1 range
        ENTER: press enter key
        ANSWER: task complete
    """
    action_type = data.get('action', '').upper()
    value = data.get('value')
    position = data.get('position')

    if action_type == 'TAP':
        if not position or len(position) < 2:
            return None
        x = int(position[0] * SCREEN_W)
        y = int(position[1] * SCREEN_H)
        return f"adb shell input tap {x} {y}"

    if action_type == 'INPUT':
        if not value:
            return None
        escaped = value.replace(" ", "%s")
        return f"adb shell input text '{escaped}'"

    if action_type == 'SWIPE':
        if not position or len(position) < 2:
            return None
        x1 = int(position[0][0] * SCREEN_W)
        y1 = int(position[0][1] * SCREEN_H)
        x2 = int(position[1][0] * SCREEN_W)
        y2 = int(position[1][1] * SCREEN_H)
        return f"adb shell input swipe {x1} {y1} {x2} {y2} 300"

    if action_type == 'ENTER':
        return "adb shell input keyevent KEYCODE_ENTER"

    if action_type == 'ANSWER':
        return "ANSWER"

    return None


# ============== Execute ADB command ==============
def execute_adb_command(cmd: str):
    """Execute ADB command via shell."""
    print(f"Executing: {cmd}")
    subprocess.run(cmd, shell=True)


# ============== Main entry point ==============
def run_from_response(response: str) -> int:
    """
    Parse ShowUI model response and execute the action.

    Returns:
      0: Completed normally
      1: Task finished (ANSWER)
     -1: Unrecognized action
    """
    try:
        data = extract_action_block(response)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[Error] Failed to parse action: {e}")
        return -1

    cmd = parse_action_to_adb(data)

    if cmd is None:
        print(f"[Warning] Could not parse action: {data}")
        return -1

    if cmd == "ANSWER":
        status = data.get('value', 'task complete')
        print(f"[Answer] {status}")
        return 1

    execute_adb_command(cmd)
    return 0
