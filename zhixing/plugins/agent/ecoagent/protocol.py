"""Source plan/decoder rules with individually documented syntax repairs."""

import json
import re

from . import _decoder


def needs_model(step):
    """Preserve case-sensitive original prefix shortcut.

    Args:
        step: Source high-level instruction.
    Returns:
        bool: Whether a speculative next action needs the executor model.
    """
    return not step.startswith(('INPUT', 'DELETE TEXT', 'PRESS_BACK', 'PRESS_HOME'))


def parse_plan(output, *, fix_protocol=True):
    """Extract ordered source fields and reject invalid plans before device indexing.

    Args:
        output: Cloud response with fenced plan JSON.
        fix_protocol: Accept the common lowercase JSON fence repair.
    Raises:
        ValueError: Missing fence, invalid JSON, empty steps or unmatched expectations.
    Returns:
        tuple: Ordered steps and expectations, preserving the original separate filters.
    """
    start = output.find('```json')
    if start == -1:
        start = output.find('```')
    end = output.find('```', start + 3) if start != -1 else -1
    if start == -1 or end == -1:
        raise ValueError('EcoAgent plan requires fenced JSON')
    content = output[start + 3:end].strip()
    content = re.sub(r'(?i)^json\s*', '', content) if fix_protocol else content.lstrip('JSON')
    try:
        plan = json.loads(content.replace('\n', '').replace('\r', '').replace('\t', '').strip())
        if not isinstance(plan, dict):
            raise ValueError()
        steps = tuple(v.get('step') for v in plan.values() if isinstance(v, dict) and v.get('step'))
        expectations = tuple(v.get('expectation') for v in plan.values() if isinstance(v, dict) and v.get('expectation'))
        if not steps or len(steps) != len(expectations) or any(not isinstance(v, str) for v in (*steps, *expectations)):
            raise ValueError()
        return steps, expectations
    except (ValueError, TypeError):
        raise ValueError('EcoAgent plan requires nonempty steps and matching expectations') from None


def commands(output, *, fix_protocol=True):
    """Yield original decoder commands in order, ignoring unknowns and stopping at finished.

    Args:
        output: Source UI-TARS response.
        fix_protocol: Accept space-separated point tags without coordinate rescaling.
    Raises:
        ValueError: Original Action block is absent.
    Returns:
        tuple[str, ...]: Source-generated commands only; this function never executes them.
    """
    result = []
    for action in _decoder._split_actions(_decoder.extract_action_block(output)):
        if fix_protocol:
            action = re.sub(r'<point>\s*(-?\d+)\s+(-?\d+)\s*</point>', r'\1,\2', action)
        command = _decoder.parse_action_to_adb(action.strip())
        if command == "echo 'Task finished'":
            break
        if command:
            result.append(command)
    return tuple(result)
