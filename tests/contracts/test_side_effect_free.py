import subprocess
import sys

from zhixing.config.contracts import AgentConfig, BenchmarkSuite, BenchmarkTask


def test_contracts_generate_json_schema():
    agent_schema = AgentConfig.model_json_schema()
    task_schema = BenchmarkTask.model_json_schema()
    suite_schema = BenchmarkSuite.model_json_schema()

    assert set(agent_schema["required"]) >= {"schema_version", "agent_type", "device", "agent"}
    assert "$defs" in task_schema
    assert suite_schema["minItems"] == 1


def test_contract_import_has_no_plugin_or_device_side_effects():
    script = """
import sys
from zhixing.config.contracts import AgentConfig, BenchmarkSuite
bad = sorted(name for name in sys.modules if name.startswith(('zhixing.plugins', 'zhixing.devices')))
assert not bad, bad
AgentConfig.model_json_schema()
BenchmarkSuite.model_json_schema()
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
