"""Lazy source-shaped EcoAgent HTTP requests with explicit bounded failure repairs."""

import base64
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from zhixing.core.factory import PluginRegistry
from zhixing.plugins.agent.ecoagent.types import EcoReply


def image_url(observation):
    """Encode source screenshot bytes using the original wire MIME label.

    Args:
        observation: DeviceObservation with an immutable screenshot artifact.
    Raises:
        OSError: Screenshot artifact is unavailable.
    Returns:
        str: Source-compatible data URL, with no pixel resizing or recompression.
    """
    return 'data:image/jpeg;base64,' + base64.b64encode(Path(observation.screenshot_path).read_bytes()).decode('ascii')


@PluginRegistry.register(namespace='llm', name='ecoagent_llm')
class EcoAgentLLM:
    """One transport implementation for the four explicitly bound request roles."""

    def __init__(self, api_key='', model=None, api_url=None, temperature=0.0,
                 max_tokens=None, max_attempts=None, request_timeout=60.0):
        """Retain public settings and runtime-resolved credentials without I/O.

        Args:
            api_key: Runtime-only cloud/local credential.
            model,api_url: Explicit model alias and complete chat-completions endpoint.
            temperature,max_tokens: Source request settings; None retains role defaults.
            max_attempts: Finite total attempts; None means cloud three, local one.
            request_timeout: Bound per HTTP request in seconds.
        Raises:
            ValueError: Numeric settings are invalid.
        Returns:
            None: No SDK import, request, config read or thread creation.
        """
        if (not 1 <= request_timeout <= 600 or max_attempts is not None and
                (type(max_attempts) is not int or not 1 <= max_attempts <= 5) or
                max_tokens is not None and (type(max_tokens) is not int or not 1 <= max_tokens <= 65536)):
            raise ValueError('Invalid EcoAgent transport settings')
        self._key, self.model, self.url = api_key, model, api_url
        self.temperature, self.max_tokens = temperature, max_tokens
        self.max_attempts, self.timeout = max_attempts, request_timeout

    def complete(self, operation, prompt, images):
        """Send exact ordered text/images without chat history, image detail or SDK defaults.

        Args:
            operation: planning, replanning, action, description or summary.
            prompt: Original selected source prompt.
            images: Ordered immutable DeviceObservations.
        Raises:
            ValueError: Operation is unknown.
            RuntimeError: Finite HTTP/JSON/reply attempts fail, without secret diagnostics.
        Returns:
            EcoReply: Text plus optional usage; no live response escapes.
        """
        if operation not in ('planning', 'replanning', 'action', 'description', 'summary'):
            raise ValueError('Unknown EcoAgent model operation')
        cloud = operation in ('planning', 'replanning')
        default_model = 'gpt-4o' if cloud else 'ui-tars' if operation == 'action' else 'DEVICE_OBSERVER'
        default_url = ('https://api.openai.com/v1/chat/completions' if cloud else
            'http://127.0.0.1:8801/v1/chat/completions' if operation == 'action' else
            'http://127.0.0.1:8800/v1/chat/completions')
        payload = {'model': self.model or default_model, 'temperature': self.temperature,
            'max_tokens': self.max_tokens or (2000 if cloud else 256), 'messages': [{'role': 'user',
            'content': [{'type': 'text', 'text': prompt}] + [{'type': 'image_url',
                'image_url': {'url': image_url(image)}} for image in images]}]}
        headers = {'Content-Type': 'application/json'}
        if self._key:
            headers['Authorization'] = 'Bearer ' + self._key
        attempts = self.max_attempts or (3 if cloud else 1)
        for index in range(attempts):
            try:
                request = Request(self.url or default_url, data=json.dumps(payload).encode(), headers=headers)
                with urlopen(request, timeout=self.timeout) as response:
                    body = json.load(response)
                text = body['choices'][0]['message']['content']
                if not isinstance(text, str):
                    raise ValueError('Model response content is not text')
                usage = body.get('usage') or {}
                return EcoReply(text, int(usage.get('total_tokens', 0)), int(usage.get('prompt_tokens', 0)),
                    int(usage.get('completion_tokens', 0)), bool(usage))
            except Exception:
                if index + 1 < attempts:
                    time.sleep(20 * 2 ** index)
        raise RuntimeError('EcoAgent model request exhausted its finite attempts') from None
