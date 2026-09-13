"""Notify Android MediaStore after filesystem changes (push / delete)."""

import logging
from typing import Any, Optional
from urllib.parse import quote

_log = logging.getLogger(__name__)


def file_uri_for_media_scan(device_path: str) -> str:
    p = device_path.replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + quote(p, safe="/")


def broadcast_media_scan(
    device,
    device_path: str,
    logger: Optional[Any] = None,
) -> None:
    """Send ``MEDIA_SCANNER_SCAN_FILE`` so gallery apps refresh for this file or directory."""
    log = logger or _log
    uri = file_uri_for_media_scan(device_path)
    cmd = (
        "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
        f"-d {uri}"
    )
    log.debug("media scan: %s", cmd)
    res = device.shell(cmd, error_raise=False)
    if res.exit_code != 0:
        log.warning(
            "media scan broadcast non-zero exit=%s for %s: %s",
            res.exit_code,
            device_path,
            (res.output or res.error or "").strip()[:500],
        )
