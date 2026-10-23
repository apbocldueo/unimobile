import os
import backoff
import time
import requests
import json
from openai import (
    APIConnectionError,
    APIError,
    RateLimitError
)

def handle_giveup(details):
    print(
        "Backing off {wait:0.1f} seconds afters {tries} tries calling fzunction {target} with args {args} and kwargs {kwargs}"
        .format(**details))

def handle_backoff(details):
    exc = details.get("exception")
    if exc:
        print(str(exc))

class VllmEngine:
    def __init__(
            self,
            port=8000,
            rate_limit=-1,
            temperature=0.5,
            top_p=0.5,
            **kwargs,
    ) -> None:
        """Init an VLLM engine
        
        """
        self.temperature = temperature
        self.top_p = top_p
        self.url = f'http://127.0.0.1:{port}/v1/chat/completions'
        # convert rate limit to minmum request interval
        self.request_interval = 0 if rate_limit == -1 else 60.0 / rate_limit
        
        # Headers
        self.headers = {
            'accept': 'application/json',
            'Content-Type': 'application/json'
        }

    @backoff.on_exception(
        backoff.constant,
        (APIError, RateLimitError, APIConnectionError),
        on_backoff=handle_backoff,
        on_giveup=handle_giveup,
        interval=0.1
    )
    def generate(self, prompt, system_prompt=None, history=[], **kwargs):
        messages = []
        if system_prompt:
            messages.append(
                {
                    "role": "system",
                    "content": system_prompt
                }
            )
        
        if history:
            for rec in history:
                role, content = rec["role"], rec["content"]        
                messages.append(
                    {
                        "role": role,
                        "content": content["text"]
                    }    
                )
        
        if type(prompt) == str:
            messages.append(
                {
                    "role": "user",
                    "content": prompt
                }
            )
        else:
            messages.append(
                {
                    "role": "user",
                    "content": prompt['text']
                }
            )
            
        payload = {
            "model": "string",
            "messages": messages,
            "do_sample": True,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "n": 1,
            "max_tokens": 8192,
            "stream": False
        }
            
        response = requests.post(
            self.url, 
            headers=self.headers, 
            data=json.dumps(payload)
        )
        
        return response.json()['choices'][0]['message']['content']


if __name__ == '__main__':
    engine = VllmEngine()
    print(engine.generate("Hi"))
    