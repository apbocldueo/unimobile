import re
import subprocess
import time
from typing import Optional, Tuple

# Screen resolution (same as other utils)
SCREEN_W, SCREEN_H = 1080, 2400


# ============== Parse Thoughts and Actions from model response ==============
def extract_action_block(response: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse OS-Atlas model output into thoughts and action.

    Expected format:
        Thoughts: ...reasoning...
        Actions: ACTION_TYPE [params]

    Returns:
        (thoughts, action) tuple. Either may be None if parsing fails.
    """
    thoughts_match = re.search(
        r'[Tt]houghts[:\s]*(.*?)[Aa]ctions?[:\s]', response, flags=re.DOTALL
    )
    thoughts = thoughts_match.group(1).strip() if thoughts_match else None

    action_match = re.search(
        r'[Aa]ctions?[:\s]*(.*)', response, flags=re.DOTALL
    )
    action = action_match.group(1).strip() if action_match else None

    return thoughts, action


# ============== Parse single Action to ADB command ==============
def parse_action_to_adb(action_text: str) -> Optional[str]:
    """
    Parse an OS-Atlas action string into an ADB command.

    Supported actions:
        CLICK <point>[[x, y]]</point>
        LONG_PRESS <point>[[x, y]]</point>
        TYPE [text]
        SCROLL [UP/DOWN/LEFT/RIGHT]
        OPEN_APP [app_name]
        PRESS_BACK / PRESS_HOME / PRESS_RECENT / ENTER
        WAIT / COMPLETE
    """
    t = action_text.strip()
    # Determine action type from the first word
    pattern = re.compile(r'^([A-Z_]+)(\s+(.*))?$', re.DOTALL)
    match = pattern.match(t)
    if not match:
        return None

    action_type = match.group(1)
    content = (match.group(3) or '').strip()

    # ---- CLICK <point>[[x, y]]</point> ----
    if action_type == 'CLICK':
        xy = _parse_point(content)
        if xy:
            x, y = _scale_coords(*xy)
            return f"adb shell input tap {x} {y}"
        return None

    # ---- LONG_PRESS <point>[[x, y]]</point> ----
    if action_type == 'LONG_PRESS':
        xy = _parse_point(content)
        if xy:
            x, y = _scale_coords(*xy)
            return f"adb shell input swipe {x} {y} {x} {y} 800"
        return None

    # ---- TYPE [text] ----
    if action_type == 'TYPE':
        m = re.match(r'^\[(.*)\]$', content, re.DOTALL)
        text = m.group(1).strip() if m else content
        if text:
            escaped = text.replace(" ", "%s")
            return f"adb shell input text '{escaped}'"
        return None

    # ---- SCROLL [direction] ----
    if action_type == 'SCROLL':
        m = re.match(r'^\[(.*)\]$', content)
        direction = (m.group(1).strip().upper() if m else content.strip().upper())
        cx, cy = SCREEN_W // 2, SCREEN_H // 2
        if direction == 'UP':
            return f"adb shell input swipe {cx} {cy} {cx} {cy - SCREEN_H // 3}"
        elif direction == 'DOWN':
            return f"adb shell input swipe {cx} {cy} {cx} {cy + SCREEN_H // 3}"
        elif direction == 'LEFT':
            return f"adb shell input swipe {cx} {cy} {cx - SCREEN_W // 3} {cy}"
        elif direction == 'RIGHT':
            return f"adb shell input swipe {cx} {cy} {cx + SCREEN_W // 3} {cy}"
        return None

    # ---- OPEN_APP [app_name] ----
    if action_type == 'OPEN_APP':
        m = re.match(r'^\[(.*)\]$', content)
        app_name = m.group(1).strip() if m else content.strip()
        if app_name:
            return (
                f"adb shell monkey -p $(adb shell cmd package resolve-activity "
                f"--brief '{app_name}' | tail -1 | cut -d'/' -f1) "
                f"-c android.intent.category.LAUNCHER 1"
            )
        return None

    # ---- System buttons ----
    if action_type == 'PRESS_BACK':
        return "adb shell input keyevent KEYCODE_BACK"
    if action_type == 'PRESS_HOME':
        return "adb shell input keyevent KEYCODE_HOME"
    if action_type == 'PRESS_RECENT':
        return "adb shell input keyevent KEYCODE_APP_SWITCH"
    if action_type == 'ENTER':
        return "adb shell input keyevent KEYCODE_ENTER"

    # ---- Special markers ----
    if action_type == 'WAIT':
        return "WAIT:3"
    if action_type == 'COMPLETE':
        return "COMPLETE"

    return None


# ============== Helpers ==============
def _parse_point(text: str) -> Optional[Tuple[int, int]]:
    """Extract [[x, y]] coordinates from <point>[[x, y]]</point> or bare [[x, y]]."""
    m = re.search(r'\[\[\s*(\d+)\s*,\s*(\d+)\s*\]\]', text)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _scale_coords(x: int, y: int) -> Tuple[int, int]:
    """Scale 0-999 coordinates to actual screen resolution."""
    return int(x / 999 * SCREEN_W), int(y / 999 * SCREEN_H)


def execute_adb_command(cmd: str):
    """Execute ADB command via shell."""
    print(f"Executing: {cmd}")
    subprocess.run(cmd, shell=True)


# ============== Main entry point ==============
def run_from_response(response: str) -> int:
    """
    Parse OS-Atlas model response and execute the action.

    Returns:
      0: Completed normally
      1: Task finished (COMPLETE)
     -1: Unrecognized action
    """
    thoughts, action = extract_action_block(response)

    if thoughts:
        print(f"[Thoughts] {thoughts}")

    if not action:
        print("[Warning] No action found in response")
        return -1

    cmd = parse_action_to_adb(action)

    if cmd is None:
        print(f"[Warning] Could not parse action: {action}")
        return -1

    if cmd.startswith("WAIT:"):
        wait_time = float(cmd.split(":")[1])
        print(f"[Wait] {wait_time}s ...")
        time.sleep(wait_time)
        return 0

    if cmd == "COMPLETE":
        print("[Complete] Task finished")
        return 1

    execute_adb_command(cmd)
    return 0
