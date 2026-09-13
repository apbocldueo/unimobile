"""Android content-provider delta verifier for graph-composed task completion."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from zhixing.components import RuntimeContext
from zhixing.core.agent.protocol import ActionType, VerifierInput, VerifierResult
from zhixing.core.factory import PluginRegistry
from zhixing.devices.probes import AndroidContentProbe, AndroidContentSnapshot


@PluginRegistry.register(
    namespace="agent.verifier",
    name="android_content_delta_verifier",
)
class AndroidContentDeltaVerifier:
    """Verify task progress through a configurable Android content collection."""

    def __init__(
        self,
        uri: str = "content://media/external/images/media",
        id_column: str = "_id",
        minimum_added: int = 1,
        baseline_actions: Iterable[str] = ("start_app",),
        baseline_key: str = "android_content",
        **kwargs: Any,
    ) -> None:
        """Create a run-isolated content-delta verifier.

        Args:
            uri (str): Android content-provider URI to query.
            id_column (str): Stable row identity column.
            minimum_added (int): Added rows required for task completion.
            baseline_actions (Iterable[str]): Action types allowed to establish
                an implicit baseline when no caller baseline is supplied.
            baseline_key (str): Runtime metadata key for an optional baseline.
            **kwargs (Any): Forward-compatible component parameters.

        Raises:
            ValueError: Threshold, baseline key, or probe configuration is invalid.

        Returns:
            None: Initializes one stateful verifier instance for a single run.
        """
        del kwargs
        if int(minimum_added) < 1:
            raise ValueError("minimum_added must be at least 1")
        if not str(baseline_key).strip():
            raise ValueError("baseline_key must not be blank")
        self.probe = AndroidContentProbe(uri=uri, id_column=id_column)
        self.minimum_added = int(minimum_added)
        self.baseline_actions = frozenset(str(item) for item in baseline_actions)
        self.baseline_key = str(baseline_key)
        self._baseline: AndroidContentSnapshot | None = None
        self._run_id = ""

    def invoke(
        self,
        input: VerifierInput,
        runtime: RuntimeContext,
    ) -> VerifierResult:
        """Compare current Android content state with this run's baseline.

        Args:
            input (VerifierInput): Task, action, observations, and action result.
            runtime (RuntimeContext): Shared context containing the selected device.

        Raises:
            TypeError: Input or runtime device does not satisfy the component contract.
            RuntimeError: Android content-provider query fails.

        Returns:
            VerifierResult: Completion decision, retry feedback, and safe delta metadata.
        """
        if not isinstance(input, VerifierInput):
            raise TypeError("android_content_delta_verifier requires VerifierInput")
        device = runtime.device
        if device is None or not callable(getattr(device, "shell", None)):
            raise TypeError(
                "android_content_delta_verifier requires an Android shell-capable device"
            )
        if self._run_id != runtime.run_id:
            self._baseline = self._baseline_from_metadata(runtime.metadata)
            self._run_id = runtime.run_id
        current = self.probe.snapshot(device)
        action_type = input.action.type.value
        if self._baseline is None:
            if action_type not in self.baseline_actions:
                return VerifierResult(
                    is_success=False,
                    feedback=(
                        "No content baseline is available; execute a configured "
                        "baseline action before the task-changing action."
                    ),
                    should_retry=False,
                    metadata={
                        "task_completed": False,
                        "baseline_missing": True,
                        "action_type": action_type,
                    },
                )
            self._baseline = current
            return VerifierResult(
                is_success=False,
                feedback="Android content baseline established; continue the task.",
                should_retry=True,
                metadata={
                    "task_completed": False,
                    "baseline_captured": True,
                    "baseline_count": current.raw_row_count,
                },
            )
        delta = self.probe.diff(self._baseline, current)
        completed = len(delta.added_ids) >= self.minimum_added
        return VerifierResult(
            is_success=completed,
            feedback=(
                f"Android content delta satisfied with {len(delta.added_ids)} added row(s)."
                if completed
                else (
                    f"Android content delta has {len(delta.added_ids)} added row(s); "
                    f"{self.minimum_added} required."
                )
            ),
            score=1.0 if completed else 0.0,
            should_retry=not completed,
            metadata={
                "task_completed": completed,
                "added_ids": delta.added_ids,
                "removed_ids": delta.removed_ids,
                "minimum_added": self.minimum_added,
            },
        )

    def _baseline_from_metadata(
        self,
        metadata: Mapping[str, Any],
    ) -> AndroidContentSnapshot | None:
        """Load an optional caller-supplied baseline without task-specific logic.

        Args:
            metadata (Mapping[str, Any]): Runtime metadata containing baseline IDs.

        Raises:
            ValueError: Supplied baseline is not an iterable of scalar identifiers.

        Returns:
            AndroidContentSnapshot | None: Parsed baseline or None.
        """
        baselines = metadata.get("android_content_baselines")
        if not isinstance(baselines, Mapping) or self.baseline_key not in baselines:
            return None
        raw_ids = baselines[self.baseline_key]
        if isinstance(raw_ids, (str, bytes)) or not isinstance(raw_ids, Iterable):
            raise ValueError("android content baseline must be an iterable of IDs")
        ids = frozenset(str(item) for item in raw_ids)
        return AndroidContentSnapshot(ids=ids, raw_row_count=len(ids))


__all__ = ["AndroidContentDeltaVerifier"]
