"""Private durable evidence namespaces for Studio Benchmark execution."""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .benchmark_errors import StudioBenchmarkStorageError


@dataclass(frozen=True)
class StudioBenchmarkEvidenceNamespace:
    """One Experiment-scoped private evidence directory and logical reference."""

    experiment_id: str
    root: Path
    runtime_root: Path
    logical_reference: str


class LocalStudioBenchmarkEvidenceStore:
    """Database-adjacent permanent evidence store with explicit preflight."""

    def __init__(
        self,
        root: str | Path,
        *,
        minimum_free_bytes: int = 16 * 1024 * 1024,
    ) -> None:
        """Configure a private permanent Benchmark evidence root.

        Args:
            root: Explicit server-owned storage directory.
            minimum_free_bytes: Minimum free capacity required before execution.

        Raises:
            ValueError: Capacity threshold is negative.

        Returns:
            None.
        """
        if minimum_free_bytes < 0:
            raise ValueError("minimum_free_bytes must not be negative")
        self.root = Path(root).expanduser().resolve()
        self.minimum_free_bytes = minimum_free_bytes

    def preflight(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkEvidenceNamespace:
        """Verify capacity/writability and allocate one permanent namespace.

        Args:
            experiment_id: Stable opaque Experiment identity.

        Raises:
            StudioBenchmarkStorageError: Storage is unavailable or too small.

        Returns:
            Ready private namespace containing no public host path.
        """
        try:
            self.root.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(self.root).free
            if free < self.minimum_free_bytes:
                raise OSError("insufficient free capacity")
            namespace_root = self.root / experiment_id
            runtime_root = namespace_root / "runtime"
            runtime_root.mkdir(parents=True, exist_ok=True)
            probe = namespace_root / ".write-probe"
            descriptor = os.open(
                probe,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
            os.close(descriptor)
            probe.unlink()
        except OSError as error:
            raise StudioBenchmarkStorageError(
                "benchmark.evidence.preflight_failed",
                "Benchmark evidence storage is unavailable",
            ) from error
        return StudioBenchmarkEvidenceNamespace(
            experiment_id=experiment_id,
            root=namespace_root,
            runtime_root=runtime_root,
            logical_reference=f"benchmark-evidence://{experiment_id}",
        )


__all__ = [
    "LocalStudioBenchmarkEvidenceStore",
    "StudioBenchmarkEvidenceNamespace",
]
