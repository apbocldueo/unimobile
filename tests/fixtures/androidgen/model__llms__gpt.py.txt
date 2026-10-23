from openai import OpenAI
import os
import backoff
import time
from openai import (
    APIConnectionError,
    APIError,
    RateLimitError
)

import base64
from dotenv import load_dotenv

config_path = os.path.join(os.path.dirname(__file__), '.token')
load_dotenv(config_path)

def handle_giveup(details):
    print(
        "Backing off {wait:0.1f} seconds afters {tries} tries calling fzunction {target} with args {args} and kwargs {kwargs}"
        .format(**details))

def handle_backoff(details):
    exc = details.get("exception")
    if exc:
        print(str(exc))

class OpenaiEngine:
    def __init__(
            self,
            model='gpt-4o-2024-08-06',
            rate_limit=-1,
            temperature=0.5,
            top_p=0.5,
            **kwargs,
    ) -> None:
        """Init an OpenAI GPT/Codex engine

        Args:
            model (_type_, optional): Model family. Defaults to None.
            rate_limit (int, optional): Max number of requests per minute. Defaults to -1.
        """
        self.temperature = temperature
        self.top_p = top_p
        self.model = model
        # convert rate limit to minmum request interval
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        self.engine = OpenAI(api_key=os.getenv('OPENAI_TOKEN'))
        
    def run_connection_test(self):
        response = self.engine.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=512,
            temperature=0.1
        )
        print(response.choices[0].message.content)
        
    def encode_image(self, image_path):
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')

    @backoff.on_exception(
        backoff.constant,
        (APIError, RateLimitError, APIConnectionError),
        on_backoff=handle_backoff,
        on_giveup=handle_giveup,
        interval=0.1
    )
    def generate(self, prompt, system_prompt=None, history=[], **kwargs):
        message = []
        if system_prompt:
            message.append(
                {
                    "role": "system",
                    "content": [{"type": "text", "text": system_prompt}]
                }
            )
        
        if history:
            for rec in history:
                role, content = rec["role"], rec["content"]
                cnt = []
                if "text" in content:
                    cnt.append(
                        {
                            "type": "text",
                            "text": content["text"]
                        }
                    )
                    
                if "image_url" in content:
                    cnt.append(
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{self.encode_image(content['image_url'])}",
                                "detail": "high"
                            }
                        }
                    )
                        
                message.append(
                    {
                        "role": role,
                        "content": cnt
                    }    
                )
        
        if type(prompt) == str:
            message.append(
                {
                    "role": "user",
                    "content": [{"type": "text", "text": prompt}]
                }
            )
        else:
            cnt = []
            if "text" in prompt:
                cnt.append(
                    {
                        "type": "text",
                        "text": prompt["text"]
                    }
                )
            if "image_url" in prompt:
                cnt.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{self.encode_image(prompt['image_url'])}",
                            "detail": "high"
                        }
                    }
                )
            message.append(
                {
                    "role": "user",
                    "content": cnt
                }
            )
                    
        response = self.engine.chat.completions.create(
            model=self.model,
            messages=message,
            max_tokens=4096,
            temperature=self.temperature,
            top_p=self.top_p,
            **kwargs,
        )
        
        return response.choices[0].message.content
    