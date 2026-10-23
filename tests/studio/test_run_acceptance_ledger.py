"""Reject incomplete or overstated ordinary Run acceptance evidence."""

import pytest
from pydantic import ValidationError

from scripts.studio_run_acceptance_ledger import SCENARIOS, RunAcceptanceLedger


def pending_ledger() -> dict:
    """Return a complete pending inventory, with safety counters unmeasured.

    Returns:
        A fresh plain ledger document for isolated validation mutations.
    """
    return {
        "schema_version": 1, "code_revision": "0" * 40,
        "dirty_baseline": "isolated ledger contract test, not execution evidence",
        "forbidden_effects": {"real-device": None, "external-network": None, "real-secret": None},
        "scenarios": [{
            "scenario_id": scenario, "environment": "android" if scenario == "A01" else "fake",
            "status": "not-run", "sources": [], "expected": "Scenario contract",
            "observed": "No execution evidence collected", "commands": [], "evidence_paths": [],
        } for scenario in SCENARIOS],
    }


def test_pending_ledger_round_trips_without_promoting_missing_proof():
    """Retain explicit not-run and unmeasured facts across serialization."""
    ledger = RunAcceptanceLedger.model_validate(pending_ledger())
    assert RunAcceptanceLedger.model_validate_json(ledger.model_dump_json()) == ledger
    assert all(s.status == "not-run" for s in ledger.scenarios)


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "pass", "absolute", "traversal", "secret", "cursor", "fake-android", "counter"])
def test_ledger_rejects_incomplete_or_unsafe_claims(mutation):
    """Reject one independently malformed evidence shape.

    Args:
        mutation: Single schema/inventory/privacy/claim violation.
    Raises:
        AssertionError: The strict ledger accepts unsupported evidence.
    """
    data = pending_ledger()
    scenario = data["scenarios"][0]
    if mutation == "missing": data["scenarios"].pop()
    elif mutation == "duplicate": data["scenarios"][1] = scenario.copy()
    elif mutation == "pass": scenario["status"] = "passed"
    elif mutation == "absolute": scenario["evidence_paths"] = ["/private/tmp/private.json"]
    elif mutation == "traversal": scenario["evidence_paths"] = ["../private.json"]
    elif mutation == "secret": scenario["api_key"] = "must-not-enter-evidence"
    elif mutation == "cursor": scenario.update(cursor=10, high_water_mark=9)
    elif mutation == "fake-android": data["scenarios"][-1]["environment"] = "fake"
    elif mutation == "counter": data["forbidden_effects"]["real-device"] = -1
    with pytest.raises(ValidationError):
        RunAcceptanceLedger.model_validate(data)
