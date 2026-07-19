import os
import time
import torch
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# Hugging Face GroundingDINO
from transformers import AutoProcessor, AutoModelForZeroShotObjectDetection

from zhixing.core.agent.interfaces import BasePerception
from zhixing.core.agent.protocol import PerceptionResult, PerceptionInput
# from zhixing.utils.registry import register_perception
from zhixing.core.factory import PluginRegistry


# @register_perception("som_perception")
@PluginRegistry.register(namespace="agent.perception", name="som_perception")
class SetOfMarksPerception(BasePerception):
    """
    Set-of-Marks: GroundingDINO 
    """
    def __init__(self, 
                 model_id="IDEA-Research/grounding-dino-tiny",
                 device="cpu",
                 confidence_threshold=0.35,
                 text_threshold=0.25,
                 detection_method="local_dino",
                 **kwargs):
        
        self.detection_method = detection_method
        self.device = device
        self.box_threshold = confidence_threshold
        self.text_threshold = text_threshold
        self.model = None
        self.processor = None
        super().__init__()

        if self.detection_method == "local_dino":
            try:
                start_time = time.time()
                self.logger.info(f"Loading GroundingDINO model: {model_id} onto {self.device.upper()}...")
                
                self.processor = AutoProcessor.from_pretrained(model_id)
                self.model = AutoModelForZeroShotObjectDetection.from_pretrained(model_id).to(self.device)
                self.model.eval()
                
                self.logger.info(f"GroundingDINO loaded successfully in {time.time() - start_time:.2f}s.")
            except Exception as e:
                self.logger.error(f"Failed to load GroundingDINO model ({model_id}): {e}", exc_info=True)
                self.detection_method = "failed"
        else:
            self.logger.info(f"SoM Perception initialized with method: {self.detection_method}")

    def perceive(self, perception_input: PerceptionInput) -> PerceptionResult:
        screenshot_path = perception_input.screenshot_path
        width = perception_input.width
        height = perception_input.height
        
        self.logger.info(f"Analyzing UI elements via GroundingDINO: {os.path.basename(screenshot_path)}")

        try:
            image = Image.open(screenshot_path).convert("RGB")
            width, height = image.size
        except Exception as e:
            self.logger.warning(f"Failed to read local screenshot at {screenshot_path}. Returning empty result. Error: {e}")
            return self._empty_result(screenshot_path, width, height)

        elements = []
        marked_image = image

        if self.detection_method == "local_dino" and self.model:
            try:
                inference_start = time.time()
                elements, marked_image = self._run_grounding_dino(image)
                self.logger.debug(f"GroundingDINO inference completed in {time.time() - inference_start:.2f}s.")
            except Exception as e:
                self.logger.error(f"GroundingDINO inference crashed: {e}", exc_info=True)
        else:
            self.logger.warning("Model is not ready or failed to load. Skipping GroundingDINO detection.")

        dir_name = os.path.dirname(screenshot_path)
        base_name = os.path.splitext(os.path.basename(screenshot_path))[0]
        marked_path = os.path.join(dir_name, f"{base_name}_som.png")

        try:
            marked_image.save(marked_path)
            self.logger.debug(f"SoM marked image saved to: {marked_path}")
        except Exception as e:
            self.logger.warning(f"Failed to save the SoM marked image to disk: {e}")
            marked_path = screenshot_path 

        # Prompt
        prompt_text = self._get_prompt_context(elements)
        self.logger.debug(f"Generated SoM Prompt:\n{prompt_text}")

        self.logger.info(f"SoM detection finished. Found {len(elements)} actionable UI elements.")

        return PerceptionResult(
            mode="set_of_marks",
            original_screenshot_path=screenshot_path,
            elements=elements,
            metadata={"width": width, "height": height},
            visual_representations=[marked_path],
            marked_screenshot_path=marked_path,
            prompt_representation=prompt_text
        )

    def _run_grounding_dino(self, image):
        """
        Run GroundingDINO
        """
        text_prompt = "icon. text. button. input box."
        
        inputs = self.processor(images=image, text=text_prompt, return_tensors="pt").to(self.device)

        with torch.no_grad():
            outputs = self.model(**inputs)

        target_sizes = torch.Tensor([image.size[::-1]]).to(self.device)
        
        try:
            results = self.processor.post_process_grounded_object_detection(
                outputs,
                inputs.input_ids,
                text_threshold=self.text_threshold,
                target_sizes=target_sizes
            )[0]
        except AttributeError:
            raise

        draw = ImageDraw.Draw(image)
        try:
            font = ImageFont.load_default()
        except Exception:
            font = None

        elements = []
        boxes = results["boxes"]
        scores = results["scores"]
        
        if "phrases" in results:
            labels = results["phrases"]
        elif "labels" in results:
            labels = results["labels"]
        else:
            labels = ["unknown"] * len(boxes)
        ignored_count = 0
        for idx, (box, score, label) in enumerate(zip(boxes, scores, labels)):
            box = box.cpu().numpy()
            score = score.item()
            
            x1, y1, x2, y2 = map(int, box)
            
            if (x2-x1) < 10 or (y2-y1) < 10:
                ignored_count += 1
                continue

            tag_id = idx + 1

            draw.rectangle([x1, y1, x2, y2], outline="red", width=3)
            
            tag_w, tag_h = 25, 20
            draw.rectangle([x1, y1, x1 + tag_w, y1 + tag_h], fill="red")
            draw.text((x1 + 5, y1), str(tag_id), fill="white", font=font)

            center_x = int((x1 + x2) / 2)
            center_y = int((y1 + y2) / 2)
            
            label_text = label if isinstance(label, str) else "ui_element"

            elements.append({
                "index": tag_id,
                "text": label_text,
                "score": score,
                "coordinates": [center_x, center_y],
                "bbox": [x1, y1, x2, y2]
            })

        if ignored_count > 0:
            self.logger.debug(f"Filtered out {ignored_count} elements because their bounding boxes were too small (<10px).")

        return elements, image

    def _get_prompt_context(self, elements: list) -> str:
        prompt = "--- Set-of-Marks (SoM) detected elements ---\n"
        prompt += "Refer to UI elements by their Tag ID (red box).\n"
        
        for e in elements[:60]:
            prompt += f"Tag ID: {e['index']} | Type: {e['text']}\n"
            
        prompt += "\nHint: Use 'element_id' in your action JSON.\n"
        return prompt

    def _empty_result(self, path, w, h):
        return PerceptionResult(
            mode="set_of_marks",
            original_screenshot_path=path,
            visual_representations=[path],
            elements=[],
            metadata={"width": w, "height": h},
            prompt_representation="No elements detected."
        )