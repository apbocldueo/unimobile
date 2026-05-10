"""Build JSON metadata for the Studio agent builder from :class:`zhixing.core.factory.PluginRegistry`.

Maps each Modular slot (perception, reasoning, …) to the exact ``agent.<slot>`` namespace so
perception plugins never appear under memory, etc.
"""

from __future__ import annotations

import importlib
import inspect
import logging
import math
import pkgutil
from typing import Any, Dict, List, Optional, Tuple, Type, get_args, get_origin

from zhixing.core.agent import interfaces as _agent_interfaces
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

# 与 ``zhixing.core.agent.interfaces`` 中各 Base* 的 ``_description`` 对齐，供 Studio 槽位卡片展示（单一事实来源）。
_SLOT_BASE_CLASS: Dict[str, Type[Any]] = {
    "planner": _agent_interfaces.BasePlanner,
    "verifier": _agent_interfaces.BaseVerifier,
    "perception": _agent_interfaces.BasePerception,
    "reasoning": _agent_interfaces.BaseReason,
    "memory": _agent_interfaces.BaseMemory,
}


def _slot_base_description(slot_id: str) -> str:
    cls = _SLOT_BASE_CLASS.get(slot_id)
    if cls is None:
        return ""
    d = getattr(cls, "_description", None)
    return d.strip() if isinstance(d, str) else ""

# ModularAgent linear pipeline (must stay aligned with ``zhixing.engine.agent.modular_agent``).
# 与 Studio 概念拓扑、YAML ``agent.components`` 角色一致（非单步代码行序）。
MODULAR_SLOT_SPECS: Tuple[Tuple[str, str, str], ...] = (
    ("planner", "Planner", "规划"),
    ("verifier", "Verifier", "校验"),
    ("perception", "Perception", "感知"),
    ("reasoning", "Reasoning", "推理"),
    ("memory", "Memory", "记忆"),
)

# Constructor kwargs injected by the runtime / YAML loader — not end-user YAML ``params``.
_SKIP_INIT_NAMES = frozenset(
    {
        "self",
        "kwargs",
        "llm_client",
        "context",
        "device",
        "config",
        "knowledge_source",
        "env_info",
    }
)


def _discover_agent_plugin_modules() -> None:
    """Import ``zhixing.plugins.agent`` tree so ``@PluginRegistry.register`` runs."""
    try:
        import zhixing.plugins.agent as root  # type: ignore
    except ImportError:
        return
    for _, mod_name, _ in pkgutil.walk_packages(root.__path__, root.__name__ + "."):
        try:
            importlib.import_module(mod_name)
        except Exception:
            # Skip broken optional deps (e.g. heavy vision stacks) — Studio still serves other plugins.
            continue


def _unwrap_optional(annotation: Any) -> Any:
    origin = get_origin(annotation)
    if origin is type(None) or origin is None:
        return annotation
    if str(origin) == "typing.Union":
        args = [a for a in get_args(annotation) if a is not type(None)]
        return args[0] if len(args) == 1 else annotation
    return annotation


def _field_from_param(name: str, param: inspect.Parameter) -> Optional[Dict[str, Any]]:
    if name in _SKIP_INIT_NAMES:
        return None
    ann = param.annotation
    if ann is not inspect.Parameter.empty:
        ann = _unwrap_optional(ann)
    default = param.default
    has_default = default is not inspect.Parameter.empty

    label = name
    hint: Optional[str] = None

    # Prefer concrete default type when annotation is missing / Any.
    eff_type = ann
    if eff_type is inspect.Parameter.empty or eff_type is Any:
        if has_default and default is not None:
            eff_type = type(default)

    kind = "text"
    extra: Dict[str, Any] = {}

    if eff_type is bool or (has_default and isinstance(default, bool)):
        kind = "select"
        extra["options"] = [{"value": "true", "label": "是"}, {"value": "false", "label": "否"}]
        if has_default:
            extra["defaultValue"] = "true" if default else "false"
        else:
            extra["defaultValue"] = "false"
    elif eff_type is int or (has_default and isinstance(default, int)):
        kind = "number"
        extra["defaultValue"] = int(default) if has_default else 0
    elif eff_type is float or (has_default and isinstance(default, float)):
        kind = "number"
        extra["defaultValue"] = float(default) if has_default else 0.0
    else:
        kind = "text"
        if has_default and default is not None:
            extra["defaultValue"] = str(default)
        elif has_default:
            extra["defaultValue"] = ""
        else:
            extra["defaultValue"] = ""

    if kind == "text" and "defaultValue" not in extra:
        extra["defaultValue"] = ""

    out: Dict[str, Any] = {"id": name, "label": label, "hint": hint, "kind": kind, **extra}
    return out


