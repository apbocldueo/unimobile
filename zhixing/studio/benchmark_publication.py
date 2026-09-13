"""Formal Core preparation and managed publication services for Benchmark."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from zhixing.benchmark import BenchmarkSuiteResult
from zhixing.benchmark.identity import canonical_hash
from zhixing.benchmark.reporting import write_experiment_artifacts
from zhixing.benchmark.reporting.safety import safe_export

from .benchmark_errors import (
    StudioBenchmarkConflictError,
    StudioBenchmarkIntegrityError,
    StudioBenchmarkStorageError,
)
from .benchmark_evidence import LocalStudioBenchmarkEvidenceStore
from .benchmark_publication_models import (
    StudioBenchmarkManagedArtifactRecordV1,
    StudioBenchmarkPreparedMemberV1,
    StudioBenchmarkPreparedPublicationV1,
    StudioBenchmarkPublicationDiagnosticV1,
    StudioBenchmarkPublicationRecordV1,
    benchmark_replay_id,
    canonical_publication_fingerprint,
)
from .benchmark_publication_protocols import (
    StudioBenchmarkBundleVerifier,
    StudioBenchmarkManagedArtifactStore,
    StudioBenchmarkPublicationPreparer,
    StudioBenchmarkPublicationRepository,
    StudioBenchmarkReplayPublisher,
)
from .benchmark_experiment_models import (
    StudioBenchmarkEventDraftV1,
    StudioBenchmarkEventSource,
)
from .benchmark_experiment_protocols import (
    StudioBenchmarkExperimentRepository,
)
from .replay_contracts import ReplayArtifactRecord


_PREPARATION_MANIFEST = "publication-preparation.json"
_STUDIO_PUBLICATION_MANIFEST = "studio-publication-manifest.json"
_STUDIO_BUNDLE = "studio-experiment-bundle.zip"
_CONTENT_TYPES = {
    ".json": "application/json",
    ".jsonl": "application/x-ndjson",
    ".png": "image/png",
    ".xml": "application/xml",
    ".zip": "application/zip",
}


def _sha256_file(path: Path) -> tuple[str, int]:
    """Hash one regular file without loading it all into memory.

    Args:
        path: Verified file path.

    Raises:
        OSError: File cannot be read.

    Returns:
        Prefixed digest and byte size.
    """
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return "sha256:" + digest.hexdigest(), size


def _atomic_json(target: Path, value: object) -> None:
    """Atomically write one deterministic private JSON document.

    Args:
        target: Server-owned destination.
        value: JSON-compatible value.

    Raises:
        OSError: File write or replacement fails.
        ValueError: Value contains non-finite JSON.

    Returns:
        None.
    """
    content = (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        + "\n"
    ).encode("utf-8")
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _atomic_copy(source: Path, target: Path) -> None:
    """Atomically copy one already-scoped private regular file.

    Args:
        source: Verified source file.
        target: Private staging destination.

    Raises:
        OSError: Reading, writing, or replacement fails.

    Returns:
        None.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.",
        dir=target.parent,
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as output, source.open(
            "rb"
        ) as input_stream:
            shutil.copyfileobj(input_stream, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def _hide_prompt_content(value: object) -> object:
    """Remove full Prompt/message content from readable runtime JSON.

    Args:
        value: Already safe-exported JSON-compatible value.

    Returns:
        Recursively filtered value retaining only non-Prompt evidence.
    """
    if isinstance(value, dict):
        filtered: dict[str, object] = {}
        for key, item in value.items():
            normalized = str(key).lower().replace("-", "_")
            if normalized in {
                "prompt",
                "prompts",
                "system_prompt",
                "user_prompt",
                "messages",
            }:
                filtered[str(key)] = "<hidden>"
            else:
                filtered[str(key)] = _hide_prompt_content(item)
        return filtered
    if isinstance(value, list):
        return [_hide_prompt_content(item) for item in value]
    return value


def _is_prompt_evidence(path: Path) -> bool:
    """Return whether a runtime member is a dedicated Prompt artifact.

    Args:
        path: Runtime evidence path.

    Returns:
        ``True`` when the filename declares Prompt-only evidence.
    """
    normalized = path.name.lower().replace("_", "-")
    return normalized == "prompt.json" or normalized.startswith("prompt-")


def _prepared_kind(reference: str) -> str:
    """Map one known Core reporting member to a stable public kind.

    Args:
        reference: Experiment-root-relative Core member reference.

    Raises:
        ValueError: Member type is outside the formal reporting contract.

    Returns:
        Stable managed artifact kind.
    """
    name = PurePosixPath(reference).name
    exact = {
        "benchmark-result.json": "task_result",
        "run-report.json": "task_report",
        "trajectory.jsonl": "task_trajectory",
        "experiment-report.json": "experiment_report",
        "experiment-result.json": "experiment_result",
        "experiment-manifest.json": "publication_manifest",
        "trajectory-bundle.zip": "core_trajectory_bundle",
        "definition-snapshot.json": "definition_snapshot",
        _STUDIO_PUBLICATION_MANIFEST: "studio_publication_manifest",
        _STUDIO_BUNDLE: "experiment_bundle",
    }
    if reference.startswith("runtime/"):
        if name.endswith(".png"):
            return "screenshot"
        if name.endswith(".xml"):
            return "ui_xml"
        if name.startswith("action-") and name.endswith(".json"):
            return "action_evidence"
        normalized = name.lower().replace("_", "-")
        if normalized == "model-response.json" or normalized.startswith(
            "model-response-"
        ):
            return "model_response"
        if name == "manifest.json":
            return "runtime_manifest"
        if name == "benchmark-result.json":
            return "runtime_task_result"
    try:
        return exact[name]
    except KeyError as error:
        raise ValueError("unsupported formal Benchmark member") from error


class CoreStudioBenchmarkPublicationPreparer:
    """Prepare complete Core reporting output in private Experiment storage."""

    def __init__(
        self,
        evidence: LocalStudioBenchmarkEvidenceStore,
        *,
        maximum_members: int = 2000,
        maximum_total_bytes: int = 512 * 1024 * 1024,
    ) -> None:
        """Configure the private preparation boundary.

        Args:
            evidence: Permanent server-owned Experiment namespace store.
            maximum_members: Maximum declared formal output members.
            maximum_total_bytes: Maximum aggregate prepared size.

        Raises:
            ValueError: Limits are not positive.

        Returns:
            None.
        """
        if maximum_members < 1 or maximum_total_bytes < 1:
            raise ValueError("publication preparation limits must be positive")
        self.evidence = evidence
        self.maximum_members = maximum_members
        self.maximum_total_bytes = maximum_total_bytes

    def prepare(
        self,
        suite: BenchmarkSuiteResult,
        *,
        planned_task_run_id: str,
        definition_snapshot: dict[str, object],
        prepared_at: int,
    ) -> StudioBenchmarkPreparedPublicationV1:
        """Write and inventory formal output from the complete Core suite.

        Args:
            suite: Complete immutable Core Benchmark result.
            planned_task_run_id: Stable Studio TaskRun mapping.
            definition_snapshot: Immutable accepted Experiment definition.
            prepared_at: Unix epoch milliseconds for this preparation.

        Raises:
            StudioBenchmarkStorageError: Formal output cannot be prepared.
            StudioBenchmarkIntegrityError: Output violates scope or limits.

        Returns:
            Durable private preparation manifest.
        """
        try:
            namespace = self.evidence.preflight(suite.experiment_id)
            staging_root = namespace.root / "publication-staging"
            artifacts = write_experiment_artifacts(
                suite,
                artifact_root=staging_root,
            )
            experiment_root = artifacts.experiment_root.resolve()
            for result in suite.results:
                namespace_reference = result.artifact_namespace
                if not namespace_reference:
                    continue
                pure_namespace = PurePosixPath(namespace_reference)
                if (
                    pure_namespace.is_absolute()
                    or ".." in pure_namespace.parts
                    or not pure_namespace.parts
                ):
                    raise ValueError("runtime artifact namespace is unsafe")
                runtime_root = namespace.runtime_root.resolve()
                runtime_namespace = runtime_root.joinpath(
                    *pure_namespace.parts
                )
                if (
                    runtime_namespace.is_symlink()
                    or not runtime_namespace.is_dir()
                ):
                    raise ValueError("runtime artifact namespace is unavailable")
                resolved_runtime = runtime_namespace.resolve(strict=True)
                if (
                    resolved_runtime != runtime_root
                    and runtime_root not in resolved_runtime.parents
                ):
                    raise ValueError("runtime artifact namespace escapes root")
                for source in sorted(resolved_runtime.rglob("*")):
                    if source.is_symlink():
                        raise ValueError(
                            "runtime evidence cannot contain symlinks"
                        )
                    if not source.is_file():
                        continue
                    if _is_prompt_evidence(source):
                        continue
                    suffix = source.suffix.lower()
                    if suffix not in {".json", ".png", ".xml"}:
                        raise ValueError("runtime evidence type is unsupported")
                    relative = source.relative_to(runtime_root)
                    target = experiment_root / "runtime" / relative
                    if suffix == ".json":
                        value = json.loads(source.read_text(encoding="utf-8"))
                        _atomic_json(
                            target,
                            _hide_prompt_content(safe_export(value)),
                        )
                    else:
                        _atomic_copy(source, target)
            _atomic_json(
                experiment_root / "definition-snapshot.json",
                {
                    "schemaVersion": 1,
                    "kind": "studio_benchmark_definition_snapshot",
                    "experimentId": suite.experiment_id,
                    "definition": definition_snapshot,
                },
            )
            declared_members: list[dict[str, object]] = []
            for path in sorted(experiment_root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("formal output cannot contain symlinks")
                if not path.is_file() or path.name in {
                    _STUDIO_PUBLICATION_MANIFEST,
                    _STUDIO_BUNDLE,
                }:
                    continue
                reference = path.relative_to(experiment_root).as_posix()
                suffix = path.suffix.lower()
                if suffix not in _CONTENT_TYPES:
                    raise ValueError("formal output type is unsupported")
                digest, size = _sha256_file(path)
                declared_members.append(
                    {
                        "reference": reference,
                        "kind": _prepared_kind(reference),
                        "contentType": _CONTENT_TYPES[suffix],
                        "size": size,
                        "sha256": digest,
                        "scope": (
                            {
                                "experimentId": suite.experiment_id,
                                "taskRunId": planned_task_run_id,
                            }
                            if reference.startswith(("runs/", "runtime/"))
                            else {"experimentId": suite.experiment_id}
                        ),
                        "availability": "available",
                        "exclusionReason": "",
                    }
                )
            _atomic_json(
                experiment_root / _STUDIO_PUBLICATION_MANIFEST,
                {
                    "schemaVersion": 1,
                    "kind": "studio_benchmark_publication_manifest",
                    "experimentId": suite.experiment_id,
                    "taskRunId": planned_task_run_id,
                    "members": declared_members,
                    "excludedEvidence": [
                        {
                            "kind": "prompt",
                            "availability": "hidden",
                            "reason": "hidden_by_default_policy",
                        }
                    ],
                },
            )
            bundle_members = [
                path
                for path in sorted(experiment_root.rglob("*"))
                if path.is_file()
                and not path.is_symlink()
                and path.name != _STUDIO_BUNDLE
            ]
            bundle_hashes = {
                path.relative_to(experiment_root).as_posix(): _sha256_file(
                    path
                )[0]
                for path in bundle_members
            }
            bundle_target = experiment_root / _STUDIO_BUNDLE
            temporary_bundle = experiment_root / f".{_STUDIO_BUNDLE}.tmp"
            with zipfile.ZipFile(
                temporary_bundle,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
            ) as archive:
                for path in bundle_members:
                    archive.write(
                        path,
                        arcname=path.relative_to(experiment_root).as_posix(),
                    )
                archive.writestr(
                    "bundle-manifest.json",
                    (
                        json.dumps(
                            {
                                "schema_version": "1.0",
                                "kind": "studio_benchmark_experiment_bundle",
                                "members": dict(sorted(bundle_hashes.items())),
                            },
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                            allow_nan=False,
                        )
                        + "\n"
                    ).encode("utf-8"),
                )
            os.replace(temporary_bundle, bundle_target)
            members: list[StudioBenchmarkPreparedMemberV1] = []
            total_size = 0
            for path in sorted(experiment_root.rglob("*")):
                if path.is_symlink():
                    raise ValueError("formal output cannot contain symlinks")
                if not path.is_file():
                    continue
                reference = path.relative_to(experiment_root).as_posix()
                suffix = path.suffix.lower()
                if suffix not in _CONTENT_TYPES:
                    raise ValueError("formal output type is unsupported")
                digest, size = _sha256_file(path)
                total_size += size
                members.append(
                    StudioBenchmarkPreparedMemberV1(
                        reference=reference,
                        kind=_prepared_kind(reference),
                        content_type=_CONTENT_TYPES[suffix],
                        size=size,
                        sha256=digest,
                        task_run_id=(
                            planned_task_run_id
                            if reference.startswith(("runs/", "runtime/"))
                            else None
                        ),
                    )
                )
            if (
                not members
                or len(members) > self.maximum_members
                or total_size > self.maximum_total_bytes
            ):
                raise ValueError("formal publication output exceeds limits")
            preparation_fingerprint = canonical_hash(
                {
                    "contract": "studio-benchmark-preparation-v1",
                    "experimentId": suite.experiment_id,
                    "taskRunId": planned_task_run_id,
                    "suite": {
                        "benchmarkPlanIdentity": (
                            suite.benchmark_plan_identity
                        ),
                        "experimentProtocolIdentity": (
                            suite.experiment_protocol_identity
                        ),
                    },
                    "members": [
                        item.model_dump(
                            mode="json",
                            by_alias=True,
                            exclude_none=True,
                        )
                        for item in members
                    ],
                }
            )
            prepared = StudioBenchmarkPreparedPublicationV1(
                experiment_id=suite.experiment_id,
                task_run_id=planned_task_run_id,
                preparation_fingerprint=preparation_fingerprint,
                members=tuple(members),
                report_reference=artifacts.report_ref,
                bundle_reference=_STUDIO_BUNDLE,
                prepared_at=prepared_at,
            )
            _atomic_json(
                namespace.root / _PREPARATION_MANIFEST,
                prepared.model_dump(
                    mode="json",
                    by_alias=True,
                    exclude_none=True,
                ),
            )
            return prepared
        except (StudioBenchmarkStorageError, StudioBenchmarkIntegrityError):
            raise
        except (OSError, TypeError, ValueError) as error:
            raise StudioBenchmarkStorageError(
                "benchmark.publication.preparation_failed",
                "Benchmark formal publication preparation failed",
            ) from error

    def load(
        self,
        experiment_id: str,
    ) -> StudioBenchmarkPreparedPublicationV1:
        """Load and verify a previously prepared private manifest.

        Args:
            experiment_id: Owning Experiment identity.

        Raises:
            StudioBenchmarkStorageError: Manifest cannot be read.
            StudioBenchmarkIntegrityError: Member inventory changed.

        Returns:
            Verified preparation manifest.
        """
        try:
            namespace = self.evidence.preflight(experiment_id)
            prepared = StudioBenchmarkPreparedPublicationV1.model_validate(
                json.loads(
                    (namespace.root / _PREPARATION_MANIFEST).read_text(
                        encoding="utf-8"
                    )
                )
            )
            if prepared.experiment_id != experiment_id:
                raise ValueError("preparation Experiment scope mismatch")
            for member in prepared.members:
                path = self.member_path(experiment_id, member.reference)
                digest, size = _sha256_file(path)
                if digest != member.sha256 or size != member.size:
                    raise StudioBenchmarkIntegrityError(
                        "benchmark.publication.preparation_corrupt",
                        "Benchmark prepared evidence failed integrity checks",
                    )
            return prepared
        except StudioBenchmarkIntegrityError:
            raise
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise StudioBenchmarkStorageError(
                "benchmark.publication.preparation_unavailable",
                "Benchmark formal preparation is unavailable",
            ) from error

    def member_path(
        self,
        experiment_id: str,
        reference: str,
    ) -> Path:
        """Resolve one declared member beneath the private staging root.

        Args:
            experiment_id: Owning Experiment identity.
            reference: Preparation-manifest-relative POSIX member.

        Raises:
            StudioBenchmarkIntegrityError: Reference escapes or is not regular.

        Returns:
            Verified regular member path.
        """
        pure = PurePosixPath(reference)
        if pure.is_absolute() or ".." in pure.parts or not pure.parts:
            raise StudioBenchmarkIntegrityError(
                "benchmark.publication.member_unsafe",
                "Benchmark prepared member reference is unsafe",
            )
        namespace = self.evidence.preflight(experiment_id)
        root = (
            namespace.root
            / "publication-staging"
            / experiment_id
        ).resolve()
        candidate = root.joinpath(*pure.parts)
        try:
            if candidate.is_symlink() or not candidate.is_file():
                raise OSError("prepared member is not a regular file")
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise StudioBenchmarkIntegrityError(
                "benchmark.publication.member_missing",
                "Benchmark prepared member is unavailable",
            ) from error
        if resolved != root and root not in resolved.parents:
            raise StudioBenchmarkIntegrityError(
                "benchmark.publication.member_escape",
                "Benchmark prepared member escapes its private scope",
            )
        return resolved


def _publication_event_id(
    experiment_id: str,
    task_run_id: str,
    publication_fingerprint: str,
    kind: str,
) -> str:
    """Derive one stable publication journal event identity.

    Args:
        experiment_id: Owning Experiment identity.
        task_run_id: Owning TaskRun identity.
        publication_fingerprint: Immutable publication identity.
        kind: Stable event kind.

    Returns:
        Stable Benchmark event identity.
    """
    suffix = canonical_hash(
        {
            "contract": "studio-benchmark-publication-event-v1",
            "experimentId": experiment_id,
            "taskRunId": task_run_id,
            "publication": publication_fingerprint,
            "kind": kind,
        }
    ).removeprefix("sha256:")[:32]
    return f"benchmark-event-{suffix}"


class DurableStudioBenchmarkPublisher:
    """Promote prepared formal output and native Replay idempotently."""

    def __init__(
        self,
        *,
        experiments: StudioBenchmarkExperimentRepository,
        publications: StudioBenchmarkPublicationRepository,
        preparer: StudioBenchmarkPublicationPreparer,
        artifacts: StudioBenchmarkManagedArtifactStore,
        bundles: StudioBenchmarkBundleVerifier,
        replay: StudioBenchmarkReplayPublisher,
    ) -> None:
        """Configure coordinated publication dependencies.

        Args:
            experiments: Durable Experiment and journal repository.
            publications: Atomic publication metadata repository.
            preparer: Private complete-suite preparation reader.
            artifacts: Managed immutable content store.
            bundles: Formal bundle verifier.
            replay: Native Benchmark Replay projector.

        Returns:
            None.
        """
        self.experiments = experiments
        self.publications = publications
        self.preparer = preparer
        self.artifacts = artifacts
        self.bundles = bundles
        self.replay = replay

    def _failed_preparation(
        self,
        *,
        experiment_id: str,
        task_run_id: str,
        result_fingerprint: str,
        journal_high_water_mark: int,
        timestamp: int,
        error: Exception,
    ) -> StudioBenchmarkPublicationRecordV1:
        """Commit bounded non-pending facts when preparation is unavailable.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Terminal TaskRun identity.
            result_fingerprint: Immutable TaskResult fingerprint.
            journal_high_water_mark: Source event prefix.
            timestamp: Publication attempt timestamp.
            error: Private preparation failure.

        Returns:
            Atomically committed failure projection.
        """
        preparation_fingerprint = canonical_hash(
            {
                "contract": "studio-benchmark-preparation-failure-v1",
                "experimentId": experiment_id,
                "taskRunId": task_run_id,
                "resultFingerprint": result_fingerprint,
                "code": (
                    getattr(error, "code", "")
                    or "benchmark.publication.preparation_unavailable"
                ),
            }
        )
        publication_fingerprint = canonical_publication_fingerprint(
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            result_fingerprint=result_fingerprint,
            preparation_fingerprint=preparation_fingerprint,
            journal_high_water_mark=journal_high_water_mark,
            artifact_digests=(),
        )
        diagnostic = StudioBenchmarkPublicationDiagnosticV1(
            code=(
                getattr(error, "code", "")
                or "benchmark.publication.preparation_unavailable"
            ),
            message="Benchmark formal preparation is unavailable",
            component="preparation",
            retryable=True,
        )
        publication = StudioBenchmarkPublicationRecordV1(
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            publication_fingerprint=publication_fingerprint,
            preparation_fingerprint=preparation_fingerprint,
            preparation_availability="failed",
            report_availability="failed",
            trajectory_availability="failed",
            bundle_availability="failed",
            replay_availability="failed",
            diagnostics=(diagnostic,),
            journal_high_water_mark=journal_high_water_mark,
            published_at=timestamp,
        )
        event = StudioBenchmarkEventDraftV1(
            event_id=_publication_event_id(
                experiment_id,
                task_run_id,
                publication_fingerprint,
                "publication.failed",
            ),
            timestamp=timestamp,
            source=StudioBenchmarkEventSource.SERVICE,
            kind="publication.failed",
            task_run_id=task_run_id,
            phase="publication",
            payload={
                "publicationFingerprint": publication_fingerprint,
                "diagnosticCode": diagnostic.code,
            },
        )
        return self.publications.commit_publication(
            publication=publication,
            artifacts=(),
            replay=None,
            replay_artifacts=(),
            events=(event,),
        )

    def publish(
        self,
        experiment_id: str,
        task_run_id: str,
        *,
        timestamp: int,
    ) -> StudioBenchmarkPublicationRecordV1:
        """Publish formal evidence and native Replay for one TaskRun.

        Args:
            experiment_id: Owning Experiment identity.
            task_run_id: Terminal TaskRun identity.
            timestamp: Unix epoch milliseconds for this attempt.

        Raises:
            ValueError: Terminal TaskResult identity is unavailable.
            StudioBenchmarkError: Coordinated metadata commit fails.

        Returns:
            Newly committed or idempotently restored publication record.
        """
        existing = self.publications.get_publication(experiment_id)
        if existing is not None:
            if existing.task_run_id != task_run_id:
                raise ValueError("publication TaskRun identity conflicts")
            return existing
        experiment = self.experiments.get_experiment(experiment_id)
        task = self.experiments.get_task_run(experiment_id, task_run_id)
        if task.result is None or task.result_fingerprint is None:
            raise ValueError("publication requires immutable TaskResult facts")
        try:
            prepared = self.preparer.load(experiment_id)
        except Exception as error:
            return self._failed_preparation(
                experiment_id=experiment_id,
                task_run_id=task_run_id,
                result_fingerprint=task.result_fingerprint,
                journal_high_water_mark=experiment.event_high_water_mark,
                timestamp=timestamp,
                error=error,
            )
        if prepared.task_run_id != task_run_id:
            raise ValueError("prepared publication TaskRun identity conflicts")
        trusted_root = self.preparer.member_path(
            experiment_id,
            prepared.bundle_reference,
        ).parent
        managed: list[StudioBenchmarkManagedArtifactRecordV1] = []
        diagnostics: list[StudioBenchmarkPublicationDiagnosticV1] = []
        failed_kinds: set[str] = set()
        total_size = sum(member.size for member in prepared.members)
        if total_size > 512 * 1024 * 1024:
            raise StudioBenchmarkIntegrityError(
                "benchmark.publication.aggregate_too_large",
                "Benchmark publication exceeds the configured aggregate limit",
            )
        for member in prepared.members:
            source = self.preparer.member_path(
                experiment_id,
                member.reference,
            )
            try:
                if (
                    member.reference == prepared.bundle_reference
                    and not self.bundles.verify(source)
                ):
                    raise ValueError("formal bundle verification failed")
                managed.append(
                    self.artifacts.import_file(
                        experiment_id=experiment_id,
                        task_run_id=member.task_run_id,
                        reference=member.reference,
                        kind=member.kind,
                        content_type=member.content_type,
                        source=source,
                        trusted_root=trusted_root,
                        expected_sha256=member.sha256,
                        hidden=member.hidden,
                        causal_identity=member.reference,
                    )
                )
            except Exception:
                failed_kinds.add(member.kind)
                diagnostics.append(
                    StudioBenchmarkPublicationDiagnosticV1(
                        code="benchmark.publication.member_failed",
                        message="A formal Benchmark member could not be published",
                        component=member.kind,
                        retryable=True,
                    )
                )
        report_record = next(
            (
                record
                for record in managed
                if record.descriptor.kind == "experiment_report"
            ),
            None,
        )
        bundle_record = next(
            (
                record
                for record in managed
                if record.descriptor.kind == "experiment_bundle"
            ),
            None,
        )
        trajectory_records = tuple(
            record
            for record in managed
            if record.descriptor.kind == "task_trajectory"
        )
        report_availability = (
            "available"
            if report_record is not None
            else "failed"
            if "experiment_report" in failed_kinds
            else "not_produced"
        )
        trajectory_availability = (
            "available"
            if trajectory_records
            else "failed"
            if "task_trajectory" in failed_kinds
            else "not_produced"
        )
        bundle_availability = (
            "available"
            if bundle_record is not None
            else "failed"
            if "experiment_bundle" in failed_kinds
            else "not_produced"
        )
        publication_fingerprint = canonical_publication_fingerprint(
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            result_fingerprint=task.result_fingerprint,
            preparation_fingerprint=prepared.preparation_fingerprint,
            journal_high_water_mark=experiment.event_high_water_mark,
            artifact_digests=tuple(
                record.descriptor.sha256
                for record in managed
                if record.descriptor.sha256 is not None
            ),
        )
        replay_id = benchmark_replay_id(publication_fingerprint)
        replay_envelope = None
        replay_artifacts: tuple[ReplayArtifactRecord, ...] = ()
        replay_availability = "not_produced"
        try:
            replay_envelope = self.replay.build(
                experiment=experiment,
                task_run=task,
                replay_id=replay_id,
                imported_at=timestamp,
                artifacts=tuple(managed),
            )
            replay_descriptors = {
                item.artifact_id: item
                for item in replay_envelope.artifacts
                if item.availability
                in {"available", "redacted", "truncated"}
            }
            replay_artifacts = tuple(
                ReplayArtifactRecord(
                    descriptor=replay_descriptors[
                        record.descriptor.artifact_id
                    ],
                    storage_ref=record.storage_ref,
                )
                for record in managed
                if record.descriptor.artifact_id in replay_descriptors
            )
            replay_availability = "available"
        except Exception:
            replay_id = None
            replay_envelope = None
            replay_artifacts = ()
            replay_availability = "failed"
            diagnostics.append(
                StudioBenchmarkPublicationDiagnosticV1(
                    code="benchmark.publication.replay_failed",
                    message="Native Benchmark Replay could not be published",
                    component="replay",
                    retryable=True,
                )
            )
        publication = StudioBenchmarkPublicationRecordV1(
            experiment_id=experiment_id,
            task_run_id=task_run_id,
            publication_fingerprint=publication_fingerprint,
            preparation_fingerprint=prepared.preparation_fingerprint,
            preparation_availability="available",
            report_availability=report_availability,
            trajectory_availability=trajectory_availability,
            bundle_availability=bundle_availability,
            replay_availability=replay_availability,
            report_artifact_id=(
                report_record.descriptor.artifact_id
                if report_record is not None
                else None
            ),
            bundle_artifact_id=(
                bundle_record.descriptor.artifact_id
                if bundle_record is not None
                else None
            ),
            replay_id=replay_id,
            artifact_ids=tuple(
                sorted(record.descriptor.artifact_id for record in managed)
            ),
            diagnostics=tuple(diagnostics),
            journal_high_water_mark=experiment.event_high_water_mark,
            published_at=timestamp,
        )
        event_kind = (
            "publication.available"
            if not diagnostics
            else "publication.partial"
        )
        event = StudioBenchmarkEventDraftV1(
            event_id=_publication_event_id(
                experiment_id,
                task_run_id,
                publication_fingerprint,
                event_kind,
            ),
            timestamp=timestamp,
            source=StudioBenchmarkEventSource.SERVICE,
            kind=event_kind,
            task_run_id=task_run_id,
            phase="publication",
            payload={
                "publicationFingerprint": publication_fingerprint,
                "reportAvailability": report_availability,
                "trajectoryAvailability": trajectory_availability,
                "bundleAvailability": bundle_availability,
                "replayAvailability": replay_availability,
            },
        )
        try:
            return self.publications.commit_publication(
                publication=publication,
                artifacts=tuple(managed),
                replay=replay_envelope,
                replay_artifacts=replay_artifacts,
                events=(event,),
            )
        except StudioBenchmarkConflictError as error:
            if (
                replay_envelope is None
                or error.code
                != "benchmark.publication.replay_identity_conflict"
            ):
                raise
            replay_diagnostic = StudioBenchmarkPublicationDiagnosticV1(
                code="benchmark.publication.replay_identity_conflict",
                message=(
                    "Native Benchmark Replay identity conflicts with "
                    "durable Replay facts"
                ),
                component="replay",
                retryable=False,
            )
            without_replay = publication.model_copy(
                update={
                    "replay_availability": "failed",
                    "replay_id": None,
                    "diagnostics": publication.diagnostics
                    + (replay_diagnostic,),
                }
            )
            partial_event = StudioBenchmarkEventDraftV1(
                event_id=_publication_event_id(
                    experiment_id,
                    task_run_id,
                    publication_fingerprint,
                    "publication.partial",
                ),
                timestamp=timestamp,
                source=StudioBenchmarkEventSource.SERVICE,
                kind="publication.partial",
                task_run_id=task_run_id,
                phase="publication",
                payload={
                    "publicationFingerprint": publication_fingerprint,
                    "reportAvailability": report_availability,
                    "trajectoryAvailability": trajectory_availability,
                    "bundleAvailability": bundle_availability,
                    "replayAvailability": "failed",
                    "diagnosticCode": replay_diagnostic.code,
                },
            )
            return self.publications.commit_publication(
                publication=without_replay,
                artifacts=tuple(managed),
                replay=None,
                replay_artifacts=(),
                events=(partial_event,),
            )


__all__ = [
    "CoreStudioBenchmarkPublicationPreparer",
    "DurableStudioBenchmarkPublisher",
]
