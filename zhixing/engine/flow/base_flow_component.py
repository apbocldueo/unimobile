from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, Literal, Optional


@dataclass
class FlowComponentResult:
    """流程控制节点执行结果（对齐设计文档中的 branch_result / msg 约定）。"""

    branch_result: Optional[Literal["true", "false"]] = None
    msg: str = ""
    follow_port_role: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class BaseFlowComponent(ABC):
    """画布节点执行基类（设计文档中的 BaseAgentComponent 语义：统一 run 入口）。"""

    node_type: str = ""

    @abstractmethod
    def run(self, node_data: Dict[str, Any], *, inbound_present: bool = True) -> FlowComponentResult:
        """执行节点逻辑；``node_data`` 为前端 Flow JSON 中该节点的 data 字段（含 operator_value 等）。"""
        raise NotImplementedError
