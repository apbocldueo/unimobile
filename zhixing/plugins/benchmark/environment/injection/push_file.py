import logging
import os
from typing import Dict, Any, List

from benchmarks.environment.initializers.base.android import AndroidEnvironmentSetup
from benchmarks.core.interface import BaseEnvOp
from benchmarks.core.protocol import EnvironmentInitializerType

logger = logging.getLogger(__name__)


class ADBInjectionPushFileGenerator(BaseEnvOp):
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

    ------------------------------------------------------------
    """
    op_type = EnvironmentInitializerType.ADB_PUSH_FILE


    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        try:
            logger.info("[PushFile] 开始执行文件推送操作")

            # ====================== 1. 核心：获取Device实例（操作手机的关键） ======================
            device = meta.get("device")
            if not device:
                logger.error("[PushFile] meta中缺少device实例！")
                return False
            
            # ====================== 2. 校验核心参数（新JSON格式） ======================
            files_config = params.get("files")
            if not files_config:
                logger.error("[PushFile] params中缺少files参数")
                return False
            files = files_config

            if len(files) == 0:
                logger.error("[PushFile] 解析后的files列表为空")
                return False
            logger.info(f"[PushFile] 准备推送{len(files)}个文件到设备")

            # ====================== 3. 遍历推送每个文件 ======================
            for file_info in files:
                local_path = file_info.get("local_path")
                device_path = file_info.get("device_path")
                if not local_path:
                    logger.error("[PushFile] 文件配置缺少local_path字段")
                    return False
                if not device_path:
                    logger.error("[PushFile] 文件配置缺少device_path字段")
                    return False
                
                if not os.path.exists(local_path):
                    logger.error(f"[PushFile] 本地文件不存在：{local_path}")
                    return False
                
                # ====================== 4. 创建设备端目标目录 ======================
                parent_dir = os.path.dirname(device_path)
                if parent_dir:
                    # 标准化设备路径分隔符
                    parent_dir = parent_dir.replace("\\", "/")
                    mkdir_cmd = f"mkdir -p {parent_dir}"
                    logger.debug(f"[PushFile] 执行设备命令：{mkdir_cmd}")

                    device.device.shell(mkdir_cmd)
                
                # ====================== 5. 推送文件到设备 ======================
                logger.info(f"[PushFile] 推送文件：{local_path} → {device_path}")
                push_result = device.push_file(local_path, device_path)
                if not push_result:
                    logger.error(f"[PushFile] 文件推送失败：{local_path} → {device_path}")
                    return False
                logger.info(f"[PushFile] 文件推送成功：{device_path}")
            
            logger.info("[PushFile] 所有文件推送完成")
            return True
        
        except Exception as e:
            logger.error(f"[PushFile] 执行异常：{str(e)}", exc_info=True)
            return False