"""Tests for independent Android task side-effect evidence."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from zhixing.devices.probes import AndroidContentProbe


@dataclass(frozen=True)
class Result:
    """Minimal Android command result."""

    output: str
    error: str = ""
    exit_code: int = 0


class FakeShellDevice:
    """Return queued MediaStore query results."""

    def __init__(self, outputs: list[str]) -> None:
        """Store deterministic shell outputs.

        Args:
            outputs (list[str]): MediaStore query outputs.

        Raises:
            None.

        Returns:
            None.
        """
        self.outputs = list(outputs)
        self.commands: list[str] = []

    def shell(self, command: str) -> Result:
        """Return one queued command result.

        Args:
            command (str): Safe content query.

        Raises:
            IndexError: No queued result remains.

        Returns:
            Result: Successful fake command result.
        """
        self.commands.append(command)
        return Result(self.outputs.pop(0))


def test_media_probe_proves_new_image_by_state_delta() -> None:
    """Require an independently added MediaStore row for photo success.

    Args:
        None.

    Raises:
        AssertionError: Added and removed IDs are computed incorrectly.

    Returns:
        None.
    """
    device = FakeShellDevice(
        [
            "Row: 0 _id=4\nRow: 1 _id=8",
            "Row: 0 _id=4\nRow: 1 _id=8\nRow: 2 _id=12",
        ]
    )
    probe = AndroidContentProbe()
    before = probe.snapshot(device)
    after = probe.snapshot(device)
    delta = probe.diff(before, after)
    assert delta.has_additions
    assert delta.added_ids == ("12",)
    assert device.commands == [
        "content query --uri content://media/external/images/media --projection _id",
        "content query --uri content://media/external/images/media --projection _id",
    ]


def test_media_probe_rejects_shell_syntax_in_configuration() -> None:
    """Keep configurable probes outside Kernel without accepting shell injection.

    Args:
        None.

    Raises:
        AssertionError: Unsafe configuration is accepted.

    Returns:
        None.
    """
    with pytest.raises(ValueError, match="URI"):
        AndroidContentProbe(uri="content://media/images;rm")
    with pytest.raises(ValueError, match="column"):
        AndroidContentProbe(id_column="_id --where")
