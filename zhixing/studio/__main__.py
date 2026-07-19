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
    log_path = f"{log_dir}/zhixing_studio.log"
    setup_logging(log_path)
    logging.getLogger(__name__).info("Starting zhixing.studio …")
    host = os.environ.get("ZHIXING_STUDIO_HOST", "127.0.0.1")
    port = int(os.environ.get("ZHIXING_STUDIO_PORT", "8765"))
    # setup_logging 只写文件，无控制台 handler；此处打印避免误以为进程卡住。
    print(
        f"ZhiXing Studio 已启动: http://{host}:{port}\n"
        f"进程将一直占用此终端（serve_forever）；按 Ctrl+C 结束。\n"
        f"访问与请求日志见: {log_path}\n"
        f"若在子目录执行 ``python -m zhixing.studio`` 无法找到包，请改为在仓库根目录运行，或: python run_studio.py",
        flush=True,
    )
    run_httpd(host=host, port=port)


if __name__ == "__main__":
    main()
