from zhixing.studio.agent_registry import build_agent_registry_payload


def test_studio_registry_exposes_backend_agent_graph_contract():
    payload = build_agent_registry_payload()
    graph = payload["agentGraph"]
    assert graph["roles"] == [
        "perception",
        "planner",
        "reasoning",
        "memory",
        "action_executor",
        "verifier",
    ]
    assert graph["portCatalog"]["roles"]["action_executor"][-1]["data_types"] == ["action_result"]
    assert any(
        item["id"] == "legacy_action_executor"
        for item in payload["modular"]["pluginsBySlot"]["action_executor"]
    )
