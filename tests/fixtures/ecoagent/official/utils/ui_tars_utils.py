import re
import subprocess
from typing import List, Optional, Tuple


# ---------- Coordinate parsing tools (x,y compatible) ----------
def _find_xy_anywhere(t: str) -> Optional[Tuple[int, int]]:
    """
    Find the first coordinate pair in the entire action text.
    Supports: 584,1264 / (584,1264) / '584,1264' / x=584, y=1264 / x : 584 , y : 1264
    Returns (x, y) or None
    """
    # 1) Explicit key-value pairs first (more accurate)
    m = re.search(r"\bx\s*[:=]\s*(-?\d+)\s*[,;]\s*y\s*[:=]\s*(-?\d+)\b", t, re.I)
    if m:
        return int(m.group(1)), int(m.group(2))
    # 2) 通用 “可带括号/引号 的 x,y”
    m = re.search(r"[('\"\s]*(-?\d+)\s*,\s*(-?\d+)[)'\"]*", t)
    if m:
        return int(m.group(1)), int(m.group(2))
    return None


def _find_two_xy_anywhere(t: str) -> Optional[List[Tuple[int,int]]]:
    """
    Extract two coordinate pairs from a single action (for drag / swipe, etc).
    Supports: drag((x1,y1),(x2,y2)) / drag('x1,y1','x2,y2') / x1=..,y1=..,x2=..,y2=.. etc.
    """
    # Prioritize matching x1,y1,x2,y2 key-value
    m = re.search(
        r"\bx1\s*[:=]\s*(-?\d+)\s*[,;]\s*y1\s*[:=]\s*(-?\d+)\b.*?\bx2\s*[:=]\s*(-?\d+)\s*[,;]\s*y2\s*[:=]\s*(-?\d+)\b",
        t, re.I | re.S
    )
    if m:
        return [(int(m.group(1)), int(m.group(2))), (int(m.group(3)), int(m.group(4)))]
    # 否则抓两对 “x,y”
    pairs = re.findall(r"(-?\d+)\s*,\s*(-?\d+)", t)
    if len(pairs) >= 2:
        (x1,y1), (x2,y2) = pairs[0], pairs[1]
        return [(int(x1),int(y1)), (int(x2),int(y2))]
    return None


def _encode_for_adb_input_text(s: str) -> str:
    # adb input text can use %s for spaces to avoid shell splitting
    return s.replace(" ", "%s")


def _shell_single_quoted(s: str) -> str:
    # Safe wrapping with single quotes
    return "'" + s.replace("'", "'\"'\"'") + "'"


# ============== Parse single Action to ADB command (Android version) ==============
def parse_action_to_adb(action_text: str) -> Optional[str]:
    t = action_text.strip()
    low = t.lower()

    # ---- click(...): grab first x,y and tap ----
    if low.startswith("click"):
        xy = _find_xy_anywhere(t)
        if xy:
            x, y = xy
            return f"adb shell input tap {x} {y}"
        return None

    # ---- long_press(..., duration=xxx) ----
    if low.startswith("long_press"):
        xy = _find_xy_anywhere(t)
        if xy:
            x, y = xy
            dur = 800
            md = re.search(r"duration\s*=\s*(\d+)", t, re.I)
            if md:
                dur = int(md.group(1))
            return f"adb shell input swipe {x} {y} {x} {y} {dur}"
        return None

    # ---- drag(...) / swipe(...) (two coordinate pairs) ----
    if low.startswith("drag") or low.startswith("swipe"):
        pts = _find_two_xy_anywhere(t)
        if pts:
            (x1,y1), (x2,y2) = pts
            # Allow passing duration (can be ignored)
            return f"adb shell input swipe {x1} {y1} {x2} {y2}"
        return None

    # ---- scroll(..., direction='down', delta=400) ----
    if low.startswith("scroll"):
        xy = _find_xy_anywhere(t)
        if xy:
            x, y = xy
            d = re.search(r"direction\s*=\s*['\"](\w+)['\"]", t, re.I)
            direction = (d.group(1).lower() if d else "down")
            md = re.search(r"delta\s*=\s*(\d+)", t, re.I)
            delta = int(md.group(1)) if md else 400
            if direction == "down":
                return f"adb shell input swipe {x} {y} {x} {y - delta}"
            elif direction == "up":
                return f"adb shell input swipe {x} {y} {x} {y + delta}"
            elif direction == "left":
                return f"adb shell input swipe {x} {y} {x - delta} {y}"
            elif direction == "right":
                return f"adb shell input swipe {x} {y} {x + delta} {y}"
        return None

    # ---- type(content='...') ----
    if low.startswith("type"):
        m = re.search(r"content\s*=\s*['\"](.*?)['\"]", t, re.I | re.S)
        if m:
            raw = m.group(1)
            text = raw.encode("utf-8").decode("unicode_escape")  # Restore \n
            needs_enter = text.endswith("\n")
            if needs_enter:
                text = text[:-1]
            encoded = _encode_for_adb_input_text(text)
            # ⚠️ Make sure input field is focused, otherwise add click action
            cmd = f"adb shell input text {_shell_single_quoted(encoded)}"
            if needs_enter:
                cmd += " && adb shell input keyevent KEYCODE_ENTER"
            return cmd

    # ---- press_* actions ----
    if low.startswith("press_home"):
        return "adb shell input keyevent KEYCODE_HOME"
    if low.startswith("press_back"):
        return "adb shell input keyevent KEYCODE_BACK"
    if low.startswith("press_enter"):
        return "adb shell input keyevent KEYCODE_ENTER"  # Enter

    # ---- finished action ----
    if low.startswith("finished"):
        return "echo 'Task finished'"

    return None


# ============== Extract Action block from model response ==============
def extract_action_block(response: str) -> str:
    m = re.search(r"Action:\s*(.+)", response, re.S | re.I)
    if not m:
        raise ValueError("No Action found in model output")
    return m.group(1).strip()


# ============== More robust action splitting: by bracket pairing ==============
def _split_actions(actions_text: str) -> List[str]:
    items, buf, depth = [], [], 0
    for ch in actions_text:
        buf.append(ch)
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth = max(0, depth - 1)
            if depth == 0:
                item = ''.join(buf).strip()
                if item:
                    items.append(item)
                buf = []
    tail = ''.join(buf).strip()
    if tail:
        items.append(tail)
    return items


# ============== Executor ==============
def execute_adb_command(cmd: str):
    print(f"🚀 Executing: {cmd}")
    subprocess.run(cmd, shell=True)


# ============== 主入口 ==============
def run_from_response(response: str) -> int:
    """
    return:
      0: Completed normally (no explicit finished)
      1: Encountered finished() and terminated early
     -1: Unrecognized action encountered (logged but continued)
    """
    actions = extract_action_block(response)
    action_list = _split_actions(actions)
    status = 0
    for act in action_list:
        cmd = parse_action_to_adb(act.strip())
        if cmd == "echo 'Task finished'":
            print("✅ Task finished")
            status = 1
            break
        elif cmd:
            execute_adb_command(cmd)
        else:
            print(f"⚠️ Unrecognized action: {act}")
            status = -1
    return status