def _param_groups_for_class(cls: Type[Any]) -> List[Dict[str, Any]]:
    try:
        sig = inspect.signature(cls.__init__)
    except (TypeError, ValueError):
        return []
    fields: List[Dict[str, Any]] = []
    for pname, p in sig.parameters.items():
        spec = _field_from_param(pname, p)
        if spec:
            fields.append(spec)
    if not fields:
        return []
    return [
        {
            "id": "constructor",
            "title": "组件参数",
            "tier": "core",
            "fields": fields,
        }
    ]


def _plugin_entry(namespace: str, name: str, cls: Type[Any]) -> Dict[str, Any]:
    doc = (cls.__doc__ or "").strip().split("\n", 1)[0].strip() if cls.__doc__ else ""
    return {
        "id": name,
        "namespace": namespace,
        "className": cls.__name__,
        "title": cls.__name__,
        "description": doc,
        "paramGroups": _param_groups_for_class(cls),
    }


def _plugins_for_namespace(namespace: str) -> List[Dict[str, Any]]:
    reg = PluginRegistry._registry.get(namespace) or {}
    out: List[Dict[str, Any]] = []
    for pname in sorted(reg.keys()):
        cls = reg[pname]
        try:
            out.append(_plugin_entry(namespace, pname, cls))
        except Exception as e:
            logger.warning("studio registry: skip plugin %s/%s (%s): %s", namespace, pname, cls, e)
            continue
    return out


def _sanitize_for_json(obj: Any) -> Any:
    """Make payload RFC-compliant (no NaN/Inf); drop non-JSON-native leaf values."""
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {str(k): _sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_for_json(v) for v in obj]
    if isinstance(obj, (str, int, bool)) or obj is None:
        return obj
    return str(obj)


def build_agent_registry_payload() -> Dict[str, Any]:
    """Return a JSON-serializable dict for ``GET /studio/builder/agent-registry``."""
    try:
        import zhixing.engine.agent.modular_agent  # noqa: F401 — registers ``modular_agent`` strategy
    except ImportError:
        pass
    _discover_agent_plugin_modules()

    slot_plugins: Dict[str, List[Dict[str, Any]]] = {}
    param_catalog: Dict[str, List[Dict[str, Any]]] = {}

    for slot_id, _title_en, _role_zh in MODULAR_SLOT_SPECS:
        ns = f"agent.{slot_id}"
        plugins = _plugins_for_namespace(ns)
        slot_plugins[slot_id] = plugins
        for p in plugins:
            pid = p["id"]
            param_catalog[pid] = p.get("paramGroups") or []

    slots = [
        {
            "slotId": sid,
            "title": ten,
            "roleLabel": rzh,
            "baseDescription": _slot_base_description(sid),
        }
        for sid, ten, rzh in MODULAR_SLOT_SPECS
    ]

    strategies = PluginRegistry._registry.get("agent.type") or {}
    modular_meta = strategies.get("modular_agent")
    modular_title = "Modular 流程"
    modular_desc = (
        "Modular 策略：按配置装配 Perception → Reasoning → Memory → Planner → Verifier；"
        "插件列表与参数来自运行中的 ZhiXing 注册表。"
    )
    if modular_meta and getattr(modular_meta, "__doc__", None):
        first = (modular_meta.__doc__ or "").strip().split("\n", 1)[0].strip()
        if first:
            modular_desc = first

    payload: Dict[str, Any] = {
        "version": 1,
        "modular": {
            "strategyId": "modular",
            "backendPluginName": "modular_agent",
            "title": modular_title,
            "description": modular_desc,
            "slots": slots,
            "pluginsBySlot": slot_plugins,
        },
        "paramCatalog": param_catalog,
    }
    return _sanitize_for_json(payload)  # type: ignore[return-value]
