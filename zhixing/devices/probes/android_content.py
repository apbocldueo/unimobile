"""Task-independent snapshots and deltas for Android content providers."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_CONTENT_URI = re.compile(r"^content://[A-Za-z0-9._/-]+$")
_COLUMN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass(frozen=True)
class AndroidContentSnapshot:
    """Represent one Android content-provider state snapshot."""

    ids: frozenset[str]
    raw_row_count: int


@dataclass(frozen=True)
class AndroidContentDelta:
    """Represent content-provider rows changed between two snapshots."""

    added_ids: tuple[str, ...]
    removed_ids: tuple[str, ...]

    @property
    def has_additions(self) -> bool:
        """Return whether the run created at least one provider row.

        Args:
            None.

        Raises:
            None.

        Returns:
            bool: True only when one or more identifiers were added.
        """
        return bool(self.added_ids)


@dataclass(frozen=True)
class AndroidContentProbe:
    """Query configurable Android content-provider state outside the Kernel."""

    uri: str = "content://media/external/images/media"
    id_column: str = "_id"

    def __post_init__(self) -> None:
        """Reject unsafe probe configuration before issuing a shell command.

        Args:
            None.

        Raises:
            ValueError: URI or column contains unsupported command syntax.

        Returns:
            None.
        """
        if not _CONTENT_URI.fullmatch(self.uri):
            raise ValueError("Android content probe URI is invalid")
        if not _COLUMN.fullmatch(self.id_column):
            raise ValueError("Android content probe column is invalid")

    def snapshot(self, device: Any) -> AndroidContentSnapshot:
        """Capture the current set of content-provider identifiers.

        Args:
            device (Any): AndroidDevice-compatible object exposing ``shell``.

        Raises:
            RuntimeError: The Android content query fails.

        Returns:
            AndroidContentSnapshot: Immutable identifier set and row count.
        """
        command = (
            f"content query --uri {self.uri} "
            f"--projection {self.id_column}"
        )
        result = device.shell(command)
        if int(getattr(result, "exit_code", 1)) != 0:
            raise RuntimeError("Android content query failed")
        output = str(getattr(result, "output", "") or "")
        ids = frozenset(
            match.group(1)
            for match in re.finditer(
                rf"(?:^|[\s,]){re.escape(self.id_column)}=([^,\s]+)",
                output,
            )
        )
        row_count = sum(
            1 for line in output.splitlines() if line.strip().startswith("Row:")
        )
        return AndroidContentSnapshot(ids=ids, raw_row_count=row_count)

    def diff(
        self,
        before: AndroidContentSnapshot,
        after: AndroidContentSnapshot,
    ) -> AndroidContentDelta:
        """Compute a deterministic content-provider state delta.

        Args:
            before (AndroidContentSnapshot): Earlier provider state.
            after (AndroidContentSnapshot): Later provider state.

        Raises:
            None.

        Returns:
            AndroidContentDelta: Sorted added and removed identifiers.
        """
        return AndroidContentDelta(
            added_ids=tuple(sorted(after.ids - before.ids)),
            removed_ids=tuple(sorted(before.ids - after.ids)),
        )


__all__ = [
    "AndroidContentDelta",
    "AndroidContentProbe",
    "AndroidContentSnapshot",
]
