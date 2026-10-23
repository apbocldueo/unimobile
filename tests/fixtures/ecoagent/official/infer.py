# Copyright 2024 The android_world Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Some LLM inference interface."""

import abc
import base64
import io
import json
import os
import time
from typing import Any, Optional
import requests
import time
from config import load_config


ERROR_CALLING_LLM = 'Error calling LLM'


class Gpt4Wrapper():
  """OpenAI GPT4 wrapper.

  Attributes:
    openai_api_key: The class gets the OpenAI api key either explicitly, or
      through env variable in which case just leave this empty.
    max_retry: Max number of retries when some error happens.
    temperature: The temperature parameter in LLM to control result stability.
    model: GPT model to use based on if it is multimodal.
  """

  RETRY_WAITING_SECONDS = 20

  def __init__(
      self,
      model_name: str = None,
      max_retry: int = None,
      temperature: float = None,
      config_loader = None,
  ):
    # Load config if not provided
    if config_loader is None:
      config_loader = load_config()
    
    llm_config = config_loader.get_llm_config()
    
    # Use provided parameters or fall back to config values
    self.model = model_name or llm_config.get('model_name', 'gpt-4o')
    self.openai_api_key = config_loader.get_llm_api_key()
    self.api_url = llm_config.get('api_url', 'https://api.openai-hk.com/v1/chat/completions')
    
    if max_retry is None:
      max_retry = llm_config.get('max_retry', 3)
    if max_retry <= 0:
      max_retry = 3
      print('Max_retry must be positive. Reset it to 3')
    self.max_retry = min(max_retry, 5)
    
    if temperature is None:
      temperature = llm_config.get('temperature', 0.0)
    self.temperature = temperature

  def predict(
      self,
      text_prompt: str,
  ) -> tuple[str, Optional[bool], Any]:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {self.openai_api_key}',
    }

    payload = {
        'model': self.model,
        'temperature': self.temperature,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': text_prompt},
            ],
        }],
        'max_tokens': 2000,
    }

    counter = self.max_retry
    wait_seconds = self.RETRY_WAITING_SECONDS
    while counter > 0:
        try:
            start_time = time.time()
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
            )

            # Calculate and print transmitted data size
            json_data = json.dumps(payload)
            data_bytes = len(json_data.encode("utf-8"))
            if data_bytes < 1024:
                size_str = f"{data_bytes} B"
            elif data_bytes < 1024**2:
                size_str = f"{data_bytes/1024:.2f} KB"
            else:
                size_str = f"{data_bytes/1024/1024:.2f} MB"

            print(f"🚀 LLM transmission data size: {size_str}")
            elapsed_time = (time.time() - start_time) * 1000
            print(f'Elapsed time: {elapsed_time:.3f} ms')

            response_json = response.json()
            total_tokens = response_json.get('usage', {}).get('total_tokens', 0)
            print(total_tokens)

            if response.ok and 'choices' in response.json():
                return (
                    response.json()['choices'][0]['message']['content'],
                    None,
                    response,
                    total_tokens,
                )
            print(
                'Error calling OpenAI API with error message: '
                + response.json()['error']['message']
            )
            time.sleep(wait_seconds)
            wait_seconds *= 2

        except Exception as e:
            time.sleep(wait_seconds)
            wait_seconds *= 2
            counter -= 1
            print('Error calling LLM, will retry soon...')
            print(e)

    return "ERROR_CALLING_LLM", None, None

  def predict_mm(
    self,
    text_prompt: str,
    image_data_url: str,   # Modified: Input is a single data URL string
) -> tuple[str, Optional[bool], Any]:
    headers = {
        'Content-Type': 'application/json',
        'Authorization': f'Bearer {self.openai_api_key}',
    }

    payload = {
        'model': self.model,
        'temperature': self.temperature,
        'messages': [{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': text_prompt},
                {
                    'type': 'image_url',
                    'image_url': {
                        'url': image_data_url   # Pass data URL directly
                    },
                }
            ],
        }],
        'max_tokens': 2000,
    }

    counter = self.max_retry
    wait_seconds = self.RETRY_WAITING_SECONDS
    while counter > 0:
        try:
            start_time = time.time()
            response = requests.post(
                self.api_url,
                headers=headers,
                json=payload,
            )

            # Calculate and print transmitted data size
            json_data = json.dumps(payload)
            data_bytes = len(json_data.encode("utf-8"))
            if data_bytes < 1024:
                size_str = f"{data_bytes} B"
            elif data_bytes < 1024**2:
                size_str = f"{data_bytes/1024:.2f} KB"
            else:
                size_str = f"{data_bytes/1024/1024:.2f} MB"

            print(f"🚀 LLM transmission data size: {size_str}")
            elapsed_time = (time.time() - start_time) * 1000
            print(f'Elapsed time: {elapsed_time:.3f} ms')

            response_json = response.json()
            total_tokens = response_json.get('usage', {}).get('total_tokens', 0)
            print(total_tokens)

            if response.ok and 'choices' in response.json():
                return (
                    response.json()['choices'][0]['message']['content'],
                    None,
                    response,
                    total_tokens,
                )
            print(
                'Error calling OpenAI API with error message: '
                + response.json()['error']['message']
            )
            time.sleep(wait_seconds)
            wait_seconds *= 2

        except Exception as e:
            time.sleep(wait_seconds)
            wait_seconds *= 2
            counter -= 1
            print('Error calling LLM, will retry soon...')
            print(e)

    return "ERROR_CALLING_LLM", None, None
  
class SLMWrapper():
  """SLM wrapper.

  Attributes:
    temperature: The temperature parameter in LLM to control result stability.
    model: SLM to use based on if it is multimodal.
  """
  def __init__(
      self,
      model_name: str = None,
      max_retry: int = None,
      temperature: float = None,
      config_loader = None,
  ):
    # Load config if not provided
    if config_loader is None:
      config_loader = load_config()
    
    slm_config = config_loader.get_slm_config()
    
    # Use provided parameters or fall back to config values
    self.model_name = model_name or slm_config.get('model_name')
    self.api_url = slm_config.get('api_url')
    
    if max_retry is None:
      max_retry = slm_config.get('max_retry', 3)
    self.max_retry = max_retry
    
    if temperature is None:
      temperature = slm_config.get('temperature', 0.0)
    self.temperature = temperature
    self.max_tokens = slm_config.get('max_tokens', 256)

  def predict_mm(
      self,
      prompt: str,
      image_data_url: Optional[str] = None,  # Modified: Single Base64 data URL string
  ) -> tuple[str, Optional[bool], Any]:
    """Multimodal prediction using UI-TARS model."""

    payload = {
                "model": self.model_name,
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_data_url}},
                        ],
                    }
                ],
                "max_tokens": self.max_tokens,
                "temperature": self.temperature,
            }
    result = requests.post(self.api_url, json=payload).json()
    return result['choices'][0]['message']['content'], None, result

  def predict(
      self,
      text_prompt: str,
  ) -> tuple[str, Optional[bool], Any]:
    """Text-only prediction."""
    return self.predict_mm(text_prompt, None)