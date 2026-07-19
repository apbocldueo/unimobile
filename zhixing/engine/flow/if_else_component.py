from __future__ import annotations

from typing import Any, Dict

from zhixing.engine.flow.base_flow_component import BaseFlowComponent, FlowComponentResult


class IfElseComponent(BaseFlowComponent):
    """If-Else 流程控制：按 operator 返回 True/False 分支，不执行业务逻辑。"""

    node_type = "ifelse"

    def run(self, node_data: Dict[str, Any], *, inbound_present: bool = True) -> FlowComponentResult:
        if not inbound_present:
            return FlowComponentResult(
                branch_result="false",
                msg="If-Else 缺少上游条件输入",
                follow_port_role="out_false",
            )

        op = node_data.get("operator_value") or node_data.get("operator") or "not_use"
        if op not in ("use", "not_use"):
            op = "not_use"

        if op == "use":
            return FlowComponentResult(
                branch_result="true",
                msg="If-Else 条件判定：使用组件，进入 True 分支",
                follow_port_role="out_true",
            )
        return FlowComponentResult(
            branch_result="false",
            msg="If-Else 条件判定：不使用组件，进入 False 分支",
            follow_port_role="out_false",
        )
