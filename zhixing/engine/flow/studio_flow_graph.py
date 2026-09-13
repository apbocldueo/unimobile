from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Set, Tuple

from zhixing.engine.flow.base_flow_component import FlowComponentResult
from zhixing.engine.flow.if_else_component import IfElseComponent


def _port_role_for_handle(node: Dict[str, Any], port_id: str) -> Optional[str]:
    data = node.get("data") or {}
    for p in data.get("ports") or []:
        if p.get("portId") == port_id or p.get("portRole") == port_id:
            return p.get("portRole")
    return None


def _node_by_id(document: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {n["nodeId"]: n for n in document.get("nodes", []) if isinstance(n, dict) and n.get("nodeId")}


def resolve_next_node_ids_after_if_else(
    document: Dict[str, Any],
    *,
    if_else_node_id: str,
    branch_result: Literal["true", "false"],
) -> List[str]:
    """根据 If-Else 判定结果，返回应从该节点沿出线到达的下游 nodeId 列表。"""
    want_role = "out_true" if branch_result == "true" else "out_false"
    out: List[str] = []
    nodes = _node_by_id(document)
    src = nodes.get(if_else_node_id)
    if not src:
        return out
    for e in document.get("edges", []) or []:
        if not isinstance(e, dict):
            continue
        if e.get("sourceNodeId") != if_else_node_id:
            continue
        sid = e.get("sourcePortId")
        if not sid:
            continue
        role = _port_role_for_handle(src, str(sid))
        if role == want_role:
            tid = e.get("targetNodeId")
            if tid:
                out.append(str(tid))
    return out


def walk_active_branch_linear(
    document: Dict[str, Any],
    *,
    start_node_id: str,
    inbound_by_node: Optional[Dict[str, bool]] = None,
) -> List[Tuple[str, str, FlowComponentResult]]:
    """从 ``start_node_id`` 起沿单路径行走；遇到 ``nodeType == ifelse`` 时求分支并只沿命中端口继续。"""
    inbound_by_node = inbound_by_node or {}
    nodes = _node_by_id(document)
    edges = [e for e in (document.get("edges") or []) if isinstance(e, dict)]

    order: List[Tuple[str, str, FlowComponentResult]] = []
    visited: Set[str] = set()
    cur: Optional[str] = start_node_id
    comp = IfElseComponent()

    while cur and cur not in visited:
        visited.add(cur)
        node = nodes.get(cur)
        if not node:
            break
        nt = str(node.get("nodeType") or "")
        data = dict(node.get("data") or {})

        if nt == "ifelse":
            present = bool(inbound_by_node.get(cur, True))
            res = comp.run(data, inbound_present=present)
            nxt_list = resolve_next_node_ids_after_if_else(
                document,
                if_else_node_id=cur,
                branch_result=res.branch_result or "false",
            )
            if not nxt_list:
                end = FlowComponentResult(
                    branch_result=res.branch_result,
                    msg=(res.msg or "") + "；当前分支无后续节点，流程结束",
                    follow_port_role=res.follow_port_role,
                )
                order.append((cur, nt, end))
                break
            order.append((cur, nt, res))
            cur = nxt_list[0]
            continue

        order.append((cur, nt, FlowComponentResult(msg=f"经过节点 {cur} ({nt})")))
        outs = [e for e in edges if e.get("sourceNodeId") == cur]
        if not outs:
            break
        nxt = outs[0].get("targetNodeId")
        cur = str(nxt) if nxt else None

    return order
