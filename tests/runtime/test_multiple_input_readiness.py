"""Behavioral regression for complete multiple-cardinality data delivery."""

import pytest

from zhixing.components import BaseMemory, MemoryOperation, MemoryResult, TaskInput, PlanResult
from zhixing.graph import (
    AgentGraphBuilder, GraphRole, Predicate, PredicateOperator, RouterCase,
    ContractPort, InvocationAdapterKind, NodeContract, NodeContractCatalog, NodeContractRef, PortDirection,
)
from zhixing.runtime import GraphExecutionKernel, KernelStatus, bind_execution_plan


class RecordingMemory(BaseMemory):
    """Expose the exact values observed in one Memory activation."""

    def __init__(self):
        """Initialize test-local observed history."""
        self.fragments, self.reads = [], []

    def invoke(self, input, runtime):
        """Append writes and record the complete batch at READ.

        Args:
            input: Standard Memory operation.
            runtime: Unused context.
        Returns:
            MemoryResult: All actual fragments received so far.
        """
        if input.operation is MemoryOperation.APPEND:
            self.fragments.append(input.fragment)
        elif input.operation is MemoryOperation.READ:
            self.reads.append(tuple(fragment.content for fragment in self.fragments))
        return MemoryResult(input.operation, fragments=tuple(self.fragments))


class DelayedPlan:
    """Produce a distinct typed value after the directly connected task."""

    def invoke(self, input, runtime):
        """Convert the input task to a plan after the router gate.

        Args:
            input: Mapping containing the original task.
            runtime: Unused test context.
        Returns:
            dict: Typed PlanResult on the declared result port.
        """
        return {"result": PlanResult("delayed")}


@pytest.mark.parametrize("deliver_delayed", [True, False])
def test_memory_waits_for_all_data_producers_even_after_first_write(deliver_delayed):
    """Consume a delayed producer or its explicit conditional omission once.

    Args:
        deliver_delayed: Whether the delayed producer passes its edge predicate.

    Raises:
        AssertionError: The tested execution or boundary violates its contract.

    Returns:
        None.
    """
    contract = NodeContract(ref=NodeContractRef(id="test.delayed_plan", version="1"),
        adapter=InvocationAdapterKind.TYPED_INVOKE, ports=(
            ContractPort(id="task", direction=PortDirection.INPUT, data_types=("task_input",), required=True),
            ContractPort(id="control", direction=PortDirection.INPUT, data_types=("control",)),
            ContractPort(id="result", direction=PortDirection.OUTPUT, data_types=("plan_result",)),
        ))
    catalog = NodeContractCatalog((contract,))
    graph = (
        AgentGraphBuilder().add_input()
        .add_component("memory", namespace="test", name="memory", role=GraphRole.MEMORY)
        .add_router("gate", (RouterCase(id="ready", predicate=Predicate(
            field="instruction", operator=PredicateOperator.EXISTS)),), default="empty")
        .add_component("delayed", namespace="test", name="delayed", contract=contract.ref)
        .add_output()
        .connect("input", "task", "memory", "write")
        .connect("input", "task", "gate", "value")
        .connect("input", "task", "delayed", "task")
        .control("gate", "ready", "delayed")
        .connect("delayed", "result", "memory", "write", condition=Predicate(
            field="content", operator=PredicateOperator.EQ,
            value="delayed" if deliver_delayed else "excluded"))
        .connect("memory", "context", "output", "result")
        .build(validate=False)
    )
    memory = RecordingMemory()
    result = GraphExecutionKernel().run(bind_execution_plan(graph, {"memory": memory, "delayed": DelayedPlan()}, contract_catalog=catalog),
                                        {"task": TaskInput("direct")})
    assert result.status is KernelStatus.SUCCESS
    assert memory.reads == [("direct", "delayed") if deliver_delayed else ("direct",)]
