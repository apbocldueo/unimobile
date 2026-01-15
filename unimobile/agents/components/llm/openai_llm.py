import base64
import os
import logging
from typing import List

from openai import OpenAI

from unimobile.core.interfaces import BaseLLM
from unimobile.utils.registry import register_llm

logger = logging.getLogger(__name__)


@register_llm("openai_llm") 
class OpenAILLM(BaseLLM):
    """
    LLM based on OpenAI format
    """
    def __init__(self, api_key: str, base_url: str = None, model: str = "gpt-4o", temperature: float = 0.1, max_tokens: int = 4096):
        if not api_key:
            logger.warning("Please provided API Key")
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.model = model

    def generate(self, prompt: str, images: List[str] = None) -> str:
        logger.info(f"llm model is: {self.model}")
        messages = [
            {
                "role": "user",
                "content": [{"type": "text", "text": prompt}]
            }
        ]

        if images:
            for img_path in images:
                if img_path and os.path.exists(img_path):
                    try:
                        base64_image = self._encode_image(img_path)
                        messages[0]["content"].append({
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}",
                                "detail": "high"
                            }
                        })
                    except Exception as e:
                        logger.error(f"Image encoding failed {img_path}: {e}")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"OpenAILLM call failed: {e}")
            return ""


    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')