"""Launch the local Studio UI/API; explicit serve/replay-import retain the backend CLI."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
from typing import Mapping, Sequence
from urllib.error import URLError
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parent


class LaunchError(Exception):
    """Safe, actionable startup failure without private configuration values."""


def parser() -> argparse.ArgumentParser:
    """Return development options; explicit backend commands bypass this parser."""
    result = argparse.ArgumentParser(description="一条命令启动 ZhiXing Studio 前后端")
    result.add_argument("--secrets", type=Path, help="本地密钥 YAML 文件")
    result.add_argument("--device-profile-config", type=Path, help="本地设备 Profile JSON 文件")
    result.add_argument("--database", type=Path, help="可选独立数据库；默认沿用项目工作区")
    result.add_argument("--backend-port", type=int, default=8765)
    result.add_argument("--frontend-port", type=int, default=5173)
    result.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    result.add_argument("--check", action="store_true", help="只检查配置、依赖和端口，不启动服务")
    return result


def local_path(path: Path, root: Path) -> Path:
    """Resolve a launcher path independently of the caller's working directory.

    Args:
        path: Explicit, environment, or conventional path.
        root: Repository root.
    Returns:
        Expanded absolute path without reading the file.
    """
    expanded = path.expanduser()
    return expanded if expanded.is_absolute() else root / expanded


def configuration_path(explicit: Path | None, environment: Mapping[str, str],
                       key: str, defaults: Sequence[str], root: Path) -> Path | None:
    """Choose CLI > environment > first existing conventional configuration.

    Args:
        explicit: Optional CLI path; invalid paths must never silently fall back.
        environment: Process environment containing optional path overrides.
        key: Existing backend environment variable name.
        defaults: Ordered repository-relative filenames.
        root: Fixed repository workspace.
    Returns:
        Selected path, or None when no configuration was supplied or found.
    """
    supplied = explicit or environment.get(key, "").strip()
    if supplied:
        return local_path(Path(supplied), root)
    return next((root / name for name in defaults if (root / name).exists()), None)


def check_dependencies(root: Path) -> str:
    """Check prerequisites without installing dependencies.

    Args:
        root: Repository root with the Studio dependency installation.
    Raises:
        LaunchError: Required Python/Node/Vite dependencies are missing.
    Returns:
        Absolute Node executable, used directly without an npm shell.
    """
    if sys.version_info < (3, 10) or any(
        importlib.util.find_spec(module) is None for module in ("pydantic", "yaml", "PIL")
    ):
        raise LaunchError('请使用 Python 3.10+，激活 unimobile 后运行：python -m pip install -e ".[openai,dev]"')
    node = shutil.which("node")
    if node is None:
        raise LaunchError("缺少 Node.js，请先安装 Node.js 22.12+。")
    try:
        result = subprocess.run([node, "--version"], capture_output=True, text=True, timeout=5, check=True)
    except (OSError, subprocess.SubprocessError) as error:
        raise LaunchError("无法检查 Node.js，请确认 node --version 能正常执行。") from error
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)\s*", result.stdout)
    if match is None or tuple(map(int, match.groups())) < (22, 12, 0):
        raise LaunchError("Node.js 版本过旧，需要 22.12+；升级后在 studio 目录运行 npm ci。")
    if not (root / "studio/node_modules/vite/bin/vite.js").is_file():
        raise LaunchError("缺少前端依赖，请先在 studio 目录运行 npm ci。")
    return node


def validate_configuration(secrets: Path | None, profiles: Path | None) -> None:
    """Use existing strict loaders, printing presence without private values.

    Args:
        secrets: Selected secret mapping, or no configuration.
        profiles: Selected device profile file, or no configuration.
    Raises:
        LaunchError: Existing loaders reject dependencies or configuration.
    Returns:
        None. No ADB connection, model call, or configuration write is performed.
    """
    try:
        from zhixing.studio.device_profiles import load_android_device_profiles
        from zhixing.studio.secrets import load_studio_secrets

        secret_map = load_studio_secrets(secrets)
        resolver = load_android_device_profiles(profiles)
    except ImportError as error:
        raise LaunchError('后端依赖不完整，请运行：python -m pip install -e ".[openai,dev]"') from error
    except (ValueError, OSError) as error:
        # Parser exception bodies may contain private input; never print them.
        raise LaunchError("本地密钥或设备配置无法加载，请检查文件路径和格式；不会回退到其他配置。") from error
    print(f"模型密钥：{'已加载配置（未测试接口连接）' if secret_map else '未加载；可编辑 Agent，运行前需配置密钥'}", flush=True)
    print(f"设备配置：{'已加载（未检查在线状态）' if resolver.safe_profiles() else '未加载；可编辑 Agent，运行前需配置设备'}", flush=True)
    if secrets is None:
        print("  密钥文件：项目根目录 secrets.local.yaml 或 secrets.yaml；格式见 secrets.example.yaml。", flush=True)
    if profiles is None:
        print("  设备文件：studio/device-profiles.json；格式见 examples/device-profiles.example.json。", flush=True)


def check_ports(ports: Sequence[int]) -> None:
    """Check loopback port availability without touching existing processes.

    Args:
        ports: Distinct backend and frontend ports.
    Raises:
        LaunchError: Port is invalid, duplicated, occupied, or inaccessible.
    Returns:
        None when ports can currently be bound.
    """
    if len(set(ports)) != len(ports) or any(not 1 <= port <= 65535 for port in ports):
        raise LaunchError("前后端端口必须不同，且位于 1–65535。")
    for port in ports:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            # Match the server's restart behavior; TIME_WAIT is not a live owner.
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                listener.bind(("127.0.0.1", port))
            except OSError as error:
                raise LaunchError(f"端口 {port} 被占用或无法监听。请先在旧服务终端按 Ctrl+C，或指定 --backend-port / --frontend-port。不会关闭已有进程。") from error


def spawn(command: Sequence[str], cwd: Path, environment: Mapping[str, str]) -> subprocess.Popen:
    """Start an owned process group with inherited terminal output.

    Args:
        command: Argument vector, never interpreted by a shell.
        cwd: Repository or frontend working directory.
        environment: Child-only environment with explicit API proxy settings.
    Raises:
        OSError: Creation fails; caller cleans up already-created children.
    Returns:
        Owned child process handle.
    """
    return subprocess.Popen(
        list(command), cwd=cwd, env=dict(environment),
        start_new_session=os.name == "posix",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
    )


def stop_children(children: Sequence[subprocess.Popen]) -> None:
    """Stop owned groups, including descendants, with a bounded graceful wait.

    Args:
        children: Successfully spawned handles, including exited group leaders.
    Returns:
        None after owned processes have been reaped.
    """
    for child in reversed(children):
        try:
            if os.name == "posix":
                os.killpg(child.pid, signal.SIGTERM)
            elif child.poll() is None:
                subprocess.run(["taskkill", "/PID", str(child.pid), "/T", "/F"], capture_output=True, timeout=5)
        except (ProcessLookupError, subprocess.SubprocessError):
            pass
    deadline = time.monotonic() + 5
    for child in children:
        try:
            child.wait(timeout=max(0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            pass
    for child in children:
        try:
            if os.name == "posix":
                os.killpg(child.pid, signal.SIGKILL)
            elif child.poll() is None:
                child.kill()
        except ProcessLookupError:
            pass
        child.wait()


def ensure_children_alive(children: Sequence[subprocess.Popen]) -> None:
    """Reject unexpected service exit, even when the child's exit code is zero.

    Args:
        children: Backend then frontend handles.
    Raises:
        LaunchError: Any service exited.
    Returns:
        None while all children are running.
    """
    for name, child in zip(("后端", "前端"), children):
        code = child.poll()
        if code is not None:
            raise LaunchError(f"{name}已退出（退出码 {code}），请查看上方服务日志。")


def wait_for_services(children: Sequence[subprocess.Popen], api_url: str,
                      ui_url: str, timeout: float = 45) -> None:
    """Wait for serving independently of execution readiness (ready=false is valid).

    Args:
        children: Owned services checked between probes.
        api_url: Loopback API base URL.
        ui_url: Loopback Vite URL.
        timeout: Total bounded startup window in seconds.
    Raises:
        LaunchError: Timeout, incompatible API, or child exit.
    Returns:
        None when both services respond; never invokes device or model probes.
    """
    opener = build_opener(ProxyHandler({}))
    pending = [api_url + "/studio/runtime-readiness", ui_url]
    deadline = time.monotonic() + timeout
    while pending and time.monotonic() < deadline:
        ensure_children_alive(children)
        try:
            with opener.open(pending[0], timeout=1) as response:
                body = response.read(1024 * 1024)
                if pending[0].startswith(api_url):
                    payload = json.loads(body)
                    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1 or not isinstance(payload.get("ready"), bool):
                        raise LaunchError("后端端口返回了不兼容的服务，请检查端口设置。")
                if response.status == 200:
                    pending.pop(0)
        except (URLError, OSError, ValueError):
            pass
        if pending:
            time.sleep(0.15)
    if pending:
        raise LaunchError("服务启动超时，请查看上方日志；本次启动的服务将自动关闭。")
    ensure_children_alive(children)


def launch(args: argparse.Namespace, root: Path = ROOT) -> int:
    """Preflight and supervise the stack using the active Python environment.

    Args:
        args: Parsed development options.
        root: Fixed repository root, injectable for isolated tests.
    Raises:
        LaunchError: Configuration, dependency, port, or startup failure.
        OSError: Host process operation fails.
    Returns:
        Zero for checks or deliberate interruption; always stops owned children.
    """
    environment = dict(os.environ)
    node = check_dependencies(root)
    secrets = configuration_path(args.secrets, environment, "ZHIXING_STUDIO_SECRETS", ("secrets.local.yaml", "secrets.yaml"), root)
    profiles = configuration_path(args.device_profile_config, environment, "ZHIXING_STUDIO_DEVICE_PROFILE_CONFIG", ("studio/device-profiles.json",), root)
    validate_configuration(secrets, profiles)
    check_ports((args.backend_port, args.frontend_port))
    if args.check:
        print("启动检查通过；尚未启动服务，也未连接设备或模型。", flush=True)
        return 0
    api_url = f"http://127.0.0.1:{args.backend_port}"
    ui_url = f"http://127.0.0.1:{args.frontend_port}"
    backend = [sys.executable, "-m", "zhixing.studio", "serve", "--host", "127.0.0.1", "--port", str(args.backend_port), "--frontend-port", str(args.frontend_port), "--workspace", str(root)]
    for flag, path in (("--secrets", secrets), ("--device-profile-config", profiles), ("--database", args.database)):
        if path is not None:
            backend.extend([flag, str(local_path(path, root))])
    frontend = [node, str(root / "studio/node_modules/vite/bin/vite.js"), "--host", "127.0.0.1", "--port", str(args.frontend_port), "--strictPort"]
    # Override stale .env destinations only for this launcher's children.
    environment.update(ZHIXING_STUDIO_PROXY_TARGET=api_url, VITE_STUDIO_API_BASE="/zhixing-studio", PYTHONUNBUFFERED="1")
    children: list[subprocess.Popen] = []
    previous_handlers = {}

    def interrupted(_signum: int, _frame: object) -> None:
        """Route SIGINT/SIGTERM to the common owned-process cleanup path."""
        raise KeyboardInterrupt

    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, interrupted)
        print("正在启动前后端；按 Ctrl+C 一起关闭。", flush=True)
        children.append(spawn(backend, root, environment))
        children.append(spawn(frontend, root / "studio", environment))
        wait_for_services(children, api_url, ui_url)
        print(f"Studio 已启动：{ui_url}\n后端：{api_url}\n配置就绪不代表设备在线或模型连接已验证。", flush=True)
        if not args.no_browser:
            try:
                if not webbrowser.open(ui_url):
                    print("无法自动打开浏览器，请手动访问上面的地址。", flush=True)
            except webbrowser.Error:
                print("无法自动打开浏览器，请手动访问上面的地址。", flush=True)
        while True:
            ensure_children_alive(children)
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\n正在关闭本次启动的前后端…", flush=True)
        return 0
    finally:
        # Repeated Ctrl+C must not interrupt cleanup and leave servers behind.
        for signum in previous_handlers:
            signal.signal(signum, signal.SIG_IGN)
        try:
            stop_children(children)
        finally:
            for signum, handler in previous_handlers.items():
                signal.signal(signum, handler)


def main(argv: Sequence[str] | None = None) -> int:
    """Dispatch the dev launcher or preserve explicit backend CLI commands.

    Args:
        argv: Optional argument vector, defaulting to process arguments.
    Returns:
        Exit code; launcher failures omit private parser input.
    """
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] in {"serve", "replay-import"}:
        from zhixing.studio.__main__ import main as studio_main

        studio_main(arguments)
        return 0
    try:
        return launch(parser().parse_args(arguments))
    except LaunchError as error:
        print(f"启动未完成：{error}", file=sys.stderr)
        return 1
    except OSError:
        print("启动未完成：无法创建或管理本地服务进程，请检查执行权限。", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
