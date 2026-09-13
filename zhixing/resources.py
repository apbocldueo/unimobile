"""Cwd-independent access to package-owned ZhiXing resources."""

from __future__ import annotations

import os
from contextlib import contextmanager
from importlib.resources import as_file, files
from pathlib import Path
from typing import Iterator


class ZhiXingResourceError(FileNotFoundError):
    """Raised when neither an explicit file nor a packaged resource exists."""


def _explicit_file(value: str | os.PathLike[str]) -> Path | None:
    candidate = Path(value).expanduser()
    return candidate if candidate.is_file() else None


def _packaged_prompt(name: str):
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ZhiXingResourceError(f"Prompt resource not found: {name!r}")
    resource = files("zhixing.prompts").joinpath(name)
    if not resource.is_file():
        raise ZhiXingResourceError(f"Prompt resource not found: {name!r}")
    return resource


def read_prompt(name_or_path: str | os.PathLike[str]) -> str:
    """Read an explicit prompt file, otherwise a named built-in prompt.

    Existing caller-selected files take precedence. A missing value containing
    path separators is not searched relative to the repository or cwd.
    """

    explicit = _explicit_file(name_or_path)
    if explicit is not None:
        return explicit.read_text(encoding="utf-8")
    return _packaged_prompt(os.fspath(name_or_path)).read_text(encoding="utf-8")


@contextmanager
def prompt_path(name_or_path: str | os.PathLike[str]) -> Iterator[Path]:
    """Yield a physical path for a prompt for APIs that genuinely require one."""

    explicit = _explicit_file(name_or_path)
    if explicit is not None:
        yield explicit.resolve()
        return
    with as_file(_packaged_prompt(os.fspath(name_or_path))) as materialized:
        yield materialized
