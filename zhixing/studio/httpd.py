"""
ZhiXing Studio 元数据 HTTP 服务（默认 8765）：供前端 Vite 代理 ``/zhixing-studio`` 调用。

流程预设由 ``data/flow_templates`` 下 YAML/JSON 驱动：目录内流程文件自动出现在列表中，可选 ``manifest.yaml`` 覆盖元数据（见 ``flow_template_loader``）。
"""
from __future__ import annotations

import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from zhixing.studio.flow_template_loader import get_flow_template_document, list_flow_templates

logger = logging.getLogger(__name__)

_DATA = Path(__file__).resolve().parent / "data"


def _json_bytes(obj: object, status: int = 200) -> tuple[int, bytes, list[tuple[str, str]]]:
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    return status, body, headers


def _file_json_bytes(path: Path) -> tuple[int, bytes, list[tuple[str, str]]]:
    if not path.is_file():
        return _json_bytes({"error": "not_found", "message": str(path)}, 404)
    body = path.read_bytes()
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", "*"),
    ]
    return 200, body, headers


class StudioHTTPRequestHandler(BaseHTTPRequestHandler):
    server_version = "ZhiXingStudio/0.1"

    def log_message(self, fmt: str, *args: object) -> None:
        logger.info("%s - %s", self.address_string(), fmt % args)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Accept, Content-Type")
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path or "/"
        try:
            if path == "/studio/nav-modules":
                payload = {
                    "modules": [
                        {"id": "builder", "name": "Agent 构建", "iconKey": "bot", "order": 10, "path": "/builder", "allowed": True},
                        {"id": "benchmark", "name": "试车场", "iconKey": "lineChart", "order": 20, "path": "/benchmark", "allowed": True},
                        {"id": "history", "name": "历史", "iconKey": "history", "order": 30, "path": "/history", "allowed": True},
                        {"id": "settings", "name": "设置", "iconKey": "settings", "order": 40, "path": "/settings", "allowed": True},
                    ]
                }
                status, body, headers = _json_bytes(payload)
            elif path == "/studio/module-config":
                qs = parse_qs(parsed.query or "")
                mid = (qs.get("moduleId") or [""])[0] or "unknown"
                payload = {"moduleId": mid, "permission": "allow", "sidebarItems": []}
                status, body, headers = _json_bytes(payload)
            elif path == "/studio/builder/flows":
                status, body, headers = _json_bytes({"flows": []})
            elif path == "/studio/builder/agent-registry":
                reg_path = _DATA / "agent_registry_skeleton.json"
                status, body, headers = _file_json_bytes(reg_path)
            elif path == "/studio/flow-templates":
                items = [
                    {"id": m.template_id, "name": m.name, "description": m.description} for m in list_flow_templates()
                ]
                status, body, headers = _json_bytes({"templates": items})
            elif path.startswith("/studio/flow-templates/") and path.endswith("/document"):
                prefix = "/studio/flow-templates/"
                suffix = "/document"
                tid = path[len(prefix) : -len(suffix)]
                doc = get_flow_template_document(tid)
                status, body, headers = _json_bytes(doc)
            else:
                status, body, headers = _json_bytes({"error": "not_found", "path": path}, 404)
        except KeyError:
            status, body, headers = _json_bytes({"error": "template_not_found"}, 404)
        except FileNotFoundError as e:
            status, body, headers = _json_bytes({"error": "document_missing", "message": str(e)}, 404)
        except Exception as e:
            logger.exception("studio_http_error path=%s", path)
            status, body, headers = _json_bytes({"error": "server_error", "message": str(e)}, 500)

        self.send_response(status)
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)


def run_httpd(host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = ThreadingHTTPServer((host, port), StudioHTTPRequestHandler)
    logger.info("ZhiXing Studio HTTP listening on http://%s:%s", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Studio HTTP")
        httpd.shutdown()
