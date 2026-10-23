
import subprocess
import sys
import agent.eco as eco
import infer
import time
import argparse
MAX_STEPS = 30

def list_adb_devices():
    """List connected adb devices and return a list of device serials."""
    cmd = ["adb", "devices"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("Error: 'adb' command not found. Make sure adb is installed and on PATH.", file=sys.stderr)
        return []
    lines = proc.stdout.strip().splitlines()
    devices = []
    for line in lines[1:]:  # skip header
        if line.strip() and "device" in line:
            serial = line.split()[0]
            devices.append(serial)
    return devices

def select_device(devices):
    """Prompt user to select a device from the list."""
    if not devices:
        print("No devices found. Please connect a device and try again.")
        sys.exit(1)
    print("Connected devices:")
    for idx, serial in enumerate(devices):
        print(f"[{idx}] {serial}")
    while True:
        choice = input(f"Select device by number (0-{len(devices)-1}): ")
        if choice.isdigit() and 0 <= int(choice) < len(devices):
            return devices[int(choice)]
        print("Invalid selection. Try again.")

def send_home(selected_device):
    """Send Home key event to selected device using adb."""
    cmd = ["adb", "-s", selected_device, "shell", "input", "keyevent", "KEYCODE_HOME"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("Error: 'adb' command not found. Make sure adb is installed and on PATH.", file=sys.stderr)
        return 127
    return proc.returncode

def send_home():
    """Send Home key event to connected device using adb.

    Returns the subprocess return code. Prints stdout/stderr.
    """
    cmd = ["adb", "shell", "input", "keyevent", "KEYCODE_HOME"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        print("Error: 'adb' command not found. Make sure adb is installed and on PATH.", file=sys.stderr)
        return 127



if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--agent', type=str, default='eco_ui-tars', help='Agent to use')
    args = parser.parse_args()

    # List and select device
    devices = list_adb_devices()
    selected_device = select_device(devices)

    # Initialize agent
    if args.agent == 'eco_ui-tars':
        agent = eco.ECO(infer.Gpt4Wrapper('gpt-4o'), infer.SLMWrapper('ui-tars'), name='eco_ui-tars')
    elif args.agent == 'eco_showui':
        agent = eco.ECO(infer.Gpt4Wrapper('gpt-4o'), infer.SLMWrapper('showui'), name='eco_showui')
    elif args.agent == 'eco_qwen3':
        agent = eco.ECO(infer.Gpt4Wrapper('gpt-4o'), infer.SLMWrapper('qwen3'), name='eco_qwen3')
    elif args.agent == 'eco_os-atlas':
        agent = eco.ECO(infer.Gpt4Wrapper('gpt-4o'), infer.SLMWrapper('os-atlas'), name='eco_os-atlas')

    # Go back to home screen
    send_home(selected_device)

    # Get user input
    default_goal = "Add a contact named Alice with phone number 1234567890."
    goal = input(f"Please enter your query:") or default_goal

    # Initialize variables
    steps = []
    expectations = []
    descriptions = []
    total_tokens = 0
    llm_calls = 0
    prev_time = time.time()

    # Start execution
    for step_n in range(MAX_STEPS):
        steps,expectations,descriptions , total_tokens, llm_calls, result= agent.step(goal, step_n, steps,expectations,descriptions,total_tokens, llm_calls)
        print('Completed step {:d}.'.format(step_n + 1))
        curr_time = time.time()
        loop_time = curr_time - prev_time
        print(f"⏰Took {loop_time:.4f} seconds")
        # Update baseline time
        prev_time = curr_time
        if result:
            print('✅Task completed successfully!')
            break
    if not result:
        print('❌Reached maximum steps without completing the task.')