"""
启动 ZhiXing Studio 元数据服务；可把本脚本放在仓库根目录，从任意工作目录执行::

    python /path/to/unimobile/run_studio.py

会把仓库根目录插入 ``sys.path``，避免在 ``studio/`` 等子目录下执行 ``python -m zhixing.studio`` 时找不到 ``zhixing`` 包。
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parent
    rs = str(root)
    if rs not in sys.path:
        sys.path.insert(0, rs)
    from zhixing.studio.__main__ import main as studio_main

    studio_main()


if __name__ == "__main__":
    main()
