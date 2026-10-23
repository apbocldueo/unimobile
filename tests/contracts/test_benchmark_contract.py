from copy import deepcopy

import pytest

from zhixing.config.contracts import (
    ContractValidationError,
    parse_benchmark_suite,
    validate_benchmark_semantics,
)


def _leaf(method="file_exist"):
    return {
        "name": "system_state",
        "params": {"method": method, "file_path": "/tmp/${file_name}"},
    }


def _task(task_id="task-1", task_type="dynamic"):
    return {
        "id": task_id,
        "instruction": "Create ${file_name}",
        "app": "files",
        "type": task_type,
        "task_initializer": {
            "prefix": {"name": "random_choice", "params": {"options": ["demo"]}},
            "file_name": {
                "name": "random_string",
                "params": {"prefix": "${prefix}_", "length": 4},
            },
        },
        "environment_initializer": [
            {"name": "android_reset_clear_directory", "params": {"phone_folder_path": "/tmp"}},
            {"name": "android_injection_create_file", "params": {"path": "/tmp/${file_name}"}},
        ],
        "evaluator": _leaf(),
        "requires_login": False,
        "max_steps": 5,
    }


def _composite(logic, rules):
    return {"name": "composite", "params": {"logic": logic, "rules": rules}}


def test_valid_dynamic_task_preserves_initializer_and_environment_order():
    suite = parse_benchmark_suite([_task()])
    task = suite.root[0]
    assert list(task.task_initializer) == ["prefix", "file_name"]
    assert [item.name for item in task.environment_initializer] == [
        "android_reset_clear_directory",
        "android_injection_create_file",
    ]


def test_static_task_may_still_have_initializers():
    raw = _task(task_type="static")
    assert parse_benchmark_suite([raw]).root[0].type == "static"


@pytest.mark.parametrize("logic", ["AND", "OR", "SEQUENCE"])
def test_recursive_composite_evaluators(logic):
    raw = _task()
    raw["evaluator"] = _composite(
        logic,
        [_leaf(), _composite("AND", [_leaf("sqlite_row_match")])],
    )
    assert parse_benchmark_suite([raw]).root[0].evaluator.name == "composite"


@pytest.mark.parametrize("legacy_field", ["task", "params_config", "setup_config", "eval_type"])
def test_legacy_task_fields_are_rejected(legacy_field):
    raw = _task()
    raw[legacy_field] = "legacy"
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert legacy_field in str(caught.value)


def test_plugin_level_type_is_rejected():
    raw = _task()
    raw["task_initializer"]["file_name"] = {"type": "random_string", "params": {}}
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert "task_initializer.file_name" in str(caught.value)


@pytest.mark.parametrize("value", [0, -1, 1.5, True])
def test_invalid_max_steps(value):
    raw = _task()
    raw["max_steps"] = value
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert "max_steps" in str(caught.value)


def test_dynamic_task_requires_initializer():
    raw = _task()
    raw["task_initializer"] = {}
    raw["instruction"] = "No placeholders"
    raw["evaluator"]["params"]["file_path"] = "/tmp/static"
    with pytest.raises(ContractValidationError):
        parse_benchmark_suite([raw])


@pytest.mark.parametrize(
    "evaluator",
    [
        {"name": "eval_composite", "params": {"logic": "AND", "rules": [_leaf()]}},
        {"name": "composite", "params": {"logic": "AND", "rules": []}},
        {"name": "composite", "params": {"logic": "XOR", "rules": [_leaf()]}},
        {"name": "system_state", "params": {"file_path": "/tmp/x"}},
    ],
)
def test_invalid_evaluator_tree(evaluator):
    raw = _task()
    raw["evaluator"] = evaluator
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert "evaluator" in str(caught.value)


def test_forward_initializer_reference_is_rejected():
    raw = _task()
    raw["task_initializer"] = {
        "first": {"name": "random_string", "params": {"prefix": "${later}"}},
        "later": {"name": "random_string", "params": {}},
        "file_name": {"name": "random_string", "params": {}},
    }
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert "earlier initializer" in str(caught.value)


def test_unresolved_external_placeholder_is_rejected():
    raw = _task()
    raw["instruction"] += " ${missing}"
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([raw])
    assert "missing" in str(caught.value)


def test_unused_initializer_is_warning_not_error():
    raw = _task()
    raw["task_initializer"]["unused"] = {"name": "random_int", "params": {"min": 1, "max": 2}}
    suite = parse_benchmark_suite([raw])
    issues = validate_benchmark_semantics(suite)
    assert any(issue.code == "benchmark.initializer.unused" for issue in issues)


def test_empty_and_duplicate_suites_are_rejected():
    with pytest.raises(ContractValidationError):
        parse_benchmark_suite([])
    with pytest.raises(ContractValidationError) as caught:
        parse_benchmark_suite([_task("duplicate"), _task("duplicate")])
    assert "duplicate" in str(caught.value)
