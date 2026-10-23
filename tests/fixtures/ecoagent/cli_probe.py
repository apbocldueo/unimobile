"""Execute the complete official CLI against external ADB/HTTP/input fixtures only."""

import base64
import builtins
import io
import json
from pathlib import Path
import runpy
import shlex
import socket
import subprocess
import sys
import time
from types import SimpleNamespace


def main():
    """Run the real module imports and original main under fixture transports.

    Raises:
        AssertionError: A request/command is unsupported or completion differs.
        Exception: Unrepaired official entry fails as expected by its caller.
    Returns:
        None: Print bounded proof metadata only.
    """
    root = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(root))
    commands, requests = [], []
    responses = iter(('0', 'fixture task'))
    builtins.input = lambda prompt='': next(responses)
    time.sleep = lambda seconds: None
    image = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')

    def denied(*args, **kwargs):
        """Deny real network. Args: args,kwargs: Socket call. Raises: AssertionError: Any access. Returns: None."""
        raise AssertionError('Real network is forbidden in the CLI fixture')

    socket.socket.connect = denied

    def adb(command, **kwargs):
        """Simulate transport only. Args: command,kwargs: Source request. Returns: object: Status/pixels."""
        words = shlex.split(command) if isinstance(command, str) else list(command)
        commands.append(words)
        assert words[0] == 'adb', words
        if words[1:] == ['devices']:
            return SimpleNamespace(returncode=0, stdout='List of devices attached\nfixture-target\tdevice\n')
        if words[1] == 'pull':
            Path(words[-1]).write_bytes(image)
        return SimpleNamespace(returncode=0, stdout='')

    def post(url, json, **kwargs):
        """Simulate the official models via source HTTP bodies. Args: url,json,kwargs: Request. Returns: object: Reply."""
        requests.append(json)
        content = json['messages'][0]['content']
        if json['model'] == 'gpt-4o':
            value = '```json\n' + __import__('json').dumps({'1': {'step':'INPUT [hi]', 'expectation':'text'},
                '2': {'step':'TAP Save','expectation':'saved'}}) + '\n```'
        elif json['model'] == 'ui-tars':
            value = "Action: click(point='<point>10 20</point>')"
        else:
            value = 'matches' if len(content)==3 else 'screen description'
        body = {'choices':[{'message':{'content':value}}], 'usage':{'total_tokens':10}}
        return SimpleNamespace(ok=True, json=lambda: body)

    subprocess.run = adb
    sys.modules['requests'] = SimpleNamespace(post=post)
    sys.argv = [str(root/'run.py')]
    runpy.run_path(str(root/'run.py'), run_name='__main__')
    assert any(words[-4:] == ['input','tap','10','20'] for words in commands)
    assert len(requests) == 6
    print('official-cli:' + json.dumps({'completed':True,'model_requests':len(requests),'real_effects':False}))


if __name__ == '__main__':
    main()
