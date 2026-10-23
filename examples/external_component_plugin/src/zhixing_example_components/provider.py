"""Formal ComponentBundle exported through the standard Entry Point."""

from __future__ import annotations

from zhixing.components import ComponentBundle, ComponentCategory, ComponentSpec
from zhixing.graph import (
    ContractPort,
    InvocationAdapterKind,
    NodeContract,
    NodeContractRef,
    PortDirection,
)

from .components import RunLabeler, RunLabelerConfig, TaskRunLabeler


RUN_LABELER_CONTRACT = NodeContract(
    ref=NodeContractRef(id="example.external.run_labeler", version="1.0"),
    ports=(
        ContractPort(
            id="value",
            direction=PortDirection.INPUT,
            data_types=("text",),
            required=True,
        ),
        ContractPort(
            id="result",
            direction=PortDirection.OUTPUT,
            data_types=("text",),
        ),
    ),
    adapter=InvocationAdapterKind.TYPED_INVOKE,
)

RUN_LABELER = ComponentSpec(
    namespace="example.external",
    name="run_labeler",
    version="1.0.0",
    contract=RUN_LABELER_CONTRACT,
    implementation=RunLabeler,
    category=ComponentCategory.EXTENSION,
    config_model=RunLabelerConfig,
    input_type=str,
    output_type=str,
    capabilities={
        "example": True,
        "runtime_context": True,
    },
)

TASK_RUN_LABELER_CONTRACT = NodeContract(
    ref=NodeContractRef(id="example.external.task_run_labeler", version="1.0"),
    ports=(
        ContractPort(
            id="task",
            direction=PortDirection.INPUT,
            data_types=("task_input",),
            required=True,
        ),
        ContractPort(
            id="result",
            direction=PortDirection.OUTPUT,
            data_types=("text",),
        ),
    ),
    adapter=InvocationAdapterKind.TYPED_INVOKE,
)

TASK_RUN_LABELER = ComponentSpec(
    namespace="example.external",
    name="task_run_labeler",
    version="1.0.0",
    contract=TASK_RUN_LABELER_CONTRACT,
    implementation=TaskRunLabeler,
    category=ComponentCategory.EXTENSION,
    config_model=RunLabelerConfig,
    input_type=TaskRunLabeler.input_type,
    output_type=str,
    capabilities={
        "example": True,
        "runtime_context": True,
        "task_input": True,
    },
)

bundle = ComponentBundle(
    components=(RUN_LABELER, TASK_RUN_LABELER),
    schema_version="1",
)


__all__ = [
    "RUN_LABELER",
    "RUN_LABELER_CONTRACT",
    "TASK_RUN_LABELER",
    "TASK_RUN_LABELER_CONTRACT",
    "bundle",
]
