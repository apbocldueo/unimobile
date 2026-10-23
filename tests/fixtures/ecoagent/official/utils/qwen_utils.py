import json
import os
import re
import subprocess
import time
from typing import Optional

# Define screen resolution of your Android device/emulator
SCREEN_W, SCREEN_H = 1080, 2400  # AndroidWorld Emulator


# ============== Parse JSON action to ADB command ==============
def parse_action_to_adb(tool_json: dict) -> Optional[str]:
    """
    Parse JSON action object to ADB command.
    
    Args:
        tool_json: Dictionary containing action type and arguments
        
    Returns:
        ADB command string or None if action cannot be parsed
    """
    if not isinstance(tool_json, dict):
        try:
            tool_json = json.loads(tool_json)
        except Exception:
            print("[Error] Invalid tool_json format.")
            return None

    args = tool_json.get("arguments", {})
    action = args.get("action")

    if not action:
        print("[Error] No action specified in tool_json.")
        return None

    # ========== 1. Click action ==========
    if action == "click":
        x, y = args.get("coordinate", [0, 0])
        px, py = x / 999 * SCREEN_W, y / 999 * SCREEN_H
        return f"adb shell input tap {int(px)} {int(py)}"

    # ========== 2. Long press action ==========
    elif action == "long_press":
        x, y = args.get("coordinate", [0, 0])
        duration = int(args.get("time", 1.0) * 1000)  # milliseconds
        px, py = x / 999 * SCREEN_W, y / 999 * SCREEN_H
        return f"adb shell input swipe {int(px)} {int(py)} {int(px)} {int(py)} {duration}"

    # ========== 3. Swipe action ==========
    elif action == "swipe":
        x1, y1 = args.get("coordinate", [0, 0])
        x2, y2 = args.get("coordinate2", [0, 0])
        px1, py1 = x1 / 999 * SCREEN_W, y1 / 999 * SCREEN_H
        px2, py2 = x2 / 999 * SCREEN_W, y2 / 999 * SCREEN_H
        return f"adb shell input swipe {int(px1)} {int(py1)} {int(px2)} {int(py2)} 300"

    # ========== 4. Type action ==========
    elif action == "type":
        text = args.get("text", "")
        # Ensure input focus is in text field
        return f"adb shell input text '{text}'"

    # ========== 5. Wait action ==========
    elif action == "wait":
        t = args.get("time", 1.0)
        # Return special marker to indicate wait action
        return f"WAIT:{t}"

    # ========== 6. System button action ==========
    elif action == "system_button":
        key = args.get("button", "").lower()
        mapping = {
            "back": "KEYCODE_BACK",
            "home": "KEYCODE_HOME",
            "menu": "KEYCODE_APP_SWITCH",
            "enter": "KEYCODE_ENTER"
        }
        if key in mapping:
            return f"adb shell input keyevent {mapping[key]}"
        return None

    # ========== 7. Terminate action ==========
    elif action == "terminate":
        status = args.get("status", "success")
        return f"TERMINATE:{status}"

    else:
        print(f"[Warning] Unknown action type: {action}")
        return None


# ============== Execute ADB command ==============
def execute_adb_command(cmd: str):
    """Execute ADB command via shell."""
    print(f"🚀 Executing: {cmd}")
    subprocess.run(cmd, shell=True)


# ============== Extract action block from model response ==============
def extract_action_block(response: str) -> str:
    """
    Extract action JSON block from model response.
    
    Args:
        response: Model output response
        
    Returns:
        JSON action block as string
    """
    # Try to find JSON block
    json_start = response.find('{')
    json_end = response.rfind('}')
    
    if json_start == -1 or json_end == -1 or json_start >= json_end:
        raise ValueError("No JSON action found in model output")
    
    return response[json_start:json_end + 1].strip()


# ============== Main entry point ==============
def run_from_response(response: str) -> int:
    """
    Parse model response and execute actions.
    
    Returns:
      0: Completed normally
      1: Task finished successfully
     -1: Unrecognized action encountered
    """
    try:
        action_json_str = extract_action_block(response)
        action_json = json.loads(action_json_str)
    except (ValueError, json.JSONDecodeError) as e:
        print(f"[Error] Failed to parse action: {e}")
        return -1

    # Parse action to ADB command
    cmd = parse_action_to_adb(action_json)
    
    if cmd is None:
        print(f"[Warning] Could not parse action")
        return -1
    
    # Handle special commands
    if cmd.startswith("WAIT:"):
        wait_time = float(cmd.split(":")[1])
        print(f"[Wait] {wait_time}s ...")
        time.sleep(wait_time)
        return 0
    
    elif cmd.startswith("TERMINATE:"):
        status = cmd.split(":")[1]
        print(f"[Terminate] Task ended with status = {status}")
        return 1 if status == "success" else 0
    
    else:
        # Execute ADB command
        execute_adb_command(cmd)
        return 0

