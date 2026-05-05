import cv2
import numpy as np
import logging
from zhixing.core.agent.interfaces import BaseVerifier
from zhixing.core.agent.protocol import VerifierInput, VerifierResult, ActionType
# from zhixing.utils.registry import register_verifier
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

# @register_verifier("screen_diff_verifier")
@PluginRegistry.register(namespace="agent.verifier", name="screen_diff_verifier")
class ScreenDiffVerifier(BaseVerifier):
    def __init__(self, threshold: float = 0.01, **kwargs):
        self.threshold = threshold

    def verify(self, input_data: VerifierInput) -> VerifierResult:
        action = input_data.action
        img_before_path = input_data.screenshot_before
        img_after_path = input_data.screenshot_after
        
        if action.type not in [ActionType.TAP, ActionType.SWIPE, ActionType.TEXT]:
            return VerifierResult(is_success=True, feedback="Action type skipped verification")

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
                    score=1.0
                )
            else:
                return VerifierResult(
                    is_success=False, 
                    feedback=f"Screen did NOT change (Diff: {diff_ratio:.2%})",
                    score=0.0,
                    should_retry=True
                )

        except Exception as e:
            logger.error(f"Verification failed: {e}")
            return VerifierResult(is_success=True, feedback=f"Verifier Error: {e}")