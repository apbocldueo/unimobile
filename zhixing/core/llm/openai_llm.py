import base64
import os
import logging
from typing import List

from openai import OpenAI

from zhixing.core.llm.base import BaseLLM
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="llm", name="openai_llm")
class OpenAILLM(BaseLLM):
    """
    LLM based on OpenAI format
    """
    def __init__(self, api_key: str, model: str = "gpt-4o", base_url: str = None, 
                 temperature: float = 0.1, max_tokens: int = 4096, **kwargs):
        if not api_key:
            self.logger.warning("Please provided API Key")
        super().__init__(api_key=api_key, model=model, base_url=base_url, 
                         temperature=temperature, max_tokens=max_tokens, **kwargs)
        
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate(self, prompt: str, images: List[str] = None) -> str:
        self.logger.info(f"llm model is: {self.model}")
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
                        self.logger.error(f"Image encoding failed {img_path}: {e}")

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=self.temperature
            )
            return response.choices[0].message.content
        except Exception as e:
            self.logger.error(f"OpenAILLM call failed: {e}")
            return ""


    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')