"""Database-neutral repository ports for Benchmark Experiment aggregates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from .benchmark_experiment_models import (
    ExperimentDefinitionSnapshotV1,
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventEnvelopeV1,
    StudioBenchmarkEventPageV1,
    StudioBenchmarkExperimentCancellationV1,
    StudioBenchmarkExperimentCreateRequestV1,
    StudioBenchmarkExperimentHistoryFilterV1,
    StudioBenchmarkExperimentRecordV1,
    StudioBenchmarkTaskRunPageV1,
    StudioBenchmarkTaskRunRecordV1,
    StudioBenchmarkTaskResultV1,
    StudioBenchmarkTaskRunLifecycle,
    StudioBenchmarkExperimentLifecycle,
    StudioBenchmarkExperimentRecordPageV1,
    StudioBenchmarkExperimentTerminalReason,
    StudioBenchmarkRecoveryCandidatePageV1,
    StudioBenchmarkRecoveryCandidateV1,
    StudioBenchmarkRecoveryDecision,
    StudioBenchmarkTaskRunTerminalReason,
)


@dataclass(frozen=True)
class StudioBenchmarkExperimentBindingAuthority:
    """Database-neutral private authority pinned to one accepted Experiment."""

    experiment_id: str
    profile_id: str
    binding_fingerprint: str
    environment_candidate: Literal["real_android", "fake_device"]
    created_at: int


@dataclass(frozen=True)
class StudioBenchmarkExperimentAggregate:
    """One coherent Experiment root and its stable planned TaskRuns."""

    experiment: StudioBenchmarkExperimentRecordV1
    task_runs: tuple[StudioBenchmarkTaskRunRecordV1, ...]
    binding_authority: StudioBenchmarkExperimentBindingAuthority | None = None


@dataclass(frozen=True)
class StudioBenchmarkExperimentCreateResult:
    """Atomic create result distinguishing a new aggregate from a retry."""

    aggregate: StudioBenchmarkExperimentAggregate
    created: bool


class StudioBenchmarkExperimentRepository(Protocol):
    """Typed persistence boundary independent from SQLite row details."""

    def find_by_client_request_id(
        self,
        client_request_id: str,
    ) -> StudioBenchmarkExperimentRecordV1 | None:
        """Find a durable request fact before definition revalidation."""
        ...

    def create_accepted_experiment(
        self,
        *,
        experiment: StudioBenchmarkExperimentRecordV1,
        request: StudioBenchmarkExperimentCreateRequestV1,
        snapshot: ExperimentDefinitionSnapshotV1,
        task_runs: tuple[StudioBenchmarkTaskRunRecordV1, ...],
        initial_event: StudioBenchmarkEventDraftV1,
        binding_authority: StudioBenchmarkExperimentBindingAuthority,
    ) -> StudioBenchmarkExperimentCreateResult:
        """Atomically create the complete accepted aggregate."""
        ...

    def get_experiment(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkExperimentRecordV1:
        """Load one durable Experiment record."""
        ...

    def list_experiments(
        self,
        *,
        limit: int,
        cursor: str | None,
        filters: StudioBenchmarkExperimentHistoryFilterV1 | None = None,
    ) -> StudioBenchmarkExperimentRecordPageV1:
        """List matching durable Experiments newest-first with an opaque cursor."""
        ...

    def get_task_run(
        self,
        experiment_id: str,
        task_run_id: str,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Load one TaskRun only through its owning Experiment scope."""
        ...

    def list_task_runs(
        self,
        experiment_id: str,
        *,
        limit: int,
        cursor: str | None,
    ) -> StudioBenchmarkTaskRunPageV1:
        """List stable TaskRuns using an opaque scoped cursor."""
        ...

    def cancel_accepted_experiment(
        self,
        experiment_id: str,
        cancellation: StudioBenchmarkExperimentCancellationV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Atomically cancel one accepted aggregate or return its terminal fact."""
        ...

    def enroll_accepted_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
    ) -> bool:
        """Enroll accepted work for this process without stealing older work."""
        ...

    def next_enrolled_experiment(
        self,
        *,
        process_owner_id: str,
    ) -> str | None:
        """Select the oldest accepted Experiment owned by this process."""
        ...

    def claim_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Claim accepted work and move its sole TaskRun to preparing."""
        ...

    def transition_execution(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        experiment_lifecycle: StudioBenchmarkExperimentLifecycle,
        task_lifecycle: StudioBenchmarkTaskRunLifecycle,
        timestamp: int,
        event: StudioBenchmarkEventDraftV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Atomically advance owner-scoped execution lifecycle and journal."""
        ...

    def append_runtime_event(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        event: StudioBenchmarkEventDraftV1,
    ) -> StudioBenchmarkEventEnvelopeV1:
        """Append one idempotent owner-scoped runtime journal event."""
        ...

    def query_events(
        self,
        experiment_id: str,
        *,
        after: int = 0,
        limit: int = 100,
    ) -> StudioBenchmarkEventPageV1:
        """Read one bounded continuous durable event page."""
        ...

    def request_cancellation(
        self,
        experiment_id: str,
        cancellation: StudioBenchmarkExperimentCancellationV1,
    ) -> StudioBenchmarkExperimentAggregate:
        """Persist accepted or active cancellation before local notification."""
        ...

    def commit_task_result(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        result: StudioBenchmarkTaskResultV1,
        fingerprint: str,
        terminal_reason: StudioBenchmarkTaskRunTerminalReason,
        timestamp: int,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Atomically commit a bounded result and terminal TaskRun fact."""
        ...

    def finish_task_without_result(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        process_owner_id: str,
        terminal_reason: StudioBenchmarkTaskRunTerminalReason,
        timestamp: int,
        error_code: str,
    ) -> StudioBenchmarkTaskRunRecordV1:
        """Close pre-runtime cancelled/failed work without inventing an outcome."""
        ...

    def finalize_experiment(
        self,
        experiment_id: str,
        *,
        process_owner_id: str,
        terminal_reason: StudioBenchmarkExperimentTerminalReason,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Atomically finalize an Experiment with one terminal event."""
        ...

    def list_recovery_candidates(
        self,
        *,
        process_owner_id: str,
        limit: int,
        cursor: str | None = None,
    ) -> StudioBenchmarkRecoveryCandidatePageV1:
        """List stale nonterminal aggregates in deterministic bounded pages.

        Args:
            process_owner_id: Current owner identity excluded from recovery.
            limit: Maximum page size.
            cursor: Optional opaque exclusive continuation cursor.

        Raises:
            StudioBenchmarkError: Query or stored-fact validation fails.

        Returns:
            Bounded typed candidate page.
        """
        ...

    def recover_requeue(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        process_owner_id: str,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Requeue accepted or side-effect-free starting work atomically.

        Args:
            candidate: Previously queried stale aggregate projection.
            process_owner_id: New process ownership identity.
            timestamp: Recovery decision timestamp.

        Raises:
            StudioBenchmarkError: Candidate validation or commit fails.

        Returns:
            Accepted aggregate owned by the new process.
        """
        ...

    def recover_interrupt(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Interrupt uncertain in-flight work without rerunning it.

        Args:
            candidate: Previously queried running or cancelling aggregate.
            timestamp: Recovery decision timestamp.

        Raises:
            StudioBenchmarkError: Candidate validation or commit fails.

        Returns:
            Immutable interrupted aggregate.
        """
        ...

    def claim_finalizing_recovery(
        self,
        candidate: StudioBenchmarkRecoveryCandidateV1,
        *,
        process_owner_id: str,
        decision: StudioBenchmarkRecoveryDecision,
        timestamp: int,
    ) -> StudioBenchmarkExperimentAggregate:
        """Claim finalizing work and persist its no-execution decision.

        Args:
            candidate: Previously queried finalizing aggregate.
            process_owner_id: New process ownership identity.
            decision: Publication-only or finalize-only recovery.
            timestamp: Recovery decision timestamp.

        Raises:
            StudioBenchmarkError: Classification, CAS, or commit fails.

        Returns:
            Finalizing aggregate owned by the new process.
        """
        ...


class StudioBenchmarkRecoveryOwnership(Protocol):
    """Exclusive executable-composition ownership for one durable workspace."""

    def close(self) -> None:
        """Release ownership without deleting durable Experiment facts.

        Returns:
            None.
        """
        ...


__all__ = [
    "StudioBenchmarkExperimentBindingAuthority",
    "StudioBenchmarkExperimentAggregate",
    "StudioBenchmarkExperimentCreateResult",
    "StudioBenchmarkExperimentRepository",
    "StudioBenchmarkRecoveryOwnership",
]
