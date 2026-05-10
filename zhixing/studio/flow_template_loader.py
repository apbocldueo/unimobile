"""
从 ``data/flow_templates`` 加载兵工厂预设。

- **自动发现**：同目录下任意新增的 ``*.json`` / ``*.yaml`` / ``*.yml``（排除 ``manifest.*``）都会出现在模板列表中，无需改代码。
- **manifest.yaml**（可选）：为部分文件指定 ``id``、展示名、描述或顺序；已在 manifest 中声明的 ``document`` 不会重复自动登记。
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DATA_ROOT = Path(__file__).resolve().parent / "data"
_TEMPLATES_DIR = _DATA_ROOT / "flow_templates"
_MANIFEST_PATH = _TEMPLATES_DIR / "manifest.yaml"

_FLOW_DOC_SUFFIXES = {".json", ".yaml", ".yml"}


@dataclass(frozen=True)
class FlowTemplateMeta:
    template_id: str
    name: str
    description: str
    document_file: str


def _load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _load_json_or_yaml_document(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"document_not_object:{path}")
    return data


def _is_manifest_filename(name: str) -> bool:
    return name.lower() in {"manifest.yaml", "manifest.yml"}


def _discover_flow_document_paths() -> list[Path]:
    if not _TEMPLATES_DIR.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(_TEMPLATES_DIR.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file():
            continue
        if _is_manifest_filename(p.name):
            continue
        # 以下划线开头的文件名视为「非模板」（片段、草稿），不参与自动发现。
        if p.name.startswith("_"):
            continue
        if p.suffix.lower() not in _FLOW_DOC_SUFFIXES:
            continue
        out.append(p)
    return out


def _humanize_stem(stem: str) -> str:
    s = stem.replace("_", " ").replace("-", " ").strip()
    if not s:
        return stem
    return s[0].upper() + s[1:] if len(s) > 1 else s.upper()


def _peek_template_labels(path: Path) -> tuple[str, str]:
    """从流程文档顶层读取展示用名称/描述；失败时退回文件名 stem。"""
    try:
        data = _load_json_or_yaml_document(path)
    except Exception:
        logger.debug("flow_template_peek_failed path=%s", path, exc_info=True)
        return _humanize_stem(path.stem), ""

    if not isinstance(data, dict):
        return _humanize_stem(path.stem), ""

    name = ""
    for key in ("flowName", "name", "title", "templateName"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            name = v.strip()
            break

    desc = ""
    for key in ("flowDescription", "description", "desc", "summary"):
        v = data.get(key)
        if isinstance(v, str) and v.strip():
            desc = v.strip()
            break

    if not name:
        name = _humanize_stem(path.stem)
    return name, desc


def _parse_manifest_metas() -> list[FlowTemplateMeta]:
    if not _MANIFEST_PATH.is_file():
        return []
    try:
        raw = _load_yaml(_MANIFEST_PATH)
    except Exception:
        logger.warning("flow_templates_manifest_unreadable path=%s", _MANIFEST_PATH, exc_info=True)
        return []
    rows = raw.get("templates") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        return []
    out: list[FlowTemplateMeta] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        tid = str(row.get("id") or "").strip()
        name = str(row.get("name") or tid).strip()
        desc = str(row.get("description") or "").strip()
        doc = str(row.get("document") or "").strip()
        if not tid or not doc:
            continue
        if ".." in doc or doc.startswith(("/", "\\")):
            logger.warning("flow_templates_manifest_bad_document id=%s document=%s", tid, doc)
            continue
        doc_path = (_TEMPLATES_DIR / doc).resolve()
        if not str(doc_path).startswith(str(_TEMPLATES_DIR.resolve())):
            logger.warning("flow_templates_manifest_path_escape id=%s document=%s", tid, doc)
            continue
        if not doc_path.is_file():
            logger.warning("flow_templates_manifest_missing_doc id=%s document=%s", tid, doc)
            continue
        out.append(FlowTemplateMeta(template_id=tid, name=name, description=desc, document_file=doc))
    return out


def _unique_template_id(desired: str, reserved: set[str]) -> str:
    base = desired.strip() or "template"
    safe = re.sub(r"[^0-9A-Za-z_.-]+", "_", base).strip("._-") or "template"
    if safe not in reserved:
        return safe
    n = 2
    while f"{safe}_{n}" in reserved:
        n += 1
    return f"{safe}_{n}"


def _merged_flow_template_metas() -> list[FlowTemplateMeta]:
    manifest_metas = _parse_manifest_metas()
    covered_docs = {m.document_file.replace("\\", "/") for m in manifest_metas}
    reserved_ids = {m.template_id for m in manifest_metas}

    auto: list[FlowTemplateMeta] = []
    for path in _discover_flow_document_paths():
        rel = path.name
        rel_norm = rel.replace("\\", "/")
        if rel_norm in covered_docs:
            continue
        name, desc = _peek_template_labels(path)
        tid = _unique_template_id(path.stem, reserved_ids)
        reserved_ids.add(tid)
        auto.append(FlowTemplateMeta(template_id=tid, name=name, description=desc, document_file=rel))

    return [*manifest_metas, *auto]


def list_flow_templates() -> list[FlowTemplateMeta]:
    return _merged_flow_template_metas()


def get_flow_template_document(template_id: str) -> dict[str, Any]:
    tid = template_id.strip()
    if not tid or ".." in tid or "/" in tid or "\\" in tid:
        raise ValueError("invalid_template_id")
    meta = next((m for m in list_flow_templates() if m.template_id == tid), None)
    if meta is None:
        raise KeyError("template_not_found")
    doc_path = (_TEMPLATES_DIR / meta.document_file).resolve()
    if not str(doc_path).startswith(str(_TEMPLATES_DIR.resolve())):
        raise ValueError("document_path_escape")
    if not doc_path.is_file():
        raise FileNotFoundError(f"document_missing:{doc_path.name}")
    return _load_json_or_yaml_document(doc_path)


def templates_dir() -> Path:
    return _TEMPLATES_DIR
