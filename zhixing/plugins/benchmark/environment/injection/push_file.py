import os
from typing import Dict, Any
from urllib.parse import quote

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.injection", name="android_injection_push_file")
class ADBInjectionPushFileGenerator(BaseEnvironmentInitializerOperation):
    """
    Android File Push Initializer

    This initializer copies files from the host machine to the Android
    device using the adb push command.

    It is mainly used to prepare datasets or media files before running
    a benchmark task.

    Typical use cases
    -----------------

    - Prepare images for Gallery tasks
    - Prepare videos for VLC tasks
    - Prepare music files for Retro Music
    - Prepare markdown files for Markor
    - Prepare documents for Files app

    ------------------------------------------------------------
    DSL Usage
    ------------------------------------------------------------

    The initializer supports two modes.

    1️⃣ Static mode

    Files are explicitly defined.

    Example:

    {
        "type": "android_injection_push_file",
        "files": [
            {
                "local_path": "assets/sample.jpg",
                "device_path": "/storage/emulated/0/Pictures/test.jpg"
            }
        ]
    }

    2️⃣ Parametric mode

    Files are generated from task parameters.

    Example:

    {
        "type": "android_injection_push_file",
        "files": {
            "source": "$params.names",
            "template": {
                "local_path": "assets/sample_song.mp3",
                "device_path": "/storage/emulated/0/Music/{item}.mp3"
            }
        }
    }

    If params =

        {
            "names": ["song1", "song2"]
        }

    Then the initializer generates:

        adb push assets/sample_song.mp3 /storage/emulated/0/Music/song1.mp3
        adb push assets/sample_song.mp3 /storage/emulated/0/Music/song2.mp3

    ------------------------------------------------------------
    DSL Rules
    ------------------------------------------------------------

    files = list
        Static files

    files = dict(source + template)
        Parametric generation

    media_scan : bool, optional
        If true (default), after each successful push the device is asked to
        scan that path into MediaStore (``MEDIA_SCANNER_SCAN_FILE``). Gallery
        and Google Photos then pick up the file without waiting for a slow
        background scan. Set false to skip (e.g. non-media payloads).

    ------------------------------------------------------------
    """
    op_type = EnvironmentInitializerPluginType.ADB_PUSH_FILE

    @staticmethod
    def _file_uri_for_media_scan(device_path: str) -> str:
        p = device_path.replace("\\", "/")
        if not p.startswith("/"):
            p = "/" + p
        return "file://" + quote(p, safe="/")

    def _request_media_scan(self, device, device_path: str) -> None:
        uri = self._file_uri_for_media_scan(device_path)
        cmd = (
            "am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE "
            f"-d {uri}"
        )
        self.logger.debug("media scan: %s", cmd)
        res = device.shell(cmd, error_raise=False)
        if res.exit_code != 0:
            self.logger.warning(
                "media scan broadcast non-zero exit=%s for %s: %s",
                res.exit_code,
                device_path,
                (res.output or res.error or "").strip()[:500],
            )

    def execute(self, meta: Dict[str, Any], params: Dict[str, Any]) -> bool:
        try:
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False

            files = params.get("files")
            if not files:
                self.logger.error("params missing 'files'")
                return False
            if len(files) == 0:
                self.logger.error("'files' list is empty")
                return False

            self.logger.info("push %d file(s) to device", len(files))
            default_media_scan = bool(params.get("media_scan", True))

            for idx, file_info in enumerate(files):
                local_path = file_info.get("local_path")
                device_path = file_info.get("device_path")
                if not local_path:
                    self.logger.error("files[%d] missing local_path", idx)
                    return False
                if not device_path:
                    self.logger.error("files[%d] missing device_path", idx)
                    return False
                if not os.path.exists(local_path):
                    self.logger.error("local file missing: %s", local_path)
                    return False

                parent_dir = os.path.dirname(device_path)
                if parent_dir:
                    parent_dir = parent_dir.replace("\\", "/")
                    mkdir_cmd = f"mkdir -p {parent_dir}"
                    self.logger.debug("ensure dir: %s", mkdir_cmd)
                    device.shell(mkdir_cmd)

                self.logger.info("push %s -> %s", local_path, device_path)
                if not device.push_file(local_path, device_path):
                    self.logger.error("push_file returned False for %s", local_path)
                    return False

                do_scan = default_media_scan
                if "media_scan" in file_info:
                    do_scan = bool(file_info["media_scan"])
                if do_scan:
                    self._request_media_scan(device, device_path)

            self.logger.info("all pushes completed OK")
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
