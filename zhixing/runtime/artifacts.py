"""Run-scoped artifact allocation for device observations and actions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


_RUN_ID = re.compile(r"^[A-Za-z0-9_.-]+$")


class ArtifactStoreError(RuntimeError):
    """Raised when a run artifact cannot be allocated or persisted."""


@dataclass(frozen=True)
class ObservationArtifactPaths:
    """Host paths and stable references for one device observation."""

    screenshot_path: Path
    screenshot_reference: str
    ui_path: Path | None = None
    ui_reference: str | None = None


class RunArtifactStore:
    """Allocate verified artifacts inside one isolated run namespace."""

    def __init__(self, root: str | Path, run_id: str) -> None:
        """Create a writable artifact namespace.

        Args:
            root (str | Path): Caller-selected artifact root.
            run_id (str): Stable run identity used as the namespace name.

        Raises:
            ValueError: The run ID is unsafe.
            ArtifactStoreError: The namespace cannot be created or written.

        Returns:
            None: Initializes and verifies the namespace.
        """
        if not _RUN_ID.fullmatch(run_id):
            raise ValueError("run_id contains unsupported artifact path characters")
        self.root = Path(root).expanduser().resolve()
        self.run_id = run_id
        self.namespace = self.root / run_id
        try:
            self.namespace.mkdir(parents=True, exist_ok=False)
            probe = self.namespace / ".write-probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except FileExistsError:
            raise ArtifactStoreError(f"Artifact namespace already exists: {self.namespace}")
        except OSError as error:
            raise ArtifactStoreError(
                f"Artifact namespace is not writable: {self.namespace}: {error}"
            ) from error
        self._observation_sequence = 0
        self._action_sequence = 0

    def allocate_observation(
        self,
        interaction_step: int,
        *,
        include_ui_tree: bool,
    ) -> ObservationArtifactPaths:
        """Allocate paths for one observation without creating fake artifacts.

        Args:
            interaction_step (int): Zero-based physical interaction position.
            include_ui_tree (bool): Whether to allocate a UI XML path.

        Raises:
            ArtifactStoreError: The interaction directory cannot be created.

        Returns:
            ObservationArtifactPaths: Host paths and root-relative references.
        """
        sequence = self._observation_sequence
        self._observation_sequence += 1
        directory = self.namespace / f"interaction-{int(interaction_step):04d}"
        try:
            directory.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise ArtifactStoreError(f"Cannot create artifact directory: {directory}") from error
        screenshot = directory / f"observation-{sequence:04d}.png"
        ui_path = directory / f"observation-{sequence:04d}.xml" if include_ui_tree else None
        return ObservationArtifactPaths(
            screenshot_path=screenshot,
            screenshot_reference=self.reference(screenshot),
            ui_path=ui_path,
            ui_reference=self.reference(ui_path) if ui_path is not None else None,
        )

    def write_action(
        self,
        interaction_step: int,
        payload: Mapping[str, Any],
    ) -> str:
        """Persist one safe action result as JSON.

        Args:
            interaction_step (int): Zero-based physical interaction position.
            payload (Mapping[str, Any]): Already sanitized action evidence.

        Raises:
            ArtifactStoreError: JSON serialization or atomic persistence fails.

        Returns:
            str: Root-relative artifact reference.
        """
        sequence = self._action_sequence
        self._action_sequence += 1
        directory = self.namespace / f"interaction-{int(interaction_step):04d}"
        path = directory / f"action-{sequence:04d}.json"
        self.write_json(path, payload)
        return self.reference(path)

    def write_manifest(self, payload: Mapping[str, Any]) -> str:
        """Persist the final run manifest.

        Args:
            payload (Mapping[str, Any]): Safe JSON-compatible run evidence.

        Raises:
            ArtifactStoreError: Manifest persistence fails.

        Returns:
            str: Root-relative manifest reference.
        """
        path = self.namespace / "manifest.json"
        self.write_json(path, payload)
        return self.reference(path)

    def write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        """Atomically persist JSON under this run namespace.

        Args:
            path (Path): Destination path inside the namespace.
            payload (Mapping[str, Any]): JSON-compatible data.

        Raises:
            ArtifactStoreError: Path escape, serialization, or write fails.

        Returns:
            None: The destination contains complete JSON.
        """
        destination = path.resolve()
        if self.namespace not in destination.parents:
            raise ArtifactStoreError("Artifact path escapes the run namespace")
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            temporary.replace(destination)
        except (OSError, TypeError, ValueError) as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ArtifactStoreError(f"Cannot persist artifact {destination}: {error}") from error

    def verify_file(self, path: str | Path, *, minimum_size: int = 1) -> None:
        """Verify that a service created a non-empty artifact.

        Args:
            path (str | Path): Host artifact path.
            minimum_size (int): Smallest accepted byte size.

        Raises:
            ArtifactStoreError: The artifact is missing, empty, or outside the namespace.

        Returns:
            None: The artifact is present and valid.
        """
        target = Path(path).resolve()
        if self.namespace not in target.parents:
            raise ArtifactStoreError("Artifact path escapes the run namespace")
        try:
            size = target.stat().st_size
        except OSError as error:
            raise ArtifactStoreError(f"Artifact is missing: {target}") from error
        if size < int(minimum_size):
            raise ArtifactStoreError(f"Artifact is too small: {target} ({size} bytes)")

    def reference(self, path: str | Path) -> str:
        """Return a root-relative stable artifact reference.

        Args:
            path (str | Path): Path inside the run namespace.

        Raises:
            ArtifactStoreError: The path is outside the configured root.

        Returns:
            str: POSIX-style reference including the run ID.
        """
        target = Path(path).resolve()
        try:
            return target.relative_to(self.root).as_posix()
        except ValueError as error:
            raise ArtifactStoreError(f"Artifact path is outside root: {target}") from error
