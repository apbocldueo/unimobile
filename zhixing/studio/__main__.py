"""
启动 Studio 元数据服务::

    python -m zhixing.studio

默认监听 ``127.0.0.1:8765``，与前端 Vite 代理一致。
"""
from __future__ import annotations

import logging
import os

from zhixing.utils.utils import setup_logging

from zhixing.studio.httpd import run_httpd


def main() -> None:
    log_dir = "temp/log"
    os.makedirs(log_dir, exist_ok=True)
    setup_logging(f"{log_dir}/zhixing_studio.log")
    logging.getLogger(__name__).info("Starting zhixing.studio …")
    host = os.environ.get("ZHIXING_STUDIO_HOST", "127.0.0.1")
    port = int(os.environ.get("ZHIXING_STUDIO_PORT", "8765"))
    run_httpd(host=host, port=port)


if __name__ == "__main__":
    main()
