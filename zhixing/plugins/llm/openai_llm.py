import base64
import os
import logging
from typing import List, Optional, Tuple

from openai import OpenAI

from zhixing.core.llm.interfaces import BaseLLM
from zhixing.core.llm.usage import usage_from_openai_response
from zhixing.core.factory import PluginRegistry

@PluginRegistry.register(namespace="llm", name="openai_llm")
class OpenAILLM(BaseLLM):
    """
    LLM based on OpenAI format
    """
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: str = None,
        temperature: float = 0.1,
        max_tokens: int = 4096,
        request_timeout: float = 45.0,
        max_retries: int = 0,
        **kwargs,
    ):
        """Create a bounded OpenAI-compatible model client.

        Args:
            api_key (str): Runtime-only API credential.
            model (str): Model identifier.
            base_url (str): Optional OpenAI-compatible endpoint.
            temperature (float): Sampling temperature.
            max_tokens (int): Maximum generated tokens.
            request_timeout (float): Per-request timeout in seconds.
            max_retries (int): Transport retry count handled by the client.
            **kwargs (Any): Additional BaseLLM configuration.

        Raises:
            ValueError: Timeout or retry values are outside supported bounds.

        Returns:
            None: Initializes the bounded model client.
        """
        if not 1.0 <= float(request_timeout) <= 600.0:
            raise ValueError("request_timeout must be between 1 and 600 seconds")
        if not 0 <= int(max_retries) <= 10:
            raise ValueError("max_retries must be between 0 and 10")
        super().__init__(api_key=api_key, model=model, base_url=base_url,
                         temperature=temperature, max_tokens=max_tokens, **kwargs)
        if not api_key:
            self.logger.warning("OpenAILLM initialized without api_key; requests will fail until configured")

        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            timeout=float(request_timeout),
            max_retries=int(max_retries),
        )

    def _generate_impl(self, prompt: str, images: List[str] = None) -> Tuple[str, Optional[dict]]:
        self.logger.debug("chat.completions model=%s", self.model)
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
            text = response.choices[0].message.content or ""
            usage = usage_from_openai_response(getattr(response, "usage", None))
            return text, usage
        except Exception as e:
            self.logger.error(f"OpenAILLM call failed: {e}")
            return "", None


    def _encode_image(self, image_path: str) -> str:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
