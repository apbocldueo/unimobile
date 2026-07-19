import logging
from typing import Any

from zhixing.core.agent.interfaces import BaseVerifier
from zhixing.core.agent.protocol import VerifierInput, VerifierResult, ActionType
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

try:
    import cv2  # type: ignore
except ImportError:
    cv2 = None  # type: ignore[assignment]

try:
    import numpy as np
except ImportError:
    np = None  # type: ignore[assignment]


@PluginRegistry.register(namespace="agent.verifier", name="screen_diff_verifier")
class ScreenDiffVerifier(BaseVerifier):
    """屏幕像素差校验；cv2/numpy 在运行 ``verify`` 时才必需，缺依赖时类仍可注册（Studio 兵工厂可见）。"""

    def __init__(self, threshold: float = 0.01, **kwargs: Any):
        self.threshold = threshold

    def verify(self, input_data: VerifierInput) -> VerifierResult:
        action = input_data.action
        img_before_path = input_data.screenshot_before
        img_after_path = input_data.screenshot_after

        if action.type not in [ActionType.TAP, ActionType.LONG_PRESS, ActionType.SWIPE, ActionType.TEXT]:
            return VerifierResult(is_success=True, feedback="Action type skipped verification")

        if cv2 is None or np is None:
            return VerifierResult(
                is_success=False,
                feedback="screen_diff_verifier 需要 opencv-python 与 numpy；请安装依赖后再运行校验。",
            )

        try:
            img1 = cv2.imread(img_before_path)
            img2 = cv2.imread(img_after_path)

            if img1 is None or img2 is None:
                return VerifierResult(is_success=False, feedback="Failed to load screenshots")

            if img1.shape != img2.shape:
                return VerifierResult(is_success=True, feedback="Screen dimension changed")

            gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
            gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
            diff = cv2.absdiff(gray1, gray2)
            _, thresh = cv2.threshold(diff, 30, 255, cv2.THRESH_BINARY)

            non_zero_count = np.count_nonzero(thresh)
            total_pixels = gray1.shape[0] * gray1.shape[1]
            diff_ratio = non_zero_count / total_pixels

            logger.debug("Screen diff ratio: %.4f", diff_ratio)

            if diff_ratio > self.threshold:
                return VerifierResult(
                    is_success=True,
                    feedback=f"Screen changed (Diff: {diff_ratio:.2%})",
                    score=1.0,
                )
            return VerifierResult(
                is_success=False,
                feedback=f"Screen did NOT change (Diff: {diff_ratio:.2%})",
                score=0.0,
                should_retry=True,
            )

        except Exception as e:
            logger.error("Verification failed: %s", e)
            return VerifierResult(is_success=True, feedback=f"Verifier Error: {e}")
